#!/usr/bin/env bash
# 03 - four failures that never jump
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"

$S reset

$S note "1. menu sync stops: the search index goes stale ~3% per simulated day"
$S set menu_sync_paused=true
$S wait --days 6
$S query 'agent:violations_per_order:1m'         --as "invariant violations per order" --by check
$S query 'agent:corrections_per_conversation:1m' --as "corrections per conversation" --unit raw
$S query 'agent:completion_rate:1m'              --as "completion rate"
$S query 'agent:refund_rate:1m'                  --as "refund rate (still catching up)"
$S alerts
$S set menu_sync_paused=false
$S wait --days 3
$S query 'agent:refund_rate:1m'                  --as "refund rate (the delayed label arrives)"

$S note "2. launch in Honolulu: inputs change, and the drift job notices"
$S reset
$S set new_city_launched=true
$S wait --days 6
$S query 'drift_column_score'          --as "drift score by column (PSI, >0.1 is drift)" --by column --unit raw
$S query 'drift_share_of_columns'      --as "share of columns drifting"
$S query 'sum by (city) (rate(agent_conversations_total{outcome="completed"}[1m])) / sum by (city) (rate(agent_conversations_total[1m]))' \
         --as "completion by city (needs the label somebody added)" --by city
$S alerts
$S note "accept Honolulu as the new normal: reset the reference, leave the city launched"
$S reference
$S wait --days 3
$S query 'drift_share_of_columns' --as "share of columns drifting"
$S alerts
$S query 'sum by (city) (rate(agent_conversations_total{outcome="completed"}[1m])) / sum by (city) (rate(agent_conversations_total[1m]))' \
         --as "completion by city (the alert cleared, this did not)" --by city

$S note "3. surprise me stops exploring: the recommender learns from itself"
$S reset
$S set surprise_exploration=false
$S wait --days 6
$S query 'surprise_catalog_coverage'   --as "catalog coverage (nightly)"
$S query 'surprise_top5_share'         --as "share going to the top 5"
$S query 'surprise:acceptance_rate:1m' --as "acceptance rate (barely moves)"
# the loop narrows what gets recommended, which the drift job sees as a changed distribution
$S query 'drift_column_score' --as "drift score by column" --by column --unit raw
$S alerts

$S note "4. injection campaign: the detector decays, the invariant does not"
$S reset
$S set injection_campaign=true
$S wait --days 5
$S query 'agent:injection_flag_rate:1m' --as "requests flagged as injection"
$S query 'agent:violations_per_order:1m{check="discount_policy"}' --as "discount violations per order"
$S wait --days 5
$S query 'agent:injection_flag_rate:1m' --as "flag rate 5 days later (recall decays)"
$S query 'agent:violations_per_order:1m{check="discount_policy"}' --as "discount violations per order"
$S alerts
$S note "deploy the guardrail"
$S set injection_guardrail=true
$S wait --days 4
$S query 'agent:violations_per_order:1m{check="discount_policy"}' --as "discount violations per order"
$S reset
