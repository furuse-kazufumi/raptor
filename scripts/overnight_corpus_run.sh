#!/usr/bin/env bash
# Overnight corpus expansion orchestrator
# Phase A: existing 17-corpus completion batch (already running, just wait)
# Phase B: arXiv fetch for 16 new corpora (parallel to A)
# Phase C: corpus2skill for tui_corpus + 16 arXiv corpora (after A and B finish)
#
# Idempotent via --resume-summaries; safe to re-run.

set -u
cd "$(dirname "$0")/.."

LOG_DIR="out/overnight_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
echo "Logs: $LOG_DIR"
echo "Start: $(date -Iseconds)"

EXISTING_BATCH_DIR="out/corpus_completion_20260512_214913"

# --- Phase B (parallel with A): arXiv fetch ---
echo "[Phase B] starting arXiv fetch..."
python3 scripts/fetch_new_corpora.py > "$LOG_DIR/fetch.log" 2>&1 &
FETCH_PID=$!
echo "[Phase B] fetch PID=$FETCH_PID"

# --- Wait for Phase A (existing batch) ---
echo "[Phase A] waiting for existing completion batch ($EXISTING_BATCH_DIR)..."
while true; do
  if [ -f "$EXISTING_BATCH_DIR/_summary.log" ] && \
     grep -q "COMPLETED 17 corpora" "$EXISTING_BATCH_DIR/_summary.log" 2>/dev/null; then
    echo "[Phase A] DONE"
    break
  fi
  sleep 120
done

# --- Wait for Phase B ---
echo "[Phase B] waiting for arXiv fetch to finish..."
wait $FETCH_PID
echo "[Phase B] DONE"

# --- Phase C: corpus2skill on all new corpora ---
NEW_CORPORA=(
  tui_corpus
  astrophysics_corpus_v2
  aerospace_corpus_v2
  satellite_engineering_corpus_v2
  reinforcement_learning_corpus_v2
  multimodal_corpus_v2
  game_ai_corpus_v2
  time_series_corpus_v2
  tinyml_corpus_v2
  hci_corpus_v2
  formal_methods_corpus_v2
  distributed_systems_corpus_v2
  compiler_corpus_v2
  cryptography_corpus_v2
  automated_theorem_proving_corpus_v2
  industrial_protocols_corpus_v2
  protein_corpus_v2
)

total=${#NEW_CORPORA[@]}
i=0
for c in "${NEW_CORPORA[@]}"; do
  i=$((i+1))
  src="C:/dev/docs/$c"
  if [[ ! -d "$src" ]]; then
    echo "[$i/$total] SKIP $c (source missing)" | tee -a "$LOG_DIR/_summary.log"
    continue
  fi
  cnt=$(find "$src" -type f \( -name "*.md" -o -name "*.rst" -o -name "*.txt" \) 2>/dev/null | wc -l)
  if [[ "$cnt" -lt 3 ]]; then
    echo "[$i/$total] SKIP $c (only $cnt files, below min cluster size)" | tee -a "$LOG_DIR/_summary.log"
    continue
  fi
  log="$LOG_DIR/${c}.log"
  echo "[$i/$total] START $c ($cnt files) -> $log"
  if python3 raptor_corpus2skill.py --source "$src" --name "$c" --resume-summaries 2>&1 | tee "$log" >/dev/null; then
    echo "[$i/$total] DONE  $c" | tee -a "$LOG_DIR/_summary.log"
  else
    rc=$?
    echo "[$i/$total] FAIL  $c (exit $rc)" | tee -a "$LOG_DIR/_summary.log"
  fi
done

echo "=== ALL COMPLETED at $(date -Iseconds) ===" | tee -a "$LOG_DIR/_summary.log"
