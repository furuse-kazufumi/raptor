"""Automated code review with approval flow using Claude API."""
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    import anthropic
    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False


class ReviewStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CHANGES = "needs_changes"


@dataclass
class ReviewResult:
    status: ReviewStatus
    summary: str
    findings: list[dict] = field(default_factory=list)
    approved_by: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "summary": self.summary,
            "findings": self.findings,
            "approved_by": self.approved_by,
            "timestamp": self.timestamp,
        }


_REVIEW_PROMPT = """\
You are a security-focused code reviewer. Review the following code diff or snippet.

Code:
```
{code}
```

Respond in JSON with this exact structure:
{{
  "status": "approved" | "needs_changes" | "rejected",
  "summary": "one-line summary",
  "findings": [
    {{"severity": "high|medium|low|info", "line": <int or null>, "message": "description"}}
  ]
}}

Focus on: security vulnerabilities, dangerous patterns, correctness issues.
Approve only if no high/critical findings exist.
"""


class CodeReviewer:
    """Automated code review using Claude API with human-approval fallback."""

    def __init__(self, model: str = "claude-opus-4-7", require_human_for_high: bool = True):
        self.model = model
        self.require_human_for_high = require_human_for_high
        self._history: list[ReviewResult] = []

    def review(self, code: str, context: str = "") -> ReviewResult:
        """Run automated review. Raises RuntimeError if SDK not available."""
        if not _SDK_AVAILABLE:
            raise RuntimeError("anthropic SDK not installed: pip install anthropic")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")

        client = anthropic.Anthropic(api_key=api_key)

        prompt = _REVIEW_PROMPT.format(code=code[:4000])
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        message = client.messages.create(
            model=self.model,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        raw = ""
        for block in message.content:
            if hasattr(block, "text"):
                raw = block.text
                break

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            data = json.loads(m.group()) if m else {"status": "needs_changes", "summary": raw, "findings": []}

        status = ReviewStatus(data.get("status", "needs_changes"))
        result = ReviewResult(
            status=status,
            summary=data.get("summary", ""),
            findings=data.get("findings", []),
            approved_by=self.model,
        )
        self._history.append(result)
        return result

    def needs_human_approval(self, result: ReviewResult) -> bool:
        if not self.require_human_for_high:
            return False
        return any(f.get("severity") == "high" for f in result.findings)

    def approve(self, result: ReviewResult, approver: str) -> ReviewResult:
        """Record human approval override."""
        result.status = ReviewStatus.APPROVED
        result.approved_by = approver
        return result

    def history(self) -> list[dict]:
        return [r.to_dict() for r in self._history]
