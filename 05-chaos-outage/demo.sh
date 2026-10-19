#!/usr/bin/env bash
# 05 - take the menu API away and watch the fallback behavior
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset
$S note "before: healthy"
$S query 'agent:tool_error_rate:1m'      --as "tool call error rate"
$S query 'agent:turn_latency_p95:1m'     --as "p95 latency per turn" --unit s
$S query 'agent:completion_rate:1m'      --as "completion rate"
$S query 'agent:violations_per_order:1m{check="item_not_on_menu"}' --as "item not on menu"

$S note "the menu API goes down"
$S set menu_api_outage=true
$S wait --days 3
$S query 'agent:tool_error_rate:1m'      --as "tool call error rate"
$S query 'agent:turn_latency_p95:1m'     --as "p95 latency per turn" --unit s
$S query 'agent:completion_rate:1m'      --as "completion rate"
$S query 'agent:handoff_rate:1m'         --as "handoff to human"
$S query 'agent:violations_per_order:1m{check="item_not_on_menu"}' --as "item not on menu (invented items)"
$S alerts

$S note "the API comes back"
$S set menu_api_outage=false
$S wait --days 3
$S query 'agent:tool_error_rate:1m'      --as "tool call error rate"
$S query 'agent:completion_rate:1m'      --as "completion rate"
$S alerts
