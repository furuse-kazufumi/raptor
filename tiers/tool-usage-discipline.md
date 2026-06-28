# Tool Usage Discipline（ツールの使い方の規律）

> 起源: 2026-06-28。ゴール「tool の使い方のミスをなくす」。この環境特有の
> シェル/ツール誤用を機械的に防ぐため。背骨は [[work_discipline]]（理解→検証→行動）。
> **機械的強制** = `libexec/raptor-tool-guard`（PreToolUse フック、Bash/PowerShell を実行前検査）。
> 本書はその「なぜ」と、ガードが助言に留める領域の早見表。

## 一言

この環境には **2 つの別シェルツール** がある。混ぜると壊れる:

- **Bash ツール** = Git Bash / POSIX sh。Unix 構文。
- **PowerShell ツール** = PowerShell 7。cmdlet と PS 構文。

片方の構文をもう片方に撃つのが最頻の誤用。**コマンドを書く前に「今どちらのツールか」を確認する。**

## 早見表（やりがちな誤用 → 正しい形）

### Bash ツールでやってはいけない（= PowerShell 構文の混入）
| 誤 | 正 |
|---|---|
| `Get-Content x` / `Get-ChildItem` 等 cmdlet | POSIX (`cat`/`ls`…) か **PowerShell ツール**に切替 |
| `$env:VAR` | `$VAR`（読み） / `export VAR=val`（設定） |
| 先頭 `$VAR = ...`（PS 代入） | `VAR=value`（`$` 無し・`=` 前後に空白なし） |
| `> NUL` | `/dev/null` |
| `@'...'@`（here-string） | heredoc `<<'EOF' ... EOF` |

### PowerShell ツールでやってはいけない（= Unix 構文の混入）
| 誤 | 正 |
|---|---|
| `head` / `tail` | `Get-Content f -TotalCount N` / `-Tail N`（または `Select-Object -First/-Last N`） |
| `which x` | `(Get-Command x).Source` |
| `touch f` | `New-Item -ItemType File f`（既存を壊す `-Force` は付けない） |
| `wc -l` | `(Get-Content f \| Measure-Object -Line).Lines` |
| `grep` / `sed` / `awk` | Grep ツール / `-replace` / `ForEach-Object` |
| `mkdir -p a/b` | `New-Item -ItemType Directory -Force a/b` |
| `rm -rf x` | `Remove-Item -Recurse -Force x` |
| `ln -s a b` | `New-Item -ItemType SymbolicLink -Path a -Target b` |
| `2>/dev/null` | `2>$null` |
| `export FOO=bar` | `$env:FOO = 'bar'` |
| `if [ -f x ]` / `[ -f x ]` / `for x in ...` | `if (Test-Path x) {}` / `foreach ($x in ...) {}` |
| `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1`(dot-source は `. .\x.ps1`) |
| `ls -la` / `gci -lah`(unix まとめフラグ) | `Get-ChildItem -Force -Recurse \| Format-Table` |
| `cut`/`tr`/`uniq`/`du`/`basename`… | native idiom(`-split`/`Sort-Object -Unique`/`Split-Path`…) |

### 専用ツールを優先（両シェル共通・ガードは warn）
- ファイル閲覧 = **Read** ツール（`cat`/`head`/`tail`/`Get-Content` でなく）
- 内容検索 = **Grep** ツール（`grep`/`Select-String` でなく）
- ファイル探索 = **Glob** ツール（`find`/`Get-ChildItem -Recurse` でなく）
- 編集 = **Edit/Write** ツール

### この環境の規約（ガードは warn）
- Python = `py -3.11`（`python`/`python3` でなく）。cp932 で日本語出力するなら `PYTHONUTF8=1` 前置。
- シェルコマンドは原則 `rtk` 前置（`rtk pytest` / `rtk git` 等。専用フィルタが無くても素通しで安全）。
- `cd` 前置は不要（作業ディレクトリは維持される。`cd` は権限プロンプトの原因）。絶対パスで直接実行。

### 不可逆操作は ASK FIRST（ガードは warn、CLAUDE.md は確認必須）
`git push --force`（`--force-with-lease` を優先） / `git reset --hard` / `rm -rf <絶対パス>` / DB drop。

## ガード `raptor-tool-guard` の挙動

`PreToolUse`（matcher `Bash|PowerShell`）で実行前に検査:

- **deny（block）**: そのシェルで**確実に失敗**する致命誤用のみ（高精度・低誤検知）。理由＋正しい形を返すので、修正して再実行する。
- **allow + additionalContext（warn）**: 規約・代替ツールの助言だけ。コマンドは実行される。
- **fail-open**: 例外・想定外は必ず通す（ガードがツールを壊すのが最悪）。
- 誤検知回避: クォート内文字列を mask し、`;`/`|`/`&&` でセグメント分割して**各セグメント先頭トークンだけ**を判定。`echo "Get-Content..."` や `[ $x = 1 ]` テストは誤爆しない。

### 環境変数で制御
| `RAPTOR_TOOL_GUARD` | 動作 |
|---|---|
| 未設定 / `block`（既定） | 致命誤用は deny、規約は助言 |
| `warn` | 致命誤用も助言に格下げ（**絶対に deny しない**） |
| `off` | 何もしない |

### 検証
`py -3.11 libexec/tests/test_raptor_tool_guard.py`（stdlib のみ・pytest 不要）。

## 失敗パターン（やってはいけない）

- 「今どちらのシェルツールか」を確認せずに書き、片方の構文をもう片方に撃つ
- ファイル閲覧/検索を `cat`/`grep`/`find` で済ませ Read/Grep/Glob を使わない
- 走らせていないものを「動いた」と報告する（[[feedback_verify_existence_before_claiming]]）
- ガードの deny を黙って `off` で回避する（致命誤用が通り、結局失敗する）
