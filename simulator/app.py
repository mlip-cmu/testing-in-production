"""
Food ordering agent simulator service.

  GET  /                 instructor control panel
  GET  /metrics          Prometheus metrics
  GET  /api/state        switches, simulated clock, hidden truth, change log
  POST /api/switches     {"menu_sync_paused": true, "upsell_experiment_pct": 50, ...}
  POST /api/control      {"paused": true} | {"day_seconds": 60} | {"reset_reference": true}

Conversation records are appended as JSON lines to $EVENTS_DIR/day_NNNNN.jsonl,
refunds to $EVENTS_DIR/refunds_NNNNN.jsonl (one file per simulated day).
"""

import json
import os
import threading
import time
from dataclasses import fields

from flask import Flask, Response, jsonify, request, send_from_directory
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

import metrics
from engine import Engine, Switches

EVENTS_DIR = os.environ.get("EVENTS_DIR", "/data/events")
DAY_SECONDS = float(os.environ.get("SIM_DAY_SECONDS", "30"))
SEED = int(os.environ.get("SIM_SEED", "7"))
KEEP_DAYS = int(os.environ.get("KEEP_DAYS", "60"))
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
TICK = 1.0  # real seconds per simulation step

os.makedirs(EVENTS_DIR, exist_ok=True)
if os.environ.get("CLEAR_EVENTS_ON_START", "true").lower() == "true":
    # a restart begins again at day 0, so old logs would mix two runs
    for name in os.listdir(EVENTS_DIR):
        if name.endswith((".jsonl", ".json")):
            os.remove(os.path.join(EVENTS_DIR, name))
engine = Engine(seed=SEED)
lock = threading.Lock()
state = {"paused": False, "day_seconds": DAY_SECONDS, "changes": []}
SWITCH_TYPES = {f.name: f.type for f in fields(Switches)}

app = Flask(__name__, static_folder="static")


def _log_change(what: str, value):
    state["changes"].insert(0, {"sim_day": round(engine.sim_day, 2), "what": what, "value": value,
                                "wall_time": time.strftime("%H:%M:%S")})
    del state["changes"][50:]
    with open(os.path.join(EVENTS_DIR, "switch_log.jsonl"), "a") as f:
        f.write(json.dumps(state["changes"][0]) + "\n")


def _append(prefix: str, day: int, rows: list):
    if not rows:
        return
    with open(os.path.join(EVENTS_DIR, f"{prefix}_{day:05d}.jsonl"), "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _cleanup(current_day: int):
    for name in os.listdir(EVENTS_DIR):
        if name.startswith(("day_", "refunds_")) and name.endswith(".jsonl"):
            try:
                day = int(name.split("_")[1].split(".")[0])
            except ValueError:
                continue
            if day < current_day - KEEP_DAYS:
                os.remove(os.path.join(EVENTS_DIR, name))


def sim_loop():
    last_cleanup = -1
    while True:
        started = time.time()
        with lock:
            if not state["paused"]:
                day = int(engine.sim_day)
                convs, refunds = engine.step(24.0 * TICK / state["day_seconds"])
                for r in convs:
                    metrics.record_conversation(r)
                for r in refunds:
                    metrics.record_refund(r)
                _append("day", day, convs)
                _append("refunds", day, refunds)
                if day != last_cleanup:
                    _cleanup(day)
                    last_cleanup = day
            metrics.record_state(engine, state["paused"])
        time.sleep(max(0.0, TICK - (time.time() - started)))


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/metrics")
def prometheus_metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@app.get("/api/state")
def get_state():
    with lock:
        return jsonify({
            "switches": engine.switches_dict(),
            "sim_day": engine.sim_day,
            "paused": state["paused"],
            "day_seconds": state["day_seconds"],
            "truth": engine.truth_snapshot(),
            "changes": state["changes"],
            "links": {"grafana": GRAFANA_URL, "prometheus": PROMETHEUS_URL},
        })


@app.post("/api/switches")
def set_switches():
    body = request.get_json(force=True) or {}
    with lock:
        for key, value in body.items():
            if key not in SWITCH_TYPES:
                return jsonify({"error": f"Unknown switch '{key}'"}), 400
            if SWITCH_TYPES[key] in (bool, "bool"):
                value = bool(value)
            else:
                value = max(0, min(100, int(value)))
            if getattr(engine.sw, key) != value:
                setattr(engine.sw, key, value)
                _log_change(key, value)
        return jsonify(engine.switches_dict())


@app.post("/api/control")
def control():
    body = request.get_json(force=True) or {}
    with lock:
        if "paused" in body:
            state["paused"] = bool(body["paused"])
            _log_change("paused", state["paused"])
        if "day_seconds" in body:
            state["day_seconds"] = max(5.0, min(600.0, float(body["day_seconds"])))
            _log_change("day_seconds", state["day_seconds"])
        if body.get("reset_reference"):
            # the drift job uses the day after this marker as its new reference
            with open(os.path.join(EVENTS_DIR, "reference_marker.json"), "w") as f:
                json.dump({"reference_start_day": int(engine.sim_day)}, f)
            _log_change("drift reference reset", int(engine.sim_day))
        return jsonify({"paused": state["paused"], "day_seconds": state["day_seconds"]})


threading.Thread(target=sim_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), threaded=True)
