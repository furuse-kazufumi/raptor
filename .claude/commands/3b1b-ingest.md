---
description: 指定した動画を恒久ナレッジに取り込む (メタ・概要・字幕要約・参照抽出)
---

# /3b1b-ingest <video_url_or_id> — 知識ベース化

明示指定した動画を `D:/knowledge/3b1b-tracker/videos/{video_id}/` に恒久ナレッジ化する。
仕様の正本: `docs/3b1b-tracker.md`。

## 手順

1. 引数 (URL or video_id) から video_id を確定。
2. `yt-dlp --skip-download --write-info-json --write-description --write-auto-sub --sub-lang ja,en`
   等でメタ・概要・字幕を取得 (動画本体は DL しない)。
3. `videos/{video_id}/` に保存:
   - `meta.yaml` (title/channel/date/url/tags/references, spec §8 形式)
   - `description.md` (概要欄。引用は短く=15 語未満、長文は paraphrase)
   - `transcript.txt` (字幕が取れた場合のみ。**全文保存せず**要約+参照タイムスタンプ)
   - `summary.md` (字幕優先、無ければ概要欄ベースの要約)
   - `references.md` (概要欄から論文・書籍・URL を抽出)
4. `index/by-topic.md` / `by-reference.md` / `by-date.md` を更新。
5. `config.yaml` の `knowledge_base_target` に従い raptor / spatial-asset の知識ベースへ投入。

## 振る舞いルール (spec §9 厳守)

- **既存破壊禁止**: 同じ video_id を再 ingest するときは `meta.yaml` を上書きせず diff を取り確認。
- **冪等**: 知識ベースへの投入は video_id をキーに二重登録しない。
- 概要欄引用 15 語未満 / 歌詞・詩は保存しない / 動画本体 DL しない。
- 失敗は `state/log/<date>.log` に明示記録 (サイレントに諦めない)。

## 前提

- `yt-dlp` 未インストールなら案内のみ (勝手に入れない)。
