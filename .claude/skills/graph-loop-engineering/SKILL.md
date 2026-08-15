---
name: graph-loop-engineering
description: |
  グラフエンジニアリング(raptor-worklog 永続 work-graph)とループエンジニアリング(llloop MAPE-K/plan-execute-verify)で
  無人・セッション横断の自走を行う手順。work-graph は SQLite/WAL でセッションを跨いで生き残り、seed→add(tool/LLM ノード+依存)
  →serve/detached driver→journal→別セッションが読む=セッション間コミュニケーション。
  AUTO-TRIGGER when: op 追加/evolution・パラメータ sweep/coverage・validation 等の多段・独立・無人で回せるバッチ、
  overnight/長時間ジョブ、セッションを跨いで継続すべき作業に着手する直前、または直接 robust.py/スイープ/多段パイプラインを
  回そうとした瞬間(「無人で」「overnight」「自走」「バッチ」「スイープ」「セッションを跨いで」「後で結果を」を発話)。
  抑制=対話的・探索的・UI レビュー・単発は対象外(直接 Workflow/Agent)。
related_skills:
  - agentic
  - test-workflows
related_memory:
  - reference_workgraph_multimodel_ops
  - feedback_max_plan_autonomy
  - feedback_parallel_first_execution
---

# graph-loop-engineering — 永続 work-graph で無人・セッション横断に自走する

## 何を解く skill か
Claude は「使える局面でも work-graph を使わず直接実行してしまう」癖がある(robust.py を背景で回す / その場の Workflow で捌く)。
それだと **セッションを消費し、横断で継続できず、無人 overnight も回せない**。本 skill は、**多段・独立・無人で回せる作業を
永続 work-graph(`libexec/raptor-worklog`、SQLite/WAL)へ積んで detached driver に自走させる**手順。graph はセッションを跨いで
生き残る = **一方のセッションが seed/add → driver が実行 → 別セッションが結果を読む** という**セッション間コミュニケーション**が成立する。
Claude 本体は「タスクを積む + 重要判断/検証」に集中し、Do は driver(headless)に委ねる。正本 = [[reference_workgraph_multimodel_ops]]。

## いつ使う / 使わない(判定)
- **使う**: op 追加パイプライン(足す→登録→halcon 検証→recapture→coverage→full suite)/ evolution・パラメータ sweep(seeds×gens×problems)/
  coverage・validation の多段 / overnight・長時間 / **セッションを跨いで結果を受け取りたい**とき。
- **使わない**: 対話的・探索的・UI レビュー・単発・ユーザーと往復しながら詰める作業 → 直接 Workflow tool / Agent の方が速い。
- 迷ったら: **独立ノードに分解でき、各ノードが「コマンド or 有界プロンプト」で完結し、監督なしで進むなら work-graph**。

## 入力前提
- `C:/dev/tools/raptor` 直下で `libexec/raptor-worklog`(`py -3.11` 実行)。
- work-graph 未初期化なら `init`、プロジェクト定義から seed するなら `claude-projects.json`。
- tool ノードで走らせる対象スクリプトが repo に存在し、決定的コマンドで起動できる。

## 手順

### 1. seed / init(グラフの器を用意)
```bash
cd C:/dev/tools/raptor
py -3.11 libexec/raptor-worklog init            # 未初期化のみ
py -3.11 libexec/raptor-worklog seed --projects claude-projects.json   # プロジェクト定義から
```

### 2. ノードを積む(tool=決定的コマンド / LLM=有界プロンプト)
**tool ノード(CommandWorker、LLM 不要・auth ゲート無し=overnight 安全)**。spec は **--spec-file(JSON)** 推奨(quote 地獄回避):
```bash
# spec.json: {"cmd":["py","-3.11","robust.py","--problem","vol_denoise","--workdir","out/macro_voldenoise","--seeds","8","--gens","80","--pop","28","--out","<OUT>.json"],
#             "cwd":"C:/dev/projects/imgevolve","env":{"IMGEVOLVE_NO_BACKENDS":"1"},"produces":"<OUT>.json","timeout":10800}
py -3.11 libexec/raptor-worklog add --title "evolve vol_denoise" --spec-file spec.json \
    --project imgevolve --capability tool --priority 0 --depends <prev_id>
```
- `<OUT>` → `out/worklog/<task_id>/result`。`cmd` は**リスト**(shell 文字列不可)。`produces` 存在 + exit0 で **done** 判定。**priority は 0 が最上位**。
- 段の連結は `--depends id1,id2`。安定チェーンパス(例 `<stage>_latest.npy`)で warm-start を橋渡し。
- **gated stage runner**(自己判定ノード): ラッパが「実行→成果物→gate 判定→`<OUT>.json` 記録、exit code=判定」を返すと、
  グラフが PDCA を回せる(Plan=add / Do=driver / Check=exit+JSON / Act=次ノード unblock or 再計画)。例 = `onocollo-complete/scripts/evis_video/hillco_stage.py`。
- LLM ノード(reason/summarize/triage)は `--capability triage,summarize` 等。**human-gated**(auth)で overnight の tool-only run では skip/idle。

### 3. driver に自走させる(無人・セッション横断)
```bash
# tool-only を安全に回す(LLM auth ゲート無し):
py -3.11 libexec/raptor-worklog run-once --available tool:command   # 1 tick(--available tool は不発、tool:command と書く)
# 常駐 driver(横断・overnight):
rap -Serve -Detach                # bin/rap.ps1 の work-graph driver。auth_halt で停止
# or detached loop: libexec/hillco-driver-loop.sh 相当(while: run-once; sleep、auth_halt で停止)
```
driver はセッションを跨いで生き残る = **このセッションが積んだ仕事を、次のセッションが結果として受け取れる**。

### 4. 進捗を read-only で監督(driver を邪魔しない)
```bash
py -3.11 libexec/raptor-worklog stats                       # counts + escalation
py -3.11 libexec/raptor-worklog list --status done|failed|leased
py -3.11 libexec/raptor-worklog show <id>                   # result_ref / journal
# 生 DB は read-only で: sqlite3.connect('file:...raptor-worklog.db?mode=ro', uri=True)
```
**watcher**(完了検知で監督セッションを再開): node が ready/leased/pending を抜けたら exit(`libexec/hillco-watch-node.sh <id>`)→ イベント駆動で Act。

### 5. ループエンジニアリング層(自己修正 loop)
plan-execute-verify を自己修正で回すなら **llloop(MAPE-K + fail-closed 安全層、`C:/dev/projects/llloop`)** を上に載せる。
gate 失敗ノードだけ再計画(Act)して graph に再投入する = Monitor→Analyze→Plan→Execute→Knowledge のループ。

### 6. 人が張り付かない運用(session-switch の無人化)= work-graph ネイティブ運用
**課題**: Claude は自力で `rap` を /exit・再起動できない([[project_ccr_automation_limits]])。素朴には session 切替に人が張り付く=work-graph の意義を殺す。
**設計(人の介在を極小化)**:
1. **tool ノード中心化**: 決定的に書ける工程は全部 tool(CommandWorker)化 → **detached driver がセッション無しで自走**(人・Claude セッション不要)。
   overnight は tool-only(`run-once --available tool:command` / detached loop)= auth ゲート無しで無人。**「人が要る」を LLM ノードだけに縮退させる**。
2. **LLM 監督は周期起動で(picker 待ちにしない)**: Plan/Check/Act(LLM 判断)は `CronCreate`(定期クラウドエージェント=`schedule` skill)や `ScheduleWakeup` で
   **時間 or イベントで Claude を起こす** → graph の done/failed を読み、gate 失敗ノードを再計画・再投入して即終了。人は picker に張り付かない。
3. **タスク注入は非同期チャネル**: FullSense email inbound(`tools/fullsense_email_inbound.py`、allowlist fail-closed)/ 公式 Remote Control で、
   セッション外から graph にタスクを積む。別のセッション/人が結果を受け取る=**セッション間コミュニケーション**。
4. **watcher でイベント駆動**: `hillco-watch-node.sh <id>` がノード完了で exit → 監督を起こす(ポーリング常駐でなくイベント)。
**honest 限界**: `rap` の物理再起動(新セッション生成)は人 or cron が引く。tool-only なら再起動自体が不要(driver が生き続ける)。
→ **運用ゴール = 「tool でできることは driver に丸投げ、LLM 判断だけを cron/watcher で最小回数起こす。人は例外時のみ」**。

**発展形 = セッション・リレー(FIFO シフト、~3 ロールのローテーション)**: `CronDelete`/`CronCreate`(`schedule` skill)で **短命の定期クラウドエージェント**を起こし、
各セッションが **1 ロール分の有界作業**(MAPE-K: Plan=graph に add / Execute=leased ノード実行監督 / Verify=done/failed の gate 判定+再計画)をして
**journal・handoff・next_plan・memory(既存の作業履歴機能)に書き戻して終了** → 次のセッションが同じ履歴を読んで続きを引く。3 セッションを Planner/Executor/Verifier で
FIFO ローテーションすれば、**人が張り付かずに生成→作業→終了→次生成**の連続稼働になる。**state は必ず work-graph + handoff + memory に外部化**(セッションの揮発メモリに依存しない)のが肝。
honest 限界=ローカル `rap` の相互起動は不可 → クラウド routines(cron)or 人 or watcher が「起こす」役を担う。まずは 2 ロール(Executor=tool driver 常駐 / Verifier=cron 定期)から実証するのが現実的。

**goal 駆動の自己終端ループ(goal 達成まで relay 継続、達成で自己停止)**: リレーの**停止条件を goal の成功基準の gate ノード**にする
(gated-stage-runner が pass/fail を返す。例=「full suite green ∧ 新 op N 件登録 ∧ `beats_hand_on_locked_holdout`」)。
- `CronCreate`(`schedule` skill)で cron relay を張る → 各発火が短命セッションを無人起動。
- 各セッションは MAPE-K 1 ロール(Plan/Execute/Verify)を実行 → journal・handoff・next_plan に書き戻して終了。
- **Verify ロールが goal gate を評価 → 未達なら継続(次の cron が発火)/ 達成なら `CronDelete` で relay を自己停止**。
  = 「goal 達成まで続き、達成したら自分を止める」自己終端。**goal と成功基準は必ず work-graph のノード(or next_plan の明示ゴール)に外部化**し、
  各セッションが同じ goal を読めるようにする(揮発メモリに置かない)。暴走防止に **cron 側で最大反復/期限**も設定。
- honest 限界=goal gate が機械判定できること(pass/fail を返す tool)が前提。判定が主観的(記事の質等)なら human-gate ノードを 1 つ挟む。

**役割数と『消費順 FIFO』(budget-ordered role rotation)**: ロールごとに 1 セッションの context/token 消費が違う
(概算 **Execute ≫ Plan > Verify > Record**)。効率化 = **1 セッションの寿命内でロールを消費の大きい順に降ろす**:
- fresh(~0–65%)= **Execute**(重い実装/workflow/敵対検証)— 重い仕事は必ず fresh context で(最も安く多く出せる)。
- mid(~65–85%)= **Plan-next**(次チャンク設計)+ **Verify**(gate 判定)。
- tail(~85–100%)= **Record/handoff**(next_plan/STATUS/memory/seed 次ノード=**元々必ずやる wrap-up=最も軽い作業を最も残り少ない budget で**)→ 終了。
- 次の fresh セッションが Execute を再開。= **ロール ⇔ budget バンド**の対応。必須の wrap-up が自然に一番安い tail に来る。
**論理フェーズは PDCA=4** が既定(Plan=graph に add / Do=Execute / Check=Verify / Act=Record・再計画。MAPE-K なら 5、OODA なら 4)。
**但し「4 ロール」≠「4 等分セッション」**: Do が突出し 1 セッションに収まらない → 実リレーは `1×Plan + N×Do + 1×Check + 1×Act`(N=execute 量÷budget)。
Check/Act は安すぎて専用セッションが無駄 → **物理セッションは消費で写像**する。
**役割数=区別できる消費ティア数**: 既定 **3**(Execute / Plan-next / Verify+Record)。Execute が突出するなら **2**
(重い Execute 専用 fresh セッション + 軽い **cron supervisor** が Plan/Verify/Record/次 seed を安く回す)。**>4 は遷移(handoff)コストが嵩むので避ける**
(似た消費ティアの 2 役は統合)。判断軸=(a) 遷移ごとの handoff コスト (b) 消費ティアの区別度 (c) 重ロールに fresh 1 本を丸ごと与えるか。
実装時は各セッションが**開始時に context 使用率と goal/graph 状態を読んで今回のロールを自己決定**し、tail に達したら Record して終了する(context 使用率は Stop フックの推定を利用)。

## 出力
- `raptor-worklog.db`(SQLite/WAL)にノード/エッジ/journal。各ノード成果 = `out/worklog/<task_id>/result*`。
- done/failed の集約は `stats`/`export`。bounded handoff = `compact --project <P> --show` → `out/worklog/handoff-<P>.md`。

## チェックリスト
- [ ] 作業を **独立ノード**に分解した(各ノード=コマンド or 有界プロンプトで完結)。
- [ ] tool ノードは **--spec-file の JSON**(`cmd` はリスト・`produces`・`timeout`)で積んだ。
- [ ] 依存は `--depends`、優先は `--priority 0` が最上位。
- [ ] overnight は **tool-only**(`run-once --available tool:command` / detached driver)で auth ゲートを避けた。
- [ ] 進捗確認は **read-only**(run-once/reclaim を serve 中に叩かない)。

## 注意 / よくある落とし穴
- **旧名 `raptor-workgraph` は存在しない** → 正しくは `raptor-worklog`([[reference_workgraph_multimodel_ops]] 2026-08-05 実測)。
- **serve/driver 稼働中に `run-once`/`reclaim` を叩かない** — `reclaim_expired()` が実行中ジョブを二重起動する。進捗は read-only SQLite。
- **lease TTL は spec.timeout 由来**(重量ジョブは長め)。`--workers 1` はループが subprocess でブロックし tick が来ないので回収されない(実測)。
- `cmd` は**リスト**(shell 文字列不可)。`<OUT>` は `out/worklog/<task_id>/result` に展開。
- 数十〜数百の大規模 fan-out は Workflow tool(JS オーケストレーション)も併用可(中間結果を main context から外に出す)。

## 関連
- `[[memory: reference_workgraph_multimodel_ops]]` — グラフエンジニアリング運用の正本(CLI/patterns/discipline)
- `[[memory: feedback_max_plan_autonomy]]` · `[[memory: feedback_parallel_first_execution]]` — 自律/並列の判定
- `[[memory: project_hillco_walk_artifact_to_locomujoco_2026_08_05]]` — 実適用例(gated stage runner / watcher / detached driver の全経緯)
- `libexec/raptor-worklog`(CLI)· `bin/rap.ps1`(`-Serve -Detach`)· `C:/dev/projects/llloop`(ループエンジニアリング MAPE-K)
