# /wrap-up — セッション終了 (SESSION_SUMMARY + next_plan 自動更新付き exit)

`/rotate` と同じ手順で SESSION_SUMMARY と `claude-projects.json` の next_plan を
**自動更新してから** `/exit` する。再起動シグナル (`.rotate-signal`) は作らないので
**そのままセッション終了** する点が `/rotate` との違い。

「exit 前に SESSION_SUMMARY と next_plan を書きますね」と毎回予告して書く運用を
1 コマンド化するのが目的。

---

## 違い (rotate / wrap-up / clear / exit)

| コマンド | next_plan 更新 | SESSION_SUMMARY 書出 | 再起動 | 用途 |
|---|---|---|---|---|
| `/rotate`  | ✓ | ✓ | ✓ (自動再起動) | context リフレッシュ + 続行 |
| **`/wrap-up`** | ✓ | ✓ | ✗ (純粋 exit) | 作業終了 (続きは別日に) |
| `/exit`    | ✗ | ✗ | ✗ | 純 exit (state 残さず) |
| `/clear`   | ✗ | ✗ | ✗ (プロセス維持) | 話題切替 |

---

## 実行手順 (この順番で必ず行う)

### ステップ 0 — プロジェクトパスを確認する

Read ツールで `.raptor-session.json` を読み、`summaryFile` と `projectPath` を取得する。
`.raptor-session.json` がない場合は RAPTOR ディレクトリの `docs/SESSION_SUMMARY.md` を使用。

### ステップ 0.5 — claude-projects.json の next_plan を更新する

1. RAPTOR dir の `claude-projects.json` を Read
2. 現プロジェクトに対応するエントリを特定 (projectPath dirname と一致する key 優先、
   傘下なら親 project = 例: llcore → fullsense)
3. **next_plan 冒頭** を本セッションの完了事項 + 次の優先作業に整合するよう
   **1-3 行で update** (旧計画は append でなく置換、肥大化防止規律
   [[feedback_fullsense_feedback_smart]] 準拠、「【以下 旧計画↓】」より前のみ
   書き換え、それ以降は保持)
4. Edit ツールで該当 next_plan を書き換え

### ステップ 1 — docs/SESSION_SUMMARY.md を書く

Write ツールで `{summaryFile}` のパスに作成 (絶対パスで指定):

```markdown
# Session Summary — {ISO 8601 日時}

## プロジェクト
{projectName} — {projectPath}

## 完了した作業
- {項目, commit hash 付き}

## 未完了タスク (優先順)
1. {タスク}

## 重要なコンテキスト
{次セッションが知るべき変数値・設計判断・エラー情報など}

## 次にすべきこと
{具体的な次のアクション (コマンドやファイルパスまで)}
```

### ステップ 2 — /exit を実行する

セッションを終了。**`.rotate-signal` は作らない**ので自動再起動せず、純粋に終了。
次回 `ccr` で再開時は SessionStart hook が SESSION_SUMMARY と claude-projects.json
next_plan を読み込み、「Session Restored:」宣言から再開される。

---

## トリガー条件

1. **手動**: ユーザーが `/wrap-up` と入力したとき
2. **判断**: ユーザーが「もう終わる」「今日はここまで」等の意思表示をした時、
   自動的に本フローで終了 (確認 1 回挟んで OK なら実行)

---

## 注意事項

- `/exit` 前に必ず SESSION_SUMMARY.md と claude-projects.json の両方を update 済か確認
- Write/Edit が失敗した場合は内容を出力しユーザーに手動保存を依頼
- `/clear` と違いセッションは終了する (会話履歴も消える)
- `/rotate` と違い再起動しない (次回起動はユーザーが `ccr` を叩く)
