# NAS 週次 Qiita 下書きパイプライン — 設計

- 日付: 2026-08-01
- ブランチ: feat/worklog-orchestration
- スコープ: 素材 → 下書き雛形 → dry-run まで自動。**散文の肉付けと公開は人手**(fail-closed)。
- 定時起動: 本設計はスクリプト一式のみ。cron/schedule への接続は動作確認後に別途。

## 背景と現状資産

前回 NAS r2 全5本を完走し、`llcore/scripts/collect_nas_material.py` が全
`nas_pareto.json` を **numbers only** の `result.md` に集約する仕組みは既にある
(`feedback_benchmark_honest_disclosure` に従い散文は書かない・`still unmeasured`
行を必ず残す)。投稿側は `fullsense/tools/qiita_public_post.py` が
`dry-run`(ローカル検証・トークン不要)/ `preflight`(+ライブAPI・トークン必須)/ `post`
を持つ。

**ギャップ**: 「numbers 素材」→「Qiita 下書き md(frontmatter + 見出し骨組み + 表)」の
橋渡しが無い。ここを埋める。

## 目標 / 非目標

- 目標: 週次で叩けば「dry-run を通る Qiita 下書き md」までを機械生成する。
- 非目標: 散文の自動生成(人間の仕事)。画像の自動添付。live preflight / 実公開。
  定時起動そのもの(cron/schedule 登録は後日)。

## アーキテクチャ(3段チェーン)

| # | コンポーネント | 配置 | 役割 |
|---|---|---|---|
| 1 | `collect_nas_material.py`(既存・不変) | `llcore/scripts` | `nas_pareto.json` 群 → numbers only の `result.md` |
| 2 | **新規 `build_qiita_draft.py`** | `llcore/scripts` | `result.md` → Qiita 下書き md |
| 3 | **新規 週次ラッパ `weekly-qiita-draft`** | `raptor/scripts` | 1→2→dry-run を順に叩く自己完結スクリプト |

各段は独立。1 の出力(`result.md`)が 2 の唯一の入力。2 は
`llcore/scripts/collect_nas_material.py` の出力フォーマットにのみ依存し、
NAS の内部実装には依存しない。

## コンポーネント2: `build_qiita_draft.py`

### 入出力
- 入力: `--material <result.md>`(collect の出力)、`--out <draft.md>`。
- 出力: 下書き md 1本。標準では画像を含まない。

### frontmatter
```yaml
---
title: 'NAS 週次レポート(YYYY-MM-DD) — TODO: 本題'
tags:
  - 機械学習
  - NAS
public_id: null
public_private: false
---
```
- `title` は仮題(人間が差し替え)。ただし空にしない(dry-run の NO TITLE 回避)。
- `tags` は機械語彙で最低1個(dry-run の NO TAGS 回避)。人間が精緻化。
- `public_id: null` = 新規 POST 経路。`public_private: false` = 一般公開既定。

### 本文(見出し骨組み)
```
## 背景
<!-- TODO: 散文(人間) -->

## 手法
<!-- TODO: 散文(人間) -->

## 結果
（collect の numbers を run ごとに表として機械流し込み）

## Honest disclosure
<!-- TODO: 散文(人間) -->
（各 run の "still unmeasured" 行を機械保持）

## Still unmeasured
（still unmeasured を箇条書きで集約・保持）

## 再現
（再現コマンドがあれば numbers 素材から転記）
```

### 不変条件(テストで固定)
1. **numbers 保持**: `result.md` 中の各 run の hypervolume / verdict / CI 等の
   数値が下書きの `## 結果` 表に欠落なく現れる。
2. **still-unmeasured 保持**: 各 run の `still unmeasured` が下書きに残る
   (`feedback_benchmark_honest_disclosure`)。
3. **frontmatter 妥当**: `title` 非空・`tags` ≥1・`public_id: null`・`public_private: false`。
4. **画像ゼロ**: 本文に画像 Markdown / `<img>` を出力しない。
5. **生成物が dry-run pass**: `qiita_public_post.py dry-run <draft.md>` が
   `registration-safe: no findings` を返す。

## コンポーネント3: 週次ラッパ `weekly-qiita-draft`

- 責務: collect(1)→ build(2)→ `dry-run`(検証)を順に実行。
- 各段の非0 exit で即停止し理由を表示。
- dry-run が BLOCKED を返したら: 下書き md は残す・非0 exit で fail 報告
  (公開に進ませない fail-closed)。
- 出力先: `fullsense/docs/articles/drafts/QIITA_nas_weekly.md`(週次で上書き)。
- トークン不要(dry-run のみ・live preflight は使わない)。
- パスは list-arg subprocess で渡す(shell 文字列補間しない)。

## エラー処理 / fail-closed

- 素材が空(run 0 件)→ ラッパは非0 で停止(空記事を作らない)。
- dry-run BLOCKED → 下書きは残すが exit≠0。人間が理由を見て修正。
- 実公開・PATCH は本パイプラインの対象外(人手 `post --yes`)。

## テスト

- `build_qiita_draft.py` の単体テスト(pytest, llcore 側):
  上記 不変条件 1–5 を、小さな合成 `result.md` を入力に検証。
  5 は実際に `qiita_public_post.py dry-run` をサブプロセスで呼ぶか、
  `safety_findings` を import して findings 0 を確認する(トークン不要な後者を優先)。

## 未決 / 後日

- 定時起動(schedule skill の cloud cron / raptor-worklog work-graph のどちらか)。
- live preflight(トークン運用 `QIITA_PUBLIC_TOKEN` の確立後)。
- 画像(グラフ)の生成と raw URL 添付。
