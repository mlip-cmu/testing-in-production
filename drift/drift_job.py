"""
Drift monitoring job.

Every few seconds: compare the most recent simulated day of conversations
against a reference window (two simulated days) with Evidently, and export
the results as Prometheus gauges on :8001/metrics.

The reference window starts at simulated day 0, or at the day stored in
reference_marker.json (set from the control panel: "Reset drift reference").
"""

import glob
import json
import os
import time

import pandas as pd
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataDriftPreset
from prometheus_client import Gauge, start_http_server

EVENTS_DIR = os.environ.get("EVENTS_DIR", "/data/events")
INTERVAL = float(os.environ.get("DRIFT_INTERVAL_SECONDS", "10"))
METHOD = os.environ.get("DRIFT_METHOD", "psi")  # PSI: >0.1 counts as drift
REFERENCE_DAYS = 2

INPUT_NUM = ["request_chars", "has_allergy_mention"]
INPUT_CAT = ["city", "cuisine", "intent"]
OUTPUT_NUM = ["turns", "n_items", "order_value"]
OUTPUT_CAT = ["outcome"]
COLUMNS = INPUT_NUM + INPUT_CAT + OUTPUT_NUM + OUTPUT_CAT
KIND = {c: "input" for c in INPUT_NUM + INPUT_CAT} | {c: "output" for c in OUTPUT_NUM + OUTPUT_CAT}

g_score = Gauge("drift_column_score", f"Per-column drift score ({METHOD})", ["column", "kind"])
g_detected = Gauge("drift_column_detected", "1 if the column drifted", ["column", "kind"])
g_share = Gauge("drift_share_of_columns", "Share of monitored columns that drifted")
g_ready = Gauge("drift_reference_ready", "1 once the reference window is complete")
g_ref_day = Gauge("drift_reference_start_day", "First simulated day of the reference window")
g_cur_day = Gauge("drift_current_window_end_day", "Simulated day at the end of the current window")
g_rows = Gauge("drift_window_rows", "Rows in each window", ["window"])
g_last = Gauge("drift_last_run_timestamp_seconds", "Unix time of the last successful run")
g_duration = Gauge("drift_last_run_duration_seconds", "Runtime of the last drift computation")

DEFINITION = DataDefinition(numerical_columns=INPUT_NUM + OUTPUT_NUM,
                            categorical_columns=INPUT_CAT + OUTPUT_CAT)


def day_files():
    files = {}
    for path in glob.glob(os.path.join(EVENTS_DIR, "day_*.jsonl")):
        try:
            files[int(os.path.basename(path)[4:9])] = path
        except ValueError:
            pass
    return files


def load_days(files, days):
    frames = []
    for d in days:
        if d in files:
            try:
                frames.append(pd.read_json(files[d], lines=True))
            except ValueError:
                pass  # file is being written; try again next round
    if not frames:
        return pd.DataFrame(columns=["sim_day"] + COLUMNS)
    return pd.concat(frames, ignore_index=True)


def reference_start():
    try:
        with open(os.path.join(EVENTS_DIR, "reference_marker.json")) as f:
            return int(json.load(f)["reference_start_day"])
    except (OSError, ValueError, KeyError):
        return 0


def run_once(cache):
    files = day_files()
    if not files:
        return
    latest_day = max(files)
    ref_start = reference_start()
    g_ref_day.set(ref_start)
    if latest_day < ref_start + REFERENCE_DAYS:
        g_ready.set(0)
        return
    ref_days = range(ref_start, ref_start + REFERENCE_DAYS)
    # the key includes file mtimes so a simulator restart invalidates the cache
    key = (ref_start, tuple(os.path.getmtime(files[d]) for d in ref_days if d in files))
    if cache.get("key") != key:
        ref = load_days(files, ref_days)
        cache.update(key=key, ref=ref[COLUMNS])
    reference = cache["ref"]

    recent = load_days(files, [latest_day - 1, latest_day])
    if recent.empty:
        return
    end = recent["sim_day"].max()
    current = recent[recent["sim_day"] > end - 1.0][COLUMNS]
    g_ready.set(1)
    g_cur_day.set(end)
    g_rows.labels("reference").set(len(reference))
    g_rows.labels("current").set(len(current))
    if len(current) < 200:
        return

    started = time.time()
    result = Report([DataDriftPreset(method=METHOD)]).run(
        Dataset.from_pandas(current, data_definition=DEFINITION),
        Dataset.from_pandas(reference, data_definition=DEFINITION),
    ).dict()

    drifted = 0
    for m in result["metrics"]:
        cfg = m["config"]
        col = cfg.get("column")
        if col is None:
            continue
        score = float(m["value"])
        threshold = float(cfg.get("threshold", 0.1))
        # distance methods (psi, wasserstein, jensenshannon): larger = more drift
        # p-value methods (ks, chisquare, z): smaller = more drift
        is_pvalue = "p_value" in str(cfg.get("method", "")) or METHOD in ("ks", "chisquare", "z")
        detected = score < threshold if is_pvalue else score >= threshold
        drifted += detected
        g_score.labels(col, KIND[col]).set(score)
        g_detected.labels(col, KIND[col]).set(int(detected))
    g_share.set(drifted / len(COLUMNS))
    g_last.set(time.time())
    g_duration.set(time.time() - started)


def main():
    start_http_server(int(os.environ.get("PORT", "8001")))
    print(f"drift job: watching {EVENTS_DIR}, method={METHOD}, every {INTERVAL}s", flush=True)
    cache = {}
    while True:
        try:
            run_once(cache)
        except Exception as exc:  # keep the job alive during the lecture
            print(f"drift job error: {exc!r}", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
