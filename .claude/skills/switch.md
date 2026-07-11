# /switch — セッション中のプロジェクト切り替え(記録を追従させる)

同一 ccr セッション中に別プロジェクトへ作業を移すとき、**離脱プロジェクトの継続を記録し、
アクティブマーカーを移す**手順。これをやると Stop hook の記録(`docs/SESSION_SUMMARY.md`)と
次回 SESSION START の復元先が、切り替え先プロジェクトへ**自動追従**する。

> **背景(2026-07-11 に解消したギャップ)**: Stop hook `raptor-auto-summary` /
> `raptor-next-session-update` は共有 resolver `libexec/_raptor_active.py` 経由で、
> 可変マーカー `.raptor-session.json`(projectPath)を env `RAPTOR_CALLER_DIR` より優先で読む。
> `/switch` が `.raptor-session.json` を書き換えると以後の記録が追従する。
> **`/rotate` との違い**: `/rotate` は終了前保存(ユーザーが /exit)。`/switch` は**セッションを続けたまま**
> 別プロジェクトへ移る(exit しない)。両者とも離脱プロジェクトの next_plan を書くのは共通。

---

## トリガー
- ユーザーが `/switch <project>` 入力 / 「<project> に切り替えて」「別プロジェクトに移る」
- セッション中に作業対象が現アクティブと別のプロジェクトへ移ると判断したとき(移る前に実行)

---

## Claude が行う手順

### ステップ 0 — 現在(離脱)プロジェクトを確認
Read で RAPTOR dir(`D:/tools/raptor`)の `.raptor-session.json` を読み、`projectName` /
`projectPath` を取得(= これから離れるプロジェクト)。切り替え先 `<target>` を確定
(`D:/projects/<dirname>` の dirname か絶対パス)。

### ステップ 1 — 離脱プロジェクトの next_plan をフラッシュ(継続記録)
RAPTOR dir の `claude-projects.json` を Read → **離脱プロジェクト**(projectPath の dirname に対応する
エントリ)の `next_plan` 冒頭を、本セッションでそのプロジェクトに対して行った完了事項+次の優先作業に
整合するよう **1-3 行で置換**(append でなく置換=肥大化防止 [[feedback_fullsense_feedback_smart]]。
完了 commit hash / 次アクション候補を含める)。Edit で書き換え。
> これを怠ると「切り替え元プロジェクトの続き」が失われる(= 今回直したギャップの本体)。

### ステップ 2 — アクティブマーカーを切り替え
Bash で機械的再ポイントを実行(fail-closed):
```
py -3.11 D:/tools/raptor/libexec/raptor-switch <target>
```
- exit 0 = 成功(`.raptor-session.json` が `<target>` へ更新、以後の Stop hook 記録が追従)。
- **非 0 = 対象が無効** → STOP して報告(勝手に別対象を推測しない)。出力の `next_plan` / `plan_ref` を控える。

### ステップ 3 — 切り替え先の継続をロードして着手
SESSION START と同じ導線で切り替え先を復元:
- `claude-projects.json` の `<target>` エントリの `plan_ref`(`memory:<name>` or `docs/<file>`)を Read。
- `<target>` の `docs/SESSION_SUMMARY.md` があれば要約。
- 「**Switched to <target>:**」で 1 行、続きとして何を進めるか宣言し **着手**。

---

## 注意
- `/switch` は **exit しない**(セッション継続)。危険操作(push/削除)は通常規約どおり(constraints 外は行わない)。
- マーカーは単一(`.raptor-session.json`)。`.rotate-signal` は書かない(再起動しないため)。
- worktree(例 `D:/projects/onocollo-complete`)も dirname/絶対パスで指定可。
