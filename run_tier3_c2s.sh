#!/bin/bash
set -u
export PYTHONIOENCODING=utf-8
ROOT="C:/Users/puruy/raptor"
DOMAINS="deep_learning neural_network diffusion optimization statistics robotics quantum_computing automotive infrastructure multivariate_analysis numerical_methods information_theory game_dev"
for d in $DOMAINS; do
  echo "=== $d ==="
  py -3.11 "$ROOT/raptor_corpus2skill.py" \
      --source "$ROOT/.claude/skills/corpus/${d}_corpus/papers" \
      --name "${d}_corpus_v2" \
      --overwrite --max-depth 2 --min-cluster-size 5 --max-clusters 8 \
      || echo "[FAIL] $d"
done
echo "=== ALL DONE ==="
