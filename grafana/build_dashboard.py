"""Builds grafana/dashboards/food_agent.json. Re-run after editing:

    python grafana/build_dashboard.py
"""

import json
import os

DS = {"type": "prometheus", "uid": "prometheus"}
panels = []
_id = 0
_y = 0


def nid():
    global _id
    _id += 1
    return _id


def target(expr, legend="", ref="A", instant=False, fmt="time_series"):
    t = {"datasource": DS, "expr": expr, "legendFormat": legend, "refId": ref, "range": not instant,
         "instant": instant, "format": fmt}
    return t


def timeseries(title, targets, x, y, w=8, h=8, unit="percentunit", desc="", stack=False,
               thresholds=None, minv=None, maxv=None, draw="line", right_axis=()):
    custom = {"drawStyle": draw, "lineWidth": 2, "fillOpacity": 25 if stack else 8,
              "showPoints": "never", "spanNulls": True,
              "stacking": {"mode": "normal" if stack else "none", "group": "A"}}
    if thresholds:
        custom["thresholdsStyle"] = {"mode": "line+area" if len(thresholds) > 1 else "line"}
    defaults = {"unit": unit, "custom": custom}
    if minv is not None:
        defaults["min"] = minv
    if maxv is not None:
        defaults["max"] = maxv
    if thresholds:
        steps = [{"color": "transparent", "value": None}]
        steps += [{"color": c, "value": v} for v, c in thresholds]
        defaults["thresholds"] = {"mode": "absolute", "steps": steps}
    return {"id": nid(), "type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [target(e, l, chr(65 + i)) for i, (e, l) in enumerate(targets)],
            "fieldConfig": {"defaults": defaults, "overrides": [
                {"matcher": {"id": "byName", "options": name},
                 "properties": [{"id": "custom.axisPlacement", "value": "right"},
                                {"id": "custom.fillOpacity", "value": 0},
                                {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [8, 6]}}]}
                for name in right_axis]},
            "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title, expr, x, y, w=4, h=4, unit="percentunit", steps=None, desc="", decimals=1):
    steps = steps or [("green", None)]
    return {"id": nid(), "type": "stat", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [target(expr, title)],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals,
                                         "thresholds": {"mode": "absolute",
                                                        "steps": [{"color": c, "value": v} for c, v in steps]}},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "background", "graphMode": "area", "textMode": "value",
                        "justifyMode": "center", "orientation": "auto"}}


def text(content, x, y, w, h, title=""):
    return {"id": nid(), "type": "text", "title": title, "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "options": {"mode": "markdown", "content": content}}


def row(title, y, collapsed=False, children=None):
    return {"id": nid(), "type": "row", "title": title, "collapsed": collapsed,
            "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": children or []}


def state_timeline(title, targets, x, y, w, h, desc="", steps=None, show_value="never"):
    return {"id": nid(), "type": "state-timeline", "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "targets": [target(e, l, chr(65 + i)) for i, (e, l) in enumerate(targets)],
            "fieldConfig": {"defaults": {"thresholds": {"mode": "absolute", "steps": steps or [
                                             {"color": "green", "value": None}, {"color": "red", "value": 1}]},
                                         "color": {"mode": "thresholds"},
                                         "custom": {"fillOpacity": 80, "lineWidth": 0}},
                            "overrides": []},
            "options": {"showValue": show_value, "mergeValues": True, "rowHeight": 0.85,
                        "legend": {"showLegend": False}, "alignValue": "left"}}


# ---------------------------------------------------------------- header
y = 0
panels.append(text(
    "### Food ordering agent in production\n"
    "One simulated day = **30 s** by default. Rates use 1-minute windows (about **2 simulated days**). "
    "Scenario switches live on the [control panel](http://localhost:8000). "
    "Decide A/B tests in the notebook, not here.", 0, y, 24, 3))
y += 3
panels += [
    stat("Simulated day", "max(sim_day)", 0, y, unit="none", decimals=0, steps=[("blue", None)]),
    stat("Completion rate", "agent:completion_rate:1m", 4, y,
         steps=[("red", None), ("orange", 0.7), ("green", 0.75)],
         desc="Share of conversations that ended with the user's goal done (order placed, complaint resolved)."),
    stat("Handoff to human", "agent:handoff_rate:1m", 8, y,
         steps=[("green", None), ("orange", 0.06), ("red", 0.09)]),
    stat("Judge fail rate", "agent:judge_fail_rate:1m", 12, y,
         steps=[("green", None), ("orange", 0.16), ("red", 0.2)],
         desc="LLM-as-judge verdicts on a random 10% sample. The judge itself is imperfect."),
    stat("Refund rate (delayed)", "agent:refund_rate:1m", 16, y,
         steps=[("green", None), ("orange", 0.045), ("red", 0.06)],
         desc="Refunds arrive 1-3 simulated days after the order: wait-and-see telemetry."),
    stat("Cost per order", "agent:cost_per_order:1m", 20, y, unit="currencyUSD", decimals=3,
         steps=[("green", None), ("orange", 0.052), ("red", 0.058)]),
]
y += 4
panels.append({
    "id": nid(), "type": "table", "title": "Firing alerts", "datasource": DS,
    "gridPos": {"x": 0, "y": y, "w": 24, "h": 6},
    "targets": [target('ALERTS{alertstate="firing"}', "", instant=True, fmt="table")],
    "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}},
    "fieldConfig": {"defaults": {"custom": {"align": "left"}}, "overrides": []},
    "transformations": [{"id": "organize", "options": {
        "excludeByName": {"Time": True, "Value": True, "__name__": True, "alertstate": True,
                          "instance": True, "job": True},
        "indexByName": {"alertname": 0, "severity": 1, "topic": 2},
        "renameByName": {"alertname": "Alert", "severity": "Severity", "topic": "Topic",
                         "prompt_version": "Prompt", "check": "Check"}}}],
})
y += 6

# ---------------------------------------------------------------- model quality
panels.append(row("Model quality from telemetry", y)); y += 1
panels += [
    timeseries("Completion and handoff", [
        ("agent:completion_rate:1m", "completion (2 days)"),
        ("agent:completion_rate:5m", "completion (10 days)"),
        ("agent:handoff_rate:1m", "handoff to human")], 0, y, minv=0, maxv=1,
        desc="Implicit feedback: did the conversation reach its goal?"),
    timeseries("User corrections per conversation", [
        ("agent:corrections_per_conversation:1m", "corrections")], 8, y, unit="none", minv=0,
        desc="Implicit feedback: users fixing items, sizes, or restaurants."),
    timeseries("Judge failures by mode", [
        ('sum by (failure_mode) (rate(agent_judge_evaluations_total{verdict="fail"}[1m])) '
         '/ ignoring(failure_mode) group_left sum(rate(agent_judge_evaluations_total[1m]))', "{{failure_mode}}")],
        16, y, stack=True, minv=0,
        desc="Share of judged conversations flagged, by the failure mode the judge named."),
]
y += 8
panels += [
    timeseries("Refund rate (delayed label)", [("agent:refund_rate:1m", "refunds / orders")], 0, y, minv=0,
               thresholds=[(0.06, "red")], desc="Refunds show up 1-3 simulated days after the problem."),
    timeseries("Orders and order value", [
        ("sum(rate(agent_orders_total[1m]))", "orders per second"),
        ("sum(rate(agent_order_value_dollars_total[1m])) / sum(rate(agent_orders_total[1m]))", "avg order value ($)")],
        8, y, unit="none", minv=0),
    timeseries("Conversations by intent", [
        ("sum by (intent) (rate(agent_conversations_total[1m]))", "{{intent}}")], 16, y, unit="reqps",
        stack=True),
]
y += 8

# ---------------------------------------------------------------- invariants
panels.append(row("Invariants: checks that need no ground truth", y)); y += 1
panels += [
    timeseries("Invariant violations per order", [
        ("agent:violations_per_order:1m", "{{check}}")], 0, y, minv=0, thresholds=[(0.02, "red")],
        desc="Items must exist on the menu, prices must match, discounts must follow policy, allergies must be respected."),
    timeseries("Discounts granted", [
        ("sum by (llm_version) (rate(agent_discount_dollars_total[1m]))", "{{llm_version}}")],
        8, y, unit="currencyUSD", stack=True, minv=0, desc="Dollars per second given away as discounts."),
    timeseries("Requests flagged as possible prompt injection", [
        ("agent:injection_flag_rate:1m", "flagged share")], 16, y, minv=0, thresholds=[(0.008, "orange")],
        desc="A heuristic detector. Attackers adapt, so its recall decays."),
]
y += 8

# ---------------------------------------------------------------- drift
panels.append(row("Data drift (Evidently job, PSI against a 2-day reference)", y)); y += 1
panels += [
    timeseries("Drift score by column", [
        ('drift_column_score{kind="input"}', "input: {{column}}"),
        ('drift_column_score{kind="output"}', "output: {{column}}")], 0, y, w=10, unit="none", minv=0,
        thresholds=[(0.1, "orange")], desc="Population stability index; above 0.1 counts as drift."),
    state_timeline("Drifted columns (orange = drift)", [("drift_column_detected", "{{column}}")], 10, y, 7, 8,
                   steps=[{"color": "green", "value": None}, {"color": "orange", "value": 0.5}]),
    timeseries("Requests by city", [
        ("sum by (city) (rate(agent_requests_by_city_total[1m])) / ignoring(city) group_left "
         "sum(rate(agent_requests_by_city_total[1m]))", "{{city}}")], 17, y, w=7, stack=True, minv=0, maxv=1),
]
y += 8

# ---------------------------------------------------------------- feedback loop
panels.append(row("Surprise me: feedback loop", y)); y += 1
panels += [
    timeseries("Catalog coverage (nightly)", [
        ("surprise_catalog_coverage", "restaurants recommended at least once"),
        ("surprise_top5_share", "share going to top 5"),
        ("surprise_new_restaurant_share", "share for restaurants opened this week")], 0, y, w=12, minv=0, maxv=1,
        desc="Computed each simulated night from the recommender's logs."),
    timeseries("Repeat recommendations and acceptance", [
        ("surprise:repeat_rate:1m", "repeat recommendation"),
        ("surprise:acceptance_rate:1m", "accepted")], 12, y, w=12, minv=0, maxv=1),
]
y += 8

# ---------------------------------------------------------------- releases
panels.append(row("Releases and experiments", y)); y += 1
panels += [
    timeseries("Completion by prompt version", [
        ("agent:completion_rate_by_prompt:1m", "{{prompt_version}}")], 0, y, minv=0, maxv=1),
    timeseries("Traffic by prompt version", [
        ("sum by (prompt_version) (rate(agent_conversations_total[1m])) / ignoring(prompt_version) group_left "
         "sum(rate(agent_conversations_total[1m]))", "{{prompt_version}}")], 8, y, stack=True, minv=0, maxv=1),
    timeseries("Order value by prompt version", [
        ("sum by (prompt_version) (rate(agent_order_value_dollars_total[1m])) / "
         "sum by (prompt_version) (rate(agent_orders_total[1m]))", "{{prompt_version}}")], 16, y,
        unit="currencyUSD", desc="Average value of placed orders. Means only; no confidence intervals here."),
]
y += 8
panels += [
    timeseries("Completion by LLM version", [
        ("agent:completion_rate_by_llm:1m", "{{llm_version}}")], 0, y, minv=0, maxv=1),
    timeseries("Refund rate by prompt version (delayed)", [
        ("sum by (prompt_version) (rate(agent_refunds_total[1m])) / "
         "sum by (prompt_version) (rate(agent_orders_total[1m]))", "{{prompt_version}}")], 8, y, minv=0),
    timeseries("Shadow release: llm-2026-09 vs production", [
        # 5m rates inline rather than as recording rules, so they render over history
        # Prometheus already has and need no config reload mid-demo. The alert keeps the 1m rule.
        ('sum(rate(shadow_invariant_violations_total{check="discount_policy"}[5m])) / '
         'sum(rate(shadow_comparisons_total[5m]))', "shadow: discount violations"),
        ('sum(rate(agent_invariant_violations_total{check="discount_policy"}[5m])) / '
         'sum(rate(agent_conversations_total[5m]))', "production: discount violations"),
        ("shadow:disagreement_rate:1m", "shadow disagrees with production")], 16, y, minv=0,
        right_axis=("shadow disagrees with production",),
        desc="Both models see the same requests; only production's answers reach users. The two discount "
             "lines share the left axis, so you can read the gap between them; the shadow model violates "
             "discount policy about 3-4x as often. Both use a 5m window (~10 simulated days), because "
             "violations are rare enough that the 1m ratio is too noisy to read. Disagreement runs about "
             "ten times higher and sits on the right axis. The ShadowModelDiscountViolations alert still "
             "uses the 1m rule, so it fires within a minute."),
]
y += 8
panels.append(text(
    "**Why not decide the A/B test here?** These panels average conversations over sliding windows. "
    "The experiment randomizes *users*, so the analysis unit is the user, and you need confidence intervals "
    "and a planned sample size. See the notebook.", 0, y, 24, 2))
y += 2

# ---------------------------------------------------------------- ops
panels.append(row("Operations", y)); y += 1
panels += [
    timeseries("Latency per turn", [
        ("histogram_quantile(0.5, sum by (le, llm_version) (rate(agent_turn_latency_seconds_bucket[1m])))",
         "p50 {{llm_version}}"),
        ("histogram_quantile(0.95, sum by (le, llm_version) (rate(agent_turn_latency_seconds_bucket[1m])))",
         "p95 {{llm_version}}")], 0, y, w=6, unit="s", minv=0, thresholds=[(4, "red")]),
    timeseries("Tokens per conversation", [
        ("sum by (llm_version, direction) (rate(agent_llm_tokens_total[1m])) / ignoring(direction) group_left "
         "sum by (llm_version) (rate(agent_conversations_total[1m]))", "{{direction}} {{llm_version}}")],
        6, y, w=6, unit="short", minv=0),
    timeseries("LLM cost per order", [("agent:cost_per_order:1m", "cost per order")], 12, y, w=6,
               unit="currencyUSD", minv=0, thresholds=[(0.058, "red")],
               desc="Illustrative prices: $3 per million input tokens, $15 per million output tokens."),
    timeseries("Tool call error rate", [("agent:tool_error_rate:1m", "error rate")], 18, y, w=6, minv=0,
               thresholds=[(0.05, "red")]),
]
y += 8
panels += [
    timeseries("Conversations per second", [("agent:conversations:rate1m", "all")], 0, y, w=6, unit="reqps",
               minv=0),
    timeseries("Turns per conversation", [
        ("histogram_quantile(0.5, sum by (le, llm_version) (rate(agent_conversation_turns_bucket[1m])))",
         "p50 {{llm_version}}"),
        ("histogram_quantile(0.9, sum by (le, llm_version) (rate(agent_conversation_turns_bucket[1m])))",
         "p90 {{llm_version}}")], 6, y, w=6, unit="none", minv=0),
    state_timeline("Scrape targets (green = up)", [("up", "{{job}}")], 12, y, 6, 8,
                   steps=[{"color": "red", "value": None}, {"color": "green", "value": 0.5}]),
    stat("Drift job: seconds since last run", "time() - max(drift_last_run_timestamp_seconds)", 18, y, w=6, h=8,
         unit="s", decimals=0, steps=[("green", None), ("orange", 30), ("red", 60)]),
]
y += 8

# ---------------------------------------------------------------- truth (collapsed)
truth_y = y + 1
truth = [
    state_timeline("Scenario switches", [('sim_switch', "{{switch}}")], 0, truth_y, 24, 10,
                   desc="Booleans as 0/1, experiments as % of users.",
                   steps=[{"color": "transparent", "value": None}, {"color": "orange", "value": 0.5}],
                   show_value="auto"),
    timeseries("Hidden state", [
        ("sim_truth_menu_stale_fraction", "menu index out of date"),
        ("sim_truth_new_city_share", "Honolulu target share")], 0, truth_y + 10, minv=0),
    timeseries("Injections: attempts, successes, flags", [
        ("sum(rate(sim_truth_injection_attempts_total[1m]))", "attempts (truth)"),
        ("sum(rate(sim_truth_injection_successes_total[1m]))", "successes (truth)"),
        ("sum(rate(agent_injection_flags_total[1m]))", "flagged (telemetry)")], 8, truth_y + 10, unit="reqps",
        minv=0),
    timeseries("True failure rate vs judge", [
        ("sum(rate(sim_truth_failures_total[1m])) / sum(rate(agent_conversations_total[1m]))", "true failure rate"),
        ("agent:judge_fail_rate:1m", "judge fail rate (10% sample)")], 16, truth_y + 10, minv=0),
]
panels.append(row("Ground truth (instructor only; a real team never sees this)", y, collapsed=True,
                  children=truth))

dashboard = {
    "uid": "food-agent",
    "title": "Food ordering agent: production monitoring",
    "tags": ["mlip", "testing-in-production"],
    "timezone": "browser",
    "editable": True,
    "graphTooltip": 1,
    "refresh": "5s",
    "time": {"from": "now-15m", "to": "now"},
    "timepicker": {"refresh_intervals": ["5s", "10s", "30s", "1m"]},
    "schemaVersion": 39,
    "version": 1,
    "panels": panels,
    "annotations": {"list": [{
        "builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": True,
        "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"}]},
}

out = os.path.join(os.path.dirname(__file__), "dashboards", "food_agent.json")
with open(out, "w") as f:
    json.dump(dashboard, f, indent=2)
print(f"wrote {out} with {len(panels)} top-level panels")
