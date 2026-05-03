---
name: sca
description: Software Composition Analysis — scan dependency manifests and query OSV database for known CVEs. Covers PyPI, npm, Maven, crates.io, Go, RubyGems, and more.
user-invocable: true
---

# SCA Skill

Software Composition Analysis pipeline that:
1. Discovers dependency manifests in the target repository
2. Parses each manifest to extract package names and versions
3. Queries the [OSV database](https://osv.dev) for known CVEs
4. Reports vulnerable dependencies with severity and CVE IDs

## When to Use

- Before or after `/scan` to check third-party dependencies
- When target repo has `requirements.txt`, `package.json`, `pom.xml`, `Cargo.toml`, `go.mod`, etc.
- To identify supply-chain vulnerabilities quickly
- As part of `/agentic` pre-flight dependency audit

---

## Invocation

```
/sca <target_path> [options]
```

**Options:**
| Flag | Description |
|------|-------------|
| `--no-osv` | Skip OSV network lookup (inventory only) |

---

## Supported Manifests

| File | Ecosystem |
|------|-----------|
| `requirements.txt` | PyPI |
| `pyproject.toml` | PyPI |
| `package.json` | npm |
| `pom.xml` | Maven |
| `build.gradle` | Maven |
| `Cargo.toml` | crates.io |
| `go.mod` | Go |
| `Gemfile` | RubyGems |

---

## Execution

```bash
libexec/raptor-run-lifecycle start sca --target <resolved_target>
# OUTPUT_DIR=<path>

python3 raptor_sca.py \
  --repo <target_path> \
  [--no-osv] \
  --out "$OUTPUT_DIR"

libexec/raptor-run-lifecycle complete "$OUTPUT_DIR"
```

---

## Output

| File | Contents |
|------|---------|
| `sca_report.json` | Full dependency inventory + OSV vuln data |

**Key fields in `sca_report.json`:**
```json
{
  "manifest_files": 3,
  "total_deps": 47,
  "summary": {
    "vulnerable_packages": 2,
    "total_cves": 4
  },
  "vulnerabilities": {
    "PyPI:requests:2.28.0": [
      {"id": "CVE-2023-XXXX", "severity": "HIGH", "summary": "..."}
    ]
  }
}
```

---

## Integration

- **After `/scan`**: Combine SAST findings with SCA for full risk picture
- **Before `/sourcehunt`**: Identify vulnerable library code to prioritize hunting
- **With `/validate`**: Vulnerable dependency version = known-exploitable attack path

---

## SWD Integration

After applying patches, verify no unintended drift:
```bash
libexec/raptor-swd snapshot <out_dir>
# ... apply patches ...
libexec/raptor-swd diff <out_dir>
```
