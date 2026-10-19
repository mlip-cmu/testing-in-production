#!/usr/bin/env bash
# 02 - shadow-test the new LLM, then upgrade for real
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset
$S note "shadow release: the candidate runs beside production, its answers discarded"
$S set shadow_new_llm=true
$S wait --days 10
$S query 'shadow:discount_violation_rate:5m'                 --as "shadow: discount violations"
$S query 'agent:discount_violations_per_conversation:5m'     --as "production: discount violations"
$S query 'shadow:disagreement_rate:1m'                       --as "models disagree"
$S alerts
$S set shadow_new_llm=false

$S note "baseline before the upgrade"
$S query 'agent:cost_per_order:1m'       --as "LLM cost per order" --unit usd
$S query 'agent:completion_rate:1m'      --as "completion rate"
$S query 'agent:violations_per_order:1m{check="discount_policy"}' --as "discount violations per order"

$S note "the provider upgrades the model; nobody deployed anything"
$S set llm_upgraded=true
$S wait --days 4
$S query 'agent:cost_per_order:1m'       --as "LLM cost per order" --unit usd
$S query 'agent:turn_latency_p95:1m'     --as "p95 latency per turn" --unit s
$S query 'agent:completion_rate:1m'      --as "completion rate"
$S query 'agent:violations_per_order:1m{check="discount_policy"}' --as "discount violations per order"
$S alerts

$S note "pin the old model"
$S set llm_upgraded=false
$S wait --days 3
$S alerts
