# RAPTOR アップデート手順（恒久ルール）

> 2026-06-01 確定（ユーザー指示）。**RAPTOR の更新は必ず `C:\dev\tools\raptor` に対して行う。**
> C:\Users\puruy\raptor は cutover 後に削除する旧環境であり、**絶対に更新しない / 更新先にしない**。

## 0. 大前提
- **正本 (single source of truth) = `C:\dev\tools\raptor`**（2026-06-01 C: から移設）。
- `ccr` はユーザー PATH 経由で `C:\dev\tools\raptor\bin` に解決される。
- 更新作業は **D: のディレクトリで** 実行する（`git -C C:\dev\tools\raptor ...` または `cd C:\dev\tools\raptor`）。

## 1. 更新前：ローカル改変を必ずコミット（最重要）
RAPTOR は upstream (origin = gadievron/raptor) の fork で、**ローカル独自改変**を多数持つ。
これらが未コミットだと `git pull` で衝突・喪失する。更新前に commit しておくこと。

**喪失してはいけないローカル改変（D: 固有 / 環境固有）:**
- `claude-auto.mjs` — ccr ランチャ。**SCRIPT_DIR を `fileURLToPath(import.meta.url)` で解決する修正**
  （2026-05-31、`process.argv[1]` だと zx 経由で誤解決するバグの修正）+ 連結バグ対策ロジック。
- `.claude/raptor.env` — `RAPTOR_DIR` / `PATH` が `C:\dev\tools\raptor` を指す（移設で C: から書換）。
- `claude-projects.json` — プロジェクト登録・`next_plan`/`plan_ref`（FullSense 系の復元情報）。
- `.claude/settings.json` / `settings.local.json` — hook・permission 設定。
- `CLAUDE.md` — プロジェクト指示（SESSION START 等）にローカル追記あり。

```powershell
git -C C:\dev\tools\raptor status            # 未コミット改変を確認
git -C C:\dev\tools\raptor add -A
git -C C:\dev\tools\raptor commit -m "local: ccr SCRIPT_DIR fix + D: 移設 + 環境設定"
```

## 2. upstream を取り込む
```powershell
git -C C:\dev\tools\raptor fetch origin           # origin = gadievron/raptor (upstream)
git -C C:\dev\tools\raptor log --oneline HEAD..origin/main   # 差分確認
git -C C:\dev\tools\raptor merge origin/main      # または rebase。衝突は手動解決
```
- ⚠️ **`claude-auto.mjs` が衝突したら SCRIPT_DIR 修正（import.meta.url 化）を必ず残す**。
  upstream 版で上書きしない。マージ後に下記の検証を必ず実行。
- raptor は「露出回避でローカル保持」方針 = public への push はしない。fork remote
  (furuse-kazufumi/raptor) へ push する場合もユーザー承認後のみ。

## 3. 依存更新（package.json / requirements が変わった場合のみ）
```powershell
cd C:\dev\tools\raptor
npm install                  # node-pty prebuilt を壊さないこと。失敗時は移設前の node_modules を温存
```

## 4. 更新後の検証（必須）
```powershell
node --check C:\dev\tools\raptor\claude-auto.mjs                 # 構文 OK
Get-Content C:\dev\tools\raptor\.claude\raptor.env              # RAPTOR_DIR/PATH が C:\dev\tools\raptor のまま
Select-String C:\dev\tools\raptor\claude-auto.mjs 'fileURLToPath\(import\.meta\.url\)'  # SCRIPT_DIR 修正が残存
```
- 次回 `ccr` 起動で状態ファイル（`.raptor-session.json` 等）が **C:\dev\tools\raptor 直下**に書かれることを確認。

## 5. やってはいけないこと
- C:\Users\puruy\raptor を更新する（cutover 後は存在しない／旧環境）。
- `claude-auto.mjs` を upstream 版でそのまま上書きして SCRIPT_DIR 修正を失う。
- node_modules を消して再ビルド（node-pty prebuilt の再ビルド失敗リスク）。不要なら触らない。

## 関連
- `docs/CCR_SCRIPT_DIR_BUG_2026-05-31.md` — SCRIPT_DIR バグ・連結バグ・D: 移設の全経緯。
