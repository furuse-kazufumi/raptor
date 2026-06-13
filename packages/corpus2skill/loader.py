"""Document loader for Corpus2Skill — supports 4 input types."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# Source code extensions to ingest
_CODE_EXTS = {".py", ".c", ".cpp", ".h", ".go", ".rs", ".js", ".ts", ".java", ".rb", ".php"}
_TEXT_EXTS = {".md", ".txt", ".rst", ".markdown"}
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
_MARKDOWN_METADATA_LINE = re.compile(
    r"^\*\*(Authors|Date|arXiv|URL|Source Query|Categories):\*\*",
    re.IGNORECASE,
)


@dataclass
class Document:
    doc_id: str
    source_path: Path
    doc_type: str       # "markdown" | "findings" | "cve" | "code"
    title: str
    text: str
    metadata: dict = field(default_factory=dict)


def load_documents(source_dir: Path) -> list[Document]:
    """Walk source_dir and load all supported documents."""
    docs: list[Document] = []
    counter = 0

    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue

        doc = None
        suffix = path.suffix.lower()

        if suffix in _TEXT_EXTS:
            doc = _load_text(path, counter)
        elif suffix == ".json":
            doc = _load_json_doc(path, counter)
        elif suffix in _CODE_EXTS:
            doc = _load_code(path, counter)

        if doc is not None and doc.text.strip():
            docs.append(doc)
            counter += 1

    return docs


def _load_text(path: Path, idx: int) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = _extract_md_title(text) if path.suffix in {".md", ".markdown"} else path.stem
    cleaned = _strip_markdown_metadata(text) if path.suffix in {".md", ".markdown"} else text
    return Document(
        doc_id=f"doc_{idx:04d}",
        source_path=path,
        doc_type="markdown",
        title=title or path.stem,
        text=cleaned[:8000],
        metadata={"ext": path.suffix},
    )


def _load_json_doc(path: Path, idx: int) -> Document | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError):
        return None

    if isinstance(data, list):
        # RAPTOR findings array
        texts = []
        for item in data:
            if isinstance(item, dict):
                texts.append(_flatten_finding(item))
        if not texts:
            return None
        text = "\n\n".join(texts)[:8000]
        return Document(
            doc_id=f"doc_{idx:04d}",
            source_path=path,
            doc_type="findings",
            title=path.stem,
            text=text,
            metadata={"count": len(data)},
        )

    if isinstance(data, dict):
        # CVE/NVD record detection
        if _is_cve_record(data):
            return _load_cve(data, path, idx)
        # RAPTOR single findings object
        if "findings" in data or "results" in data:
            items = data.get("findings", data.get("results", []))
            texts = [_flatten_finding(f) for f in items if isinstance(f, dict)]
            text = "\n\n".join(texts)[:8000]
            return Document(
                doc_id=f"doc_{idx:04d}",
                source_path=path,
                doc_type="findings",
                title=data.get("target", path.stem),
                text=text or json.dumps(data)[:4000],
                metadata={"count": len(items)},
            )
        # Generic JSON — stringify top-level keys
        text = _stringify_dict(data)[:4000]
        return Document(
            doc_id=f"doc_{idx:04d}",
            source_path=path,
            doc_type="findings",
            title=path.stem,
            text=text,
            metadata={},
        )

    return None


def _load_cve(data: dict, path: Path, idx: int) -> Document:
    cve_id = (data.get("id") or data.get("cve_id") or
              data.get("CVE_data_meta", {}).get("ID", "UNKNOWN"))
    desc = _extract_cve_description(data)
    severity = data.get("severity", [])
    affected = data.get("affected", [])
    text = f"CVE: {cve_id}\n\n{desc}"
    if severity:
        text += f"\n\nSeverity: {json.dumps(severity)[:500]}"
    if affected:
        text += f"\n\nAffected: {json.dumps(affected)[:500]}"
    return Document(
        doc_id=f"doc_{idx:04d}",
        source_path=path,
        doc_type="cve",
        title=cve_id,
        text=text[:6000],
        metadata={"cve_id": cve_id},
    )


def _load_code(path: Path, idx: int) -> Document:
    text = path.read_text(encoding="utf-8", errors="replace")
    return Document(
        doc_id=f"doc_{idx:04d}",
        source_path=path,
        doc_type="code",
        title=str(path.name),
        text=f"# {path}\n\n{text[:6000]}",
        metadata={"lang": path.suffix.lstrip(".")},
    )


# ── helpers ───────────────────────────────────────────────────────────────────

def _extract_md_title(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _strip_markdown_metadata(text: str) -> str:
    """Remove fetch-time metadata that should not influence TF-IDF labels."""
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!--") and "source-query:" in stripped.lower():
            continue
        if _MARKDOWN_METADATA_LINE.match(stripped):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _is_cve_record(data: dict) -> bool:
    return bool(
        data.get("id", "").startswith("CVE-")
        or data.get("cve_id", "").startswith("CVE-")
        or "CVE_data_meta" in data
        or ("aliases" in data and any(
            str(a).startswith("CVE-") for a in data.get("aliases", [])
        ))
    )


def _extract_cve_description(data: dict) -> str:
    # OSV format
    if "summary" in data:
        return data["summary"]
    if "details" in data:
        return data["details"]
    # NVD format
    desc_data = data.get("description", {})
    if isinstance(desc_data, dict):
        items = desc_data.get("description_data", [])
        if items:
            return items[0].get("value", "")
    return str(desc_data)[:500]


def _flatten_finding(item: dict) -> str:
    parts = []
    for key in ("title", "message", "description", "check_id", "rule_id",
                 "severity", "cve_id", "path", "file"):
        val = item.get(key)
        if val:
            parts.append(f"{key}: {val}")
    return "\n".join(parts)


def _stringify_dict(data: dict) -> str:
    lines = []
    for k, v in data.items():
        if isinstance(v, (str, int, float, bool)):
            lines.append(f"{k}: {v}")
        elif isinstance(v, list) and v and isinstance(v[0], str):
            lines.append(f"{k}: {', '.join(str(x) for x in v[:10])}")
    return "\n".join(lines)
