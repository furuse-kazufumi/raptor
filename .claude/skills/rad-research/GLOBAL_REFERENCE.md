# RAD グローバル参照ポリシー（Raptor 横断）

このファイルは Raptor 配下のすべてのスキル・コマンド・タスクから
**RAD コーパスを広く参照する**ためのポリシーをまとめたものです。

## 基本方針

**「アイデア出し・調査・差別化分析が必要なときは、まず RAD を当たれ」**

- 21+ 分野の論文・記事メタデータを一次情報として持っている
- どの分野にも該当しない問題でも、隣接分野からヒントが取れる
- 既存研究との重複・差別化の即時確認に使える

## 自動参照すべきタイミング

| Raptor のタスク | 参照するべき RAD 分野 |
|----------------|--------------------|
| `/agentic` 開始時 | security + 該当領域 |
| `/scan` 結果分析 | security + 関連応用分野 |
| `/sourcehunt` ヒント取得 | security + 言語別 |
| `/exploit` 設計 | security + information_theory |
| `/patch` 提案 | security + 数学系 |
| `/understand` データフロー | 該当分野（image / industrial_iot 等） |
| `/validate` 攻撃可達性 | security + automotive / infrastructure |
| `/oss-forensics` | security + DBLP コミュニティ |
| `/triz-ideation` | 全分野（矛盾分野マッピング） |
| `/cross-domain-ideation` | 主分野 + 隣接 2 + 遠隔 2 |
| `/gsd-explore` Socratic | 該当分野 + 隣接 1 |
| `/gsd-spec-phase` | 該当応用分野 + 関連数学分野 |
| `/gsd-discuss-phase` | 該当応用分野 + 隣接技術分野 |
| 新機能設計（一般） | 主分野 + 数学 1 つ |

## 参照例（`/sourcehunt` で `paho-mqtt` ライブラリの脆弱性ハント）

```
1. RAD: security_corpus  → MQTT 関連 CVE / 攻撃論文
2. RAD: industrial_iot   → MQTT 産業実装ノウハウ
3. RAD: information_theory → MQTT-SN 圧縮 / 認証理論
→ ヒント文として 3 分野の上位 5 件を流す
```

## キャッシュ戦略

- 各スキル毎にクエリ結果をローカル（`out/<run>/rad_cache/`）にキャッシュ
- 同一クエリの 24 時間以内再呼出はキャッシュ利用
- 月次の bulk_corpus_collector 実行後はキャッシュ全クリア

## RAD コーパスの場所

```
C:/Users/puruy/raptor/.claude/skills/corpus/<domain>_corpus/
    ├── arxiv_*.jsonl
    ├── crossref_*.jsonl
    ├── dblp_*.jsonl
    ├── pubmed_*.jsonl    （medical 分野のみ）
    ├── hn_*.jsonl
    ├── consolidated.jsonl  （月次重複除去後）
    └── queries.md
```

## クエリの最小スニペット（任意のスキルから埋込み可）

```python
import json, glob
from pathlib import Path

def rad_search(keywords, domains=None, top_n=10):
    """RAD 横断検索の最小実装。
    domains=None なら全分野を当たる。"""
    base = Path("C:/Users/puruy/raptor/.claude/skills/corpus")
    if domains is None:
        domains = [d.name for d in base.iterdir() if d.is_dir() and d.name.endswith("_corpus")]
    hits = []
    for dom in domains:
        for f in (base / dom).glob("*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                d = json.loads(line)
                blob = (d.get("title", "") + " " + d.get("abstract", "")).lower()
                if all(k.lower() in blob for k in keywords):
                    hits.append((dom, d))
                    if len(hits) >= top_n:
                        return hits
    return hits
```

## 引用ルール

- メタデータ（title + abstract + URL）のみを使う
- 出典は必ず `<arxiv_id> | <doi> | <source>` 形式で表示
- フルテキストは外部サイトへリンクのみ

## 自動拡張

未収録分野が頻繁に問い合わされる場合、新規分野コーパスとして追加:

```bash
# 例: ロボティクス制御理論を独立分野にする場合
python tools/bulk_corpus_collector.py --domain control_theory --target 10000 \
    --queries "model predictive control mpc" "lqr optimal control" "system identification"
```

その後 `corpus2skill` で階層化し、本ガイドに追記。

---

**注**: 本ファイルは AI エージェントが起動時に読み込むことを想定し、
「**まず RAD を当たる**」という発想を Raptor のデフォルト挙動として
組み込むためのドキュメントです。
