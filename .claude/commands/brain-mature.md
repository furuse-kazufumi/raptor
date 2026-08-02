---
description: 第二の脳の Inbox 捕捉を昇格 — ローカル LLM が行き先(10_Journal/50_MOC)/タイトル/リンク/要約を提案し、人が承認したものだけ安全に移動(削除しない)
---

# /brain-mature — Inbox 捕捉の昇格(propose → apply)

`00_Inbox/` の生メモをローカル LLM(qwen2.5)で分類し、`10_Journal` / `50_MOC` へ昇格する。
捕捉→熟成→整理ループの最後。設計 = `2ndbrain/docs/superpowers/specs/2026-08-02-second-brain-mature.md`。

## 安全モデル(organizer と同じ:提案してから実行)
- **報告のみがデフォルト**。`00_Inbox/_mature_suggestions.md` に提案(行き先/タイトル/リンク/要約)。
- `--apply` は報告で `- [x]` された Inbox ノートを行き先へ **移動**(内容保持・git 可逆・`matured:` 刻印)。**削除しない**・**vault 外/生成層(20/30/40)へは移さない**・**既存を上書きしない**。
- 提案リンクは vault で解決した実ノートのみ(**broken link を作らない**)。LLM 自由文はサニタイズ(偽装承認行を作らせない)。Ollama 停止時は全 `keep`(要レビュー)で fail-safe。

## 手順
1. 報告生成(qwen2.5 起動時。決定論で見るなら `--no-llm`):
   ```
   cd C:/dev/projects/brain && PYTHONUTF8=1 py -3.11 tools/brain_mature.py --vault .
   ```
2. `_mature_suggestions.md` の各提案を 1 行で要約報告(件数と代表例)。
3. ユーザーが `- [x]` を付けた後にのみ昇格を適用(constraints に承認がある時のみ):
   ```
   PYTHONUTF8=1 py -3.11 tools/brain_mature.py --vault . --apply
   ```
4. **push は human-gate**。
