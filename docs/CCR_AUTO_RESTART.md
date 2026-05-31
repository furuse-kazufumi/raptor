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
  └─ submitSequence(): FIRST_DELAY 後、各コマンドを
        write(cmd) → TYPE_DELAY → write('\r')  を SEQ_DELAY 間隔で繰り返す
```

`/effort ultracode` は **単独 submission** になるため、後続本文を引数化してしまう連結バグは構造的に起きない。
将来 `/workflow ...` など任意のスラッシュコマンド列も同じ仕組みで順次投入できる (`RAPTOR_AUTO_PRECOMMANDS`)。

### 修正した連結バグ (2026-05-31)

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

順序: `/effort <level>` → (任意 `RAPTOR_AUTO_PRECOMMANDS`) → 復元プロンプト。

- 復元プロンプトは `SESSION_SUMMARY.md` がある時のみ付与 (ユーザーがトリガ文を打たず SESSION START → 自律継続)。
- `SESSION_SUMMARY.md` が無い起動では `/effort ultracode` のみ投入。

---

## 4. 設定 (環境変数)

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `RAPTOR_AUTO_EFFORT_LEVEL` | `ultracode` | 投入する effort レベル。空文字 `""` で effort 投入を無効化 |
| `RAPTOR_AUTO_PRECOMMANDS` | (なし) | `/effort` と復元の間に挟む追加コマンド。`||` 区切り (例 `/workflow foo||コメント`) |
| `RAPTOR_AUTO_PTY_FIRST_DELAY_MS` | `2500` | TUI 起動待ち (最初の submit まで) |
| `RAPTOR_AUTO_PTY_TYPE_DELAY_MS` | `350` | テキスト流し込み → Enter までの反映待ち |
| `RAPTOR_AUTO_SEQ_DELAY_MS` | `1500` | submission 間隔 |
| `RAPTOR_AUTO_PTY_DISABLE` | (なし) | `1` で PTY を使わず通常 spawn (初期コマンド投入なし) |
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

---

## 7. 更新時に直すドキュメント

`claude-auto.mjs` / ccr フローを変更したら、本ファイルと
`D:/projects/SOFTWARE_UPDATE_DOC_CHECKLIST.md` の ccr 行を更新すること。
