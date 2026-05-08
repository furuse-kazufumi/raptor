#!/bin/bash
# Run corpus2skill on all 4 RAD domains sequentially using Python 3.11
set -u
export PYTHONIOENCODING=utf-8
PY=py
PY_ARGS="-3.11"
ROOT="C:/Users/puruy/raptor"

for d in agents llm vllm security; do
  echo "=== $d ==="
  $PY $PY_ARGS "$ROOT/raptor_corpus2skill.py" \
      --source "$ROOT/.claude/skills/corpus/${d}_corpus/papers" \
      --name "${d}_corpus_v2" \
      --overwrite --max-depth 2 --min-cluster-size 5 --max-clusters 8 \
      || echo "[FAIL] $d"
done
echo "=== ALL DONE ==="
