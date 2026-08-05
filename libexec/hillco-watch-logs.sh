#!/usr/bin/env bash
# hillco-watch-logs.sh <max_seconds> <log1> <log2> ...
# Wait until every given log contains a "RESULT " line (method finished) or timeout, then exit.
set -u
MAX="${1:-9000}"; shift
START=$(date +%s)
while :; do
  done=1
  for f in "$@"; do grep -q "RESULT " "$f" 2>/dev/null || done=0; done
  if [ "$done" = "1" ]; then echo "all methods finished"; exit 0; fi
  now=$(date +%s)
  if [ $((now - START)) -ge "$MAX" ]; then echo "timeout after ${MAX}s"; exit 0; fi
  sleep 90
done
