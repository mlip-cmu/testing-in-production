"""Drive one lecture scenario against the running stack.

Every demo.sh in this repo is a short script of calls to this tool: flip a switch on the
control panel, wait a few simulated days, read what Prometheus recorded, flip it back. The
transcripts next to each demo.sh are its output.

    uv run ../tools/scenario.py state
    uv run ../tools/scenario.py set menu_sync_paused=true
    uv run ../tools/scenario.py wait --days 4
    uv run ../tools/scenario.py query "agent:completion_rate:1m" --as "completion rate"
    uv run ../tools/scenario.py alerts
    uv run ../tools/scenario.py reset
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SIM = "http://localhost:8000"
PROM = "http://localhost:9090"
BOOLS = ("menu_sync_paused", "llm_upgraded", "new_city_launched", "injection_campaign",
         "injection_guardrail", "menu_api_outage", "surprise_exploration", "flywheel",
         "shadow_new_llm")
NUMBERS = ("upsell_experiment_pct", "canary_v3_pct")


def _retry(call, attempts=4, timeout=20):
    """The simulator and Prometheus both stall occasionally under load. A scenario that
    runs for twenty simulated minutes should survive that, so retry before giving up."""
    for attempt in range(attempts):
        try:
            return call(timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt == attempts - 1:
                raise SystemExit(f"  {type(exc).__name__} after {attempts} attempts: {url_of(exc)}")
            time.sleep(2 * (attempt + 1))


def url_of(exc):
    return getattr(exc, "filename", "") or str(exc)


def _get(url):
    def call(timeout):
        with urllib.request.urlopen(url, timeout=timeout) as f:
            return json.load(f)
    return _retry(call)


def _post(url, body):
    def call(timeout):
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as f:
            return json.load(f)
    return _retry(call)


def sim_state():
    return _get(f"{SIM}/api/state")


def sim_day():
    return float(sim_state().get("sim_day", 0))


def day_seconds():
    return float(sim_state().get("day_seconds", 30))


def promql(expr):
    """Return [(labels dict, float value)] for an instant query."""
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    try:
        res = _get(url)["data"]["result"]
    except (urllib.error.URLError, KeyError, TimeoutError, SystemExit):
        return []
    out = []
    for r in res:
        try:
            out.append((r["metric"], float(r["value"][1])))
        except (ValueError, KeyError):
            pass
    return out


def fmt(value, unit):
    if unit == "pct":
        return f"{value:7.2%}"
    if unit == "usd":
        return f"${value:7.4f}"
    if unit == "s":
        return f"{value:6.2f}s"
    return f"{value:9.3f}"


def cmd_state(args):
    s = sim_state()
    sw = s.get("switches", s)
    on = {k: v for k, v in sw.items() if v not in (False, 0, None)}
    print(f"simulated day {float(s.get('sim_day', 0)):6.1f}   "
          f"{day_seconds():g} s per simulated day")
    print(f"switches on:   {on if on else 'none'}")


def cmd_set(args):
    body = {}
    for pair in args.assignments:
        key, _, raw = pair.partition("=")
        if key in BOOLS:
            body[key] = raw.lower() in ("1", "true", "on", "yes")
        elif key in NUMBERS:
            body[key] = int(raw)
        else:
            sys.exit(f"unknown switch: {key}")
    _post(f"{SIM}/api/switches", body)
    print(f"day {sim_day():6.1f}   set {body}")


def cmd_reset(args):
    body = {k: False for k in BOOLS}
    body["surprise_exploration"] = True          # on by default: exploration is healthy
    body.update({k: 0 for k in NUMBERS})
    _post(f"{SIM}/api/switches", body)
    print(f"day {sim_day():6.1f}   switches back to defaults")
    # Gradual effects unwind over simulated days rather than instantly: the new city's traffic
    # share decays at 0.3/day, menu staleness at 1.0/day. A [1m] rate covers two simulated
    # days. So settle first, and only then take the drift reference, or the reference window
    # captures the previous scenario on its way down and everything after it reads as drift.
    if args.settle > 0:
        target = sim_day() + args.settle
        while sim_day() < target:
            time.sleep(min(5.0, day_seconds()))
        print(f"day {sim_day():6.1f}   settled {args.settle:g} simulated days, windows clear")
    _post(f"{SIM}/api/control", {"reset_reference": True})
    print(f"day {sim_day():6.1f}   drift reference taken on settled traffic")


def cmd_wait(args):
    target = sim_day() + args.days
    while sim_day() < target:
        time.sleep(min(5.0, day_seconds()))
    print(f"day {sim_day():6.1f}   waited {args.days} simulated days")


def cmd_query(args):
    label = args.as_ or args.expr
    rows = [(m, v) for m, v in promql(args.expr) if v == v]   # drop NaN: arms with no traffic
    if not rows:
        print(f"           {label:<42} no data")
        return
    if len(rows) == 1 and not rows[0][0].get(args.by or ""):
        print(f"day {sim_day():6.1f}   {label:<42} {fmt(rows[0][1], args.unit)}")
        return
    print(f"day {sim_day():6.1f}   {label}")
    for metric, value in sorted(rows, key=lambda r: -r[1]):
        name = metric.get(args.by, "") if args.by else \
            ", ".join(f"{k}={v}" for k, v in metric.items() if k != "__name__")
        print(f"           {name:<42} {fmt(value, args.unit)}")


def cmd_reference(args):
    """Accept the current traffic as the new baseline, leaving every switch alone."""
    _post(f"{SIM}/api/control", {"reset_reference": True})
    print(f"day {sim_day():6.1f}   drift reference reset, switches untouched")


def cmd_alerts(args):
    rows = promql('ALERTS{alertstate="firing"}')
    names = sorted({m.get("alertname", "?") for m, _ in rows})
    print(f"day {sim_day():6.1f}   firing alerts: {', '.join(names) if names else 'none'}")


def cmd_note(args):
    print(f"\n--- {' '.join(args.text)}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("state").set_defaults(func=cmd_state)
    r = sub.add_parser("reset")
    r.add_argument("--settle", type=float, default=2.0,
                   help="simulated days to wait so rate() windows clear (default 2)")
    r.set_defaults(func=cmd_reset)
    sub.add_parser("alerts").set_defaults(func=cmd_alerts)
    sub.add_parser("reference").set_defaults(func=cmd_reference)

    s = sub.add_parser("set"); s.add_argument("assignments", nargs="+"); s.set_defaults(func=cmd_set)
    w = sub.add_parser("wait"); w.add_argument("--days", type=float, required=True); w.set_defaults(func=cmd_wait)
    n = sub.add_parser("note"); n.add_argument("text", nargs="+"); n.set_defaults(func=cmd_note)

    q = sub.add_parser("query")
    q.add_argument("expr")
    q.add_argument("--as", dest="as_", default="")
    q.add_argument("--by", default="")
    q.add_argument("--unit", default="pct", choices=["pct", "usd", "s", "raw"])
    q.set_defaults(func=cmd_query)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
