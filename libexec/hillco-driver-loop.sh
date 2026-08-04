#!/usr/bin/env bash
# hillco-driver-loop.sh — autonomous tool-only work-graph driver for the hillco balance
# curriculum. Repeatedly drains ready `tool:command` nodes (weight-shift / capture-step /
# walk / ...), logging each tick. Tool-only => no LLM auth gate, safe to run unattended.
# The supervising Claude session adds/advances nodes (PDCA Act); this loop is the Do engine.
#
# Usage: hillco-driver-loop.sh [max_seconds] [idle_sleep_seconds]
set -u
RAPTOR_DIR="C:/dev/tools/raptor"
cd "$RAPTOR_DIR" || exit 1
MAX_SECONDS="${1:-54000}"      # ~15h safety bound
IDLE_SLEEP="${2:-60}"
LOG="$RAPTOR_DIR/out/worklog/hillco_driver.log"
mkdir -p "$(dirname "$LOG")"
START=$(date +%s)
tick=0
echo "[$(date '+%F %T')] hillco-driver-loop start max=${MAX_SECONDS}s idle_sleep=${IDLE_SLEEP}s" >> "$LOG"
while :; do
  now=$(date +%s)
  elapsed=$(( now - START ))
  if [ "$elapsed" -ge "$MAX_SECONDS" ]; then
    echo "[$(date '+%F %T')] lifetime reached (${elapsed}s) — exiting" >> "$LOG"
    break
  fi
  tick=$(( tick + 1 ))
  out=$(py -3.11 libexec/raptor-worklog run-once --available tool:command 2>&1)
  action=$(printf '%s' "$out" | py -3.11 -c "import json,sys
try:
    print(json.loads(sys.stdin.read()).get('action','?'))
except Exception:
    print('parse_err')" 2>/dev/null)
  echo "[$(date '+%F %T')] tick=$tick action=$action :: $out" >> "$LOG"
  case "$action" in
    completed)
      # more work may be immediately ready — loop without sleeping
      continue ;;
    idle|needs_human|stalled|parse_err|"?")
      sleep "$IDLE_SLEEP" ;;
    auth_halt)
      echo "[$(date '+%F %T')] auth_halt — stopping (never continue past auth)" >> "$LOG"
      break ;;
    *)
      sleep "$IDLE_SLEEP" ;;
  esac
done
echo "[$(date '+%F %T')] hillco-driver-loop exit after ${tick} ticks" >> "$LOG"
