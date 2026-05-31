# ccr シーケンシャル入力 — 不整合監査レポート (read-only)

作成 2026-05-31。ユーザー指摘「ccr の構造やシーケンシャルなコメント入力が今の作業履歴参照と一致していないのではないか」を受けた **読み取り専用の突合調査**。コードは変更していない。方針決定の材料。

---

## 0. 結論 (一行)

**ユーザーの指摘は正しい。** 私が今セッションで作った「シーケンシャル送信機構」(node-pty 起動注入) は、作業履歴に既存する「シーケンシャル入力機構」(claude-loop キュー) と**別レイヤーで重複し、相互参照ゼロ**。私のドキュメントは既存機構に一言も触れておらず、整合していない。

---

## 1. 確認した事実 (証拠)

| 項目 | 事実 |
|---|---|
| ccr 起動 | `bin/ccr.ps1` (実体は batch) → `zx claude-auto.mjs %*` ✅ 私の理解通り |
| claude-loop キュー実在 | `libexec/raptor-loop-queue` (Python) が実在。**キュー実体は `D:/tools/claude-loop/`** (`_root()` が Windows+D: で返す。`RAPTOR_LOOP_DIR` で上書き可)。ディレクトリは **`queue / inbox / _inflight / done`** (※当初 "processing" と誤記したが正しくは `_inflight`) |
| キュー現状 | 未初期化 (まだ `init`/`push` されておらず `D:/tools/claude-loop/` 自体が未作成。`ingest`/`init` 実行時に生成される) |
| **claude-auto.mjs が loop/queue を参照** | **0 回** (grep `loop\|inbox\|queue\|ingest`) |
| **CCR_AUTO_RESTART.md が claude-loop に言及** | **0 回** |
| session 参照 | `.raptor-session.json`=fullsense / `RAPTOR_CALLER_DIR`=llcore / 実作業=llcore |

---

## 2. 二つの「シーケンシャル入力」機構

### 機構A — node-pty 起動注入 (claude-auto.mjs, 今セッションで私が実装)
- **レイヤー**: session 起動時の **一発** (one-shot)
- **動作**: node-pty で claude を起動し、`/effort ultracode` → (任意 preCommands) → 復元プロンプト を**別々の submission** として順次投入してから対話を引き渡す
- **設定**: `RAPTOR_AUTO_EFFORT_LEVEL` / `RAPTOR_AUTO_PRECOMMANDS` (`||` 区切り) / `RAPTOR_AUTO_PTY_*` / `RAPTOR_AUTO_SEQ_DELAY_MS`
- **目的**: 起動時に ultracode を効かせる + 自律復元を走らせる
- **状態**: 実装済・**実 ccr 起動での動作未検証**

### 機構B — claude-loop キュー (既存: raptor-loop-queue + claude-loop/)
- **レイヤー**: session **稼働中・継続** (毎反復ポーリング、CLAUDE.md SESSION START 手順6)
- **動作**: タスク JSON (`{id,title,description,constraints}`) が `inbox → ingest → queue → pop → processing → done <id>` と流れる
- **入力源**: Telegram inbound (`fullsense/tools/fullsense_telegram_inbound.py` が inbox/ にタスク化) + 手動 inbox 配置
- **制約尊重**: `constraints` の `no-push` / `needs-human-judgment` で危険操作を抑止
- **状態**: 稼働機構として CLAUDE.md 手順6 + README に正式記載

---

## 3. 不整合の正体 (4点)

1. **レイヤー取り違え**: ユーザーが「コメント/コマンドを順次送る仕組み」と言ったとき、本命は **作業中ずっと効く機構B (タスク粒度・Telegram 給餌)**。私は **起動時 1 回きりの機構A** として実装した = 狭く・違う層を解いた。
2. **重複の再発明**: `RAPTOR_AUTO_PRECOMMANDS` (機構A) は機構Bのキューの「コマンド列を順次流す」を、Bに繋がず**起動時限定で再発明**している。順次入力経路が2系統に分裂。
3. **相互参照ゼロ**: claude-auto.mjs も CCR_AUTO_RESTART.md も claude-loop を**参照していない** (各0回)。私の ccr 作業は既存機構と完全分離。
4. **ドキュメント矛盾**: CCR_AUTO_RESTART.md は機構Aを「シーケンシャル送信機構」と説明するが、作業履歴 (CLAUDE.md 手順6) の正規シーケンシャル機構は**機構B**。doc が作業履歴と食い違う = 「作業履歴参照と一致しない」の実体。

---

## 4. 整合している点 (過大評価しないため)

- `ccr → zx claude-auto.mjs` は正しい。
- **機構Aの核 (起動時に `/effort ultracode` を単独 submission で送る)** は正当で代替不能: フラグは ultracode 非対応 (実機検証済)、連結すると `Invalid argument: ultracode` バグ。この一点は機構Bでは代替できない (Bは「起動後」の機構だから)。
- → 機構Aは**間違いではなく、スコープが広すぎ (PRECOMMANDS) + 文書が既存機構Bと未接続**なだけ。

---

## 5. 推奨整合方針 (実装は別途・要承認)

1. **機構Aを起動時 `/effort ultracode` (+ 任意で復元プロンプト) だけに限定**。これがAの代替不能な核。
2. **「稼働中の順次コメント/コマンド」は機構B (claude-loop inbox) に一本化**。
3. `RAPTOR_AUTO_PRECOMMANDS` は (a) 廃止、または (b) 起動時に `claude-loop/inbox/` へ enqueue する橋渡しへ変更 (= キューを1系統に統合)。
4. **CCR_AUTO_RESTART.md に「起動時注入 (A) と 稼働中キュー (B) の2層」を明記** + CLAUDE.md 手順6 と `claude-loop/README.md` を相互リンク。

---

## 6. session ポインタのずれ (私の判断)

- 現象: `.raptor-session.json`=fullsense / caller=llcore / 実作業=llcore。
- **しかし機能上は壊れていない**: `claude-projects.json` の `fullsense.plan_ref` = `memory:project_llcore_init_2026_05_29` で、その「次セッション最優先」section = ③ 谷深さ実測 workflow = **今まさにやっている作業**。つまり「fullsense を選ぶ → plan_ref → llcore ③」の復元連鎖は**設計通り機能**している (FullSense=マスター進捗、llcore=その③の実体)。
- caller dir (llcore) ≠ 選択 project (fullsense) の差は、CLAUDE.md 手順2a が `.raptor-session.json` を優先する仕様で fullsense に解決 = 意図通り。
- **判断: 現状維持で問題なし。** 直接性のため llcore を claude-projects.json の独立エントリにする選択肢はあるが必須でない。今回は変更しない (記録のみ)。

---

## 7. 次アクション (ユーザー判断待ち)

§5 の整合実装に進むか、現状維持で記録だけ残すか。ccr コア+自律ループに触る sensitive 領域のため、本レポートを材料にユーザーが方針決定する。
