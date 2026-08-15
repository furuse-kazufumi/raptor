# /wrap-up — セッション終了 (next_plan 更新 + bounded handoff 付き exit)

`/rotate` と同じ状態保存を行ってから **そのまま `/exit`**(再起動シグナルを作らない)。
`/rotate` との違いは再起動しない点だけ。

> **このファイルは手順書**であり `Skill(wrap-up)` では呼べない(登録スキルでない →
> `Unknown skill`)。ユーザーが `/wrap-up` と打ったら **Read して以下を手動で実行**する
> ([[feedback_rotate_is_markdown_not_skill]])。

---

## 違い (rotate / wrap-up / clear / exit)

| コマンド | next_plan 更新 | bounded handoff | 再起動 | 用途 |
|---|---|---|---|---|
| `/rotate`  | ✓ | ✓ (任意) | ✓ (ccr=現在廃止ゆえ手動) | context リフレッシュ + 続行 |
| **`/wrap-up`** | ✓ | ✓ (任意) | ✗ (純粋 exit) | 作業終了 (続きは別日に) |
| `/exit`    | ✗ | ✗ | ✗ | 純 exit (state 残さず) |
| `/clear`   | ✗ | ✗ | ✗ (プロセス維持) | 話題切替 |

> **SESSION_SUMMARY.md は書かない。** Stop フック(`libexec/raptor-auto-summary`)が毎ターン
> git 状態で自動生成・上書きするため、手動 Write は必ず `File has been modified since read`
> エラーになり、成功しても次ターンで消える。次回復元の正本は **`claude-projects.json` の
> next_plan(=plan_ref)**+ `docs/STATUS.md`([[feedback_rotate_is_markdown_not_skill]])。

---

## 実行手順 (この順番で必ず)

### ステップ 0 — プロジェクトパスを確認
Read で `.raptor-session.json` を読み `projectPath` を取得(無ければ手動確認)。
`summaryFile` は **参照するが Write しない**(上記ボックス)。

### ステップ 1 — claude-projects.json の next_plan を JSON-safe に更新(肥大化させない)
1. RAPTOR dir の `claude-projects.json` を Read → projectPath dirname に一致するエントリ
   (傘下なら親 project = 例 llcore→fullsense)を特定。
2. **next_plan 冒頭の「現在の最優先」ブロックだけを 1-3 行で置換**(append 禁止=肥大化防止
   [[feedback_fullsense_feedback_smart]])。完了 commit hash + 次アクション候補を簡潔に。旧履歴は
   「---(旧計画↓)---」以降に **必要最小限**だけ残す。**rich 詳細は STATUS.md と worklog handoff
   (ステップ2)に逃がし、next_plan は短い pointer に保つ**(next_plan を作業ログ本体にしない)。
3. **生ダブルクォート `"` を文字列値に入れない**(JSON が壊れ SESSION START が読めなくなる。
   実例 2026-08-15: `halcon=""` で `Expecting ',' delimiter`)。`空文字`・「」・'' で代替。
4. Edit 後に **必ず検証**:
   ```
   py -3.11 -c "import json; json.load(open('claude-projects.json',encoding='utf-8')); print('valid')"
   ```
   エラーが出たら生 `"` を除去して再検証してから次へ進む。

### ステップ 2 — (推奨) bounded handoff を work-graph に生成(next_plan を短く保つ受け皿)
rich な進捗は next_plan に積まず、固定容量 handoff に委ねる(=膨大化の本命対策):
```
PYTHONUTF8=1 py -3.11 libexec/raptor-worklog compact --project <project> --show
```
→ `out/worklog/handoff-<project>.md`(bounded・local NN 要約)。`corpus --project <project>` で
navigable INDEX.md も生成可。work-graph が空なら先に `raptor-worklog seed`(claude-projects.json
から task を起こす)。詳細 = `libexec/raptor-worklog --help` / [[reference_workgraph_multimodel_ops]]。

### ステップ 3 — /exit を促す(Claude は自力で exit しない)
状態保存(0〜2)完了後、こう促して **停止する**:
> 「状態保存が完了しました。`/exit` で終了してください。」

**Claude は `/exit`・再起動しない**([[project_ccr_automation_limits]])。ここで手を止めユーザー操作を待つ。
`.rotate-signal` は作らない(=自動再起動しない。純粋 exit)。

---

## トリガー条件
1. **手動**: ユーザーが `/wrap-up` と入力(このファイルを Read して実行。Skill 呼び出し不可)。
2. **判断**: 「もう終わる」「今日はここまで」等の意思表示 → 確認 1 回挟んで本フロー。

## 注意事項(2026-08-15 の失敗を仕様化)
- **`Skill(wrap-up)`/`Skill(rotate)`/`Skill(switch)` を呼ばない**(手順書=Read して従う。Skill レジストリに無い)。
- **`docs/SESSION_SUMMARY.md` を Write しない**(自動上書き=エラー&無駄。plan_ref を正本に)。
- **claude-projects.json は編集後 必ず `json.load` で検証**(生 `"` で壊さない)。
- next_plan は **置換で短く**(rich 詳細は STATUS.md / `raptor-worklog compact` へ逃がす)。
- Write/Edit が失敗したら内容を出力しユーザーに手動保存を依頼。
