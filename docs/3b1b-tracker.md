# 3Blue1Brown / Ufolium 追跡ルール (Claude Code 用)

> **raptor 適用メモ (2026-05-24, scaffold 段階)**
> - **storage root**: 原文の `~/knowledge/3b1b-tracker/` ではなく、D ドライブ運用方針
>   ([[feedback_d_drive_preference]]) に合わせ **`D:/knowledge/3b1b-tracker/`** を使う。
>   config.yaml / state / feed / videos / index はそこに配置済 (空状態)。
> - **scaffold 済**: `config.yaml` + dir 構造 + `state/last_seen.json={}` +
>   slash command 定義 (`.claude/commands/3b1b-{check,ingest,search}.md`)。
> - **未実施 (要ユーザー判断)**: yt-dlp インストール / RSS・ネット取得 / Ufolium channel_id 取得 /
>   cron・タスクスケジューラ登録。= 外部副作用を伴う「動かす」部分は保留 (現状非破壊)。
> - 将来チャンネルが増えたら本書を `youtube-channel-tracker.md` にリネームし汎用化 (§10)。
> - 接続: 追跡領域 (group_theory/conformal_map/complex_analysis 等) は FullSense の
>   Hyperdimensional Thinking の表現空間の数学そのもの = 表現空間ライブラリの知識入力源
>   (`fullsense/docs/vision/hyperdimensional_connection_map.md` §2)。

> Claude Code に教育系数学・科学チャンネルを継続的に追跡させ、新着の検知・要約と、視聴済み動画の知識ベース化を行わせるためのルール。
> 手動コマンド呼び出しと、スケジューラによる自動実行の両方をサポートする。

---

## 1. 追跡対象

| チャンネル名 | ハンドル | チャンネルID | 言語 | 役割 |
|---|---|---|---|---|
| 3Blue1Brown | `@3blue1brown` | `UCYO_jab_esuFRV4b17AJtAw` | 英語 | 一次情報源 |
| 3Blue1BrownJapan | `@3blue1brownJapan` | `UCBevyiJ2ierZY-0yZhfLrmQ` | 日本語 | 公式翻訳 |
| Ufolium | `@Ufolium` | (yt-dlp で取得して `config.yaml` に記録) | 日本語 | 翻訳元・派生コース |

すべて教育目的の数学・科学コンテンツ。広告動画・短編 Shorts は対象外(後述のフィルタで除外)。

---

## 2. 追跡の目的

### 目的A: 新着動画の検知と要約 (継続監視)
- チャンネルに新しい動画がアップされたら検知する
- タイトル・概要・参照論文/書籍を抽出して短い要約を生成する
- 既存の興味領域(AI/LLM、3D計測、3DGS、群論・等角写像など)とのタグマッチを行う

### 目的B: 知識ベース化 (蓄積)
- 視聴済み動画(または追跡対象として明示した動画)を恒久的なナレッジに取り込む
- `mcp-spatial-asset-profile` または `raptor` の知識ベースに統合する
- 後で「この概念について3Blue1Brownで扱っていたか」を検索可能にする

---

## 3. ストレージレイアウト

```
D:/knowledge/3b1b-tracker/
├── config.yaml              # 対象チャンネル一覧 + フィルタ
├── state/
│   ├── last_seen.json       # チャンネルごとの最終確認video_id
│   └── log/                 # 実行ログ(日付別)
├── feed/                    # 新着検知の出力(目的A)
│   └── YYYY-MM-DD.md        # その日の新着+要約
├── videos/                  # 動画ごとのナレッジ(目的B)
│   └── {video_id}/
│       ├── meta.yaml        # title, channel, date, url, tags, references
│       ├── description.md   # 動画概要欄(原文)
│       ├── transcript.txt   # 字幕(取得できた場合)
│       ├── summary.md       # Claudeによる要約
│       └── references.md    # 動画内で言及された論文・書籍・URL
└── index/                   # 全動画を横断検索するためのインデックス
    ├── by-topic.md
    ├── by-reference.md
    └── by-date.md
```

---

## 4. 設定ファイル

`D:/knowledge/3b1b-tracker/config.yaml`:

```yaml
channels:
  - name: 3Blue1Brown
    handle: "@3blue1brown"
    id: UCYO_jab_esuFRV4b17AJtAw
    language: en
    role: primary
  - name: 3Blue1BrownJapan
    handle: "@3blue1brownJapan"
    id: UCBevyiJ2ierZY-0yZhfLrmQ
    language: ja
    role: translation
  - name: Ufolium
    handle: "@Ufolium"
    id: ""  # yt-dlp --print id "https://www.youtube.com/@Ufolium" で取得
    language: ja
    role: original

filters:
  exclude_shorts: true        # 60秒未満は除外
  min_duration_seconds: 120
  exclude_keywords:           # タイトル・概要に含まれていたら除外
    - "ad"
    - "promo"
  include_topic_tags:         # 興味領域(マッチしたら優先タグ付け)
    - linear_algebra
    - calculus
    - topology
    - complex_analysis
    - group_theory
    - probability
    - neural_network
    - transformer
    - signal_processing
    - geometry
    - conformal_map
    - manim

knowledge_base_target: raptor  # raptor / spatial-asset / both
```

---

## 5. 必要なツール

Claude Code が呼び出す外部ツール:

- **yt-dlp**: 動画メタデータ・概要欄・字幕取得 (`pip install yt-dlp`)
- **YouTube Data API v3** (任意): RSS で十分なケースが多いが、詳細なメタが必要なときに使用
- **RSS feed**: 各チャンネルの新着は `https://www.youtube.com/feeds/videos.xml?channel_id={ID}` で取得可能(API キー不要、レート制限なし)

新着検知は RSS で行い、詳細取得は yt-dlp で行うのが推奨パターン。

---

## 6. 手動実行コマンド (Claude Code スラッシュコマンド)

`.claude/commands/` 以下に配置:

### `/3b1b-check` — 新着検知

最後のチェック以降にアップされた動画を一覧し、要約する。
処理:
1. `config.yaml` の各チャンネルの RSS を取得
2. `state/last_seen.json` と差分を取る
3. フィルタ(shorts除外、キーワード除外)を適用
4. 残った動画について `yt-dlp --skip-download --write-info-json --write-description` でメタ取得
5. 各動画について 200字程度の要約を生成
6. `feed/YYYY-MM-DD.md` に追記
7. 興味タグマッチがあれば、ユーザーにハイライト報告
8. `last_seen.json` を更新

### `/3b1b-ingest <video_url_or_id>` — 知識ベース化

明示的に指定した動画をナレッジ化する。
処理:
1. yt-dlp でメタ・概要・字幕を取得
2. `videos/{video_id}/` に保存
3. 概要欄から参照(論文・書籍・URL)を抽出
4. 字幕があれば要約を生成、なければ概要欄ベースで要約
5. `index/` を更新
6. `knowledge_base_target` に応じて RAPTOR または spatial-asset に投入

### `/3b1b-search <query>` — 横断検索

蓄積された動画ナレッジから検索する。
処理:
1. `index/` を引く(タグ・参照・日付)
2. ヒットした動画の `summary.md` を提示
3. 必要なら元動画 URL と該当箇所を返す

---

## 7. 自動実行 (cron / Windows タスクスケジューラ)

### Linux / WSL
```cron
# 毎朝 8:00 に新着チェック
0 8 * * * cd /d/knowledge/3b1b-tracker && claude code --headless --command "/3b1b-check" >> state/log/cron.log 2>&1
```

### Windows タスクスケジューラ
- トリガー: 毎日 8:00
- 操作: `claude` (Claude Code CLI)
- 引数: `code --headless --command "/3b1b-check"`
- 作業フォルダ: `D:\knowledge\3b1b-tracker`

ヘッドレス実行時は `--dangerously-skip-permissions` ではなく、許可済みコマンドリストに `yt-dlp`, `curl`, `git` を含めた `.claude/settings.json` を使う。

---

## 8. 出力フォーマット

### `feed/YYYY-MM-DD.md` の例

```markdown
# 2026-05-24 新着

## 🆕 3Blue1BrownJapan: 絵の対数を取るとはどういうことか
- URL: https://youtu.be/vwFSC_XrRmU
- 公開: 2026-05-23
- 元動画: How (and why) to take a logarithm of an image (3Blue1Brown)
- タグ: #complex_analysis #conformal_map #escher
- 要約: エッシャーの「Print Gallery」を題材に、画像を複素平面上の関数とみなして
  対数を取ると渦巻く歪みが平坦な格子に戻ること、Lenstra-de Smit の解析を
  視覚化した動画。複素対数の応用としての位置付け。
- 参照:
  - de Smit & Lenstra (2003) "The Mathematical Structure of Escher's Print Gallery"
  - Locher, J. L. *Magic of MC Escher*
  - mathvisuals.org/PrintGallery/
- 興味マッチ: ★★★ (conformal_map, geometry)
```

### `videos/{id}/meta.yaml` の例

```yaml
video_id: vwFSC_XrRmU
title: 絵の対数を取るとはどういうことか
channel: 3Blue1BrownJapan
channel_id: UCBevyiJ2ierZY-0yZhfLrmQ
language: ja
published_at: 2026-05-23
duration_seconds: null  # 取得できれば埋める
url: https://youtu.be/vwFSC_XrRmU
original:
  channel: 3Blue1Brown
  title: How (and why) to take a logarithm of an image
tags:
  - complex_analysis
  - conformal_map
  - escher
  - geometry
references:
  papers:
    - "de Smit & Lenstra (2003) The Mathematical Structure of Escher's Print Gallery"
  books:
    - "Locher, J. L. — Magic of MC Escher"
  urls:
    - https://mathvisuals.org/PrintGallery/
ingested_at: 2026-05-24
```

---

## 9. Claude Code の振る舞いルール

- **概要欄からの引用は短く**: 著作権配慮のため、原文の引用は 15 語未満。長い記述は paraphrase する
- **歌詞・詩は要約しない**: 万一動画概要に含まれていても保存しない
- **字幕の扱い**: 取得できた場合も全文をそのまま保存せず、要約と参照箇所のタイムスタンプを保存する
- **動画自体はダウンロードしない**: メタ情報・概要・字幕(テキスト)のみ
- **失敗時はサイレントに諦めない**: チャンネルが取れなかった、yt-dlp が失敗した、などは `state/log/` に明示的に記録する
- **既存ファイルを破壊しない**: 同じ video_id に対して再 ingest するときは、`meta.yaml` を上書きせず diff を取って確認する
- **RAPTOR/spatial-asset への投入は冪等に**: 同じ動画を二重に登録しない(video_id をキーにする)

---

## 10. 拡張の方向

このルールは 3Blue1Brown / Ufolium 専用だが、構造は他のチャンネルにも転用可能:

- Veritasium, Numberphile, Mathologer などを `channels:` に追加するだけで同じパイプラインが動く
- 設定ファイルを `config.yaml` 一本にしてあるのは、将来の汎用化のため
- 「教育系数学・科学チャンネル追跡」一般のテンプレとして扱える

将来、扱うチャンネルが増えたら本ドキュメントを `youtube-channel-tracker.md` 等にリネームし、汎用化することを推奨する。

---

## 11. 初期セットアップ手順

```bash
# 1. ディレクトリ作成 (scaffold 済)
mkdir -p D:/knowledge/3b1b-tracker/{state,feed,videos,index}
mkdir -p D:/knowledge/3b1b-tracker/state/log

# 2. yt-dlp インストール (未実施 — 動かす段階で)
pip install -U yt-dlp

# 3. Ufolium のチャンネルID取得 (未実施)
yt-dlp --print "%(channel_id)s" "https://www.youtube.com/@Ufolium" | head -1
# 出力された ID を config.yaml に記入

# 4. config.yaml を配置 (scaffold 済)

# 5. 初回 last_seen.json を作成 (scaffold 済 — 空 {})

# 6. Claude Code スラッシュコマンドを配置 (scaffold 済)
#    .claude/commands/3b1b-{check,ingest,search}.md
```

---

**このルールが機能していれば**: 毎朝、新着の数学・科学解説動画が短い要約とタグ付きで届く。「あの概念は3B1Bで扱っていたか?」が即座に検索できる。動画自体を見返さなくても、参照論文・書籍がローカルナレッジから引ける。
