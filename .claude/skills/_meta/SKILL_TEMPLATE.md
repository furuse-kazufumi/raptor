---
name: <kebab-case-name>
description: |
  <1-3 行で skill の目的・入出力・auto-trigger 条件を記述。
  Auto-trigger when: ユーザーが「<キーワード1>」「<キーワード2>」を発話、
  または <文脈条件>。>
related_skills:
  - <skill-name-1>
  - <skill-name-2>
related_memory:
  - feedback_<topic>
  - project_<area>
---

# <skill-name> — <1 行サマリー>

## 何を解く skill か

<2-4 行で問題と解決アプローチを説明。「なぜこの skill が要るか」
を最初に書くと、Claude / 人間が起動判断を即できる。>

## 入力前提

<必要なファイル / 環境 / 前提状態。例:>
- `<repo>/<path>` が存在する
- テストが PASS している
- `<tool>` がインストール済

## 手順

<番号付きステップで、各ステップに具体コマンド or ファイル編集箇所を併記。
1 ステップは 1-5 行で書く。長くなる場合はサブセクションに分ける。>

### 1. <ステップ名>

<具体的な操作>

```bash
<コマンド or コード例>
```

### 2. <ステップ名>

<...>

## 出力

<生成されるファイル / 副作用 / commit 内容>

## チェックリスト (任意)

- [ ] <確認項目 1>
- [ ] <確認項目 2>

## 注意 / よくある落とし穴

- <注意点 1>
- <注意点 2>

## 関連

- `[[skill: <skill-name>]]` — 連携 skill
- `[[memory: <slug>]]` — 関連 memory
- `<file path>` — 主要 source / target ファイル
