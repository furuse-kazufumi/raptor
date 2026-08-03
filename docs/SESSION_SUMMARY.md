# Session Summary — 2026-08-01T03:20+09:00

## プロジェクト
default (RAPTOR) — C:\dev\tools\raptor
ブランチ: feat/worklog-orchestration

## 完了した作業（コミット）

- `a329f92f` **CommandWorker** — work-graph が非LLMのコマンド実行を持てるようになり「自律レンダ→ダッシュボード掲載」が成立。
  `<OUT>` 置換のみがテンプレート面、list-arg subprocess 固定、`produces` 不在は fail-closed。
  driver の verify を `tool:` でスキップ（tool spec を LLM レビュアーに渡す誤 FAIL を防止）。
- `be591eaa` **lease TTL を spec.timeout 由来に** — 従来は常に 900s で、期限切れ後の tick が実行中ジョブを再リースし
  **重量級ジョブを二重起動**、元の run の `complete()` が stale lease で失敗して成果を捨てる危険があった。
- `f92a0183` **board 30秒自動更新 + 描画時刻表示**（`WORKLOG_WEB_REFRESH`、0で無効）。
- `30000a32` **ギャラリーの自己説明化** — カードにタイトル/プロジェクト/生成モデル/サイズ/時刻。
  実行中タスクの "running now" バナー追加。
- `5e012b65` **rap: Remote Control 既定 ON**（セッション名=プロジェクト名、`-NoRemote` で opt-out）。
- `993ffc8c` **context-check を bytes/4 推定に較正** — 行数ベース(150/250行)は窓が4倍以上ずれ、実測48%で
  毎ターン誤 CRITICAL を出していた。実測点(2,018,606 bytes = 48%)で較正し誤差2.5pt。env で上書き可。

テスト **90 passed**。グローバル Stop hook (`~/.claude/hooks/save_system_state.py`) の
`D:/projects/CLAUDE.md` 参照エラーもガードで解消（本来のスナップショット保存は元から成功していた）。

## llcore NAS r2 の結果（**全5本完走**・人手介在ゼロ）

| # | タスク | 時間 | evals | 結果 |
|---|---|---|---|---|
| 1 | collapse-band | 6h06m | 751 | memetic frontier dominates greedy **+42.6%** |
| 2 | distill-shift | 7h51m | 751 | 蒸留は frontier をほぼ動かさず **+0.199%**（探索の1/214） |
| 3 | needle | 3h32m | 751 | 長文検索 **argmax_acc 0.0**（全6条件、対照 0.40–0.75） |
| 4 | cross-corpus | 3h42m | 751 | Shakespeare で **+45.72%** CI[44.69,46.78] p_win=1.0 |
| 5 | **1p5b (1.5B)** | 8h05m | 515 | **+71.2%** CI[68.77,74.40] p_win=1.0 |

**最大の発見: 優位はモデルが大きいほど拡大する。** 0.5B の +42.6% に対し 1.5B は **+71.2%（1.67倍）**。
手法が小型モデル限定の産物でないことを示す。0.5B系4本が `751 evals` / `evolved_hv=150.48338064604678` で
**4回ビット単位一致**していることが、この比較のベースラインを担保している。

serve は残タスクが human-gated のみになった時点で clean exit
（`ticks 20, completed 15, failed 2, done 22`）。

- **決定性**: 1〜4本目で `real_evals=751` / `evolved_hv=150.48338064604678` が**4回完全一致**。
- **過適合なし**: 別コーパスで優位が落ちるどころか上回る。ただし個別点の絶対 Δnll は中央値 1.15倍悪化（最悪1.89倍）で、
  **転移するのは「絶対性能」ではなく「greedy に対する相対優位」**。
- **needle は要注意**: control_acc が 5サンプル程度と n が極小。「0% vs 40–75%」は示唆的だが結論不可。
- **holdout のコスト**: 同じ751 evals で holdout あり6.10h / なし3.53h = **1.73倍**。
- NAS は `device: cpu` / `float32` の **CPU only**（GPU 未使用）。

## 未完了タスク（優先順）

0. **次回試す実験 — コンテキスト経済**。今回の実測: 29時間の計算がコンテキストの **1.8%** で済んだ一方、
   私の説明文が **44.8%**、`/loop` スキル本文の再注入が **6.7%（204KB / 26回）** を占めた。
   → ①定時 `/loop` をやめ **Monitor + PushNotification 単独**にする
     ②引き継ぎを手書きでなく `raptor-worklog compact --project P`（ローカルNN要約）で生成する
   グラフは *実行* をコンテキストの外に出せるが *監督* は出せない、という構造への対策。
1. **Qiita 週次自動化** — 「下書き+preflight まで、公開は人手」で合意済み。着手前に疎通確認が必要:
   `py -3.11 C:\dev\projects\fullsense\tools\qiita_public_post.py verify`
   （`~/.config/qiita-cli/credentials.json` が**存在しない**。env `QIITA_PUBLIC_TOKEN` 運用かは未確認）
4. NAS の GPU 化検討（走行中の系列と混ぜないため次スイープから）
5. `server_tuned.log` が 4.8 GB — 別件

## 重要なコンテキスト

- **運用規律**: NAS 実行中に `run-once`/`reclaim` を叩かない。tick 冒頭の `reclaim_expired()` が
  実行中ジョブを二重起動させる。進捗確認は read-only（`sqlite3.connect('file:...?mode=ro', uri=True)`）。
- `complete()` は `lease_expires` を見ず `lease_owner` 一致のみで判定。`--workers 1` ではループが
  `subprocess.run` でブロックし tick が来ないので回収されない（実測確認済み）。
- 進捗は `<out>/eval_cache.json` の `entries` 件数で追える。探索終了後に数分〜24分の後段（集計/cross-corpus 評価）がある。
- **BVH 実長**: 09_01=**1.24s**（既定 `--start 1.0` だと0.24秒しか出ず事実上破損）、13_11=3.47s、
  05_10=6.82s、05_20=9.13s、13_09=9.19s、05_02=9.37s。それ以上の長尺は `fetch_cmu_dance.py --all` の 15_04 のみ。
- **長尺は mp4**: `_save_clip` が拡張子で h264 に切替（GIFより桁で小さい）。`--dur` は `--dance` のみ有効で
  `--reaction`/`--posing` は固定尺（伸ばすにはスクリプト改修が必要）。
- board: `http://127.0.0.1:8765/`。meta refresh 方式のため、サーバ停止中に自動更新が当たるとエラーページで固まる → 手動リロード。

## 次にすべきこと

```powershell
# 1. NAS 5本目の進捗（read-only。run-once は叩かない）
py -3.11 -c "import sqlite3;c=sqlite3.connect('file:C:/dev/tools/raptor/raptor-worklog.db?mode=ro',uri=True);[print(tuple(r)) for r in c.execute(\"select id,status from task where id like 'nas-%-r2'\")]"

# 2. ギャラリー確認（mp4 3本が出ていれば 15 件）
rap -Web

# 3. serve が死んでいたら再開
cd C:\dev\tools\raptor
nohup py -3.11 libexec/raptor-worklog serve --workers 1 --poll 5 --no-seed > out/worklog/serve-nas-r2.log 2> out/worklog/serve-nas-r2.err &
```
