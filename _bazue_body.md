:::note info
**📚 FullSense ナレッジベースのご案内** <!-- fullsense-team-kb -->
FullSense 開発全史 60+ 記事 (4 言語版・物語ベースの[読む順ガイド](https://qiita.com/furuse-kazufumi/items/ac398349ec42e40913f1)・かみくだき版・4 コマ漫画つき) は Qiita Team **[FullSense KB](https://fullsense.qiita.com/)** に集約しています (チームメンバー向け)。
:::

## なぜ開発履歴を残すか

llive (リブ) は 2026-05-13 に発足した自己進化型 LLM フレームワーク。本記事は **発足から本日 (2026-05-17) までの 5 日間で何をどう作り、何で躓き、何を学んだか** を時系列でまとめたものです。

- 設計判断の理由を残す
- 失敗を honest に残す (`feedback_benchmark_honest_disclosure` 教訓)
- 「なぜそうなっているか」が後から分かる状態を維持
- 翌日以降の自分 (および Claude Opus 4.7 ccr 経由) が文脈を読めるように

## 5 日間の超概要

| Day | 日付 | バージョン | キーワード |
|---|---|---|---|
| 1 | 2026-05-13 | v0.1.0 | プロジェクト発足 + Phase 1 MVR 完走 |
| 2 | 2026-05-13 | v0.2.0 | Phase 2 Adaptive Modular System |
| 3 | 2026-05-14 | v0.3.0 → v0.5.0 | Phase 3 (Evolve) + Phase 4 (Security) + Phase 5 (Rust) |
| 4 | 2026-05-16 | v0.6.0 | 9 axes skeleton + Apache 2.0 + FullSense umbrella |
| 5 | 2026-05-17 | v0.7 候補 (本日) | Brief API + COG-FX + MATH + ORG-FX 要件化 |

5 日でテスト数は 49 → 1014 (約 21 倍)、コードは MVR から 9 軸 + 32 件 v0.7+ 要件まで。

## Day 1: 2026-05-13 (Tue) — 発足とPhase 1 MVR

### 発足の背景

llmesh (secure LLM hub) と llove (TUI dashboard) という 2 製品を既に持っていた状態で、第三のメンバーとして **「自己進化型モジュラー記憶 LLM フレームワーク」** を作る判断。命名は `l` から始まる 4 文字 (llmesh / llove / llive) で統一。

### 設計の核 (Day 1 で確立、現在まで不変)

1. 固定 Decoder-only LLM コア + 可変周辺で能力吸収
2. 4 層メモリ (semantic / episodic / structural / parameter) の責務分離
3. 宣言的構造記述 (YAML)
4. 審査付き自己進化 (オンライン制限 + オフライン審査経由のみ昇格)
5. 生物学的記憶モデル (海馬-皮質 consolidation cycle)
6. 形式検証付き promotion (Lean / Z3 / TLA+)
7. llmesh / llove ファミリー統合
8. TRIZ 内蔵 (40 原理 + 矛盾マトリクス)

### v0.1.0 リリース

- GSD `/gsd-new-project` で初期化 → PROJECT.md / REQUIREMENTS.md (46 reqs) / ROADMAP.md (4 phases) / STATE.md / config.json 生成
- src/llive/ 8 層: schema / core / container / memory / router / evolution / observability / triz
- 49 tests pass / 82% coverage
- CLI: `llive run --template specs/templates/qwen2_5_0_5b.yaml --prompt "..." --mock`
- 設計判断: faiss / torch / sentence-transformers は **optional extras** にして、Phase 1 テストは numpy + hash 埋め込み fallback で動かす

### 教訓

- Optional extras 設計が Windows + CI の両立に必須
- GSD ワークフロー (`--auto` モード) で 1 日で Phase 1 完走可能

## Day 2: 2026-05-13 (Tue 夜) — Phase 2 Adaptive

### v0.2.0 リリース

- structural memory (graph) + parameter memory (adapter store) 追加
- Bayesian Surprise Gate (FR-21) でメモリ書き込み閾値を動的化
- Consolidation サイクルが夜間 batch で走る
- llove TUI で route trace + memory link viz
- LLM Wiki 統合 (LLW-04)
- 連続 5 タスク学習で BWT ≥ -1% を達成
- **308 tests / 99% coverage / 0 lint**

### 設計判断

- "Bayesian surprise" として書き込み制御 → 単なる threshold より柔軟
- 4 層メモリの間に **phase transition** (short → mid → long → archived → erased) を入れて life cycle 管理

## Day 3: 2026-05-14 (Wed) — 大規模自律セッション

ここから 1 日で 3 バージョン (v0.3 → v0.4 → v0.5) を進めた。

### v0.3.0 — Phase 3 (Controlled Self-Evolution) + Phase 4 (Production Security) 同時リリース

Phase 3 (Evolve):
- EVO-04 Z3 静的検証
- EVO-06 Failed Reservoir (DuckDB 順序保持)
- EVO-07 Reverse-Evo Monitor (JSONL audit)
- TRIZ-02 Contradiction Detector
- TRIZ-03 Principle Mapper (39×39 matrix)
- TRIZ-04 RAD-Backed Idea Generator (pluggable IdeaLLM Protocol)
- TRIZ-07 Self-Reflection Session
- LLW-04 Wiki Contradiction
- LLW-05 Wiki diff ChangeOp

Phase 4 (Security):
- SEC-01 Quarantined Memory Zone
- SEC-02 Ed25519 Signed Adapter
- SEC-03 SHA-256 audit hash chain (stdlib sqlite3 のみ)

**429 tests / 98% coverage / 0 lint**

### v0.4.0 — Phase 5 Rust skeleton

- `crates/llive_rust_ext/` PyO3 0.22 + maturin scaffold
- RUST-01 (skeleton) / RUST-02 (compute_surprise baseline) / RUST-04 (jaccard baseline) / RUST-13 (Hypothesis parity 1e-6)
- `llive.rust_ext.HAS_RUST` flag + Python fallback
- 439 tests pass

### v0.5.0 — Phase 5 wire-in

- RUST-03 (bulk_time_decay) Rust kernel + Python wrapper + 5 parity tests
- BayesianSurpriseGate.compute_surprise が rust_ext.HAS_RUST 時に自動委譲 (numpy fallback)
- EdgeWeightUpdater.apply_time_decay が rust_ext.bulk_time_decay で 1 pass precompute
- **444 tests / 98% coverage / 0 lint**

### Day 3 の設計判断

- **Rust 移植は意味論固定後** に段階的に (5x 性能向上ゲート設定)
- 全 RUST-XX 拡張は **Python fallback 必須**、Rust 不在環境でも動作維持
- 残 RUST-02 rayon / 05 jsonschema-rs / 06 crossbeam / 07 ChangeOp / 08 hora HNSW / 09 tokio async / 10 phf TRIZ / 11 Z3 bridge は v0.7 まで deferred

### Day 3 の教訓

- 1 日で 3 バージョン進めるには **コア設計** と **Optional extras 設計** が必須
- 「ベンチで 5x 出たら採用、そうでなければ revert」のゲートを明示

## Day 4: 2026-05-16 (Thu) — 9 axes + Apache 2.0 + FullSense umbrella

### v0.6.0 リリース

- **9 axes skeleton** 完成 — KAR / DTKR / APO / ICP / TLB / Math / PM / RPAR / SIL
- C-1 Approval Bus production 化 (Policy + SQLite Ledger)
- C-2 `@govern` + ProductionOutputBus (Policy gate × 副作用 emit)
- C-3 Cross-substrate migration spike (§MI1)
- C-14 ICP IdleCollaborator MVP (idle 中 peer LLM 問い合わせ)
- **970 PASS / 0 lint**

### 法務・ブランド整備

- **Apache-2.0 + Commercial dual-license** 切替
- **FullSense umbrella ブランド** 導入 (llmesh / llive / llove の親)
- NOTICE / CONTRIBUTING(DCO) / SECURITY / TRADEMARK 追加
- SPDX header を 204 .py に付与

### 同日のもう 1 つの動き — Brief A/B run

- `scripts/run_brief.py` で 4 brief を回したところ、llive が **doing-agent ではなく thinking-evaluator** であることが判明
- 8 件の bug を `docs/BUGS_2026-05-16_brief_ab.md` に記録
- 設計ドラフト `docs/proposals/brief_api_design.md` を作成 (5 日見積)

### Day 4 の教訓

- 9 軸 (KAR/DTKR/APO/ICP/TLB/Math/PM/RPAR/SIL) を明示することで責務分離が visible に
- A/B run が **「ここまで動く」「ここから動かない」** の境界を可視化、Brief API 必要性が確定

## Day 5: 2026-05-17 (Fri, 本日) — Brief API + 32 件要件追加

### Brief API end-to-end (LLIVE-001/002)

設計ドラフト (5 日見積) を **1 日で完走**:

- `src/llive/brief/types.py` — Brief / BriefStatus / BriefResult (COG-01 で confidence/assumptions/missing_evidence 追加)
- `src/llive/brief/loader.py` — YAML loader (unknown-key reject)
- `src/llive/brief/ledger.py` — append-only JSONL + `trace_graph()` (COG-03)
- `src/llive/brief/runner.py` — 7 段パイプライン (Stimulus 変換 / loop / approval / tool 実行 / outcome)
- `src/llive/brief/grounding.py` — BriefGrounder (TRIZ × RAD citation, S1)
- `src/llive/brief/governance.py` — GovernanceScorer (4 軸 scoring, COG-02)
- `src/llive/cli/main.py` — `llive brief submit|ledger`
- `src/llive/mcp/tools.py` — `submit_brief` MCP tool
- テスト 46 → 78 件追加

### 要件追加 32 件

| グループ | 件数 | 内容 |
|---|---|---|
| v0.7-vertical MATH | 8 | SI 単位次元解析 / 内蔵計算エンジン / Sympy 検算 / CODATA 辞書 / 等 |
| v0.8 CABT | 7 | Cognitive-aware Transformer Block (forward hook で attention bias) |
| v0.9 CREAT | 5 | KJ法 / MindMap / Six Hats / Synectics / 構造化変換 |
| v1.0-frame COG-FX | 4 | Triple Output / Governance Scoring / Trace Graph / Role-based Agents |
| v2.0-core ORG-FX | 8 | Qwen 依存からの 5 段階離脱 + 補完戦略 |

### 実装したもの

- **MATH-01** SI 7 基本単位次元解析 + 派生単位 (N/J/W/Pa/Hz/C/V/ohm)
- **MATH-08** SafeCalculator (AST visitor + whitelist 28 関数 + 0 除算検出)
- **COG-01** Triple Output (confidence / assumptions / missing_evidence)
- **COG-02** Governance Scoring (usefulness/feasibility/safety/traceability の 4 軸)
- **COG-03** Trace Graph (evidence_chain / tool_chain / decision_chain の 3 層 view)

### ベンチマーク 4 種

| 種類 | セル数 | 主要観察 |
|---|---|---|
| progressive matrix | 5×3=15 | overhead < 1 %、decision 全 note |
| fair re-bench (誤算定→修正) | 24 | llive (LLM attached) は ollama 直叩きの 2-4 倍遅い |
| quiz Debug | 10 | passed 6/10、ms mean 22.3s |
| quiz Release | 10 | passed 7/10、ms mean 22.8s、Debug overhead +1.8% |

### Honest disclosure 事件

- 最初の bench で llive 4/4 OK 134-184ms という「変に速い」結果
- ユーザー指摘「変に高速ですね、何かおかしくないですか?」
- 調査 → LLMBackend 未 attach + chars 指標が JSON 全長 + 134-184ms は subprocess RTT 起因
- 修正版で再走 → llive 32-51s (ollama 直叩きの 2-4 倍遅い) と正直に開示
- 教訓を memory `feedback_benchmark_honest_disclosure.md` に保存

### 公開記事 11 本 + 統合 2 本

- 01-03: Brief API / 10 思考因子 / 数学 vertical
- 04-06: 設計予告 (CABT / CREAT / MATH-02)
- 07-08: bench (fair / quiz)
- 09-11: 構造独自性 / Qwen 離脱 / Qwen 補完
- QIITA_SUMMARY: 技術者向け統合 (694 行)
- QIITA_GENERAL: 非エンジニア向け統合 (255 行)
- 本記事 (12): 開発履歴

### Day 5 の設計判断

- Brief API は **frozen dataclass + append-only JSONL ledger** で replay 可能性を最優先
- LLM コアは依然 frozen、CABT は forward hook で **重み凍結のまま** attention に bias
- 「ベンチで自社が速かったら疑う」を memory に確立
- 「毎日色んな側面で記事を書く」「Qiita tags はスペース区切り + 5 件以内」「非エンジニア向け版も作る」「開発履歴も書く」を運用ルールに

### Day 5 の教訓

- **Honest disclosure が研究の信頼を支える** — 速い数字が出ても疑う
- **多側面で書くと自分の理解も深まる** — 技術 / 戦略 / 哲学 / 業務応用 を並行で書く
- **「ベンチで勝つ」より「ベンチで何を測っているか把握」** が大事

## 5 日間の累積メトリクス

| メトリクス | Day 1 開始 | Day 5 終了 (本日) | 倍率 |
|---|---|---|---|
| テスト数 | 0 | 1014 PASS | — |
| バージョン | (未) | v0.6.0 + v0.7 候補 | — |
| 要件 (FR) | 0 | 100 | — |
| RAD 分野 | 0 | 49 (raptor 共有) | — |
| Phase | 0/4 | 4/4 完了 + Phase 5-12 計画 | — |
| LoC (推定) | 0 | ~30 000 (テスト含む) | — |
| 公開記事 | 0 | 12 本 + 統合 2 本 | — |
| GitHub repo | 0 | 4 (llive + llmesh + llove + fullsense) | — |
| PyPI 公開 | 0 | 6 versions (v0.1.0 〜 v0.5.0 + suite) | — |

## これから (2026-05-18 以降の予想)

### 短期 (~2 週間)

- MATH-02 Sympy 検算 + EVO-04 数式版
- MATH-05 CODATA 辞書を RAD metrology に append
- S2 CABT-01 HFAdapter forward hook prototype
- 数学・物理 quiz set v2 (現状の v1 を拡張、N≥30)

### 中期 (~3 ヶ月)

- CREAT-01 KJ法ノード + clustering
- CABT-02 Stage-aware Block Routing prototype
- Brief API を lldesign / lltrade に組み込み、実 use case 駆動で改善
- credential 復旧後の 6-model full matrix benchmark

### 長期 (~1 年)

- ORG-FX Stage B (LoRA で llive 用 adapter)
- ORG-FX Stage C (qwen2.5:14b → llive-7b 蒸留)
- llove TUI Creative Workbench
- llmesh-suite v1.0 (4 製品統合インストーラ)

## 5 日間で確立した「llive 哲学」

- **frozen LLM コア + 可変周辺** = replay 可能性を最優先
- **append-only ledger** = 何が起きたか全部後から見える
- **HITL を architecture level に** = Approval Bus は飾りではなく中核
- **TRIZ を mutation policy に内蔵** = 創造性を構造に持ち込む
- **on-prem only** = Local 環境こそ AI の本来の居場所 (feedback_llive_measurement_purity)
- **honest disclosure** = 失敗を消さない、教訓を memory に残す
- **多側面で書く** = 技術 / 戦略 / 哲学 / 業務応用を毎日並行で発信

## 関連ドキュメント

- llive リポジトリ: <https://github.com/furuse-kazufumi/llive>
- llive CHANGELOG: <https://github.com/furuse-kazufumi/llive/blob/main/CHANGELOG.md>
- llive PROGRESS.md: <https://github.com/furuse-kazufumi/llive/blob/main/docs/PROGRESS.md>
- fullsense ポータル: <https://github.com/furuse-kazufumi/fullsense>
- 同日記事:
  - [QIITA_SUMMARY](./QIITA_SUMMARY.md) — 技術者向け統合
  - [QIITA_GENERAL](./QIITA_GENERAL.md) — 非エンジニア向け統合
  - [01〜11 個別記事](./README.md)

---

> 5 日で v0.1 → v0.7 候補。1 日 1 バージョン以上のペースで進めながら、その都度
> honest disclosure を残す。AI と一緒に開発する時代の研究記録として残します。
