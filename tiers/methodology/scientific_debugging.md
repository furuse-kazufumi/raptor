# 科学的デバッグ — 推測でなく仮説検証

> 出典: Andreas Zeller "Why Programs Fail" / David Agans "Debugging: 9 rules"。
> 関連 skill: `superpowers:systematic-debugging`。CLAUDE.md「失敗時の振る舞い」とも整合。

## 核

バグは**推測で当てない**。症状を観測し、原因の**仮説**を立て、それを**棄却できる
実験**を設計し、結果で仮説を更新する。科学的方法そのもの。

## サイクル（Zeller）

1. **症状を再現する** — 安定した再現手順がない限り何も始まらない。
2. **仮説を立てる** — 「X が原因では」。複数あってよい。
3. **予測する** — 「X が原因なら、Y をすると Z になるはず」。
4. **実験する** — Y を実行し Z を観測。仮説を支持/棄却。
5. **結論・反復** — 棄却されたら次の仮説へ。支持されたら絞り込む。

## Agans の 9 rules（特に効く 5 つ）

- **Understand the system** — 直す前に仕組みを理解する（理解 → 行動の順）。
- **Make it fail** — 確実に再現させる。再現できない不具合は直せない。
- **Quit thinking and look** — 推測をやめて実際に見る。ログ・実値・スタックを見る。
  「たぶん X が原因」より「X を確認する。確認方法は Y」（CLAUDE.md）。
- **Divide and conquer** — 二分探索で原因範囲を狭める（git bisect 等）。
- **Check the plug** — 当たり前の前提（設定・パス・バージョン・電源）をまず疑う。

## RAPTOR での適用

- スタックトレースは末尾でなく根本原因まで遡る（CLAUDE.md）。
- `rtk err <cmd>` でログを絞ってから読む。
- エラー原因を推測する前にエラーメッセージ全文と再現コマンドを確認する。
- 2026-06-01 の失敗＝「症状の再現も観測もせず原因（インジェクション）を捏造」。
  rule 3「Quit thinking and look」「Check the plug」を破った典型。
