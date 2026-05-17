---
name: skill-governance
description: |
  raptor 配下の SKILL.md 群を標準テンプレ
  (`.claude/skills/_meta/SKILL_TEMPLATE.md`) に揃え、新規 skill 作成時も
  同じ構造を踏襲できるようにする governance skill。
  `libexec/raptor-new-skill` (生成) と `libexec/raptor-skill-lint` (検査) を
  併用する。Auto-trigger when: ユーザーが「新しい skill」「skill 標準化」
  「skill lint」「SKILL.md 作成」を発話、または新規 skill を追加する直前。
related_skills:
  - corpus-index
  - corpus2skill
---

# skill-governance — SKILL.md 標準化フレームワーク

## 何を解く skill か

raptor には 78 以上 (+ corpus 4000+ 自動生成) の SKILL.md が混在し、
作成時期と vendor が違うため frontmatter / セクション構成がバラバラ。
新規 skill を「同じ構造で踏襲」できる規律をスクリプト + テンプレで強制する。

## 構成要素

| 役割 | 場所 |
|---|---|
| **テンプレ** | `.claude/skills/_meta/SKILL_TEMPLATE.md` |
| **生成スクリプト** | `libexec/raptor-new-skill <name> [--scope project|global] [--type workflow|reference]` |
| **lint スクリプト** | `libexec/raptor-skill-lint [path] [--skip-corpus] [--quiet]` |
| **本 meta skill** | `.claude/skills/_meta/SKILL.md` (この文書) |

## 新規 skill 作成手順

### 1. ジェネレータで雛形を作る

```bash
python3 libexec/raptor-new-skill observe-cycle \
    --description "<1-3 行でこの skill が解く問題と auto-trigger 条件>" \
    --type workflow
```

オプション:
- `--scope project` (default) — raptor 配下 `.claude/skills/<name>/SKILL.md`
- `--scope global` — `~/.claude/skills/<name>/SKILL.md`
- `--type workflow` — 手順実行型 (e.g. observe-cycle, add-grounding-channel)
- `--type reference` — 参照型 (e.g. rad-research, claude-api)
- `--force` — 既存上書き

### 2. SKILL.md 本文を編集

テンプレに従って:
- `## 何を解く skill か` — 2-4 行、なぜこの skill が要るか
- `## 入力前提` — 必要なファイル / 環境 / 状態
- `## 手順` — 番号付きステップ + 具体コマンド
- `## 出力` — 生成ファイル / 副作用 / commit 内容
- `## チェックリスト` (任意) — 確認項目
- `## 注意 / よくある落とし穴` — 限界・注意点
- `## 関連` — `[[skill: name]]`, `[[memory: slug]]`, file path

### 3. lint で検証

```bash
python3 libexec/raptor-skill-lint .claude/skills/<name>/SKILL.md
```

exit code:
- `0` — issues 無し
- `1` — hard issue (frontmatter `name` / `description` 欠落)
- `2` — soft issue (recommended section 欠落のみ)

### 4. (将来) git commit

```bash
git add .claude/skills/<name>/SKILL.md
git commit -m "feat(skills): <name> skill 追加 — <一行説明>"
```

## 既存 SKILL.md の改善

新規 skill は本フレームワークで一貫化。**既存の vendor skill** (gsd-*,
SecOpsAgentKit, structured-autonomy-*, arize-* 等) は触らない方針:
- vendor 由来の SKILL.md は独自テンプレに従っており、書き換えると上流
  追随コストが発生
- lint は警告のみ (soft issue) で、ハード強制はしない
- 必要に応じて `--skip-corpus` で自動生成 corpus skill を除外

## チェックリスト (skill 作成完了基準)

- [ ] `libexec/raptor-new-skill` 経由 (or テンプレ手動コピー) で生成
- [ ] frontmatter `name` (kebab-case) と `description` (auto-trigger 条件
      含む 1-3 行) が埋まっている
- [ ] `何を解く skill か` 節がある (日本語 or 英語)
- [ ] `手順` 節があり、具体コマンド or ファイル編集箇所が併記されている
- [ ] `libexec/raptor-skill-lint <path>` が exit 0 or 2 で終わる
- [ ] commit メッセージで「他 skill との関係」を 1 行説明

## 注意

- `description` が長すぎる (600+ chars) と Claude が auto-trigger を判断
  しにくい — 1-3 行に絞る
- 「Auto-trigger when: ...」のフレーズを description 中に含めると Claude
  Code 側で意図的起動の精度が上がる
- 日本語 section 名 (`手順` 等) と英語 section 名 (`Steps` 等) は OR で
  許容している。プロジェクト方針に合わせて統一しても OK

## 関連

- `.claude/skills/_meta/SKILL_TEMPLATE.md` — テンプレ
- `libexec/raptor-new-skill` — ジェネレータ
- `libexec/raptor-skill-lint` — lint
- `[[skill: corpus-index]]` — 同じパターン (生成 + lint) の前例
- `[[skill: corpus2skill]]` — corpus → skill 変換 (auto-generates 4000+
  SKILL.md、本 governance の lint --skip-corpus 対象)
