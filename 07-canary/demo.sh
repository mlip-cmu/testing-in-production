#!/usr/bin/env bash
# 07 - 10% of users meet a broken prompt
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset
$S query 'agent:completion_rate:1m' --as "completion rate before the canary"

$S note "canary: prompt v3 to 10% of users"
$S set canary_v3_pct=10
$S wait --days 4
$S query 'agent:completion_rate_by_prompt:1m' --as "completion by arm" --by prompt_version
$S query 'agent:completion_rate:1m'           --as "overall completion rate (barely moves)"
$S query 'sum by (prompt_version) (rate(agent_conversations_total[1m])) / ignoring(prompt_version) group_left sum(rate(agent_conversations_total[1m]))' \
         --as "traffic share by arm" --by prompt_version
$S alerts

$S note "roll back"
$S set canary_v3_pct=0
$S wait --days 3
$S query 'agent:completion_rate:1m' --as "completion rate after rollback"
$S alerts
