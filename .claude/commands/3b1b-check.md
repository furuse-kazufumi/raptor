---
description: 3Blue1Brown/Ufolium 等の教育系チャンネルの新着動画を検知して要約する
---

# /3b1b-check — 新着検知

教育系数学・科学チャンネルの新着動画を RSS で検知し、要約して `feed/` に追記する。
仕様の正本: `docs/3b1b-tracker.md`。storage root = **`D:/knowledge/3b1b-tracker/`**。

## 手順

1. `D:/knowledge/3b1b-tracker/config.yaml` を読む (channels / filters)。
2. 各 channel の RSS を取得: `https://www.youtube.com/feeds/videos.xml?channel_id={ID}`
   (curl, API キー不要)。`id` が空の channel (Ufolium 未取得等) はスキップし `state/log/` に記録。
3. `state/last_seen.json` と差分を取り、最終確認以降の新着 video_id を抽出。
4. フィルタ適用: `exclude_shorts` (min_duration_seconds 未満を除外) / `exclude_keywords`
   (タイトル・概要に含まれたら除外)。duration は yt-dlp で確認。
5. 残った動画を `yt-dlp --skip-download --write-info-json --write-description` でメタ取得。
6. 各動画 200 字程度の要約を生成し、`include_topic_tags` とのマッチでタグ付け。
7. `feed/YYYY-MM-DD.md` に追記 (フォーマットは spec §8)。
8. 興味タグマッチがあればユーザーにハイライト報告。
9. `state/last_seen.json` を更新。

## 振る舞いルール (spec §9 厳守)

- 概要欄の原文引用は **15 語未満**。長い記述は paraphrase。歌詞・詩は保存しない。
- 動画自体はダウンロードしない (メタ・概要・字幕テキストのみ)。
- 失敗 (channel 取得不可 / yt-dlp 失敗) はサイレントに諦めず `state/log/<date>.log` に明示記録。
- 冪等: 同じ video_id を二重処理しない。

## 前提 (未整備なら案内して停止)

- `yt-dlp` 未インストールなら `pip install -U yt-dlp` を案内 (勝手に入れない)。
- Ufolium の channel_id 未取得なら
  `yt-dlp --print "%(channel_id)s" "https://www.youtube.com/@Ufolium" | head -1` を案内し config.yaml への記入を促す。
