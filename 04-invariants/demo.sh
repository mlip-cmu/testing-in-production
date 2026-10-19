#!/usr/bin/env bash
# 04 - the same four checks, two different causes
set -euo pipefail
cd "$(dirname "$0")"
S="uv run --project ../tools ../tools/scenario.py"
show() { $S query 'agent:violations_per_order:1m' --as "$1" --by check; }

$S reset
$S note "baseline: all four checks quiet"
show "violations per order"

$S note "cause 1: the menu index goes stale"
$S set menu_sync_paused=true
$S wait --days 6
show "violations per order (menu and price light up)"
$S alerts
$S reset
$S wait --days 3

$S note "cause 2: an injection campaign"
$S set injection_campaign=true
$S wait --days 6
show "violations per order (only discounts light up)"
$S alerts
$S reset
