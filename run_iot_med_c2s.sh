#!/bin/bash
set -u
export PYTHONIOENCODING=utf-8
ROOT="C:/Users/puruy/raptor"
for d in industrial_iot medical; do
  echo "=== $d ==="
  py -3.11 "$ROOT/raptor_corpus2skill.py" \
      --source "$ROOT/.claude/skills/corpus/${d}_corpus/papers" \
      --name "${d}_corpus_v2" \
      --overwrite --max-depth 2 --min-cluster-size 5 --max-clusters 8 \
      || echo "[FAIL] $d"
done
echo "=== ALL DONE ==="
