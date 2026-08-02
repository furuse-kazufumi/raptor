---
description: 第二の脳 (brain repo) の生成層 20_/30_/40_ を raptor memory / RAD_INDEX / claude-projects.json から再生成する
---

# /brain-sync — 第二の脳の mirror を再生成

private brain repo (`C:/dev/projects/brain`) の生成層を source-of-truth から冪等に再生成する。
設計の正本 = `C:/dev/projects/2ndbrain/docs/superpowers/{specs,plans}/2026-08-01-*`。

## 手順

1. 実行:
   ```
   cd C:/dev/projects/brain && PYTHONUTF8=1 py -3.11 tools/brain_sync.py --brain .
   ```
2. 出力サマリ (`memory=<n> corpora=<n> projects=<n>`) を 1 行で報告。
3. `git -C C:/dev/projects/brain status --porcelain` の差分を提示。

## 規律

- **生成層 `20_Projects/ 30_Knowledge/ 40_Memory/` は再生成専用**(手編集禁止・banner 付き)。
- **push は human-gate**(private repo・個人の判断/記憶を含む)。勝手に push しない。
- source (`~/.claude/.../memory`, `C:/dev/docs/RAD_INDEX.md`, raptor `claude-projects.json`) は read-only。
