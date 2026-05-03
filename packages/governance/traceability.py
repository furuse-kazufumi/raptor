"""Multi-AI action traceability — track actions across Claude/GPT/Gemini agents."""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ActionRecord:
    trace_id: str
    agent_id: str
    provider: str          # "claude", "openai", "gemini", "unknown"
    action_type: str       # "tool_call", "llm_response", "human_input", "approval"
    content: str
    timestamp: float
    parent_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "action_type": self.action_type,
            "content": self.content[:500],  # truncate for storage
            "timestamp": self.timestamp,
            "parent_id": self.parent_id,
            **self.metadata,
        }


class ActionTracer:
    """Trace multi-AI actions into a causal chain for auditability."""

    KNOWN_PROVIDERS = {"claude", "openai", "gemini", "mistral", "unknown"}

    def __init__(self):
        self._records: list[ActionRecord] = []
        self._active_trace: Optional[str] = None

    def start_trace(self, root_agent_id: str, provider: str = "unknown") -> str:
        trace_id = str(uuid.uuid4())[:8]
        self._active_trace = trace_id
        self.record(
            agent_id=root_agent_id,
            provider=provider,
            action_type="trace_start",
            content=f"Trace started by {root_agent_id}",
            trace_id=trace_id,
        )
        return trace_id

    def record(
        self,
        agent_id: str,
        action_type: str,
        content: str,
        provider: str = "unknown",
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        **metadata,
    ) -> ActionRecord:
        rec = ActionRecord(
            trace_id=trace_id or self._active_trace or "untraced",
            agent_id=agent_id,
            provider=provider if provider in self.KNOWN_PROVIDERS else "unknown",
            action_type=action_type,
            content=content,
            timestamp=time.time(),
            parent_id=parent_id,
            metadata=metadata,
        )
        self._records.append(rec)
        return rec

    def get_trace(self, trace_id: str) -> list[ActionRecord]:
        return [r for r in self._records if r.trace_id == trace_id]

    def by_agent(self, agent_id: str) -> list[ActionRecord]:
        return [r for r in self._records if r.agent_id == agent_id]

    def by_provider(self, provider: str) -> list[ActionRecord]:
        return [r for r in self._records if r.provider == provider]

    def causal_chain(self, trace_id: str) -> list[ActionRecord]:
        """Return records in causal order (parent before child)."""
        records = {r.timestamp: r for r in self.get_trace(trace_id)}
        return sorted(records.values(), key=lambda r: r.timestamp)

    def summary(self) -> dict:
        from collections import Counter
        providers = Counter(r.provider for r in self._records)
        action_types = Counter(r.action_type for r in self._records)
        traces = len({r.trace_id for r in self._records})
        return {
            "total_actions": len(self._records),
            "traces": traces,
            "providers": dict(providers),
            "action_types": dict(action_types),
        }

    def export_jsonl(self, path) -> None:
        import json
        from pathlib import Path
        with open(Path(path), "w", encoding="utf-8") as f:
            for rec in self._records:
                f.write(json.dumps(rec.to_dict()) + "\n")
