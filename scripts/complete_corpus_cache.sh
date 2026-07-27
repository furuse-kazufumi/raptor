#!/usr/bin/env bash
# Complete the corpus2skill cache for all v2 corpora missing from .claude/skills/corpus/
# Sequential execution to respect API rate limits. Idempotent via --resume-summaries.

set -u
cd "$(dirname "$0")/.."

LOG_DIR="out/corpus_completion_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"
echo "Logs: $LOG_DIR"

CORPORA=(
  hacker_corpus_v2
  neuro_ethics_corpus
  neuro_ethics_corpus_v2
  neural_prosthetics_corpus
  neural_prosthetics_corpus_v2
  bci_corpus
  bci_corpus_v2
  neural_dataset_corpus
  neural_dataset_corpus_v2
  neural_signal_corpus
  neural_signal_corpus_v2
  neuromorphic_corpus
  neuromorphic_corpus_v2
  neuroscience_corpus
  neuroscience_corpus_v2
  cognitive_ai_corpus
  cognitive_ai_corpus_v2
)

total=${#CORPORA[@]}
i=0
for c in "${CORPORA[@]}"; do
  i=$((i+1))
  src="C:/dev/docs/$c"
  if [[ ! -d "$src" ]]; then
    echo "[$i/$total] SKIP $c (source dir missing)" | tee -a "$LOG_DIR/_summary.log"
    continue
  fi
  log="$LOG_DIR/${c}.log"
  echo "[$i/$total] START $c -> $log"
  if python3 raptor_corpus2skill.py --source "$src" --name "$c" --resume-summaries 2>&1 | tee "$log" >/dev/null; then
    echo "[$i/$total] DONE  $c" | tee -a "$LOG_DIR/_summary.log"
  else
    rc=$?
    echo "[$i/$total] FAIL  $c (exit $rc)" | tee -a "$LOG_DIR/_summary.log"
  fi
done

echo "=== COMPLETED $total corpora at $(date -Iseconds) ===" | tee -a "$LOG_DIR/_summary.log"
