#!/usr/bin/env bash
# 06 - watch the arms; decide in the notebook
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset
$S note "upsell prompt to 50% of users, assignment hashed per user"
$S set upsell_experiment_pct=50
$S wait --days 10

$S query 'sum by (prompt_version) (rate(agent_conversations_total[1m])) / ignoring(prompt_version) group_left sum(rate(agent_conversations_total[1m]))' \
         --as "traffic share by arm (sample ratio check)" --by prompt_version
$S query 'agent:completion_rate_by_prompt:1m' --as "completion by arm" --by prompt_version
$S query 'sum by (prompt_version) (rate(agent_order_value_dollars_total[1m])) / sum by (prompt_version) (rate(agent_orders_total[1m]))' \
         --as "order value by arm" --by prompt_version --unit usd
$S query 'sum by (prompt_version) (rate(agent_refunds_total[1m])) / sum by (prompt_version) (rate(agent_orders_total[1m]))' \
         --as "refund rate by arm (the guardrail)" --by prompt_version
$S alerts
$S note "higher order value, lower completion, more refunds. The notebook decides, not this."
$S reset
