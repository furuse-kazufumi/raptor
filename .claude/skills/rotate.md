# /rotate — セッション終了前の状態保存

コンテキスト上限に近づいた、または区切りで終了したいとき、**終了する前に**作業状態を
`docs/SESSION_SUMMARY.md` と `claude-projects.json` の `next_plan` に書き出す手順。

> **重要(役割分担・これが従来「毎回つまづく」を断つ)**: Claude は **自力で `/exit`・再起動・再ログインできない**
> ([[project_ccr_automation_limits]])。よって rotate は「**Claude が状態を保存する終了前手順**」であり、
> **実際の `/exit`・再起動はユーザーが行う**。Claude は再起動を完遂しようとしない(=ステップ3 を自分でやろうとしない)。

---

## Claude が行う手順 (ステップ 0〜2 のみ)

### ステップ 0 — プロジェクトパスを確認
Read で `.raptor-session.json` を読み `summaryFile` と `projectPath` を取得。
無ければ RAPTOR dir の `docs/SESSION_SUMMARY.md` を使用。

### ステップ 0.5 — claude-projects.json の next_plan を更新
RAPTOR dir の `claude-projects.json` を Read → projectPath dirname に対応するエントリの
`next_plan` 冒頭(現「次回最優先」)を、本セッションの完了事項と次の優先作業に整合するよう
**1-3 行で置換**(append でなく置換=肥大化防止 [[feedback_fullsense_feedback_smart]])。
完了 commit hash / 次アクション候補を 1-2 行で。Edit で書き換え。

### ステップ 1 — docs/SESSION_SUMMARY.md を書く
Write で `{summaryFile}`(絶対パス)に:

```markdown
# Session Summary — {ISO 8601 日時}

## プロジェクト
{projectName} — {projectPath}

## 完了した作業
- {項目}

## 未完了タスク（優先順）
1. {タスク}

## 重要なコンテキスト
{次セッションが知るべき変数値・設計判断・エラー情報など}

## 次にすべきこと
{具体的な次のアクション（コマンド・ファイルパスまで含める）}
```

### ステップ 2 — (任意) .rotate-signal を作成
**ccr 経由で起動している場合のみ**作る(直接 `claude` 起動なら無意味なので省略)。
Write で RAPTOR dir(`.raptor-session.json` のある場所)の `.rotate-signal` に `rotate` と書く。
これがあると **ユーザーが /exit したとき** ccr ラッパーが 3 秒後に自動再起動する。
(`.rotate-signal` を作る前に必ず SESSION_SUMMARY.md を完成させること。Write 失敗時は `Bash(echo rotate > .rotate-signal)`。)

---

## ユーザーが行うこと (ステップ 3)
Claude が 0〜2 を終えたら、こう促して **停止する**:
> 「状態保存が完了しました。`/exit` で終了してください(`.rotate-signal` があれば ccr が自動再起動します)。」

**Claude は `/exit` しない**。ここで手を止め、ユーザーの操作を待つ。

---

## トリガー
- **手動**: ユーザーが `/rotate` 入力 / 「rotate して」「終了前に保存して」
- **判断/警告**: Stop フックに `[ROTATE:WARN]`(≥70%) / `[ROTATE:CRITICAL]`(≥90%) → Claude は
  状態保存(0〜2)を行い、ユーザーに /exit を促す。**Claude は自分で /exit しない**(自動再起動は ccr+ユーザー操作の協調)。
