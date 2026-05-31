# ccr 機能チェックリスト (claude-auto.mjs)

ccr (`bin/ccr.ps1` → `zx claude-auto.mjs`) の機能を「実証済 / 論理上健全 / 要注意 / 修正済」で棚卸しする。
2026-05-31 に 4 レンズ独立 adversarial 検証 (workflow `ccr-fix-verification`) を実施し、本表に反映。
**正本**: 本ファイル + `CCR_AUTO_RESTART.md` (仕様) + `CCR_SEQUENTIAL_INPUT_AUDIT.md` (機構A/B 監査)。

凡例: ✅ verified_live (実機実証) / ◹ logic_sound (論理上健全・未E2E) / ⚠ at_risk (検証で問題発見) / 🔧 fixed (本セッション修正)

---

## 0. 今回 (2026-05-31) の修正 3 点 — workflow high finding 対応

| # | 対応 finding | 修正 | 効果 | env |
|---|---|---|---|---|
| 🔧1 | win32 #1 (reset→readline が同一 tick で端末処理猶予ゼロ) | `selectProject` の `resetTerminalInput()` 後に grace sleep を挿入 | DECRST (?9001l) を端末が適用する猶予を作りメニュー化けを減らす | `RAPTOR_AUTO_RESET_GRACE_MS` (既定 60) |
| 🔧2 | exit #1/#4 (onExit 未発火でハング→Ctrl+C 脱出で端末破壊→次回化け) | PTY 終了の後始末を `cleanup()` 関数化 + `settled` ガード + **SIGINT でも cleanup を通し端末復元してから exit(130)** | ハングを Ctrl+C で抜けても raw mode / win32-input-mode を復元 → 次回化けの連鎖を断つ | — |
| 🔧3 | interference low / ユーザー要望 | `selectProject` に DEBUG hex tap 追加 (`process.stdin` 'data' を `.input-debug.log` へ追記) | 次回 `RAPTOR_AUTO_INPUT_DEBUG=1` でメニュー化けの生バイト (CSI レコード) を証拠取得可能に | `RAPTOR_AUTO_INPUT_DEBUG=1` |

> 注: これらは **次回 ccr 起動から有効**。実行中の本セッションは旧コードで動いているため、今回の `/exit` は旧経路 (ハングしたら Ctrl+C → 端末が壊れる可能性が残る) で動く。

---

## 0.5 変更トレーサビリティ台帳 (auto-commit に埋もれた変更の逆引き)

backup-hook が編集直前に `auto: …編集前` コミットを打つため、意図ある変更が git log 上で
無名コミットに分散する ([[feedback_backup_hook_breaks_git_merge]])。以下が finding → 実装 → 記録の完全対応。

| finding (workflow wg54mws8s) | 実装 (claude-auto.mjs) | 検証 | 記録先 | E2E |
|---|---|---|---|---|
| win32 high #1 (reset→readline 同一 tick) | `selectProject` の `resetTerminalInput()` 直後に `await sleep(RAPTOR_AUTO_RESET_GRACE_MS, 既定60)` | node --check OK | §0 🔧1 + コードコメント | §4-2 |
| exit high #1/#4 (onExit 未発火ハング→Ctrl+C 端末破壊) | `runClaudeWithPty` 終了待ちを `cleanup()` 関数化 + `settled` ガード + `process.on('SIGINT')` → `exit(130)` | node --check OK | §0 🔧2 + コードコメント | §4-1 |
| interference low / ユーザー要望 | `selectProject` の DEBUG `menuTap` (process.stdin 'data' → `.input-debug.log`) | node --check OK | §0 🔧3 + コードコメント | §4-2 |
| memory high (next_plan mojibake) | **実装せず — 誤検出と確定** | `py` U+FFFD=0 | §1 記憶引き継ぎ行 | — |

- **コミット**: 意図コミット `e18dafdf` (メッセージが全体を統括)。実コード差分は backup-hook の
  `a2bccb3c` / `0c4a661f` / `73a66323` / `47e47dcd` (`auto: …編集前`) に分散。HEAD = working tree に全反映済 (clean)。
- **逆引き**: `git log -p --follow claude-auto.mjs` で reset grace / SIGINT cleanup / menuTap の diff を辿れる。
- **根本対策 (要承認・未実施)**: backup-hook の auto-commit メッセージ改善 or 意図コミット後の squash で git log 粒度を回復。

---

## 1. 機能別チェックリスト

### 起動 / PTY
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| node-pty (@homebridge/...prebuilt) で claude を PTY 起動・対話引き渡し | ✅ | 本セッションが現にこの経路で稼働 | `Get-Process node,conhost` で PTY ホスト確認 |
| TUI 準備完了の検出 (FIRST_DELAY_MS=2500 固定・probe 無し) | ⚠ HIGH | 遅い PC / 初回オンボーディングが 2.5s 超で Esc/本文ドロップ → effort 無音失敗 | `RAPTOR_AUTO_PTY_FIRST_DELAY_MS` を 1000/2500/4000 で振り effort 適用率比較 |

### effort 投入 (機構A)
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| `/effort ultracode` を単独 submission 投入し連結バグ回避 | ✅ | 本セッション冒頭で連結なく適用済 | 初回+ウォーム起動で `Invalid argument: ultracode` が出ないこと |
| slash の Enter 2 回送信 (メニュー吸収の保険) | ⚠ HIGH | effort 確認ピッカーを開く版だと 2 回目 \r が既定誤確定しうる | effort 選択 UI を持つ版で誤確定しないか |
| Enter 正規化 (CRLF/LF→CR, normalizeEnter) | ⚠ MED | bracketed paste 内 LF も無条件 CR 化。「壊れない」は未検証 | `RAPTOR_AUTO_INPUT_DEBUG=1` で多行ペースト hex を `RAPTOR_AUTO_INPUT_RAW=1` と比較 |

### 記憶引き継ぎ (rotate)
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| plan_ref (claude-projects.json→memory) + SESSION_SUMMARY から復元 | ✅ | 本セッションで llcore ③ を plan_ref 経由で実機復元 | ccr で起動し SESSION START が `Next plan` を宣言し自律継続するか |
| 引き継ぎ先アドレッシングの一貫性 | ⚠ HIGH | **実機で乖離**: `.raptor-session.json`=fullsense vs `RAPTOR_CALLER_DIR`=llcore。rotate は SESSION_CFG を消さない。乖離下では戦略を A に書き次回が B を読む | runSession 先頭で両者一致を assert / 現状不一致を再現 |
| 戦略正本 next_plan の健全性 (UTF-8) | ✅ (agent の mojibake は誤検出と確定) | **検証済 2026-05-31**: `py -3.11` 実測で U+FFFD(破損)=0、U+25A0(■)×2 は見出し装飾、「次回最優先」も正常コードポイント。agent が見た `repr` の化けは PowerShell cp932 の表示問題でファイルは健全。CLAUDE.md「外部 AI finding 鵜呑み禁止」適用例 | `py -3.11 -c "...s.count(chr(0xfffd))..."` で 0 を確認済 |
| next_plan の自動保守 | ⚠ MED | これを触る hook 皆無。保存は手作業 rotate step0.5 に 100% 依存 | step0.5 省略時に陳腐な next_plan が流れること |
| auto-summary の手書き SESSION_SUMMARY 上書き保護 | ⚠ MED | auto-summary は手書きを git 状態で毎ターン上書き (自認)。今回残ったのは env が別 proj を指した偶然 | env と summaryFile 一致下で手書き→Stop 発火→上書きされるか |
| 復元プロンプト投入 (PTY submit) | ◹ | submit 失敗/PTY 不在で欠落しうるが SESSION START 自体は走る | node-pty 有/無で自律継続するか |

### 終了 / シェル復帰
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| `/exit` → onExit cleanup → process.exit(0) で pwsh 復帰 | ◹→🔧 | 正常系は健全。onExit 未発火 (ConPTY drain #375/#1810) でハングしうる。**🔧 SIGINT cleanup で Ctrl+C 脱出時の端末破壊を防止** | `/exit` 後 pwsh 即復帰 + `Get-Process` 残留 0 / 長出力中 `/exit` でハング有無 |
| `/rotate` → kill → onExit → 次セッション (continue) | ◹ | 概ね成立。fs.watch 多重発火で kill 多重の余地 (実害小) | `.rotate-signal` 検知ログが 1 回 rotate で複数出ないか |
| 長時間 /rotate ループのリソース | ⚠ MED | kill ごとに conpty_console_list_agent fork + Worker/timer 残置、累積しうる | 10-20 回連続 rotate で Thread/Handle 単調増加しないか |
| onExit 未発火ハングの自動救済 | ⚠ (未修正) | watchdog 未実装。**回避策=ハングしたら新 WT タブで ccr 起動 (下記§3)** | 長出力中 /exit を複数回試行 |

### メニュー入力 (selectProject)
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| win32-input-mode 残留の self-heal (起動時 ?9001l) | ⚠→🔧 | byte 正確・common case で直る。**🔧 reset 後 grace sleep で適用猶予を確保**。ただし Microsoft「確実な無効化手段なし」+ ConPTY 再要求 (#6859) で best-effort | win32-input-mode を強制 ON にして起動→メニュー化け有無 (slow/immediate 入力) |
| メニュー化け時のフェイルセーフ | ✅ | 60 秒無入力で最新 proj 自動選択。「0 で起動」もこの保険 | 化けた状態で 60 秒放置→自動選択されるか |
| console mode 腐敗 (Issue #19674) への耐性 | ⚠ MED | ?9001l では直らない別系統。要 SetConsoleMode (node 直接 binding なし) | 数時間 TUI 後に再起動しメニュー化け有無 |

### フォールバック (node-pty 不在)
| 機能 | status | 備考 / リスク | E2E 手順 |
|---|---|---|---|
| 通常 spawn フォールバック | ◹ | 対話は起動するが **initialCommands 全欠落 = effort/自律継続が黙ってデグレード** (警告 1 行) | `RAPTOR_AUTO_PTY_DISABLE=1` で effort 欠落+pwsh 復帰確認 |
| fallback /rotate の子プロセス掃除 | ⚠ LOW | child.kill('SIGTERM') は Windows でツリー非伝播。MCP 孫が孤立しうる | `RAPTOR_AUTO_PTY_DISABLE=1; ccr`→/rotate で MCP 残留確認 |

---

## 2. 未対応の at_risk (優先度順) — 次の改善候補

1. **HIGH 記憶アドレッシング分裂** (`.raptor-session.json` vs `RAPTOR_CALLER_DIR`): runSession 先頭で一致を assert/是正。乖離下で記憶が別 proj に飛ぶ。
2. **HIGH next_plan mojibake**: cp932 console での Edit 書込が U+25A0 を再注入。UTF-8 lint + plan_ref 必須化。
3. **HIGH FIRST_DELAY 固定**: readiness probe (TUI のプロンプト検出) へ置換。遅環境で effort 無音失敗。
4. **HIGH slash Enter 2 回**: effort ピッカー版での誤確定検証 → 必要なら条件付き送信。
5. **MED onExit 未発火ハングの watchdog**: PTY 子 pid 監視で onExit 未発火時に強制 cleanup (誤発火回避に子終了検知が前提)。
6. **MED normalizeEnter の paste 範囲除外**: bracketed paste 区間は変換しない。

---

## 3. ハング・化け時のユーザー回避策 (即効)

- **メニューが `;13;1;0;1_` と化ける**: ① そのまま 60 秒待てば最新 proj 自動選択 ② Ctrl+C して **新しい Windows Terminal タブ**で `ccr` (クリーン端末=残留なし、最も確実) ③ pwsh で手動 RIS: `[Console]::Write([char]27 + 'c')`。
- **`/exit` 後 pwsh に戻らずハング**: 5-10 秒待って戻らなければ Ctrl+C。**次回起動からは SIGINT cleanup が端末を復元する**ので化けが連鎖しない (本セッションは旧コードなので化けたら新タブで)。
- **effort が ultracode にならない**: 遅い起動が原因なら `$env:RAPTOR_AUTO_PTY_FIRST_DELAY_MS=4000; ccr`。node-pty 不在なら raptor で `npm install`。

---

## 4. 次回 ccr 起動時の E2E 優先 3 項目

1. **/exit → pwsh 復帰**: `/exit` で即座に pwsh に戻るか。長出力直後の `/exit` でもハングしないか数回試行。戻ったら `Get-Process node,claude,conhost` で残留 0 を確認。
2. **メニュー入力**: `$env:RAPTOR_AUTO_INPUT_DEBUG=1; ccr` で起動し 0 以外を選択 → Enter が通るか。化けたら `.input-debug.log` に `[selectProject]` 行の hex (CSI レコード) が残る (🔧 新 tap)。
3. **記憶引き継ぎ**: 起動後 SESSION START が plan_ref を読み `Next plan` を宣言して自律継続するか。`.raptor-session.json` の projectPath が実作業プロジェクトと一致するか目視。

---

## 更新規律

`claude-auto.mjs` / ccr フローを変更したら本ファイル + `CCR_AUTO_RESTART.md` + `D:/projects/SOFTWARE_UPDATE_DOC_CHECKLIST.md` の ccr 行を更新。検証は `ccr-fix-verification` workflow を再実行。
