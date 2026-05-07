---
name: triz-ideation
description: TRIZ-based ideation skill — 40 inventive principles, 39×39 contradiction matrix, ARIZ algorithm, and 9-windows. Combines with RAD corpus for evidence-grounded ideas.
user-invocable: true
---

# TRIZ Ideation Skill

**TRIZ**（Theory of Inventive Problem Solving、発明的問題解決理論）に基づく
体系的アイデア出し支援。Raptor の RAD（Research Aggregation Directory、
21 分野・約 21 万論文）と連動させ、**抽象原理**と**実例**を行き来しながら
新しい解決策を導きます。

## いつ使うか

- 設計上のトレードオフ（**矛盾**）に行き詰まっている
- 既存技術の組合せで新規性のあるアイデアを探したい
- 異分野の手法を借用して問題を解きたい
- 特許出願前の先行技術調査と発想の補強
- 研究テーマの差別化ポイントを探したい

## 起動

```
/triz-ideation [problem statement]
```

例: `/triz-ideation 産業センサーの異常検知精度を上げると false positive が増える`

## 使う 4 つのツール

### 1. 40 の発明原理（Inventive Principles）

汎用的な発明アイデアの "頻出パターン" 40 種を、対象問題に当てはめてみる。

| # | 原理 | 例 |
|---|------|----|
| 1 | 分割（Segmentation） | モノリスをモジュール化 |
| 2 | 引き出し（Extraction） | 邪魔な要素を分離 |
| 3 | 局所的性質（Local Quality） | 場所別に最適化 |
| 4 | 非対称化（Asymmetry） | 対称を崩す |
| 5 | 統合（Merging） | 別物を一体化 |
| 6 | 多用途化（Universality） | 1 つで複数役割 |
| 7 | 入れ子（Nested Doll） | A の中に B |
| 8 | 釣り合い（Anti-Weight） | 反対の力で打ち消す |
| 9 | 先取り反作用（Preliminary Anti-Action） | 副作用を先に消す |
| 10 | 先取り作用（Preliminary Action） | 必要前に処置 |
| 11 | 緩衝（Cushioning） | 失敗時の備え |
| 12 | 等ポテンシャル（Equipotentiality） | 高低差をなくす |
| 13 | 逆転（The Other Way Around） | 反対にする |
| 14 | 球面化（Spheroidality） | 直線→曲線 |
| 15 | 動性化（Dynamicity） | 静→動 |
| 16 | 部分的に（Partial Action） | 多くも少なくも |
| 17 | 多次元化（Another Dimension） | 1D→2D→3D |
| 18 | 振動（Vibration） | 振動を加える |
| 19 | 周期化（Periodic Action） | 連続→周期 |
| 20 | 有用作用継続（Continuity of Useful Action） | 休みなし |
| 21 | 高速化（Hurrying） | 速くやり過ぎる |
| 22 | 災い転じて福（Convert Harm into Benefit） | 害を利用 |
| 23 | フィードバック（Feedback） | 出力を入力に戻す |
| 24 | 仲介（Mediator） | 中継者を入れる |
| 25 | セルフサービス（Self-Service） | 対象に作業させる |
| 26 | コピー（Copying） | 安価な複製 |
| 27 | 使い捨て（Cheap Short-Living） | 高耐久より使い捨て |
| 28 | 機械系の置換（Mechanics Substitution） | 物理→電気→光 |
| 29 | 流体（Pneumatics & Hydraulics） | 気体・液体に置換 |
| 30 | 柔らかい膜（Flexible Shells） | 硬い→柔らかい |
| 31 | 多孔質（Porous Materials） | 空隙を持たせる |
| 32 | 色変化（Color Change） | 視認性を上げる |
| 33 | 同質性（Homogeneity） | 似たものを使う |
| 34 | 排除と再生（Discarding & Recovering） | 使い捨て＋再生 |
| 35 | パラメータ変化（Parameter Changes） | 状態を変える |
| 36 | 相変化（Phase Transitions） | 固/液/気の遷移 |
| 37 | 熱膨張（Thermal Expansion） | 温度差利用 |
| 38 | 強い酸化剤（Strong Oxidants） | 反応を促進 |
| 39 | 不活性雰囲気（Inert Atmosphere） | 反応を抑制 |
| 40 | 複合材料（Composite Materials） | 異素材組合せ |

### 2. 矛盾マトリクス（Contradiction Matrix）— 39×39

「**改善したい特性 X** vs **悪化する特性 Y**」の交点に、有効な発明原理が
推奨されます。本スキルでは以下の **39 工学的特性**で矛盾を表現:

```
1.  動体の重量          21. 動力
2.  静体の重量          22. エネルギーの損失
3.  動体の長さ          23. 物質の損失
4.  静体の長さ          24. 情報の損失
5.  動体の面積          25. 時間の損失
6.  静体の面積          26. 物質の量
7.  動体の体積          27. 信頼性
8.  静体の体積          28. 測定精度
9.  速度                29. 製造精度
10. 力                  30. 物体への有害要因
11. 応力・圧力          31. 有害な副作用
12. 形                  32. 製造容易性
13. 物体の安定性        33. 操作容易性
14. 強度                34. 修理容易性
15. 動体の耐久性        35. 適応性・多用途性
16. 静体の耐久性        36. 装置の複雑さ
17. 温度                37. 制御の困難さ
18. 明るさ              38. 自動化のレベル
19. 動体の使用エネルギー 39. 生産性
20. 静体の使用エネルギー
```

例: 「精度（28）を上げたいが製造容易性（32）が悪化する」→ 推奨原理:
**1（分割）, 32（色変化）, 35（パラメータ変化）, 28（機械系の置換）**

### 3. ARIZ（発明的問題解決アルゴリズム）9 ステップ

1. **問題分析** — 何を改善したいか
2. **問題のモデル化** — 図式化
3. **理想最終結果**（IFR）の定義
4. **物理的矛盾**の特定（時間/空間/条件で分離）
5. **資源**の洗い出し（時間・空間・物質・場・情報）
6. **過去の発明標準解**の適用
7. **物理効果ライブラリ**の参照
8. **解の評価**
9. **解の発展と適用**

### 4. 9 画法（System Operator）— 多視点で問題を捉える

|         | 過去 | 現在 | 未来 |
|---------|------|------|------|
| **上位系** | 上位系の歴史 | 現在の上位系 | 上位系の未来 |
| **対象系** | 対象の歴史 | 現在の対象 | 対象の未来 |
| **下位系** | 下位系の歴史 | 現在の下位系 | 下位系の未来 |

→ 9 つの視点から発想を広げる。

## TRIZ × RAD 連携手順（推奨フロー）

```
1. ユーザの問題文を分析
   ↓
2. 矛盾を 39 特性に翻訳 → 推奨原理 N 個を取得
   ↓
3. 各原理に対応する **RAD 分野** をピックアップ
   （例: 原理 1「分割」→ "agents", "industrial_iot" など分野横断）
   ↓
4. RAD コーパスから関連論文をサンプリング（実例）
   ↓
5. 抽象原理 × 実例 を結合した解候補を 5-10 個提示
   ↓
6. 各候補に対し ARIZ Step 8（評価）を実施
   ↓
7. 上位 3 件を IFR との整合性で並び替え
```

## 出力フォーマット（推奨）

```markdown
## 問題分析
- 改善したい: <特性名>
- 悪化する:  <特性名>
- 物理的矛盾: <ある/ない>
- 理想最終結果（IFR）: <目標状態>

## 適用する TRIZ 原理（矛盾マトリクスから）
1. **原理 #X** — <原理名>
   - RAD 関連分野: <分野>
   - 既存研究: <論文タイトル + URL>
   - 適用案: <問題への翻訳>
2. ...

## 9 画法での発想拡張
| 過去 | 現在 | 未来 |
|------|------|------|
|...|

## アイデア候補（5-10 個）
1. **アイデア A**
   - 適用原理: #X, #Y
   - 既存研究との差別化: <gap>
   - 想定実装難度: ★☆☆ / ★★☆ / ★★★
2. ...

## 推奨ネクストアクション
1. <優先候補> の PoC 設計
2. RAD `<分野>` の追加調査
3. ...
```

## RAD 分野マッピング（参考）

問題のキーワードから検索すべき RAD 分野へのマッピング:

| キーワード | 候補分野（Raptor `.claude/skills/corpus/` 配下） |
|-----------|---------------------------------------|
| 異常検知 | multivariate_analysis, statistics, industrial_iot |
| 高速化 | mlops, vllm, numerical_methods, optimization |
| 分割・モジュール化 | agents, robotics |
| 適応・学習 | deep_learning, neural_network, llm |
| 通信・データ | information_theory, security |
| 物理現象応用 | quantum_computing, automotive |
| 画像処理 | image, diffusion, vllm |
| プライバシー | security, medical, infrastructure |

## チェックリスト

- [ ] 矛盾を 39 特性で表現できたか
- [ ] 矛盾マトリクスの推奨原理を確認したか
- [ ] 各原理について RAD で実例を確認したか
- [ ] IFR を明確に書けたか
- [ ] 物理的矛盾の場合、分離原理（時間/空間/条件）を試したか
- [ ] 9 画法で時間軸（過去・未来）も検討したか
- [ ] アイデア間で原理の重複を確認したか

## 参考文献

TRIZ の詳細は [Wikipedia: TRIZ](https://en.wikipedia.org/wiki/TRIZ) や
Genrich Altshuller の原典を参照。本スキルは TRIZ の核となる
40 発明原理・39×39 マトリクス・ARIZ・9 画法を、Raptor の RAD（21 分野
コーパス）と組み合わせて運用する点が独自。

---

**併用推奨スキル**:
- [`rad-research`](../rad-research/SKILL.md) — 21 分野 RAD 横断調査
- [`cross-domain-ideation`](../cross-domain-ideation/SKILL.md) — 異分野横断発想
- [`corpus2skill`](../corpus2skill/SKILL.md) — 新コーパスの階層化
