---
description: 第二の脳の設計を Obsidian Canvas に自動生成 — vault 実ファイルを file ノード、[[wikilink]] を named エッジにした .canvas を出力(生成のみ・装飾ゼロ)
---

# /brain-canvas — 第二の脳の視覚設計サーフェス生成

private brain repo (`C:/dev/projects/brain`) の構造から JSON Canvas(`.canvas`)を生成し、
Obsidian で開ける設計図にする。元 2ndBrain の視覚ビジョン(SP4)。設計 =
`2ndbrain/docs/superpowers/specs/2026-08-01-second-brain-sp4-canvas.md`。

## 4原則(生成で担保)
1. **各ノード=実ファイル**: 全 `file` ノードは vault の実 `.md` を指す(`verify_canvas` ゲート、未 file-backed があれば `main` は書き込まず非ゼロ終了)。
2. **データフロー=named エッジ**: 実 `[[wikilink]]` から生成、関係で命名(project→memory=`memory` 等)。
3. **装飾ボックス禁止**: `file`/`group` ノードのみ。未解決リンクはノード化しない(organizer の broken-link に回る)。
4. **空間レイアウト**: レイヤー別グループ(Projects | Knowledge | Memory | MOC …)にグリッド配置。

## 手順
1. 生成(既定=16 projects を種に depth 1 で projects+参照 memory):
   ```
   cd C:/dev/projects/brain && PYTHONUTF8=1 py -3.11 tools/brain_canvas.py --vault .
   ```
   焦点を変える: `--seeds 20_Projects/llcore.md --depth 2` / 出力先 `--out 50_MOC/<name>.canvas`。
2. サマリ(`files=/groups=/edges=`)を 1 行で報告。Obsidian で `50_MOC/brain.canvas` を開くと graph 化。

## 正直な限界(過大主張しない)
- **生成のみ**(vault→.canvas)。Obsidian の Canvas でブロックを動かしても **vault の wikilink は変わらない**(vanilla に双方向同期は無い)。レイアウトの正本は再生成。
- **push は human-gate**(private repo)。
