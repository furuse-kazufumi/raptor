---
name: corpus2skill
description: Convert document corpus into a navigable hierarchical skill directory for LLM agents (TF-IDF + k-means + claude-haiku summarization)
user-invocable: true
---

# Corpus2Skill

Transform large document collections into a hierarchical skill directory that LLM agents can navigate like a filesystem — no vector DB required at query time.

## When to Use

- You have a large set of security research documents, CVE data, or RAPTOR findings and want to make them navigable
- You want to build a reusable knowledge base from past analysis runs under `out/`
- You need structured LLM-navigable knowledge from unstructured markdown/JSON/code files
- Standard RAG vector search is missing context due to flat document structure

## Invocation

```
/corpus2skill <source_dir> [options]
```

Or via Python:

```bash
python3 raptor.py corpus2skill --source <source_dir> [options]
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--source <path>` | *(required)* | Source directory containing documents to ingest |
| `--name <name>` | basename of `--source` | Output corpus name (used as skill directory name) |
| `--max-depth <n>` | `2` | Maximum hierarchy depth |
| `--min-cluster-size <n>` | `3` | Minimum documents per cluster leaf |
| `--max-clusters <n>` | `8` | Maximum clusters per hierarchy level |
| `--model <model_id>` | `claude-haiku-4-5-20251001` | LLM model for cluster summarization |
| `--overwrite` | off | Overwrite existing skill directory |
| `--out <dir>` | auto | Run report output directory |

## Supported Document Types

| Type | Extensions | Extracted Content |
|------|-----------|-------------------|
| Markdown / text | `.md`, `.txt`, `.rst` | Full text (first 8000 chars) |
| RAPTOR findings | `.json` with findings/results keys | title + description + severity + CVE ID |
| CVE / NVD data | `.json` with CVE ID keys | CVE ID + description + affected + severity |
| Source code | `.py`, `.c`, `.cpp`, `.go`, `.rs`, `.js`, `.ts` | File path + source (first 6000 chars) |

## Pipeline

```
Source dir
    ↓
[LOAD]      Discover files → Document objects (4 types)
    ↓
[EMBED]     TF-IDF vectorization (max 5000 features, sublinear_tf)
    ↓
[CLUSTER]   k-means (k = √n, capped at max-clusters-per-level)
    ↓         ↻ recurse if cluster > min_cluster_size × 2
[SUMMARIZE] claude-haiku generates SKILL.md per cluster
    ↓
[WRITE]     .claude/skills/corpus/<name>/ hierarchy
```

## Execution

```bash
# Standard run on past RAPTOR findings
libexec/raptor-run-lifecycle start corpus2skill --target out/
# OUTPUT_DIR=out/corpus2skill_<timestamp>

python3 raptor_corpus2skill.py \
  --source out/ \
  --name past_findings \
  --out "$OUTPUT_DIR"

libexec/raptor-run-lifecycle complete "$OUTPUT_DIR"
```

## Output

| File | Description |
|------|-------------|
| `.claude/skills/corpus/<name>/INDEX.md` | Top-level navigation index |
| `.claude/skills/corpus/<name>/cluster_*/SKILL.md` | Cluster summaries with sub-cluster links |
| `.claude/skills/corpus/<name>/cluster_*/docs/*.md` | Individual documents (text-converted) |
| `.claude/skills/corpus/<name>/metadata.json` | Build metadata and statistics |
| `out/corpus2skill_<timestamp>/corpus2skill_report.json` | Run report (counts, timing, output path) |

## Navigating the Output (Online Phase)

When investigating a topic after `/corpus2skill` has been run:

1. Read `.claude/skills/corpus/<name>/INDEX.md` to identify the relevant cluster
2. Read that cluster's `SKILL.md` for an overview and links to sub-clusters
3. Descend into sub-clusters until you find relevant `docs/`
4. Load specific documents as needed

## Integration

Run after `/sca` or `/sourcehunt` to convert findings into reusable knowledge:

```bash
# Build knowledge base from all past scan results
python3 raptor.py corpus2skill --source out/ --name scan_history --overwrite

# Build CVE knowledge base
python3 raptor.py corpus2skill --source /path/to/cve-data/ --name cve_kb

# Self-apply: build knowledge from RAPTOR's own skills
python3 raptor.py corpus2skill --source .claude/skills/ --name raptor_skills
```

## Dependencies

- `scikit-learn` — TF-IDF vectorization and k-means clustering
- `anthropic` SDK — cluster summarization via claude-haiku (already in RAPTOR)
