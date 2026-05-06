# Session Summary — 2026-05-06

## プロジェクト
RAPTOR — C:\Users\puruy\raptor（次セッション後は D:\projects\raptor）

## 完了した作業
- `ccr` コマンド（3文字起動）実装 → bin/ccr.ps1, ccr.cmd, ccr（bash）
- `claude-auto.mjs` — zxラッパー完成（D:\projects\ 自動スキャン、--dangerously-skip-permissions）
- `claude-projects.json` — メタデータオーバーレイ形式（llmesh/mcp-3d/browser-use-project）
- `libexec/raptor-context-check` — Stop フック（150msgs WARN / 250msgs CRITICAL）
- `libexec/raptor-backup-hook` — PreToolUse フック（Edit/Write前にgit commit + D:\backup\before_edit\）
- `libexec/raptor-backup` — 全プロジェクト一括バックアップ（robocopy + git bundle 3世代）
- `.claude/settings.json` — Stop / PreToolUse フック登録、Write(session_summary.md)/.rotate-signal 権限追加
- `.claude/skills/rotate.md` — /rotate スキル（シグナル規則・手順）
- `.claude/skills/work-log.md` — PROGRESS.md / DEBUG_LOG.md / TEST_RESULTS.md 記録ルール
- `CLAUDE.md` — SESSION START更新（.raptor-session.json読込・自動ローテーションルール）、/rotate追加
- `mcp-3d` → D:\projects\mcp-3d 移動完了
- `browser-use-project` → D:\projects\browser-use-project コピー完了（元フォルダはロック中、手動削除要）

## 未完了タスク
1. **RAPTOR の移動**（最重要）: このセッション終了後に PowerShell で実行
   ```powershell
   cd C:\Users\puruy\raptor
   .\move-raptor-to-d.ps1
   ```
2. `C:\Users\puruy\browser-use-project` の削除（ロック解除後）
3. `claude-auto.mjs` の SCRIPT_DIR が移動後も正しく動くか確認（相対パスなので問題ないはず）

## 重要なコンテキスト

### ファイル規則（全プロジェクト共通）
```
<project>/docs/
  SESSION_SUMMARY.md  ← /rotate が書く、起動時に自動読込
  PROGRESS.md         ← 実装進捗
  DEBUG_LOG.md        ← デバッグ記録
  TEST_RESULTS.md     ← テスト結果
  REQUIREMENTS.md     ← 要件定義
  ROADMAP.md          ← ロードマップ
```

### シグナル規則
```
[ROTATE:WARN]     — 150msgs超 → 任意で /rotate
[ROTATE:CRITICAL] — 250msgs超 → Claude が自動 /rotate
.rotate-signal    — ローテーション要求（RAPTOR dir）
.raptor-session.json — 現在プロジェクト情報（ccr が起動時に書く）
```

### 既知のパス
- claude.exe: C:\Users\puruy\.local\bin\claude.exe
- zx: npm global（v8.8.5）
- D:\projects\ — 全プロジェクトのホーム
- D:\backup\ — バックアップ先

## 次にすべきこと
1. `.\move-raptor-to-d.ps1` で RAPTOR を D:\projects\raptor へ移動
2. 新しいターミナルで `ccr` を実行して動作確認
3. LLMesh の開発を再開する場合は ccr → 1（LLMesh）を選択
