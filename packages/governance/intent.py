"""Semantic intent classification — detect dangerous prompts before tool execution."""
import re
from dataclasses import dataclass


@dataclass
class IntentSignal:
    category: str
    confidence: float
    evidence: str


THREAT_SIGNALS: list[tuple[str, str, float]] = [
    # Data exfiltration
    (r"(?i)send\s+(all|every|entire)\s+\w+\s+to\s+", "data_exfiltration", 0.8),
    (r"(?i)export\s+.*\s+to\s+(external|outside|third.?party)", "data_exfiltration", 0.9),
    (r"(?i)curl\s+.*\s+-d\s+", "data_exfiltration", 0.7),
    # Privilege escalation
    (r"(?i)(sudo|as\s+root|admin\s+access)", "privilege_escalation", 0.8),
    (r"(?i)chmod\s+777", "privilege_escalation", 0.9),
    # System destruction
    (r"(?i)(rm\s+-rf|del\s+/[sq]|format\s+c:)", "system_destruction", 0.95),
    (r"(?i)(drop\s+database|truncate\s+table)", "system_destruction", 0.9),
    # Prompt injection
    (r"(?i)ignore\s+(previous|above|all)\s+(instructions?|rules?)", "prompt_injection", 0.9),
    (r"(?i)you\s+are\s+now\s+(a|an)\s+", "prompt_injection", 0.7),
    (r"(?i)disregard\s+your\s+(previous|prior|earlier)\s+", "prompt_injection", 0.85),
    # Credential harvesting
    (r"(?i)(api[_-]?key|secret|password)\s*[:=]\s*\S+", "credential_exposure", 0.9),
    (r"(?i)print\s+(all\s+)?(env|environment|credentials?)", "credential_exposure", 0.8),
]


def classify_intent(content: str) -> list[IntentSignal]:
    """Return all threat signals detected in content."""
    signals = []
    for pattern, category, weight in THREAT_SIGNALS:
        match = re.search(pattern, content)
        if match:
            signals.append(IntentSignal(
                category=category,
                confidence=weight,
                evidence=match.group(),
            ))
    return signals


def is_safe(content: str, threshold: float = 0.7) -> bool:
    """Return True if no signal meets or exceeds threshold confidence."""
    return not any(s.confidence >= threshold for s in classify_intent(content))


class IntentClassifier:
    """Stateful classifier with configurable threshold and custom signals."""

    def __init__(self, threshold: float = 0.7, extra_signals: list[tuple] | None = None):
        self.threshold = threshold
        self.signals = list(THREAT_SIGNALS) + (extra_signals or [])

    def classify(self, content: str) -> list[IntentSignal]:
        results = []
        for pattern, category, weight in self.signals:
            match = re.search(pattern, content)
            if match:
                results.append(IntentSignal(
                    category=category,
                    confidence=weight,
                    evidence=match.group(),
                ))
        return results

    def is_safe(self, content: str) -> bool:
        return not any(s.confidence >= self.threshold for s in self.classify(content))

    def threats(self, content: str) -> list[IntentSignal]:
        return [s for s in self.classify(content) if s.confidence >= self.threshold]
