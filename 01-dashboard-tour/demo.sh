#!/usr/bin/env bash
# 01 - the healthy baseline, read twice
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset
$S note "baseline, no scenario running"
$S state

for round in 1 2; do
  $S note "reading $round"
  $S query 'agent:completion_rate:1m'              --as "completion rate"
  $S query 'agent:handoff_rate:1m'                 --as "handoff to human"
  $S query 'agent:corrections_per_conversation:1m' --as "corrections per conversation" --unit raw
  $S query 'agent:judge_fail_rate:1m'              --as "judge fail rate (10% sample)"
  $S query 'agent:refund_rate:1m'                  --as "refund rate (delayed)"
  $S query 'agent:violations_per_order:1m'         --as "invariant violations per order" --by check
  $S query 'agent:cost_per_order:1m'               --as "LLM cost per order" --unit usd
  $S alerts
  if [ "$round" = 1 ]; then $S wait --days 4; fi
done
