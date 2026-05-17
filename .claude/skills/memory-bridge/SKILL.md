---
name: memory-bridge
description: |
  memory (`~/.claude/projects/.../memory/`) と CLAUDE.md の drift を
  検出して read-only な差分レポートを生成する skill。memory にあるが
  CLAUDE.md で言及されていない project memory、CLAUDE.md にあるが memory
  ファイルが消えた stale 参照、type 別件数を 1 つの md にまとめる。
  Auto-trigger when: ユーザーが「memory 整理」「CLAUDE.md と memory の差分」
  「stale memory mention」を発話、または定期的な memory メンテ時。
related_skills:
  - skill-governance
related_memory: []
---

# memory-bridge — memory ↔ CLAUDE.md drift レポート

## 何を解く skill か

memory `project_*` は実装の文脈を持つが、長期セッションで蓄積すると
**CLAUDE.md に反映漏れ** や **CLAUDE.md に残った stale slug 参照** が出る。
このスキルは read-only に差分を md レポートで surface し、operator が
何を手で CLAUDE.md に転記すべきかの判断材料を出す。**CLAUDE.md は人間管理**
を維持する設計。

## 入力前提

- raptor リポジトリ root にいる
- `~/.claude/projects/C--Users-puruy-raptor/memory/` が存在
- `~/.claude/CLAUDE.md` (グローバル) と `CLAUDE.md` (プロジェクト) のいずれか
  が存在

## 手順

### 1. レポート生成

```bash
python3 libexec/raptor-memory-bridge
# → out/memory-bridge-<YYYY-MM-DD>.md
```

オプション: `--out <path>` で出力先を変更可能。

### 2. レポートを読む

3 セクション:

| セクション | 用途 |
|---|---|
| **Summary** | type 別件数、orphan / stale 件数の集計 |
| **Project memories candidates for CLAUDE.md surface** | CLAUDE.md に未言及の project memory リスト |
| **Stale CLAUDE.md mentions** | CLAUDE.md にあるが memory ファイルが消えた slug |

### 3. 判断 (人間担当)

各 orphan project memory について:
- **active で load-bearing**: CLAUDE.md `# 主な進行中プロジェクト` 等に 1 行追加
- **過去のスナップショット**: そのまま放置 (memory として残るが CLAUDE.md には不要)
- **古くて不要**: memory ファイル自体を削除

各 stale mention について:
- **memory を復元すべき**: 該当 slug の memory を再作成
- **削除すべき**: CLAUDE.md から該当行を除去

## 出力

| ファイル | 内容 |
|---|---|
| `out/memory-bridge-<YYYY-MM-DD>.md` | drift レポート (上書きせず日付別) |

## チェックリスト

- [ ] `python3 libexec/raptor-memory-bridge` が exit 0 で終わる
- [ ] レポートを読んで surface した候補のうち **active なもの** を
      手動で CLAUDE.md に反映 (1 行ずつ)
- [ ] stale mention があれば 0 件になるまで CLAUDE.md を整える

## 注意

- このスクリプトは **CLAUDE.md を絶対に変更しない**。差分提示のみ
- 55+ orphans が普通 (snapshot 系 memory は CLAUDE.md には乗せない)
- `description:` フィールドの長さを 140 文字で truncate するため、長い説明は
  memory ファイル本体で確認すること

## 関連

- `libexec/raptor-memory-bridge` — スクリプト本体
- `~/.claude/CLAUDE.md` — グローバル CLAUDE.md (memory ↔ ここの整合)
- `~/.claude/projects/C--Users-puruy-raptor/memory/MEMORY.md` — memory index
- `[[skill: skill-governance]]` — skill 群の標準化 (本 skill は memory 系の同等品)
