# The Pragmatic Programmer — 要点

> 出典: Andrew Hunt & David Thomas "The Pragmatic Programmer"。実装判断の定番。

## 設計・実装の核原則

- **DRY (Don't Repeat Yourself)** — 知識の重複を作らない。同じ事実が 2 箇所にあると
  片方だけ更新され drift する。今日の例: claude-projects.json の next_plan と CLAUDE.md と
  ccr 再開トリガーで「復元手順」が三重化 → 一本化（CLAUDE.md を正本）したのは DRY。
- **Orthogonality（直交性）** — 部品を独立させ、片方の変更が他方に波及しないようにする。
  並列 Agent の「file/module 非接触」条件はこれ。接触するものを並列化しない。
- **Tracer Bullets（曳光弾）** — 全体を貫く細い動く経路をまず通し、当たりを見てから
  肉付け。段階的 PoC（小→大、[[feedback_dev_process_all_projects]]）と同じ。
- **Prototype to learn** — プロトタイプは学習のため。使い捨て前提なら作り込まない。
- **Don't live with broken windows（壊れた窓を放置しない）** — 小さな綻び（雑な
  ハック・未修正の警告）を放置すると荒廃が加速する。気づいたら直すか記録する。

## 態度・規律

- **Take responsibility（DRY な責任）** — 「猫が宿題を食べた」を言わない。
  失敗は honest に報告し、選択肢と次手を出す（CLAUDE.md / honest disclosure）。
- **Good-enough software** — 完璧主義で止めず、要求された品質を満たしたら出す。
  ただし「good enough」は品質基準を**満たす**こと。検証省略の言い訳ではない。
- **Estimate to avoid surprises** — 見積もりを言い、turn 上限・scope を明示する。
- **Don't assume it, prove it** — 仮定するな、証明せよ。これが今日いちばん破った原則。
  「在るはず」でなく ls/grep で在ることを示してから言及する。
