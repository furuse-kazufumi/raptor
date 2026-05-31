# ccr 自動ローテーター / effort 設定 — 仕様

`claude-auto.mjs` は ccr (Claude Code 連続運用ラッパ) の中核となる **zx 製セッション自動ローテーター**である。
`D:\projects\` を自動スキャンしてプロジェクトを選ばせ、Claude Code を起動し、`/rotate` のたびに
新セッションへ自動継続させる。

- 対象ファイル: `claude-auto.mjs` (raptor リポジトリ直下、`#!/usr/bin/env zx`)
- 起動エントリ: `bin/ccr.ps1` (ExternalScript) → `zx claude-auto.mjs`
- 関連コミット: `ddf36cba` (effort 注入の初版・連結バグあり) → 本仕様で **`--effort` フラグ方式**へ修正
- 関連 memory: `project_ccr_auto_resume`, `project_ccr_memory_replay_fix`, `project_ccr_hang_watchdog`

---

## 1. 全体フロー

```
ccr (bin/ccr.ps1)
  └─ zx claude-auto.mjs
       ├─ discoverProjects()  D:\projects\ をスキャン (claude-projects.json で名前/説明上書き)
       ├─ selectProject()     メニュー表示 + 60 秒無入力で最新 mtime を自動選択
       └─ while(true) runSession()  ← メインループ
            ├─ writeSessionConfig()  .raptor-session.json を書く (projectName/path/docs...)
            ├─ claude を spawn (stdio: inherit, --effort + initial prompt)
            ├─ .rotate-signal を watch → 検知で child.kill(SIGTERM)
            └─ child 終了後:
                 ├─ .rotate-signal あり → SESSION_SUMMARY をアーカイブ → 3 秒後に次セッション
                 └─ .rotate-signal なし → 正常終了、.raptor-session.json 削除して break
```

---

## 2. effort 設定 (ultracode)

ccr 起動時は常に ultracode effort で起動する (ユーザー指示 2026-05-31)。

**方式 = CLI フラグ `--effort ultracode`**。`runSession()` で:

```js
const EFFORT_LEVEL = process.env.RAPTOR_AUTO_EFFORT_LEVEL ?? 'ultracode';
const args = ['--dangerously-skip-permissions'];
if (EFFORT_LEVEL) args.push('--effort', EFFORT_LEVEL);
```

### 修正した連結バグ (2026-05-31)

初版 (`ddf36cba`) は initial prompt の **先頭に連結**していた:

```js
args.push('/effort ultracode' + '\n\n' + 'セッション再開。...')   // ← バグ
```

Claude Code は **単一の positional プロンプトを 1 メッセージ**として扱う。先頭が `/effort` だと
スラッシュコマンドのパーサが **後続本文全体を引数**として受け取り、以下のエラーになる:

```
Invalid argument: ultracode

セッション再開。CLAUDE.md SESSION START を実行し...
. Valid options are: low, medium, high, xhigh, max, ultracode, auto
```

(`ultracode` 自体は valid options に含まれるのに、完全一致しないため弾かれる。)

### なぜフラグで解決できるか (実機検証)

当初コメントの「`--effort` フラグは ultracode 非対応 (low/medium/high/xhigh/max のみ)」は **誤り**だった。
実機検証で `--effort ultracode` はフラグとして **受理される**:

| コマンド | 結果 | 解釈 |
|---|---|---|
| `claude --effort ultracode -p "hi"` | exit 124 (timeout) | arg 検証通過 → API へ進んだ = **有効** |
| `claude --effort zzz -p "hi"` | exit 2 (即エラー) | commander が無効値を拒否 |

→ in-band スラッシュ連結を廃止し、フラグで設定。positional プロンプトは復元指示のみになり、
連結バグは構造的に発生しなくなった。

---

## 3. 初回プロンプト自動投入

`SESSION_SUMMARY.md` があるプロジェクトを選んだ場合のみ、positional プロンプトとして
復元指示を投入する (ユーザーが毎回トリガ文を打たずに SESSION START → 自律継続が走る):

```
セッション再開。CLAUDE.md SESSION START を実行し、SESSION_SUMMARY.md から前回作業を
復元して即座に自律継続してください。「進めますか？」…確認・メニュー提示はせず、宣言してそのまま着手すること。
```

`SESSION_SUMMARY.md` が無い起動では positional プロンプトを付けず、effort フラグのみで
対話起動する (クリーンな ultracode 対話開始)。

---

## 4. 設定 (環境変数)

| 環境変数 | 既定 | 説明 |
|---|---|---|
| `RAPTOR_AUTO_EFFORT_LEVEL` | `ultracode` | `--effort` に渡すレベル。空文字 `""` で effort 指定を無効化 |
| `RAPTOR_CALLER_DIR` | (runSession が設定) | 選択プロジェクトのパス。CLAUDE.md SESSION START が参照 |

---

## 5. ファイル

| ファイル | 役割 |
|---|---|
| `.rotate-signal` | `/rotate` が作成。ローテーターが watch して検知すると Claude を終了させる。次ループで消費 |
| `.raptor-session.json` | runSession が起動時に書く。projectName/projectPath/docsDir/summaryFile/progressFile/debugFile/testFile。CLAUDE.md SESSION START が読む |
| `docs/SESSION_SUMMARY.md` | `/rotate` が書くセッション引き継ぎ。ローテート時に `SESSION_SUMMARY_<date>.md` へアーカイブ |
| `claude-projects.json` | プロジェクト名/説明の上書き + per-project `next_plan`/`plan_ref` |

---

## 6. シーケンシャル送信について (将来拡張・honest disclosure)

現アーキテクチャは **1 セッション = 1 回の対話 `claude` spawn (stdio inherit) + 単一 positional プロンプト**。
そのため「`/effort` を送る → 次に `/workflow ...` を送る → 復元指示を送る」のような
**複数メッセージのシーケンシャル投入は argv では不可能**。

- effort は本修正で **フラグ化**したので連結の必要が無くなった (この用途では sequential 不要)。
- それでもスラッシュコマンド列を順番に流したい場合の正攻法は Claude Code の
  `--input-format stream-json` + `--print` (非対話・プログラム投入) を使う別経路。
  対話 (stdio inherit) のままキーストロークを順次注入する堅牢な方法は PTY 無しでは難しい。
- 必要になったら「stream-json で初期コマンド列を流してから対話に渡す」モードを
  別途実装する (現状は未実装)。

---

## 7. 更新時に直すドキュメント

`claude-auto.mjs` / ccr フローを変更したら、本ファイルと
`D:/projects/SOFTWARE_UPDATE_DOC_CHECKLIST.md` の ccr 行を更新すること。
