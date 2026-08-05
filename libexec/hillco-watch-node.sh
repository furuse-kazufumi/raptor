#!/usr/bin/env bash
# hillco-watch-node.sh <task_id> [max_seconds] [poll_seconds]
# Blocks until the given work-graph node leaves ready/leased (done/failed) or times out,
# then exits — used to re-invoke the supervising session exactly when a stage finishes.
set -u
cd "C:/dev/tools/raptor" || exit 1
TID="${1:?task id required}"
MAX="${2:-3000}"
POLL="${3:-60}"
START=$(date +%s)
while :; do
  st=$(py -3.11 libexec/raptor-worklog show "$TID" 2>/dev/null | py -3.11 -c "import json,sys
try: print(json.loads(sys.stdin.read()).get('status','?'))
except Exception: print('err')" 2>/dev/null)
  now=$(date +%s); el=$(( now - START ))
  if [ "$st" != "ready" ] && [ "$st" != "leased" ] && [ "$st" != "pending" ]; then
    echo "node $TID reached status=$st after ${el}s"; exit 0
  fi
  if [ "$el" -ge "$MAX" ]; then echo "watch timeout ${el}s status=$st"; exit 0; fi
  sleep "$POLL"
done
