# ccr 自動ローテーター / effort 設定 / シーケンシャル投入 — 仕様

`claude-auto.mjs` は ccr (Claude Code 連続運用ラッパ) の中核となる **zx 製セッション自動ローテーター**である。
`D:\projects\` を自動スキャンしてプロジェクトを選ばせ、Claude Code を **node-pty 上で**起動し、
`/effort ultracode` などの初期コマンド列を**シーケンシャルに投入**してから対話を実端末へ引き渡す。
`/rotate` のたびに新セッションへ自動継続させる。

- 対象ファイル: `claude-auto.mjs` (raptor 直下、`#!/usr/bin/env zx`)
- 起動エントリ: `bin/ccr.ps1` (ExternalScript) → `zx claude-auto.mjs`
- 依存: `@homebridge/node-pty-prebuilt-multiarch` (prebuilt、native ビルド不要。`package.json` に宣言、`node_modules` は gitignore)
- 関連コミット: `ddf36cba` (effort 注入の初版・連結バグ) → 本仕様で **node-pty シーケンシャル投入**へ修正
- 関連 memory: `project_ccr_auto_resume`, `project_ccr_memory_replay_fix`, `project_ccr_effort_sequential_fix`

---

## 1. 全体フロー

```
ccr (bin/ccr.ps1)
  └─ zx claude-auto.mjs
       ├─ discoverProjects()  D:\projects\ をスキャン (claude-projects.json で名前/説明上書き)
       ├─ selectProject()     メニュー + 60 秒無入力で最新 mtime を自動選択
       └─ while(true) runSession()  ← メインループ
            ├─ writeSessionConfig()      .raptor-session.json を書く
            ├─ buildInitialCommands()    [/effort ultracode, (preCommands…), 復元プロンプト]
            ├─ runClaudeWithPty()        node-pty で claude 起動 → 初期コマンド列を順次 submit → 対話引き渡し
            └─ child 終了後:
                 ├─ .rotate-signal あり → SESSION_SUMMARY をアーカイブ → 3 秒後に次セッション
                 └─ .rotate-signal なし → 正常終了、.raptor-session.json 削除して break
```

---

## 2. シーケンシャル投入 (`runClaudeWithPty`)

擬似端末 (PTY) 上で claude を起動し、**各コマンドを個別 submission として順番に流し込む**。

```
node-pty.spawn(claude, ['--dangerously-skip-permissions'])
  ├─ PTY出力 → process.stdout                (画面転送)
  ├─ process.stdin(raw) → PTY                (キー転送; ユーザーはそのまま対話可能)
  ├─ process.stdout.resize → PTY.resize      (リサイズ追従)
  ├─ .rotate-signal 監視 → PTY.kill()
  └─ submitSequence(): 起動完了を待ち (gateFirst)、各コマンドを (2026-05-31 真因修正後)
        Esc×2 (メニュー閉→全クリア) → Ctrl+U (行クリア) → write(cmd)
        → (slash のみ) Esc 1 回 (引数メニュー閉) → write('\r') 単一 Enter
        各操作の待ちを出力静止で gating しつつ繰り返す (gateType/gateSeq、2026-06-01)
```

`/effort ultracode` は **単独 submission** になるため、後続本文を引数化してしまう連結バグは構造的に起きない。
将来 `/workflow ...` など任意のスラッシュコマンド列も同じ仕組みで順次投入できる (`RAPTOR_AUTO_PRECOMMANDS`)。

### タイミング: quiescence gating (2026-06-01, 既定)

各待ち (起動 / キー間 / submission 間) は **既定で固定 sleep ではなく PTY 出力の静止検知**で行う。
固定 2.5s では遅い PC / 初回オンボーディングで TUI 起動前に Esc/本文を撃ち `/effort` が無音失敗
していた (`CCR_FUNCTIONAL_CHECKLIST.md` §2 HIGH #3)。

- `waitQuiet(quietMs, maxMs, minMs, requireData)`: PTY 出力が `quietMs` 静止するまで待つ。
  `minMs` 未満では返さず (床)、`maxMs` で必ず打ち切る (ハードキャップ = spinner 等で出力が
  止まらなくても有界・**旧固定 sleep より長くハングしない**)。
- `gateFirst` (起動) = `requireData=true`: 「一度も出力を見ていない (`sawData=false`)」状態を
  静止と誤認せず **first-byte 前の早撃ちを防ぐ**。TUI が本当に無音でも `maxMs` で進む。
- `gateType` (キー間) / `gateSeq` (submission 間) = `minMs` 床で write→redraw 開始を待ってから
  静止を測る (per-key race 対策)。
- `RAPTOR_AUTO_QUIESCE_DISABLE=1` で **旧固定 sleep に退避** (回帰 A/B)。全数値 knob は `envNum` で
  sanitize (未設定/空/NaN/負 → 既定。NaN が `maxMs` に入るとキャップ無効化で spin するため必須)。
- 4 レンズ adversarial review (workflow `wytuxciea`, 2026-06-01) の high/med findings 反映済
  (起動早撃ち=`sawData` / per-key race=`*_MIN_MS` 床 / env NaN spin=`envNum`)。**実機 E2E 未確認** (台帳 §4 item 5)。

### 連結バグ "再々発" の真因修正 (2026-05-31 実機 E2E)

初版 (ddf36cba) の positional 連結を node-pty 分割で直し、さらに「slash は Enter×2」の
初回対策を入れたが、**実機 (llcore) で連結が再々発**: `/effort ultracode<改行>セッション再開…`
→ `Invalid argument: ultracode` で自律継続喪失。

**真因**: `/effort` は引数候補 (low/…/ultracode/auto) を持つため**引数メニュー**が開く。初回対策の
**Enter×2** は、メニューが 1 回目を吸収した後、2 回目が「**改行挿入**」となり入力欄を**複数行化**。
次コマンド前の Ctrl+U は**行単位**クリアのため複数行残骸 (`/effort ultracode\n`) を消せず、
復元プロンプト本文がその後ろへ連結する。**= 初回対策の double-Enter 自体が連結の主因**。

**真因対策** (`submitSequence`): (1) 各コマンド前を **Esc×2 + Ctrl+U** に強化 (複数行残骸も除去)、
(2) slash は本文後 **Esc 1 回で引数メニューだけ閉じてから単一 Enter** (double-Enter 廃止)、
(3) `submitSequence` に debug ログ (`[submitSequence]` 行) を追加。退避 `RAPTOR_AUTO_SLASH_DOUBLE_ENTER=1`。
graceful degradation: 万一 (2) の Esc がテキストごと消しても続く単一 Enter は空欄 no-op で連結せず、
最悪 effort 不適用で済む (フリーズしない)。**実機 E2E 未確認** (台帳 = `CCR_FUNCTIONAL_CHECKLIST.md` §0.5 / §4-4)。

### 修正した連結バグ — 初版 positional 連結 (2026-05-31)

初版 (`ddf36cba`) は initial prompt の **先頭に連結**していた:

```js
args.push('/effort ultracode' + '\n\n' + 'セッション再開。…')   // ← バグ
```

Claude Code は **単一 positional プロンプトを 1 メッセージ**として扱う。先頭が `/effort` だと
スラッシュパーサが**後続本文全体を引数**として受け取り、以下になる:

```
Invalid argument: ultracode

セッション再開。CLAUDE.md SESSION START を実行し...
. Valid options are: low, medium, high, xhigh, max, ultracode, auto
```

### なぜフラグでは直せなかったか (実機検証)

`--effort` **フラグ**は ultracode を受け付けない (実機確認):

| コマンド | 結果 |
|---|---|
| `claude --effort ultracode -p "hi"` | `error: argument 'ultracode' is invalid. It must be one of: low, medium, high, xhigh, max` (exit 1) |
| `claude --effort max -p "hi"` | 受理 |

`ultracode` はスラッシュ `/effort` のみ valid。フラグ不可・スラッシュは単一メッセージ占有 →
**両立には複数メッセージのシーケンシャル投入 (= node-pty) が必須**。

---

## 3. 初期コマンド列 (`buildInitialCommands`)

順序: `/effort <level>` → (任意 `RAPTOR_AUTO_PRECOMMANDS`) → **再開トリガー (1 行)**。

**設計方針 (2026-05-31 ユーザー指示)**: ccr 側の責務は「**ultracode を効かせる**」+
「**自律継続の合図を送る**」までに絞る。**前回作業の復元手順・参照先パスは CLAUDE.md の
SESSION START 節が唯一の正本**で、ccr は復元ロジックを持たない。よって再開トリガーは旧来の
長い復元プロンプト (「確認するな」「選択肢を出すな」等) ではなく
`セッション再開。CLAUDE.md の SESSION START 手順に従って…自律継続` の **1 行**だけにする
(文言重複の排除 + 連結リスク低減)。

- 再開トリガーは `SESSION_SUMMARY.md` がある時のみ付与 (ユーザーがトリガ文を打たず SESSION START → 自律継続)。
- `SESSION_SUMMARY.md` が無い起動では `/effort ultracode` のみ投入。
- `RAPTOR_AUTO_RESUME_PROMPT` で再開トリガーを上書き (`""` で無効化 = effort のみ投入)。
- 参照先パス (正本 = CLAUDE.md SESSION START 側): `.raptor-session.json` / `RAPTOR_CALLER_DIR` /
  raptor dir の `claude-projects.json` の `plan_ref` / 各プロジェクト `docs/SESSION_SUMMARY.md`。
- **確定 (2026-05-31, claude-code-guide agent が公式 docs で確認)**: slash コマンド
  (`/effort` `/model` `/config` 等のビルトイン設定系) は **ローカル処理のみで Claude の
  アシスタントターンを起こさない**。よって `/effort ultracode` を slash 単独で投入しても
  CLAUDE.md の SESSION START 指示 (= アシスタントへのプロンプト) は走らない。**SESSION START を
  発火させる「最小テキスト 1 つ」が必須**で、これが再開トリガーの存在意義。= 現行設計
  (`/effort ultracode` + 1 行トリガーの 2 投入) が必要十分であり、トリガーをゼロにはできない。
  - 出典: code.claude.com/docs/en/commands, how-claude-code-works (agentic loop), agent-sdk/slash-commands。
  - 含意: 投入が最低 2 つである以上、連結バグ対策 (Esc×2+Ctrl+U / 単一 Enter) は引き続き要。
    なお `.startup-output` を作る `source:startup` の **SessionStart hook** と、CLAUDE.md の
    **SESSION START 指示** は別物 (hook はセッション初期化で自動実行、指示はターンが必要)。

---

## 4. 設定 (環境変数)

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `RAPTOR_AUTO_EFFORT_LEVEL` | `ultracode` | 投入する effort レベル。空文字 `""` で effort 投入を無効化 |
| `RAPTOR_AUTO_PRECOMMANDS` | (なし) | `/effort` と復元の間に挟む追加コマンド。`||` 区切り (例 `/workflow foo||コメント`) |
| `RAPTOR_AUTO_PTY_FIRST_DELAY_MS` | `2500` | TUI 起動待ち (**quiescence 無効時のみ**。既定は出力静止で判定) |
| `RAPTOR_AUTO_PTY_TYPE_DELAY_MS` | `350` | キー反映待ち (**quiescence 無効時のみ**) |
| `RAPTOR_AUTO_SEQ_DELAY_MS` | `1500` | submission 間隔 (**quiescence 無効時のみ**) |
| `RAPTOR_AUTO_QUIESCE_DISABLE` | (なし) | `1` で quiescence (出力静止検知) を無効化し上記固定 sleep に退避 (回帰 A/B) |
| `RAPTOR_AUTO_QUIESCE_POLL_MS` | `25` | 静止検知のポーリング解像度 (ms) |
| `RAPTOR_AUTO_STARTUP_MIN_MS` / `_QUIET_MS` / `_MAX_MS` | `1500` / `700` / `10000` | 起動 gate: 最低待ち床 / 静止判定 / ハードキャップ。`sawData` で first-byte 前早撃ち防止 |
| `RAPTOR_AUTO_KEY_MIN_MS` / `_QUIET_MS` / `_MAX_MS` | `80` / `180` / `1500` | キー間 gate: 同上 |
| `RAPTOR_AUTO_SEQ_MIN_MS` / `_QUIET_MS` / `_MAX_MS` | `150` / `400` / `3500` | submission 間 gate: 同上 |
| `RAPTOR_AUTO_PTY_DISABLE` | (なし) | `1` で PTY を使わず通常 spawn (初期コマンド投入なし) |
| `RAPTOR_AUTO_SLASH_DOUBLE_ENTER` | (なし) | `1` で slash の旧 double-Enter 挙動へ退避 (連結バグ A/B 切り分け用。§6 追補2) |
| `RAPTOR_AUTO_INPUT_RAW` | (なし) | `1` で Enter 正規化 (CRLF/LF→CR 畳み込み) を無効化 |
| `RAPTOR_AUTO_INPUT_DEBUG` | (なし) | `1` で入力バイトを `.input-debug.log` に hex 記録 (`selectProject` / `onInput` / `submitSequence` の 3 経路) |
| `RAPTOR_AUTO_RESET_GRACE_MS` | `60` | selectProject の端末リセット後 readline 生成までの猶予 (ms) |
| `RAPTOR_CALLER_DIR` | (runSession 設定) | 選択プロジェクトのパス。CLAUDE.md SESSION START が参照 |

---

## 5. ファイル

| ファイル | 役割 |
|---|---|
| `.rotate-signal` | `/rotate` が作成。watch で検知すると PTY (claude) を終了。次ループで消費 |
| `.raptor-session.json` | runSession が起動時に書く (projectName/path/docs...)。CLAUDE.md SESSION START が読む |
| `docs/SESSION_SUMMARY.md` | `/rotate` が書く引き継ぎ。ローテート時に `SESSION_SUMMARY_<date>.md` へアーカイブ |
| `claude-projects.json` | プロジェクト名/説明の上書き + per-project `next_plan`/`plan_ref` |
| `package.json` / `package-lock.json` | node-pty 依存宣言。`node_modules` は gitignore 済 |

---

## 6. 既知の制約 (honest disclosure)

- node-pty は native モジュール。本環境 (node v24 / ABI 137) では `@homebridge/node-pty-prebuilt-multiarch@0.13.0`
  の prebuilt が動作する (MSVC 不要)。node を上げて prebuilt が無くなった場合は別 fork / build tools が要る。
- `runClaudeWithPty` は **node-pty 不在時に通常 spawn へフォールバック**する (対話は可能だが初期コマンド投入なし)。
  その際は「`npm install` を実行」と警告を出す。
- submit のタイミング (`FIRST_DELAY`/`TYPE_DELAY`/`SEQ_DELAY`) は TUI 起動速度に依存。
  スラッシュ補完が Enter を奪う等の事象が出たら env で調整する。**次回 実 ccr 起動で要動作確認**。
- **`/exit` 後に PowerShell プロンプトが返らない問題 (2026-05-31 修正)**: node-pty は
  Windows/ConPTY で「子シェルが自分で終了 (= `/exit`) すると `onExit` は発火するのに
  親プロセス (winpty-agent/conhost) と libuv ハンドルが残り node プロセスが終了しない」
  既知バグがある (microsoft/node-pty [#333](https://github.com/microsoft/node-pty/issues/333) /
  [#413](https://github.com/microsoft/node-pty/issues/413))。対策 2 点を実装済:
  (1) `onExit` 内で `ptyProc.kill()` を呼び ConPTY/agent を明示クリーンアップ、
  (2) メインループ正常終了 (`.rotate-signal` 無し) で `process.exit(0)` を明示呼び出し、
  制御をシェルへ返す。`.rotate-signal` 検知時のローテーション経路は従来どおり
  ループを継続するため影響なし。**次回 実 ccr 起動で `/exit` → プロンプト復帰を要確認**。

- **プロジェクト選択メニューでの入力化け (2026-05-31 修正)**: `selectProject()` で 0 以外を
  選ぼうとすると `番号を選択 [4]: ;13;1;0;1_;13;0;0;1_…` と化け、Enter が認識されない事象。
  原因は **win32-input-mode** (ConPTY が有効化する rich-input、DECSET `?9001`)。これは
  **端末エミュレータ側の状態**で node プロセスが死んでも残る。直前の `ptyProc.kill()` +
  `process.exit(0)` 急停止で ConPTY が終了時に無効化シーケンスを出せず、外側端末が
  win32-input-mode のまま → 次回 ccr の `readline` がキーをレコード
  (`CSI Vk;Sc;Uc;Kd;Cs;Rc _`、終端 `_`=0x5F) として受け取り cooked 行入力にならず化ける。
  対策: `TERM_INPUT_RESET` (win32-input-mode/bracketed-paste/mouse/kitty を無効化する制御列) を
  (1) `selectProject()` の readline 前 (毎起動 self-heal)、(2) PTY `onExit` cleanup、
  (3) 最終 `process.exit(0)` 前、の 3 箇所で発行。**次回 実 ccr 起動でメニュー選択を要確認**。

- **追補 (2026-05-31, workflow `ccr-fix-verification` 4 レンズ検証の high finding 対応)**:
  (a) `selectProject` の `reset→readline` が同一同期 tick で、Windows Terminal が `?9001l` を
  適用する前に最初のキーが win32 符号化され化けうる (win32 high), (b) `onExit` は conout socket
  'close' 由来で ConPTY drain デッドロック (#375/#1810) 時に未発火 → 終了待ち Promise 未解決で
  **無期限ハング**、それを Ctrl+C で抜けると端末復元が走らず raw mode/win32-input-mode 残留 →
  次回メニュー化け (exit high) を検出。対応 3 点を実装:
  (1) `selectProject` の `resetTerminalInput()` 後に grace sleep (`RAPTOR_AUTO_RESET_GRACE_MS`, 既定 60ms)。
  (2) PTY 後始末を `cleanup()` 関数化 + `settled` ガード化し、**`SIGINT` でも cleanup を通して
  端末復元してから `process.exit(130)`** (Ctrl+C 脱出時の端末破壊→次回化けの連鎖を断つ)。
  (3) `selectProject` に DEBUG hex tap を追加 (`RAPTOR_AUTO_INPUT_DEBUG=1` でメニュー化けの
  生バイト=CSI レコードを `.input-debug.log` の `[selectProject]` 行に記録。従来 tap は PTY 経路の
  対話入力のみで selectProject を捕捉できなかった)。**残 at_risk・全機能の棚卸し・ハング回避策・
  E2E 手順は `docs/CCR_FUNCTIONAL_CHECKLIST.md` を正本とする**。

---

## 7. 更新時に直すドキュメント

`claude-auto.mjs` / ccr フローを変更したら、本ファイルと
`D:/projects/SOFTWARE_UPDATE_DOC_CHECKLIST.md` の ccr 行を更新すること。
