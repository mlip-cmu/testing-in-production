"""
Generate a 30-day event log offline (no Docker, no waiting) by replaying a
scripted scenario. Used for the notebook and as a backup if the live demo fails.

    python offline.py --out ../data/sample
"""

import argparse
import csv
import gzip
import os

from engine import Engine

# (sim_day, switch, value, note)
SCENARIO = [
    (5,  "upsell_experiment_pct", 50,    "A/B test: upsell prompt v2 for 50% of users"),
    (8,  "menu_sync_paused",      True,  "Menu index sync job silently stops (stale model)"),
    (10, "new_city_launched",     True,  "Launch in Honolulu (data drift)"),
    (13, "upsell_experiment_pct", 0,     "A/B test ends"),
    (13, "surprise_exploration",  False, "Exploration disabled in Surprise me (feedback loop)"),
    (14, "menu_sync_paused",      False, "Menu sync fixed"),
    (14, "shadow_new_llm",        True,  "Shadow-test llm-2026-09"),
    (16, "shadow_new_llm",        False, "Shadow test ends"),
    (16, "llm_upgraded",          True,  "Provider silently upgrades the LLM (jump)"),
    (18, "llm_upgraded",          False, "Pin old LLM version (rollback)"),
    (19, "canary_v3_pct",         10,    "Canary: prompt v3 to 10%"),
    (20, "canary_v3_pct",         0,     "Canary rolled back"),
    (21, "injection_campaign",    True,  "Prompt-injection campaign starts (adversary)"),
    (22, "flywheel",              True,  "Mine judge-flagged failures into eval set (flywheel)"),
    (24, "injection_guardrail",   True,  "Injection guardrail deployed"),
    (26, "menu_api_outage",       True,  "Chaos experiment: menu API down"),
    (26.5, "menu_api_outage",     False, "Menu API restored"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../data/sample")
    ap.add_argument("--days", type=float, default=30)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    eng = Engine(seed=args.seed)
    step_h = 0.5
    pending = sorted(SCENARIO)
    conv_rows, refund_rows, daily_truth, timeline = [], [], [], []
    last_day = -1
    while eng.sim_day < args.days:
        while pending and pending[0][0] <= eng.sim_day + 1e-9:
            day, key, val, note = pending.pop(0)
            setattr(eng.sw, key, val)
            timeline.append({"sim_day": day, "switch": key, "value": val, "note": note})
        convs, refunds = eng.step(step_h)
        conv_rows += convs
        refund_rows += refunds
        if int(eng.sim_day) != last_day:
            last_day = int(eng.sim_day)
            t = eng.truth_snapshot()
            flat = {"sim_day": last_day, **{k: v for k, v in t.items() if not isinstance(v, dict)}}
            flat.update({f"surprise_{k}": v for k, v in t["surprise"].items()})
            flat.update({f"failrate_{k}": v for k, v in t["failure_rates"].items()})
            daily_truth.append(flat)

    def write(name, rows):
        with gzip.open(os.path.join(args.out, name), "wt", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    write("conversations.csv.gz", conv_rows)
    write("refunds.csv.gz", refund_rows)
    write("daily_state.csv.gz", daily_truth)
    write("timeline.csv.gz", timeline)
    print(f"wrote {len(conv_rows)} conversations, {len(refund_rows)} refunds to {args.out}")


if __name__ == "__main__":
    main()
