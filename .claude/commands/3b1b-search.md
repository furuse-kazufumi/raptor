---
description: 蓄積した教育系動画ナレッジを横断検索する (タグ・参照・日付)
---

# /3b1b-search <query> — 横断検索

`D:/knowledge/3b1b-tracker/` に蓄積した動画ナレッジを検索する。
仕様の正本: `docs/3b1b-tracker.md`。

## 手順

1. `index/by-topic.md` / `by-reference.md` / `by-date.md` を引いて query にマッチする動画を探す
   (タグ・参照論文/書籍・日付・タイトルで照合)。
2. ヒットした各動画の `videos/{video_id}/summary.md` を提示。
3. 必要なら元動画 URL と該当箇所 (字幕タイムスタンプ) を返す。
4. ヒットゼロなら、近いタグ・領域を提案 (例: "conformal_map" → "complex_analysis")。

## メモ

- 検索はローカルナレッジのみ (ネット取得しない)。新着取得は `/3b1b-check`、
  個別取り込みは `/3b1b-ingest`。
- index が未生成 (まだ ingest していない) なら、その旨を案内し `/3b1b-ingest` を促す。
