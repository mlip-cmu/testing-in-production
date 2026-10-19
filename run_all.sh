#!/usr/bin/env bash
# Run every scenario in order and write its transcript, as the CI does.
#   ./run_all.sh                  all scenarios
#   ./run_all.sh 05-chaos-outage  one scenario
set -euo pipefail
cd "$(dirname "$0")"

if ! curl -sf --max-time 5 http://localhost:8000/api/state >/dev/null; then
  echo "The stack is not running. Start it with: docker compose up --build -d" >&2
  exit 1
fi

projects=("$@")
if [ ${#projects[@]} -eq 0 ]; then
  projects=(01-dashboard-tour 02-release-jump 03-slow-degradation 04-invariants \
            05-chaos-outage 06-ab-experiment 07-canary 08-judge-validation)
fi

for p in "${projects[@]}"; do
  echo "=== $p"
  if [ -x "$p/demo.sh" ]; then
    (cd "$p" && ./demo.sh) | tee "$p/transcript.txt"
  elif [ -f "$p/validate_judge.py" ]; then
    (cd "$p" && uv run validate_judge.py) | tee "$p/transcript.txt"
  else
    echo "  nothing runnable in $p" >&2
  fi
done
