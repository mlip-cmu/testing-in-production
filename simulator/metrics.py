"""Prometheus metrics exported by the food ordering agent simulator.

Label cardinality is kept small on purpose (a lesson in itself): no user IDs,
no restaurant IDs, no free text in labels.

The three quality counters also carry `city` (3 values), so completion, corrections
and judge verdicts can be sliced per city. No dashboard panel reads it yet; the
lecture adds that panel live. Every recording rule aggregates with sum(), which
drops the label, so nothing downstream changed.
"""

from prometheus_client import Counter, Gauge, Histogram

PV = ["prompt_version", "llm_version"]

conversations = Counter("agent_conversations", "Finished conversations",
                        PV + ["intent", "outcome", "city"])
requests_by_city = Counter("agent_requests_by_city", "Conversations by user city", ["city"])
orders = Counter("agent_orders", "Orders placed by the agent", PV)
order_value = Counter("agent_order_value_dollars", "Order value placed by the agent", PV)
discounts = Counter("agent_discount_dollars", "Discounts granted by the agent", PV)
corrections = Counter("agent_user_corrections", "Times users corrected the agent (implicit feedback)",
                      PV + ["city"])
refunds = Counter("agent_refunds", "Refunds (delayed label, arrives 1-3 days after the order)", PV)
refund_value = Counter("agent_refund_dollars", "Refunded dollars (delayed)", PV)

turns = Histogram("agent_conversation_turns", "Turns per conversation", PV,
                  buckets=[2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20])
latency = Histogram("agent_turn_latency_seconds", "Mean LLM latency per turn", ["llm_version"],
                    buckets=[0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7, 10])
tokens = Counter("agent_llm_tokens", "LLM tokens", ["llm_version", "direction"])
cost = Counter("agent_llm_cost_dollars", "LLM cost (illustrative prices)", PV)
tool_calls = Counter("agent_tool_calls", "Tool calls by status", ["status"])

violations = Counter("agent_invariant_violations", "Invariant check failures on placed orders",
                     PV + ["check"])
judge = Counter("agent_judge_evaluations", "LLM-as-judge verdicts on a 10% sample",
                PV + ["verdict", "failure_mode", "city"])
injection_flags = Counter("agent_injection_flags", "Requests flagged by the prompt-injection heuristic")

surprise_recs = Counter("surprise_recommendations", "Surprise-me recommendations",
                        ["accepted", "repeat", "new_restaurant"])
surprise_coverage = Gauge("surprise_catalog_coverage",
                          "Share of open restaurants recommended at least once yesterday (nightly job)")
surprise_top5 = Gauge("surprise_top5_share", "Share of yesterday's recommendations going to the top 5 restaurants")
surprise_new_share = Gauge("surprise_new_restaurant_share",
                           "Share of yesterday's recommendations for restaurants opened in the last 7 days")

shadow = Counter("shadow_comparisons", "Shadow model vs production outcome", ["shadow_llm", "result"])
shadow_violations = Counter("shadow_invariant_violations", "Invariant failures in shadow orders",
                            ["shadow_llm", "check"])

assignments = Counter("experiment_assignments", "Conversations by experiment arm", ["experiment", "arm"])

sim_day = Gauge("sim_day", "Simulated day")
sim_paused = Gauge("sim_paused", "1 if the simulation is paused")
sim_switch = Gauge("sim_switch", "Scenario switch values (bool as 0/1, experiments as %)", ["switch"])

# Hidden ground truth -- a real team would not have these.
truth_menu_stale = Gauge("sim_truth_menu_stale_fraction", "TRUTH: share of menu index out of date")
truth_injection_attempts = Counter("sim_truth_injection_attempts", "TRUTH: injection attempts")
truth_injection_successes = Counter("sim_truth_injection_successes", "TRUTH: successful injections")
truth_failures = Counter("sim_truth_failures", "TRUTH: conversation failures", PV + ["failure_mode"])
truth_new_city_share = Gauge("sim_truth_new_city_share", "TRUTH: target traffic share of the new city")


def record_conversation(r: dict) -> None:
    pv = (r["prompt_version"], r["llm_version"])
    conversations.labels(*pv, r["intent"], r["outcome"], r["city"]).inc()
    requests_by_city.labels(r["city"]).inc()
    if r["n_items"] > 0:
        orders.labels(*pv).inc()
        order_value.labels(*pv).inc(r["order_value"])
    if r["discount_value"]:
        discounts.labels(*pv).inc(r["discount_value"])
    if r["corrections"]:
        corrections.labels(*pv, r["city"]).inc(r["corrections"])
    turns.labels(*pv).observe(r["turns"])
    latency.labels(r["llm_version"]).observe(r["latency_s"])
    tokens.labels(r["llm_version"], "input").inc(r["input_tokens"])
    tokens.labels(r["llm_version"], "output").inc(r["output_tokens"])
    cost.labels(*pv).inc(r["cost_usd"])
    tool_calls.labels("ok").inc(r["tool_calls"] - r["tool_errors"])
    if r["tool_errors"]:
        tool_calls.labels("error").inc(r["tool_errors"])
    for check in ("item_not_on_menu", "price_mismatch", "discount_policy", "allergen"):
        if r[f"viol_{check}"]:
            violations.labels(*pv, check).inc()
    if r["judge_sampled"]:
        judge.labels(*pv, r["judge_verdict"], r["judge_failure_mode"] or "none", r["city"]).inc()
    if r["injection_flagged"]:
        injection_flags.inc()
    if r["surprise_restaurant"]:
        surprise_recs.labels(str(r["surprise_accepted"]), str(r["surprise_repeat"]),
                             str(r["surprise_new_restaurant"])).inc()
    if r["shadow_agree"] != "":
        shadow.labels("llm-2026-09", "agree" if r["shadow_agree"] else "disagree").inc()
        if r["shadow_viol_discount_policy"]:
            shadow_violations.labels("llm-2026-09", "discount_policy").inc()
    assignments.labels("upsell", r["exp_upsell_arm"]).inc()
    assignments.labels("canary_v3", r["canary_v3_arm"]).inc()
    if r["truth_injection_attempt"]:
        truth_injection_attempts.inc()
    if r["truth_injection_success"]:
        truth_injection_successes.inc()
    if r["truth_failure_mode"]:
        truth_failures.labels(*pv, r["truth_failure_mode"]).inc()


def record_refund(r: dict) -> None:
    refunds.labels(r["prompt_version"], r["llm_version"]).inc()
    refund_value.labels(r["prompt_version"], r["llm_version"]).inc(r["refund_amount"])


def record_state(engine, paused: bool) -> None:
    t = engine.truth_snapshot()
    sim_day.set(t["sim_day"])
    sim_paused.set(1 if paused else 0)
    for k, v in engine.switches_dict().items():
        sim_switch.labels(k).set(float(v))
    truth_menu_stale.set(t["menu_stale_fraction"])
    truth_new_city_share.set(t["new_city_share"])
    s = t["surprise"]
    surprise_coverage.set(s["coverage"])
    surprise_top5.set(s["top5_share"])
    surprise_new_share.set(s["new_restaurant_share"])
