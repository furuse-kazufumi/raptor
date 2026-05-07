---
name: cross-domain-ideation
description: 異分野横断アイデア出し — RAD 21+ 分野から離れた組合せをサンプリングして既知の手法を別分野に転用する発想を生成。AUTO-TRIGGER when ユーザが「異分野」「他分野」「cross-domain」「interdisciplinary」「別の業界」「他の領域」「分野を超えて」「転用」「borrowing from」と発話したとき / triz-ideation の資源探索段階 / 主分野で行き詰まり別分野からのヒントを求めるとき。triz-ideation と併用推奨。
user-invocable: true
auto-trigger: true
---

# Cross-Domain Ideation Skill

**異分野横断発想**支援スキル。Raptor の RAD（21+ 分野）から、
「分野 A の手法を分野 B に持ち込む」という **転用型イノベーション**を
体系的に生成します。

## いつ使うか

- 既存分野で手詰まり → 他分野からヒントが欲しい
- 新規研究テーマの着想
- 特許・論文の差別化軸の発見
- TRIZ で「資源（Resource）」の探索段階に入ったとき

## 起動

```
/cross-domain-ideation [problem statement]
```

## 標準フロー

```
1. 問題 P の主分野 D_main を特定
2. 隣接 2 分野 + 遠隔 2 分野（合計 4-5 分野）を選定
3. 各分野で「P と類似の課題」を 5-10 件 RAD から抽出
4. 「分野 X の手法 → P に転用」型のアイデアを生成
5. 評価軸（実装難度、新規性、影響度）でスコアリング
6. 上位 3 候補を提示
```

## 4 つの転用パターン

### パターン A: **手法転用**（Method Transfer）
分野 X で確立した手法を分野 Y へ
- 例: 量子情報の符号 → 産業 IoT のエラー訂正
- 例: 拡散モデル → ロボット動作生成

### パターン B: **目的転用**（Purpose Re-application）
A 用に作られた仕組みを B のために
- 例: ゲームの procedural generation → 工場レイアウト最適化
- 例: 医療画像の DICOM スクラビング → ゲームテレメトリの個人情報除去

### パターン C: **抽象化転用**（Abstraction）
A の根本原理を抽出し別領域へ
- 例: 統計 SPC → LLM 応答品質モニタリング
- 例: 多変量解析 → ビル管理 BMS の異常検知

### パターン D: **逆転発想**（Reverse Application）
A の弱点を逆手に取って B で使う
- 例: 拡散モデルのノイズ → プライバシー保護のためのノイズ付与

## 「遠隔分野」選定の指針

主分野からの "距離" を測る簡易ヒューリスティック:

| 主分野 | 隣接（近い） | 遠隔（遠い） |
|-------|------------|------------|
| industrial_iot | infrastructure, automotive | game_dev, diffusion |
| llm | agents, neural_network | quantum_computing, infrastructure |
| medical | image, multivariate_analysis | game_dev, robotics |
| security | information_theory | game_dev, medical |
| robotics | automotive, image | medical, statistics |

**意図的に離れた分野を 1〜2 個含める**ことで、ありきたりな組合せを
避けて新規性を確保します。

## 出力テンプレート

```markdown
## 課題
> <ユーザの問題>

## 主分野 + 周辺分野
- 主分野: <X>
- 隣接: <A>, <B>
- 遠隔: <C>, <D>

## 各分野からの転用候補

### 分野 A — <分野名>
- 手法: <手法名>（出典: arXiv:..., year）
- 転用案: <P へどう適用するか>
- 適用難度: ★☆☆ / ★★☆ / ★★★

### 分野 B — ...

## 上位 3 案（スコア順）
1. **アイデア X**（新規性 ★★★ / 実現性 ★★☆ / 影響度 ★★★）
   - 採用パターン: <A〜D のいずれか>
   - 実装ステップ: 1) ... 2) ... 3) ...
   - リスク: ...
2. ...

## 推奨アクション
- [ ] <候補 1> の文献詳細を rad-research で深掘り
- [ ] PoC スケッチ作成
- [ ] triz-ideation で矛盾解析を実施
```

## チェックリスト

- [ ] 隣接分野 2 つに加えて遠隔分野 2 つを参照したか
- [ ] パターン A/B/C/D の全 4 種類を試したか
- [ ] 各候補に具体的な出典 RAD 論文があるか
- [ ] 「明らかに無理」な案も 1 つは出したか（発想広げ）
- [ ] 結果を triz-ideation や rad-research に引き継いだか

## 連携スキル

- [`rad-research`](../rad-research/SKILL.md) — 各分野の論文取得
- [`triz-ideation`](../triz-ideation/SKILL.md) — 矛盾解析
- [`corpus2skill`](../corpus2skill/SKILL.md) — 新分野の階層化
- [`gsd-explore`](../gsd-explore/SKILL.md)（GSD 系） — Socratic 調査
- [`superpowers:brainstorming`](../superpowers/brainstorming/SKILL.md) — ブレスト補助

## 設計原則

1. **明示的に「遠い」分野を含める** — 安全策で隣接ばかり選ばない
2. **論文出典を必ず添付** — RAD で検証可能
3. **ばかげた案を 1 つは出す** — クリエイティブ発想の安全弁
4. **スコアリングは 3 軸**（新規性/実現性/影響度）
5. **次アクションを具体化** — アイデア出しで終わらせず PoC へ繋ぐ
