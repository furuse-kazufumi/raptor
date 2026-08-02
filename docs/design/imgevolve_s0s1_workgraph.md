# imgevolve — S0+S1 を work-graph タスクとして設計

> 画像処理アルゴリズムを **設計する** AI(前段調査で差別化確定)の PoC を、raptor の
> work-graph 上に「永続開発ハーネス」として載せる設計。**S0=正直な床 / S1=進化コア**。
> 作業名 `imgevolve`(公開名は衝突実測後に確定=[[feedback_name_collision_check]])。

## 0. 位置づけ(なぜ work-graph か)
- 実行(baseline 測定・進化探索・集計)は **CommandWorker(`tool`)= セッション/トークン非消費**で自律。
- 監督コストは **ローカル ollama 要約(`summarize`)** で圧縮(SESSION_SUMMARY #0 のコンテキスト経済対策)。
- 人が残るのは **1ノードだけ**(`reason`=Claude, human-gated):「進化は holdout で手組みを正直に上回ったか / S2 へ進むか」。
- → NAS r2(29h 自律)で実証済みの構造をそのまま画像 op 探索へ転用。**評価器が信頼できる区間 = 永続で回る**。

## 1. 対象タスク(S0/S1 の的)
**画像デノイズ**(GT が明確・holdout が自然):
- データ: 小さな clean 画像セット → 既知ノイズ(gaussian σ)付与。GT=clean。
- 指標: **holdout 画像**の PSNR / SSIM(train と disjoint)。
- なぜこれ: 「進化が手組み(固定 Gaussian)を holdout で上回るか」を**1つの数字で正直に問える**。

## 2. IR / op-DSL(S0/S1 最小)
genome = 型付き画像 op の小さな **DAG**(S0/S1 は線形チェーン〜浅い DAG)。各 op は `image → image`。

| op | パラメータ | 備考 |
|---|---|---|
| `blur(sigma)` | σ∈[0.3,3] | gaussian |
| `median(k)` | k∈{3,5,7} | 非線形 |
| `conv(kernel_id, scale)` | bank から選択 | sobel/laplacian/box/sharpen |
| `bilateral(sigma_s, sigma_r)` | | エッジ保存平滑 |
| `gamma(g)` | g∈[0.5,2] | |
| `clip/normalize` | | |
| `add/absdiff/mul(branch)` | 2入力 | 分岐合成(DAG) |

- **型付き**ゆえ検証可能・S2 で多言語 codegen 可(Halide 下敷き or 自前は S2 判断、S0/S1 に影響なし)。
- genome エンコード = op 列 + パラメータベクトル(r2 の CMA-ES/memetic がそのまま乗る)。

## 3. タスクグラフ
```
 s0-baseline ──► s1-evolve ──► s1-metrics ──► s1-summarize ──► s1-review
   [tool]          [tool]         [tool]        [summarize]       [reason]
  手組み+乱択     memetic探索    champion vs    ローカルNN要約    人の判断/例外
  の床(honest)  holdout-gated   baseline/gap    (監督コスト↓)   S2へ進むか
   自律            自律(長時間)    自律            自律(無料)       human-gated
```

| id | capability | worker | depends | produces | 役割 |
|---|---|---|---|---|---|
| `imgevolve-s0-baseline` | `tool` | CommandWorker | — | `<OUT>.json` | 手組み+乱択 baseline(train/holdout) |
| `imgevolve-s1-evolve` | `tool` | CommandWorker | s0-baseline | `<OUT>.json` | memetic 探索 → pareto+champion |
| `imgevolve-s1-metrics` | `tool` | CommandWorker | s1-evolve | `<OUT>.md` | champion vs baseline・汎化 gap・overfit flag |
| `imgevolve-s1-summarize` | `summarize` | ollama(無料) | s1-metrics | md | 人向け短要約(context 経済) |
| `imgevolve-s1-review` | `reason` | claude(human) | s1-summarize | — | 「正直に勝ったか / S2 へ」= 例外的人手 |

**データ受け渡し**: 共有 workdir `out/worklog/imgevolve/`(worklog ボードが拾う)。各 script は
`--workdir out/worklog/imgevolve` を受け、baseline.json→evolve→champion.json→report を順に読む。
`<OUT>` はギャラリー掲載用コピー、実データは共有 workdir(NAS 週次 collector と同じ流儀)。

## 4. 実際の投入コマンド(spec は JSON=`--spec-file`)
```powershell
# 事前: 共有 workdir & project
$W = "out/worklog/imgevolve"
# 各 tool spec は {cmd,cwd,env,produces,timeout} の JSON ファイル(specs/ 配下)

raptor-worklog add --id imgevolve-s0-baseline --project imgevolve `
  --title "S0 baseline (hand-built + random search)" `
  --capability tool --spec-file specs/s0_baseline.json --priority 2

raptor-worklog add --id imgevolve-s1-evolve --project imgevolve `
  --title "S1 memetic evolution (holdout-gated)" `
  --capability tool --spec-file specs/s1_evolve.json --depends imgevolve-s0-baseline --priority 2

raptor-worklog add --id imgevolve-s1-metrics --project imgevolve `
  --title "S1 metrics: champion vs baseline, generalization gap" `
  --capability tool --spec-file specs/s1_metrics.json --depends imgevolve-s1-evolve --priority 2

raptor-worklog add --id imgevolve-s1-summarize --project imgevolve `
  --title "S1 digest for human (local NN)" `
  --capability summarize --spec-file specs/s1_summarize.txt --depends imgevolve-s1-metrics --priority 2

raptor-worklog add --id imgevolve-s1-review --project imgevolve `
  --title "S1 decision: did evolution beat baseline honestly? proceed to S2?" `
  --capability reason --spec "…(下記 review プロンプト)…" --depends imgevolve-s1-summarize `
  --constraints needs-human-judgment
```

### tool spec 例(`specs/s1_evolve.json`)
```json
{
  "cmd": ["py","-3.11","evolve.py","--workdir","out/worklog/imgevolve",
          "--baseline","out/worklog/imgevolve/baseline.json",
          "--gens","60","--pop","24","--seed","0","--out","<OUT>.json"],
  "cwd": "C:/dev/projects/imgevolve",
  "env": {"PYTHONUTF8":"1"},
  "produces": "<OUT>.json",
  "timeout": 21600
}
```
> list-arg のみ・shell 文字列なし・`produces` 不在は fail-closed(CommandWorker 規約)。

## 5. script インターフェース(実装は次段)
- `baseline.py --workdir W --out <p>`: clean/noisy を split(train/holdout)→ 手組み(固定σ Gaussian)と
  **乱択 baseline**(N ランダム genome の最良)を holdout で評価 → `baseline.json{train_psnr,holdout_psnr,hand,random}`。
- `evolve.py --workdir W --baseline b.json --gens --pop --seed --out <p>`: **r2 の memetic/CMA-ES を再利用**、
  op-DAG genome を探索、fitness=train PSNR、holdout を毎世代トラック(fitness には使わない)→ `pareto.json`+`champion.json`(IR)。
  **決定性**(seed 固定・NAS r2 のビット一致規律)。
- `report.py --workdir W --out <p>`: champion vs baseline を **holdout** で比較、
  **汎化 gap = train − holdout**、gap 過大なら `overfit=true` を立て、`metrics.json`+`report.md`。

## 6. honest gate(trait③=過学習の正直開示)
- fitness は **train のみ**で回し、**holdout は評価専用**(pseudo-equation trap 対策)。
- report が (a) champion holdout ≤ baseline holdout、または (b) 汎化 gap > 閾値 → **overfit フラグ**。
- review ノード(人)には「勝った/負けた」を**数字と gap 付き**で提示(誇張禁止=honest disclosure)。

## 7. なぜ永続か / どう回し続けるか
- s0→s1→metrics→summarize は **全部自律**(tool+ollama)。人は review 1ノードのみ。
- **再投入で永続**: `imgevolve-s1-evolve` を seed 違い/gens 増で再 add(NAS r2 と同様)→ metrics/gate が毎回正直に判定。
- 監督イベント化: review は Monitor+PushNotification で「gate 結果が出たら」だけ人に上げる(定時 /loop を使わない=#0)。
- 進捗確認は **read-only SQLite**(実行中に run-once/reclaim を叩かない=[[project 運用規律]])。

## 8. honest な残リスクと守り
| リスク | 守り |
|---|---|
| 報酬ハック(train に過適合) | holdout 分離 + gap 閾値 + overfit フラグ |
| op-DSL が貧弱で進化<手組み | それも**正直な結果**として残す(負けを消さない)。op 追加は S3 で LLM 提案 |
| CommandWorker 二重起動 | 長時間ジョブ中に reclaim/run-once を叩かない運用規律 |
| 監督コスト線形 | ollama 要約 + review をイベント化 |

## 9. 未決(S0/S1 着手には不要)
- 公開名(衝突実測後)/ 新 project dir `C:/dev/projects/imgevolve` の作成。
- S2 codegen を **Halide 下敷き** か **自前 IR** か(S2 の判断)。
- 対象タスクを denoise 以外(エッジ/二値化)へ広げるか(S4)。

## 10. 着手順
1. `C:/dev/projects/imgevolve/` 作成 + `baseline.py`/`evolve.py`/`report.py` 骨組み(r2 memetic 再利用)。
2. `specs/*.json` を書き、上記 `raptor-worklog add` でグラフ投入。
3. `raptor-worklog serve --workers 1` で自律実行 → review ノードで人が結果を見る。
4. gate が「進化>手組み(holdout)」を示せば S2、示さなければ op-DSL を正直に見直す。
