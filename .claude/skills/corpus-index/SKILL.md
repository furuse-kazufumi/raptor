---
name: corpus-index
description: |
  raptor の corpus skill 階層 (`.claude/skills/corpus/<source>/cluster_*/.../SKILL.md`、
  80+ sources / 4000+ files) のフラット横断インデックス
  (`.claude/skills/corpus/INDEX.md`) を再生成する。Auto-trigger when:
  ユーザーが「corpus index」「全 corpus 一覧」「コーパス横断」を発話、
  または corpus を拡張・剪定した直後。corpus2skill の post-step で自動
  呼び出されるため通常は手動不要。
related_skills:
  - corpus2skill
related_memory: []
---

# corpus-index — corpus 階層のフラット横断インデックス

## 何を解く skill か

corpus2skill は corpus ごとに `<name>/INDEX.md` (per-corpus) を生成するが、
**80+ corpus 全体を見渡したい** 場面では別途フラット index が要る。
本 skill は `.claude/skills/corpus/INDEX.md` を再生成し、
`(source, clusters, total SKILL.md count, description)` を 1 表に集約する。

## 入力前提

- raptor リポジトリ root にいる (cwd)
- `.claude/skills/corpus/` 配下に corpus2skill 生成物が存在

## 手順

### 1. 直接実行

```bash
python3 libexec/raptor-corpus-index
```

最終行に `Wrote .claude/skills/corpus/INDEX.md: <N> sources, <M> SKILL.md files`
が出ることを確認。

### 2. corpus2skill 経由 (自動)

`python3 raptor.py corpus2skill` を実行すると、ジョブ完了直後に
`raptor-corpus-index` が自動呼び出しされ INDEX.md が refresh される
([[skill: corpus2skill]] の post-step を参照)。

### 3. 結果確認

`.claude/skills/corpus/INDEX.md` を開き、追加した corpus が
- "Sources overview" 表に行が増えている
- "Cluster index" 節に該当 source のセクションがある

を確認。

## 出力

| ファイル | 内容 |
|---|---|
| `.claude/skills/corpus/INDEX.md` | 全 corpus の横断インデックス (上書き) |

## チェックリスト

- [ ] `python3 libexec/raptor-corpus-index` が exit 0 で終わる
- [ ] INDEX.md の `<N> sources` が現在の corpus 数と一致
- [ ] 新規 corpus が "Sources overview" に出る
- [ ] description 欄が `(no description)` の corpus は per-corpus
      `INDEX.md` か top-level `SKILL.md` を整備したか検討

## 注意 / 落とし穴

- このスクリプトは破壊的 (上書き) — git で差分を見て予期せぬ corpus 消失が
  ないか確認する
- description はトップレベル SKILL.md の frontmatter `description:` から
  読む。per-corpus は corpus2skill 生成の `<name>/INDEX.md` を別途参照
- 4000+ SKILL.md の rglob が遅い場合がある (Windows で 5-10 秒程度)

## 関連

- `[[skill: corpus2skill]]` — corpus 生成側 (post-step で本 skill を呼ぶ)
- `libexec/raptor-corpus-index` — スクリプト本体
- `.claude/skills/corpus/INDEX.md` — 出力先
