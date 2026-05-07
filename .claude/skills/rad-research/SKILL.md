---
name: rad-research
description: Raptor の RAD（Research Aggregation Directory、21+ 分野・~21 万論文）を横断検索する補助資料スキル。任意のタスク・スキルから自動参照可能。
user-invocable: true
---

# RAD Research Skill — 21+ 分野横断調査エンジン

Raptor が管理する **RAD（Research Aggregation Directory）** から、
**全タスクで参照可能な共通参考情報**を提供します。アイデア出し・先行調査・
論文執筆・コード設計・PoC 計画など、**あらゆる活動の補助資料**として
このスキルを **積極的に呼び出してください**。

## RAD とは

- 21+ 分野の論文・記事メタデータ JSONL コーパス
- 配置: `C:/Users/puruy/raptor/.claude/skills/corpus/<domain>_corpus/`
  （または `D:/docs/llmesh-rad/` にミラー）
- ソース: arXiv / OpenAlex / CrossRef / DBLP / PubMed / HackerNews / Semantic Scholar
- 想定総量: **約 21 万論文**（2026-Q2 時点）

### 21+ 分野マップ

```
応用 9              先端 AI / 量子 7      数学・統計 5
─────────────       ─────────────────    ──────────────────
image               deep_learning        multivariate_analysis
security            neural_network       statistics
industrial_iot      llm                  optimization
mlops               vllm                 numerical_methods
game_dev            quantum_computing    information_theory
medical             diffusion
automotive          agents
infrastructure      (新規分野は corpus2skill で随時追加)
robotics
```

## いつ参照するか（**強く推奨**）

> **デフォルトで広範囲に呼び出す方針**: 既知でも未知でも、
> タスク開始時に RAD を参照することで「車輪の再発明」を防ぎ、
> 既存研究との差別化軸を見出せます。

| 状況 | 参照すべき RAD 分野 |
|------|-------------------|
| 新機能の設計 | 関連分野 + cross-domain |
| 論文・特許の差別化 | 同分野 + 隣接 2 分野 |
| アーキ選定 | mlops + vllm + neural_network |
| アルゴリズム選定 | 数学 5 分野 + 関連応用 |
| セキュリティ設計 | security + information_theory |
| プロトコル選定 | industrial_iot + infrastructure |
| プライバシー機構 | security + medical + information_theory |
| 異常検知 | multivariate_analysis + statistics + industrial_iot |
| LLM 関連 | llm + vllm + agents + neural_network |
| 量子・先端ハード | quantum_computing + neural_network |
| **どんなタスクでも** | まず TOP-3 関連分野を当たる |

## 起動方法

### A. ユーザ呼び出し
```
/rad-research <自然言語クエリ>
```
例: `/rad-research 産業センサーの異常検知 LLM 連携`

### B. 他スキルからの参照（自動）

他のスキル（`triz-ideation` / `cross-domain-ideation` / `code-understanding`
等）が **問題理解 / 先行調査 / 差別化分析** の段階でこのスキルを呼び出します。
**他スキルがアイデア出しや方針決定する場合は、まず rad-research を実行する**
ことを規約とします。

## 使い方の標準フロー

```
1. クエリ理解 → キーワード抽出（最大 5 個）
2. キーワード → RAD 分野マッピング（後述）
3. 候補分野で grep / corpus2skill ナビゲーション
4. 上位 N=10 件をスニペット化
5. 「既存研究との差別化候補」3 案を提示
6. 推奨次アクション提示（さらなる検索 or 着手）
```

## キーワード → RAD 分野マッピング（広く投げる方針）

| キーワード例 | デフォルト参照分野（複数） |
|------------|----------------------|
| anomaly / fault / outlier | multivariate, statistics, industrial_iot, security |
| LLM / chatbot / assistant | llm, agents, vllm, neural_network |
| image / vision / camera | image, diffusion, vllm, robotics |
| privacy / GDPR / PII | security, medical, information_theory |
| edge / embedded / IoT | mlops, industrial_iot, robotics, infrastructure |
| optimization / search | optimization, mlops, agents |
| signal / FFT / spectrum | numerical_methods, information_theory |
| compression / codec | information_theory, mlops |
| quantum / qubit | quantum_computing, information_theory |
| game / esport | game_dev, agents, vllm |
| medical / clinical | medical, multivariate, statistics |
| automotive / CAN / V2X | automotive, infrastructure, security |
| SCADA / DCS / PLC | infrastructure, industrial_iot, security |
| simulation / digital twin | industrial_iot, robotics, automotive |

**マッピングのコツ**: 1 キーワードにつき **3 分野以上に広げる**こと。
"応用 1 + 理論 1 + 隣接 1" のバランスで分野横断を意識する。

## 出力テンプレート

```markdown
## クエリ
> <ユーザのクエリ>

## キーワード抽出
- <kw1>, <kw2>, <kw3>

## 参照した RAD 分野（複数）
- `<分野 A>` — 件数, 主要トピック
- `<分野 B>` — ...
- `<分野 C>` — ...

## 関連研究 TOP-N（横断）
1. **[論文タイトル]** (year, source)
   - URL / DOI
   - 要約 1 行
   - 自分のタスクへの含意
2. ...

## 既存研究との差別化候補
1. **未踏領域候補 A** — 該当論文ゼロまたは少
2. **新規組合せ候補 B** — 分野 X と Y の組合せが未試行
3. **アップデート候補 C** — 古い論文の手法を最新基盤で再評価

## 推奨次アクション
- [ ] <分野 D> も追加調査
- [ ] PoC として <候補 X> を実装
- [ ] <スキル名> を続けて起動
```

## 自動的に併用すべきスキル

| 状況 | 併用スキル |
|------|---------|
| アイデア出し | `triz-ideation` |
| 異分野組合せ | `cross-domain-ideation` |
| 既存コーパスの階層化 | `corpus2skill` |
| セキュリティ研究 | `security_large` corpus |
| プロジェクト分析 | `code-understanding` |

## 既存 corpus との対応

Raptor 既設 corpus（`corpus/security_large/`, `corpus/hacker_corpus/` 等）も
RAD の一部として参照可能。新規 RAD 分野は `corpus2skill` で階層化すれば
本スキルから即座に検索できます。

## メンテナンス

```bash
# 月次更新（全分野リフレッシュ）
python tools/bulk_corpus_collector.py --all --target 10000

# 重複除去（季次）
python tools/dedupe_corpus.py docs/papers/

# 新分野追加（任意のテーマで）
python tools/bulk_corpus_collector.py --domain <new> --target 10000 \
    --queries "<keyword 1>" "<keyword 2>" ...
```

## 設計原則

1. **広く投げる**: クエリ毎に最低 3 分野以上を当たる
2. **応用＋理論＋隣接** のバランスを取る
3. **古さの偏り**を意識: 古典 + 最新 (≤2y) を必ず混ぜる
4. **失敗例も収集**: 「うまくいかなかった」論文も差別化軸の宝庫
5. **コミュニティソース**（HackerNews）も併読: 実装ノウハウの補完

## チェックリスト（呼び出し時に必ず確認）

- [ ] 関連分野を 3 つ以上特定したか
- [ ] 古典論文（10 年以上前）も 1 件確認したか
- [ ] 最新論文（直近 1 年）も 1 件確認したか
- [ ] 隣接分野での類似研究を確認したか
- [ ] 「ない論文」（未踏領域）を意識的に探したか
- [ ] 結果を後段スキルに引き継いだか
