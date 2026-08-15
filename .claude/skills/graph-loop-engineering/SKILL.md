---
name: graph-loop-engineering
description: |
  グラフエンジニアリング(raptor-worklog 永続 work-graph)とループエンジニアリング(llloop MAPE-K/plan-execute-verify)で無人・セッション横断の自走を行う手順。work-graph は SQLite/WAL でセッションを跨いで生き残り、seed→add(tool/LLM ノード+依存)→serve/detached driver→journal→別セッションが読む=セッション間コミュニケーション。AUTO-TRIGGER: op 追加/evolution・パラメータ sweep/coverage・validation 等の多段・独立・無人で回せるバッチ、overnight/長時間ジョブ、セッションを跨いで継続すべき作業に着手する直前、または直接 robust.py/スイープ/多段パイプラインを回そうとした瞬間。抑制=対話的・探索的・UI レビュー・単発は対象外(直接 Workflow/Agent)。
  Auto-trigger when: ユーザーが「<追加キーワード>」「<追加キーワード>」を発話、
  または ユーザーが対応する workflow を起動したい意図を発話、または前段の作業が完了した直後。>
related_skills:
  - <skill-name-1>
  - <skill-name-2>
related_memory:
  - feedback_<topic>
  - project_<area>
---

# <skill-name> — グラフエンジニアリング(raptor-worklog 永続 work-graph)とループエンジニアリング(llloop MAPE-K/plan-execute-verify)で無人・セッション横断の自走を行う手順

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
