"""Measure the LLM judge against hand-labeled traces, then correct the dashboard.

The dashboard's judge fail rate is the output of a model nobody has checked. This script
treats the judge as a classifier, measures its true positive and true negative rates against
16 human labels, and inverts the relationship to recover the true failure rate.
"""

import json
import pathlib
import urllib.parse
import urllib.request

TRACES = pathlib.Path(__file__).parent / ".." / "notebook" / "traces_sample.json"
PROM = "http://localhost:9090"


def wilson(hits, n, z=1.96):
    """Wilson score interval: honest about small samples, unlike the normal approximation."""
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def observed_fail_rate():
    """Today's judge fail rate from Prometheus, if the stack is running."""
    q = urllib.parse.urlencode({"query": "agent:judge_fail_rate:1m"})
    try:
        with urllib.request.urlopen(f"{PROM}/api/v1/query?{q}", timeout=5) as f:
            res = json.load(f)["data"]["result"]
        return float(res[0]["value"][1]) if res else None
    except Exception:
        return None


def main():
    traces = json.loads(TRACES.resolve().read_text())
    tp = fp = tn = fn = 0
    disagreements = []
    for t in traces:
        human_fail = t["human_label"] == "fail"
        judge_fail = t["example_judge_verdict"] == "fail"
        if human_fail and judge_fail:
            tp += 1
        elif human_fail and not judge_fail:
            fn += 1
            disagreements.append((t["trace_id"], "missed a real failure", t["human_failure_mode"]))
        elif not human_fail and judge_fail:
            fp += 1
            disagreements.append((t["trace_id"], "false alarm on a good conversation", ""))
        else:
            tn += 1

    n = len(traces)
    print(f"{n} hand-labeled traces, judge verdicts from traces_sample.json\n")
    print(f"{'':22}{'judge: fail':>13}{'judge: pass':>13}")
    print(f"  {'human: fail':20}{tp:>13}{fn:>13}")
    print(f"  {'human: pass':20}{fp:>13}{tn:>13}")
    print(f"\n  agreement              {(tp + tn)}/{n} = {(tp + tn) / n:.0%}")

    for tid, what, mode in disagreements:
        print(f"    {tid}: {what}{f' ({mode})' if mode else ''}")

    s = tp / (tp + fn) if tp + fn else float("nan")
    t_ = tn / (tn + fp) if tn + fp else float("nan")
    s_lo, s_hi = wilson(tp, tp + fn)
    t_lo, t_hi = wilson(tn, tn + fp)
    print(f"\n  sensitivity (catches a real failure)   {s:.0%}   95% CI [{s_lo:.0%}, {s_hi:.0%}]  n={tp + fn}")
    print(f"  specificity (lets a good one pass)     {t_:.0%}   95% CI [{t_lo:.0%}, {t_hi:.0%}]  n={tn + fp}")
    print("\n  Those intervals are the finding. Sixteen traces cannot tell 85% from 60%.")

    o = observed_fail_rate()
    if o is None:
        print("\n  (stack not running, so no dashboard number to correct)")
        o = 0.15
        print(f"  Using {o:.0%} as an illustrative observed rate.")
    else:
        print(f"\n  dashboard now: judge fails {o:.1%} of sampled conversations")

    denom = s - (1 - t_)
    if denom > 0:
        p = max(0.0, (o - (1 - t_)) / denom)
        print(f"  corrected for judge error: about {p:.1%} of conversations truly fail")
        print(f"  the gap, {o - p:+.1%}, is the judge's own false alarms")


if __name__ == "__main__":
    main()
