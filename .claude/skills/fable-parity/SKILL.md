---
name: fable-parity
description: |
  Opus など Fable 未満のモデルで走っているとき、1 回の深い推論に頼る代わりに
  オーケストレーション(並列 attempt + 敵対的検証 + 統合)を「消費」して
  Fable 級の出力品質を取り戻すための scaffold 集。6 つの Workflow を用途別に
  提供する。Auto-trigger when: 難問・高stakes(誤りが高コスト/後段に波及/巻き戻し困難)な
  reasoning・research・planning・検証タスクに着手するとき、ユーザーが「最高品質で」
  「fable-parity」「Fable 級」を発話したとき。★trivial/lookup/既知ファイル編集など
  容易なタスクでは起動しない(オーバーヘッドの無駄)。
user-invocable: true
auto-trigger: true
related_skills:
  - superpowers:brainstorming
  - superpowers:systematic-debugging
  - superpowers:dispatching-parallel-agents
  - doublecheck
  - rad-research
related_memory:
  - feedback_parallel_first_execution
  - feedback_definition_of_done_real_path
  - feedback_benchmark_honest_disclosure
---

# fable-parity — オーケストレーションで per-pass 知能差を買い戻す

## 何を解く skill か

強いモデル(Fable 5, Mythos-class, Opus 超)が弱いモデル(Opus)に勝つのは、
主に **1 パスあたりの推論の深さ・自己検証・探索幅** による。この per-pass の差は、
Opus 側で **オーケストレーションを消費** すれば買い戻せる — 問題を分解し、多様な attempt を
並列に走らせ、敵対的に検証し、最良部分を接ぎ木して統合する。その乗り物が Workflow tool。
本 skill はこの手口を再利用可能な scaffold として 6 本に固めたもの。**新しい能力は生まない**
(=モデルが 1 パスで到達不能な事実・推論ステップは復元できない)。買えるのは信頼性と自己検証。

## いつ使うか / ゲート

**デフォルトは「直接答える」。** scaffold は token と(並列系は)wall-clock を数倍にする。
起動は次の 3 条件を **すべて** 満たす hard / high-stakes タスクに限る:

1. **Stakes** — 誤りが高コスト(ユーザーに出る/意思決定を駆動/巻き戻し困難/後段で誤りが複利)。
2. **Single-pass risk** — 直接 1 パスでは浅く/誤りやすい(長い依存連鎖・広い解空間・claim 過多の主張・遠い horizon の計画)。
3. **利用可能な非対称性** — 候補の検証/選別/反証が生成より安い(テスト・validator・executor・retrievable な出典、最低でも clean context での独立 adversarial re-read)。検証が生成と同じだけ難しいなら scaffold は base rate に劣化する。

**起動しない:** trivial/mechanical/lookup(既知ファイル編集・定義・確信ある一行recall)、
一目で自明に検証可能なもの、純粋な知識/事実ギャップ(sampling は情報を増やさない → retrieval/tools が正解。
例外は実際に検索する `research-synthesize` のみ)。詳細な判定は `references/routing.md` の Gate 0/1。

## ルーティング表(task shape → workflow → 一言)

| task shape | workflow(file / args) | 一言 |
|---|---|---|
| 単一の難問・導出・分析で、1 パスの Opus では浅い/誤りやすい | **deep-reason** — `workflows/deep-reason.js` / `{ task: string, context?: string, attempts?: number (default 3) }` | 分解 → N 個の多様な独立 attempt を並列 → 各を敵対的検証 → 最強部分を接ぎ木して統合 |
| draft の回答/finding があり、出荷前に Fable 級の自己検証をかけたい | **adversarial-verify** — `workflows/adversarial-verify.js` / `{ answer?: string, claims?: string[], context?: string, voters?: number (default 3) }` | 荷重 claim を抽出 → claim ごとに N 人の独立 skeptic を「反証せよ(不確実なら反証扱い)」で spawn → 多数決 → 生存 claim + 反証 claim(理由付き)+ 修正版回答 |
| breadth と citation が要る open な research / survey / prior-art | **research-synthesize** — `workflows/research-synthesize.js` / `{ question: string, depth?: "quick" \| "standard" \| "deep" (default standard) }` | 多モードで検索 fan-out(各 agent が別の探し方)→ dedup → 上位 source を deep-read → completeness critic loop → 出典付き統合 |
| 解空間が広く、初稿の計画では角度を見落とす design/実装計画 | **plan-critique** — `workflows/plan-critique.js` / `{ goal: string, constraints?: string, candidates?: number (default 3) }` | N 個の多様な候補計画(別 framing)を生成 → judge panel が複数レンズで採点 → 勝者を統合しつつ runner-up の良案を接ぎ木 → 敵対的な risk/edge-case pass |
| research の答えを **行動に使う** / 各 claim を一次情報で検証したい(cited だけでは不足) | **research-verify** — `workflows/research-verify.js` / `{ question: string, depth?: "quick"\|"standard"\|"deep", voters?: number (default 2), max_claims?: number (default 6) }` | research-synthesize を実行 → 荷重 claim 抽出 → 各 claim を一次/独立情報で反証試行 → CONFIRMED/REFUTED/UNCERTAIN 採点付きの修正版レポート(research-synthesize + adversarial-verify の合成) |
| **実行する計画**で、暗黙の前提(feature 存在/API 対応/可逆性/依存の可用性/上限値)が誤れば壊れる | **plan-verify** — `workflows/plan-verify.js` / `{ goal: string, constraints?: string, candidates?: number (default 3), voters?: number (default 2), max_assumptions?: number (default 6) }` | plan-critique で計画 → 荷重 assumption 抽出 → 各を一次/独立情報で反証検証 → REFUTED は blocker/計画変更・UNCERTAIN は「着手前に検証」に畳み込んだ hardened plan + assumption 台帳(plan-critique + adversarial-verify の合成) |
| draft の claim を **Opus と別の model 系列**で反証したい(Opus 一色の検証は共有重みの盲点で誤答を通す) | **adversarial-verify-ext** — `workflows/adversarial-verify-ext.js` / `{ answer?: string, claims?: string[], context?: string, opus_voters?: number (default 2) }` | claim 抽出 → 各 claim を Opus skeptic **と** 外部非Opus系列(OpenAI Codex/gpt-5.4 経由 `bin/ext_verify.py`)の両方で反証 → いずれかが反証で refuted・`external_only_catches` に「外部だけが捕捉」を可視化(de-correlation が本体) |

per-token の安い順に手を出す: 直接回答 < `deep-reason`(低 `attempts`)< 単発 `adversarial-verify`
< decomposition/research < 重い多候補 planning。**最初から最重量を開かない。**

## Opus での起動方法

前提: session model が **Opus**(`/model opus` で切替、`/model` で確認)。手順の正本は
`references/usage-on-opus.md`。各 workflow は Workflow tool に **`scriptPath`(絶対パス)** と
**`args`(下記の契約 shape)** を渡して起動する(Workflow tool は opt-in)。1 例:

```
Workflow tool
  scriptPath: D:/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js
  args: {
    "task": "Derive the worst-case tail-latency bound for our token-bucket rate limiter under bursty arrivals, then check it against the leaky-bucket variant and state which is tighter and why.",
    "context": "Bucket size B=200, refill r=50/s, arrivals bursty up to 500. We care about p99.9, single-node.",
    "attempts": 3
  }
```

## workflow 一覧（7 本）

- **deep-reason** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/deep-reason.js` — `{ task: string, context?: string, attempts?: number (default 3), external_verify?: boolean (default true) }` — 汎用ハード推論の底上げ(分解 → 並列多様 attempt → 各敵対検証 → 統合)。`external_verify`(既定 ON)は各 attempt の結論を独立 non-Opus 系列(Codex)で追加反証し、Opus 自己検証の相関盲点を塞ぐ(外部反証 attempt を synthesis 先頭に立たせない/`external_summary.external_only_catches` に「Opus は通したが外部が捕捉」)。`false` で従来挙動、codex 不在・relay 失敗は no-op で degrade。
- **adversarial-verify** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/adversarial-verify.js` — `{ answer?: string, claims?: string[], context?: string, voters?: number (default 3) }` — 後付けの検証(claim 抽出 → 反証 default の独立 skeptic 多数決 → 修正版回答)。
- **research-synthesize** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/research-synthesize.js` — `{ question: string, depth?: "quick" | "standard" | "deep" (default standard) }` — 検索 fan-out → dedup → deep-read → completeness critic → 出典付き統合。
- **plan-critique** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/plan-critique.js` — `{ goal: string, constraints?: string, candidates?: number (default 3) }` — 多候補計画 → judge panel → 勝者統合+良案接ぎ木 → 敵対的 risk/edge-case pass。
- **research-verify** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/research-verify.js` — `{ question: string, depth?: "quick" | "standard" | "deep" (default standard), voters?: number (default 2), max_claims?: number (default 6), external_verify?: boolean (default true) }` — **高保証 research**(research-synthesize + adversarial-verify の合成)。探索 → 荷重 claim 抽出 → 各 claim を一次/独立情報で反証検証 → CONFIRMED/REFUTED/UNCERTAIN 採点付きの修正版レポート。cited だけでは不足で、答えを行動に使う時。`external_verify`(既定 ON)=独立 non-Opus 系列(Codex)で各 claim を追加反証、**downgrade-only**(外部反証は CONFIRMED→UNCERTAIN に格下げのみ、tool-less な外部の survives で格上げしない)、`external_dissent` で「Opus は confirmed だが外部が反証」を可視化。
- **plan-verify** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/plan-verify.js` — `{ goal: string, constraints?: string, candidates?: number (default 3), voters?: number (default 2), max_assumptions?: number (default 6) }` — **検証付き計画**(plan-critique + adversarial-verify の合成)。計画 → 荷重 assumption 抽出 → 一次/独立情報で反証検証 → REFUTED は blocker/計画変更・UNCERTAIN は「着手前に検証」に畳み込んだ hardened plan + assumption 台帳。実行する計画で前提の誤りが高コストな時。plan-critique 内蔵の pre-mortem(内省)が届かない「前提の外部接地」を補う。
- **adversarial-verify-ext** — `D:/tools/raptor/.claude/skills/fable-parity/workflows/adversarial-verify-ext.js` — `{ answer?: string, claims?: string[], context?: string, opus_voters?: number (default 2) }` — **異系列(heterogeneous)検証**。claim を Opus skeptic **と** 独立の非Opus系列(OpenAI Codex/gpt-5.4)で並列に反証し、いずれかが反証すれば refuted。`external_only_catches` に「Opus だけなら通っていたが外部系列が捕捉した」claim を出す。共有重みの相関盲点(2026-07-05 baseline で実証: Opus 一色の合成が degenerate 出力を出荷)への対策。外部呼び出しは `bin/ext_verify.py`(単発)/`bin/ext_verify_batch.py`(並列集約)— どちらも refute-by-default・fail-closed(infra 失敗は `unverified` で pass 扱いしない)。Codex 実働確認済(2026-07-05)、Gemini は GCP 認証が要り現状 fallback。

## 正直な限界

この skill は Fable/Opus のギャップを **原理的な根拠**(test-time compute + 独立検証)で
埋めるよう **設計** されている。しかし **測定済みの parity ベンチマークは同梱していない**。
Opus+scaffold が実際に Fable の 1 パスと同等だと **測ったわけではない**。したがって
「parity に達した」と、実際に測っていないのに **決して主張しない**(user memory の
`feedback_benchmark_honest_disclosure` / verify-existence-before-claiming に一致)。
自分のワークロードで parity を実測する手順は `eval/parity-eval.md` を参照。
**parity が失敗する箇所は失敗として報告し、平均で薄めない。** 復元不能なもの(欠落した知識・事実、
coverage floor 未満の答え、非対称性のない verification-hard タスク、共有重みの系統誤差、
真に新規な推論ステップ)は `references/principles.md` の non-recoverable を参照。

## 関連

- `[[skill: superpowers:brainstorming]]` — 発想・要件探索(plan-critique の前段)
- `[[skill: superpowers:systematic-debugging]]` — バグ/失敗の体系デバッグ
- `[[skill: superpowers:dispatching-parallel-agents]]` — 並列 fan-out の機構(再文書化しない)
- `[[skill: doublecheck]]` — 出力の内容正しさ検証(adversarial-verify と補完)
- `[[skill: rad-research]]` — RAD corpus から prior-art/文脈注入(知識ギャップ半分を埋める)
- `[[memory: feedback_parallel_first_execution]]` — 独立タスクは Agent 並列既定
- `[[memory: feedback_definition_of_done_real_path]]` — 完了=実経路 e2e + 多視点 + レビュー
- `[[memory: feedback_benchmark_honest_disclosure]]` — 異常に良い結果は内訳を疑う(honesty の背骨)
- `references/routing.md` — Gate 0/1 と per-archetype tier map
- `references/usage-on-opus.md` — Opus での操作手順(正本)
- `references/always-on.md` — Opus を「常時ゲート評価つき自動ルーティング」で走らせる 3 層セットアップ(`UserPromptSubmit` gate hook + `FABLE_PARITY_ALWAYS` トグル)。無条件常時オーケストレーションは ceiling-effect で有害なので採らない
- `references/principles.md` — recoverable/non-recoverable の原理
- `eval/parity-eval.md` — parity を実測する手順(唯一の測定の正本)
