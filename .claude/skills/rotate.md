# /rotate — セッション終了前の状態保存

コンテキスト上限に近づいた、または区切りで終了したいとき、**終了する前に**作業状態を
`claude-projects.json` の `next_plan`(=plan_ref、次回復元の正本)に書き出す手順。
`/wrap-up` と実質同じ状態保存を行い、違いは **再起動を想定する**点のみ(下表)。

> **このファイルは手順書**であり `Skill(rotate)` では呼べない(登録スキルでない →
> `Unknown skill: rotate`)。ユーザーが `/rotate` と打ったら **Read して以下を手動で実行**する
> ([[feedback_rotate_is_markdown_not_skill]])。
>
> **役割分担**: Claude は **自力で `/exit`・再起動・再ログインできない**([[project_ccr_automation_limits]])。
> rotate は「**Claude が状態を保存する終了前手順**」であり、実際の `/exit`・再起動はユーザーが行う。
> Claude はステップ3を自分でやろうとしない。

---

## Claude が行う手順 (ステップ 0〜2 のみ)

### ステップ 0 — プロジェクトパスを確認
Read で `.raptor-session.json` を読み `projectPath` を取得(無ければ RAPTOR dir を対象)。
`summaryFile`(SESSION_SUMMARY.md)は **参照するが Write しない**(下記)。

> **SESSION_SUMMARY.md は書かない。** Stop フック(`libexec/raptor-auto-summary`)が毎ターン git
> 状態で自動生成・上書きするため、手動 Write は必ず `File has been modified since read` エラーになり、
> 成功しても次ターンで消える(旧 rotate はこのフック導入前の名残で SESSION_SUMMARY を書いていた)。
> 次回復元の正本は **next_plan(plan_ref)**+ `docs/STATUS.md`([[feedback_rotate_is_markdown_not_skill]])。

### ステップ 1 — claude-projects.json の next_plan を JSON-safe に更新(肥大化させない)
1. RAPTOR dir の `claude-projects.json` を Read → projectPath dirname に一致するエントリ
   (傘下なら親 project = 例 llcore→fullsense)を特定。
2. **next_plan 冒頭の「現在の最優先」ブロックだけを 1-3 行で置換**(append 禁止=肥大化防止
   [[feedback_fullsense_feedback_smart]])。完了 commit hash + 次アクション候補を簡潔に。旧履歴は
   「---(旧計画↓)---」以降に **必要最小限**だけ残す。**rich 詳細は STATUS.md と worklog handoff
   (ステップ2)に逃がし、next_plan は短い pointer に保つ**。
3. **生ダブルクォート `"` を文字列値に入れない**(JSON が壊れ SESSION START が読めなくなる。実例
   2026-08-15: `halcon=""` で `Expecting ',' delimiter`)。`空文字`・「」・'' で代替。
4. Edit 後に **必ず検証**:
   ```
   py -3.11 -c "import json; json.load(open('claude-projects.json',encoding='utf-8')); print('valid')"
   ```
   エラーが出たら生 `"` を除去して再検証してから次へ。

### ステップ 2 — (推奨) bounded handoff を work-graph に生成 + (任意) .rotate-signal
**(a) bounded handoff**(next_plan を短く保つ受け皿 = 膨大化の本命対策):
```
PYTHONUTF8=1 py -3.11 libexec/raptor-worklog compact --project <project> --show
```
→ `out/worklog/handoff-<project>.md`(bounded・local NN 要約)。work-graph が空なら先に
`raptor-worklog seed`。詳細 = [[reference_workgraph_multimodel_ops]]。

**(b) .rotate-signal**: **ccr 経由起動のときのみ**作る(ccr は現在廃止=通常は省略、[[reference_launch_rap_picker]])。
作る場合は RAPTOR dir の `.rotate-signal` に `rotate` と書く(Write 失敗時 `Bash(echo rotate > .rotate-signal)`)。
**必ず next_plan 更新(ステップ1)を終えてから作る。**

---

## ユーザーが行うこと (ステップ 3)
Claude が 0〜2 を終えたら、こう促して **停止する**:
> 「状態保存が完了しました。`/exit` で終了してください(`.rotate-signal` があれば ccr が自動再起動します)。」

**Claude は `/exit` しない**。ここで手を止め、ユーザーの操作を待つ。

---

## トリガー
- **手動**: ユーザーが `/rotate` 入力 / 「rotate して」「終了前に保存して」(Read して実行、Skill 呼び出し不可)。
- **判断/警告**: Stop フックに `[ROTATE:WARN]`(≥70%)/`[ROTATE:CRITICAL]`(≥90%)→ 状態保存(0〜2)を行い
  ユーザーに /exit を促す。**Claude は自分で /exit しない**。

## 注意事項(2026-08-15 の失敗を仕様化)
- **`Skill(rotate)`/`Skill(wrap-up)`/`Skill(switch)` を呼ばない**(手順書=Read して従う)。
- **`docs/SESSION_SUMMARY.md` を Write しない**(自動上書き=エラー&無駄)。
- **claude-projects.json は編集後 必ず `json.load` で検証**(生 `"` で壊さない)。
- next_plan は **置換で短く**(rich 詳細は STATUS.md / `raptor-worklog compact` へ逃がす)。
