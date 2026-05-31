# ccr 診断記録 — SCRIPT_DIR 誤解決 + /effort 連結バグ (2026-05-31)

> 発端: ccr 起動直後に `/effort ultracode` のエラー出力へ「セッション再開。CLAUDE.md の
> SESSION START 手順に従って…」が混入していた件をユーザーが指摘 → 調査で 2 つの独立バグを確定。
> 記録者: Claude (llcore セッション中、raptor の ccr 改造タスクとして)。

---

## 1. 症状 (ユーザー観測)

ccr 起動直後の TUI 表示:

```
❯ /effort ultracode                            セッション再開。CLAUDE.md の SESSION START 手順に従って前回作業を復元し、自律継続してください。
  ⎿  Invalid argument: ultracode
     セッション再開。CLAUDE.md の SESSION START 手順に従って前回作業を復元し、自律継続してください。. Valid options are: low, medium, high, xhigh, max, ultracode, auto
```

→ `/effort` に `ultracode⏎セッション再開…` という**複数行文字列が単一引数**として渡り `Invalid argument`。
再開トリガー (②) は**独立メッセージとして発火していない**。

---

## 2. バグ A: /effort 連結バグ (再々発、未解決)

### 因果
- ccr (`claude-auto.mjs`) は起動時に 2 つの submission を順次投入する設計:
  1. `/effort ultracode` (slash, arg メニューを開く)
  2. `セッション再開。CLAUDE.md の SESSION START…` (再開トリガー本文)
- ①の `\r` が **引数オートコンプリートメニュー表示中に届くと「送信」でなく「改行挿入」**として
  吸収される。結果 `/effort ultracode\n` となり、続く②が同じ入力欄に連結 → 1 メッセージとして
  submit され `/effort` の引数が複数行化。

### ログ実証 (`.input-debug.log`, UTC)
```
13:44:41.514 [submitSequence] begin [1/2] slash=true  len=17   (= "/effort ultracode")
13:44:43.328 [submitSequence] sent body+enter (single)
13:44:45.018 [submitSequence] begin [2/2] slash=false len=60   (= 再開トリガー)
13:44:46.521 [submitSequence] sent body+enter (single)
13:44:46.525 [submitSequence] done
```
→ **コードは仕様どおり単一 Enter を送っている**。それでも連結 = Esc+単一Enter 対策
(commit 489ed52d 等) でも防げていない。旧 double-Enter 時の診断と同じ現象が単一 Enter でも再現。

### 現対策の限界
- 各コマンド前の `Esc Esc Ctrl+U` は**複数行バッファを確実には消せない** (Ctrl+U は 1 行、
  Esc の挙動は TUI/メニュー状態依存)。
- slash 後の `Esc`(引数メニュー閉) → `\r` も、メニューが TYPE_DELAY(350ms) 内に閉じきらないと
  `\r` が改行挿入になる。**固定 sleep では TUI の submit-ready 状態を保証できない**。

### 推奨する次の修正方針 (未着手、要ユーザー判断)
1. **Quiescence gating (出力静止検知)**: `onData` で最終出力時刻を記録し、コマンド本文投入後に
   「出力が N ms 静止＝メニュー確定」を待ってから `\r`。Enter 後も静止を待ち「入力欄が空に
   なった」ことを確認してから次コマンド。固定 sleep を廃する。
2. 代替: `/effort` 自動投入そのものを廃し、effort 設定を別経路 (設定ファイル/env) で与えられるか
   調査 (`--effort` フラグは ultracode 非対応)。
3. A/B 切り分け: `RAPTOR_AUTO_SLASH_DOUBLE_ENTER=1` で旧挙動と比較。

### 機能影響度
- 中。`/effort` 不適用 + 再開トリガー不発でも、SessionStart hook と最初のターンで Claude は
  起動し SESSION START を実行できる (今回も実際に復元・継続できた)。ハードフリーズではない。

---

## 3. バグ B: SCRIPT_DIR 誤解決 (主因、修正済)

### 根本原因
```js
// 旧 (誤り)
const SCRIPT_DIR = path.dirname(process.argv[1]);
```
ccr.ps1 は `& zx claude-auto.mjs` で起動する。実プロセスは:
```
node  C:\Users\puruy\AppData\Roaming\npm\node_modules\zx\build\cli.js  claude-auto.mjs
```
→ **`process.argv[1]` は zx の CLI 本体**であって `claude-auto.mjs` ではない。
よって `SCRIPT_DIR` が **zx の build ディレクトリ**を指していた。

### 実証
zx build 配下に ccr の状態ファイルが書かれていた:
```
…\zx\build\.raptor-session.json   mtime 2026-05-31 22:44  内容 = llcore (正しい・今回の書込)
…\zx\build\.input-debug.log       148 KB・稼働中
```
一方 CLAUDE.md SESSION START が読む cwd(raptor) 側:
```
C:\Users\puruy\raptor\.raptor-session.json  mtime 2026-05-23  内容 = fullsense (化石)
```

### 実害 (silent 障害)
- **プロジェクト復元の誤り**: SESSION START は raptor dir の `.raptor-session.json` を読むが、
  それは 8 日前の fullsense。今回 llcore に収束したのは next_plan が両者とも llcore ③ を
  指していた偶然による。
- **`.input-debug.log` が「無い」ように見えた** (zx build に書かれていた) → 連結バグの診断が遅れた。
- **プロジェクトメニューに説明文が出ない** (`claude-projects.json` を SCRIPT_DIR=zx build で
  探して見つからず meta={})。
- **`/rotate` 自動再起動が壊れている疑い**: watcher が `watch(SCRIPT_DIR)=zx build` を監視するが、
  `/rotate` スキルは raptor dir(cwd) に `.rotate-signal` を書く → 不一致で検知されない。
- これは**回帰**。2026-05-23 時点では raptor dir に正しく書けていた (当時は argv[1] が
  claude-auto.mjs だった or 起動経路が違った)。zx のバージョン/呼出し方の変化で顕在化。

### 適用した修正
```js
import { fileURLToPath } from 'url';
// …
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
```
`import.meta.url` は起動経路 (zx / 直接 node / シンボリックリンク) に依らず常に
claude-auto.mjs 自身の場所を返す。`node --check` PASS。

### 残作業
- [ ] 次回 ccr 起動で raptor dir に `.raptor-session.json` / `.input-debug.log` が
      書かれることを実機確認。メニュー説明文が復活することを確認。
- [ ] `/rotate` の signal 経路一致を確認 (watcher と書込先)。
- [ ] zx build 配下の stray ファイル除去:
      `…\zx\build\.raptor-session.json` / `.input-debug.log` (node_modules 汚染)。
- [ ] raptor dir 側の化石 `.raptor-session.json` (2026-05-23 fullsense) は次回起動で上書きされるが、
      混乱回避のため掃除してよい。

---

## 4. raptor 環境の D ドライブ移設 (ユーザー指摘 2026-05-31)

> 「そもそも D ドライブに環境構築していないと、PC が壊れた時に何も対処が取れなくなる。」

### 4.1 背景
- 現状 raptor 本体は **C:\Users\puruy\raptor** (PATH の `bin/ccr.ps1` もここ)。OS ドライブ上のため
  C: 障害で環境ごと喪失リスク。
- `D:\backup\projects\raptor` は **git ですらない古いコピー** = DR として頼れない。
- 移設先決定: **D:\tools\raptor** (既に `D:\tools\raptor-analytics.db` を使用しており一貫。
  ccr のプロジェクトメニュー (D:\projects スキャン) に raptor 自身が出ない)。ユーザー選択 2026-05-31。

### 4.2 データ構成 (調査で判明、要注意点)
- **生 RAD コーパスは既に D: にある**: `D:\docs\<domain>_corpus_v2\` (40+ ディレクトリ) +
  `D:\docs\hacker_corpus`。CLAUDE.md 既定も `D:/docs/hacker_corpus/` (`RAPTOR_CORPUS_DIR` で上書き可)。
- raptor / llcore / llive はこの生コーパスを **path 参照** (D:/docs/...)。**llive は C: raptor に
  依存していない**。
- C: raptor 内の `.claude/skills/corpus/` は corpus2skill の **skill 階層** (rad-research ヒント用)
  で、生データではない。かつ **gitignore 対象 = 生成物**。
- ⚠️ **この skill 階層は Karpathy LLM Wiki 構造へ移行中の可能性** (memory
  `project_llm_wiki_pattern`)。C: 版を権威と決めつけない。生コーパス (D:\docs) から再生成可能。

### 4.3 移設方法 (lean copy)
- **重い再生成可能ディレクトリを除外**して essential のみ robocopy:
  - 除外: `.claude\skills\corpus` (gitignore/wiki移行中) / `tmp_hacker_corpus` / `tmp_corpus_large` /
    `tmp_papers` / `tmp_papers_arxiv` / `tmp_security_extra` / `out` / `.hypothesis`
  - 含む: `.git` (履歴) / `node_modules` (node-pty prebuilt 再ビルド回避) / `core` `packages` `engine`
    `bin` `libexec` `docs` `.claude`(corpus 除く) 等のコード・設定。
- コーパス skill 階層が必要になったら D:\docs から `/corpus2skill` で D: 側に再生成する。

### 4.4 移設で直す箇所 (特定済み)
| 対象 | 内容 | 状態 |
|---|---|---|
| `D:\tools\raptor\.claude\raptor.env` | `RAPTOR_DIR` と `PATH` を C: → `D:\tools\raptor` | **要修正** (CLAUDE_ENV_FILE 経由でセッションに注入されるため必須) |
| ユーザー PATH | `C:\Users\puruy\raptor\bin` → `D:\tools\raptor\bin` | **要修正** |
| `ccr.ps1`/`ccr.cmd`/`ccr`(bash) | `$PSScriptRoot`/`%~dp0`/`dirname` で自己解決 | 変更不要 ✓ |
| リポジトリ hook (`.claude/settings.json`) | 全て `$CLAUDE_PROJECT_DIR/libexec/...` 相対 | 自動追従 ✓ |
| グローバル hook (`~/.claude/settings.json`) | raptor リポジトリ外 (`~/.claude/hooks/`) | 無関係 ✓ |
| `.claude/skills/corpus/*/metadata.json` | C: 絶対パスの provenance 記録 (output_dir/source_dir) | 履歴のみ・runtime 非依存 → 放置可 |

### 4.5 D: コーパス動作検証 (ユーザー要件「D: の RAD コーパスで動くなら問題ない」)
- `KnowledgeBase.auto_discover()` を **D:\tools\raptor から実行 → 成功**。`corpus_dir = D:\docs\hacker_corpus`
  を採用 (skill_dir は None=除外したため)。生コーパスへ正しくフォールバック。
- `get_hints` は C: (skill 階層あり) でも D: (生コーパスのみ) でも **同一の結果 (テストタグで 0 chars)**。
  → **0 件は移設前からの既存挙動であり移設とは無関係**。capec(616 md)/ghsa(json) 等の生データは実在し、
  `_extract_snippet` が keyword 一致必須 + 各 source 最新 5 ファイルのみ sampling という既存仕様による。
- **結論: 移設は corpus 機能を劣化させていない**。raptor は D: からでも C: と同一に D: 側 RAD コーパスを使う。
- skill 階層のリッチなヒントが必要なら D:\docs から `/corpus2skill --source D:/docs/hacker_corpus
  --name hacker_corpus` で D: 側に再生成 (wiki 移行検討と併せて別途)。

### 4.6 検証ステータス (2026-05-31)
- [x] D:\tools\raptor へ essential lean copy (4438 files, FAILED 0)
- [x] D: `claude-auto.mjs` に SCRIPT_DIR 修正反映 + `node --check` OK
- [x] D: `.claude/raptor.env` を D: パスへ修正
- [x] ユーザー PATH を `D:\tools\raptor\bin` へ付け替え (old 除去確認)
- [x] D: から corpus auto_discover 成功 (D:\docs 採用) / get_hints は C: と同一挙動
- [ ] **次回 ccr 起動で E2E** (新 PATH で ccr が D: に解決 / 状態ファイルが D:\tools\raptor 直下に書かれる /
      メニュー説明文復活 / `/effort` 連結バグの現状) ← SCRIPT_DIR 修正と連結バグの実機確認を兼ねる
- [ ] (任意) corpus skill 階層を D: で再生成 / C: 旧環境の掃除 (検証後)
- ⚠️ **caveat**: Claude Code の auto-memory は cwd パスのハッシュで分かれる。D: 起動後は
      `D--tools-raptor` 側の memory dir になり、既存 `C--Users-puruy-raptor` の raptor memory は
      自動ロードされなくなる可能性。継続性が要るなら memory の移送 or 参照を別途検討。

### 4.7 DR 補足
- raptor は次計画で「露出回避でローカル保持」= GitHub 公開 push 不可 → DR は **D: 上の実体 +
  生コーパス (D:\docs) + (任意で) private remote** で担保。
- C: は動作確認が取れるまでフォールバックとして残置。検証後に掃除を提案。

---

## 5. 関連
- `docs/CCR_FUNCTIONAL_CHECKLIST.md` (全機能棚卸し台帳 §0.5)
- `docs/CCR_AUTO_RESTART.md` (自動再起動仕様)
- memory: `project_ccr_effort_sequential_fix` / `project_ccr_memory_replay_fix` / `project_ccr_auto_resume`
