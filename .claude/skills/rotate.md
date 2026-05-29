# /rotate — セッションローテーション

コンテキスト上限に近づいた際、作業状態を `docs/SESSION_SUMMARY.md` に書き出し、
`claude-auto.mjs` ラッパーに再起動シグナルを送って新セッションへ引き継ぐ。

---

## シグナル・メッセージ規則

| 識別子 | 種別 | 送信者 | 意味 |
|--------|------|--------|------|
| `[ROTATE:WARN]`           | Stop フック出力 | `raptor-context-check` | 使用量 ≥70%。任意で /rotate |
| `[ROTATE:CRITICAL]`       | Stop フック出力 | `raptor-context-check` | 使用量 ≥90%。**Claude が即座に自動実行** |
| `.rotate-signal`           | ファイル（RAPTOR dir） | Claude | ローテーション要求。ラッパーが検知して再起動 |
| `docs/SESSION_SUMMARY.md`  | ファイル（プロジェクト dir） | Claude | 次セッションへの引き継ぎ |

---

## 実行手順（この順番で必ず行う）

### ステップ 0 — プロジェクトパスを確認する

Read ツールで `.raptor-session.json` を読み、`summaryFile` と `projectPath` を取得する。
`.raptor-session.json` がない場合は RAPTOR ディレクトリの `docs/SESSION_SUMMARY.md` を使用。

### ステップ 0.5 — claude-projects.json の next_plan を更新する

**SESSION_SUMMARY と並行して claude-projects.json も更新する** (rotate 1 コマンドで
next_plan も自動同期、ユーザーが手動更新する手間を排除).

1. RAPTOR dir の `claude-projects.json` を Read
2. 現プロジェクト (projectPath の dirname に対応するエントリ) を特定
   - 例: projectPath=`D:/projects/llcore` → `fullsense` エントリ (llcore は fullsense
     傘下なので) or 該当する独立エントリ
   - 判断付かない場合は **projectPath dirname** と一致する key を優先、無ければ
     ユーザーが想定するエントリ (SESSION_SUMMARY と整合する記録先) を選ぶ
3. **next_plan の冒頭** (現「次回最優先」section) を、本セッションの完了事項と
   次の優先作業に整合するよう **1-3 行で update** する。原則:
   - 旧計画は **append でなく置換** ([[feedback_fullsense_feedback_smart]] 規律:
     肥大化防止). 完了済事項は plan_ref 先 (memory) に詳細を残し、next_plan は
     現行最優先のみ
   - 完了 commit hash, 今後のアクション候補 (例: ARCHITECTURE_LANDSCAPE §9 候補
     "C/D/F/G/H/I" 等) を 1-2 行で言及
   - 「【以下 旧計画 (...参考保持)↓】」より前を update、それ以降は保持
4. Edit ツールで `claude-projects.json` の該当 next_plan を書き換え

**ユーザー確認**: SESSION_SUMMARY と claude-projects.json の両方が更新済か mental check.
両方とも書く前に `.rotate-signal` を作らないこと.

### ステップ 1 — docs/SESSION_SUMMARY.md を書く

Write ツールで `{summaryFile}` のパスに作成（絶対パスで指定）:

```markdown
# Session Summary — {ISO 8601 日時}

## プロジェクト
{projectName} — {projectPath}

## 完了した作業
- {項目}

## 未完了タスク（優先順）
1. {タスク}

## 重要なコンテキスト
{次のセッションが知るべき変数値・設計判断・エラー情報など}

## 次にすべきこと
{具体的な次のアクション（コマンドやファイルパスまで含める）}
```

### ステップ 2 — .rotate-signal を作成する

Write ツールで RAPTOR dir の `.rotate-signal` を作成:

```
rotate
```

パスは `.raptor-session.json` がある場所（例: `C:\Users\puruy\raptor\.rotate-signal`）。

### ステップ 3 — /exit を実行する

セッションを終了。ラッパーが `.rotate-signal` を検知して 3 秒後に再起動する。

---

## トリガー条件

1. **自動**: フック通知に `[ROTATE:CRITICAL]` が含まれる → ユーザー確認なしで即実行
2. **手動**: ユーザーが `/rotate` と入力したとき
3. **判断**: コンテキスト残量が少ないと判断した場合（`[ROTATE:WARN]` 目安）

---

## 注意事項

- `.rotate-signal` を作成する**前**に必ず `docs/SESSION_SUMMARY.md` を完成させること
- Write ツールが失敗した場合は `Bash(echo rotate > .rotate-signal)` で代替
- `ccr` コマンドを使わず直接 `claude` を起動している場合、自動再起動は行われない
