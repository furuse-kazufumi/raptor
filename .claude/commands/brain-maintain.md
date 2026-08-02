---
description: 第二の脳の自律 organizer — stale/superseded/orphan/broken-link/dead-memory を検出し、ローカル LLM 提案つきレビュー報告を生成 (安全: 削除しない)
---

# /brain-maintain — 第二の脳の自律整理 (organizer)

private brain repo (`C:/dev/projects/brain`) の decay/clutter を検出し `50_MOC/_maintenance.md`
に **レビュー報告** を書く。設計の正本 = `2ndbrain/docs/superpowers/specs/2026-08-01-second-brain-sp3-autonomy-organizer.md`。

## 安全モデル (絶対厳守)

- **報告のみがデフォルト**。ツールは **削除しない**・**vault 外を触らない**。
- `--apply-archive` は報告で `- [x]` された **vault 内** ファイルを `99_Archives/` へ **移動**(git 可逆)。恒久削除はしない。
- source (memory / project docs) は **surface のみ**。手で対応する。**`delete` verdict は提案であって自動実行しない**。

## 手順

1. 報告生成(Ollama qwen2.5 が起動していれば keep/archive/delete 提案つき。停止中は mechanical のみで fail-safe 続行):
   ```
   cd C:/dev/projects/brain && PYTHONUTF8=1 py -3.11 tools/brain_maintain.py --vault . --sync
   ```
   決定論的に見たい時は `--no-llm`。
2. `50_MOC/_maintenance.md` の各セクション件数を 1 行で報告(stale/superseded/orphans/broken/dead-memory)。
3. **broken index / 明確な superseded** など actionable な実 finding があれば要点を提示(ユーザーレビュー用)。
4. ユーザーが報告で `- [x]` を付けた後にのみ、archive を適用:
   ```
   PYTHONUTF8=1 py -3.11 tools/brain_maintain.py --vault . --apply-archive
   ```
   これは constraints に archive 承認が含まれる時のみ。**push は human-gate**。

## always-on 化

`tools/register_maintain_task.ps1`(daily report-only)をユーザーが実行 → 離席中も報告が更新される。
Claude はスケジュール登録(system 変更)を勝手に実行しない。
