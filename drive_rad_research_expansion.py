#!/usr/bin/env python3
"""研究直結 RAD コーパス分類の自動追加 (ユーザー全面承認 2026-06-01).

llcore の現研究 (進化型アーキテクチャ探索 + Z3 検証 + 統計健全性) に欠落していた
3 分野を自動構築する:
  - evolutionary_computation : GA/GP/ES/QD/MAP-Elites/novelty/open-endedness/ALife/neuroevolution (③研究の本体)
  - dynamical_systems        : Lipschitz/contraction/Hurwitz/Lyapunov/attractor/edge-of-chaos/reservoir (Stage 1b + kernel)
  - statistics_experimental_design : power/effect size/multiple comparisons/nonparametric/causal (統計抑制監査)

各分野: C:/dev/docs/<domain>_corpus/arxiv_queries.txt を書き出し → fetch_arxiv_topical.py で
papers/ に取得 → raptor_corpus2skill.py で階層 (Wiki 層) を構築 → C:/dev/docs/<domain>_corpus_v2/ へ配置。
arXiv レート制限衝突回避のため逐次実行。分野単位で continue-on-error (生 paper が RAD の主検索対象
なので corpus2skill が失敗しても papers は残り使える)。
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = Path("C:/dev/docs")
PER_QUERY = 60
SINCE = "2016-01-01"

QUERIES = {
    "evolutionary_computation": [
        "# evolutionary_computation — GA/GP/ES/QD/MAP-Elites/novelty/open-endedness/ALife/neuroevolution",
        "all:quality AND all:diversity AND all:evolution",
        "all:map AND all:elites AND all:behavior",
        "all:novelty AND all:search AND all:evolutionary",
        "all:open AND all:ended AND all:evolution",
        "all:neuroevolution AND all:neural",
        "all:neat AND all:augmenting AND all:topologies",
        "all:genetic AND all:programming AND all:evolution",
        "all:evolution AND all:strategies AND all:optimization",
        "all:lexicase AND all:selection",
        "all:artificial AND all:life AND all:evolution",
        "all:fitness AND all:landscape AND all:deceptive",
        "all:competitive AND all:coevolution AND all:algorithm",
        "all:behavioral AND all:diversity AND all:repertoire",
        "all:illumination AND all:algorithm AND all:behavior",
    ],
    "dynamical_systems": [
        "# dynamical_systems — Lipschitz/contraction/Hurwitz/Lyapunov/attractor/edge-of-chaos/reservoir",
        "all:lipschitz AND all:neural AND all:network",
        "all:contraction AND all:analysis AND all:dynamical",
        "all:lyapunov AND all:stability AND all:neural",
        "all:hurwitz AND all:stability AND all:matrix",
        "all:edge AND all:of AND all:chaos AND all:network",
        "all:edge AND all:of AND all:stability AND all:training",
        "all:reservoir AND all:computing AND all:echo AND all:state",
        "all:recurrent AND all:network AND all:fixed AND all:point",
        "all:attractor AND all:neural AND all:dynamics",
        "all:spectral AND all:radius AND all:recurrent",
        "all:contractive AND all:dynamics AND all:stability",
        "all:line AND all:attractor AND all:neural",
        "all:input AND all:state AND all:stability AND all:network",
        "all:certified AND all:lipschitz AND all:bound",
    ],
    "statistics_experimental_design": [
        "# statistics_experimental_design — power/effect size/multiple comparisons/nonparametric/causal/bootstrap",
        "all:statistical AND all:power AND all:analysis",
        "all:effect AND all:size AND all:estimation",
        "all:multiple AND all:comparisons AND all:correction",
        "all:false AND all:discovery AND all:rate",
        "all:nonparametric AND all:hypothesis AND all:test",
        "all:wilcoxon AND all:signed AND all:rank",
        "all:bootstrap AND all:confidence AND all:interval",
        "all:causal AND all:inference AND all:experimental",
        "all:experimental AND all:design AND all:optimal",
        "all:type AND all:error AND all:hypothesis AND all:testing",
        "all:benchmark AND all:evaluation AND all:reproducibility",
        "all:permutation AND all:test AND all:significance",
        "all:bayesian AND all:experimental AND all:design",
        "all:sequential AND all:analysis AND all:adaptive",
    ],
}


def run(cmd, **kw):
    print(f"\n[drive] $ {' '.join(str(c) for c in cmd)}", flush=True)
    return subprocess.run(cmd, check=False, **kw)


def fetch(domain: str):
    cdir = DOCS / f"{domain}_corpus"
    cdir.mkdir(parents=True, exist_ok=True)
    qf = cdir / "arxiv_queries.txt"
    qf.write_text("\n".join(QUERIES[domain]) + "\n", encoding="utf-8")
    papers = cdir / "papers"
    papers.mkdir(parents=True, exist_ok=True)
    print(f"\n[drive] === FETCH {domain} ===", flush=True)
    run([
        sys.executable, "fetch_arxiv_topical.py",
        "--query-file", str(qf),
        "--output", str(papers),
        "--per-query", str(PER_QUERY),
        "--since", SINCE,
    ], cwd=ROOT)
    n = len(list(papers.glob("*.md")))
    print(f"[drive] {domain}: {n} papers in {papers}", flush=True)
    return papers if n >= 30 else None


def build(domain: str, papers: Path):
    name = f"{domain}_corpus_v2"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    print(f"\n[drive] === CORPUS2SKILL {name} ===", flush=True)
    rc = run([
        sys.executable, "raptor_corpus2skill.py",
        "--source", str(papers),
        "--name", name,
        "--overwrite",
        "--max-depth", "2",
        "--min-cluster-size", "5",
        "--max-clusters", "8",
    ], cwd=ROOT, env=env)
    built = ROOT / ".claude" / "skills" / "corpus" / name
    dest = DOCS / name
    if built.exists():
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(built, dest)
        print(f"[drive] placed Wiki layer: {built} -> {dest}", flush=True)
    else:
        print(f"[drive] WARN: corpus2skill output not found at {built} (rc={rc.returncode}); "
              f"raw papers remain at {papers}", flush=True)


def main():
    t0 = time.monotonic()
    done, fetched = [], []
    for d in QUERIES:
        try:
            papers = fetch(d)
            if papers is not None:
                fetched.append(d)
                build(d, papers)
                done.append(d)
            else:
                print(f"[drive] {d}: <30 papers, skip build (papers kept)", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[drive] ERROR {d}: {e}", flush=True)
    elapsed = time.monotonic() - t0
    print(f"\n[drive] === ALL DONE ({elapsed:.0f}s) fetched={fetched} built={done} ===", flush=True)
    try:
        from packages.notify.telegram import notify_pipeline_event
        notify_pipeline_event(
            "rad-expansion",
            f"新規RADドメイン構築\nfetch: {', '.join(fetched) or 'なし'}\n"
            f"wiki: {', '.join(done) or 'なし'}\n経過: {elapsed:.0f}s",
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
