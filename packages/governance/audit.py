"""Append-only audit trail for agent governance events."""
import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditEntry:
    timestamp: float
    agent_id: str
    tool_name: str
    action: str
    policy_name: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "tool": self.tool_name,
            "action": self.action,
            "policy": self.policy_name,
            **self.details,
        }


class AuditTrail:
    """Append-only audit trail — never modify or delete entries."""

    def __init__(self):
        self._entries: list[AuditEntry] = []

    def log(self, agent_id: str, tool_name: str, action: str,
            policy_name: str, **details) -> None:
        self._entries.append(AuditEntry(
            timestamp=time.time(),
            agent_id=agent_id,
            tool_name=tool_name,
            action=action,
            policy_name=policy_name,
            details=details,
        ))

    def denied(self) -> list[AuditEntry]:
        return [e for e in self._entries if e.action == "denied"]

    def by_agent(self, agent_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.agent_id == agent_id]

    def by_action(self, action: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.action == action]

    def __len__(self) -> int:
        return len(self._entries)

    def export_jsonl(self, path: str | Path) -> None:
        """Export as JSON Lines for log aggregation systems."""
        with open(path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(json.dumps(entry.to_dict()) + "\n")

    def summary(self) -> dict:
        from collections import Counter
        actions = Counter(e.action for e in self._entries)
        return {
            "total": len(self._entries),
            "allowed": actions.get("allowed", 0),
            "denied": actions.get("denied", 0),
            "errors": actions.get("error", 0),
        }
