"""Agent trust scoring with temporal decay for multi-agent systems."""
import math
import time
from dataclasses import dataclass, field


@dataclass
class TrustScore:
    """Trust score with temporal decay — trust erodes without ongoing good behavior."""
    score: float = 0.5
    successes: int = 0
    failures: int = 0
    last_updated: float = field(default_factory=time.time)

    def record_success(self, reward: float = 0.05) -> None:
        self.successes += 1
        self.score = min(1.0, self.score + reward * (1 - self.score))
        self.last_updated = time.time()

    def record_failure(self, penalty: float = 0.15) -> None:
        self.failures += 1
        self.score = max(0.0, self.score - penalty * self.score)
        self.last_updated = time.time()

    def current(self, decay_rate: float = 0.001) -> float:
        """Score after exponential decay since last update."""
        elapsed = time.time() - self.last_updated
        return self.score * math.exp(-decay_rate * elapsed)

    @property
    def reliability(self) -> float:
        total = self.successes + self.failures
        return self.successes / total if total > 0 else 0.0

    def __repr__(self) -> str:
        return (
            f"TrustScore(current={self.current():.3f}, "
            f"successes={self.successes}, failures={self.failures}, "
            f"reliability={self.reliability:.2%})"
        )


class AgentTrustRegistry:
    """Registry of trust scores for agents in a multi-agent system."""

    def __init__(self, default_score: float = 0.5):
        self._default = default_score
        self.scores: dict[str, TrustScore] = {}

    def get_trust(self, agent_id: str) -> TrustScore:
        if agent_id not in self.scores:
            self.scores[agent_id] = TrustScore(score=self._default)
        return self.scores[agent_id]

    def record_success(self, agent_id: str, **kwargs) -> None:
        self.get_trust(agent_id).record_success(**kwargs)

    def record_failure(self, agent_id: str, **kwargs) -> None:
        self.get_trust(agent_id).record_failure(**kwargs)

    def meets_threshold(self, agent_id: str, threshold: float) -> bool:
        return self.get_trust(agent_id).current() >= threshold

    def most_trusted(self, agents: list[str]) -> str:
        if not agents:
            raise ValueError("Empty agent list")
        return max(agents, key=lambda a: self.get_trust(a).current())

    def summary(self) -> list[dict]:
        return [
            {"agent_id": aid, **{
                "score": ts.current(),
                "successes": ts.successes,
                "failures": ts.failures,
                "reliability": ts.reliability,
            }}
            for aid, ts in sorted(self.scores.items(), key=lambda x: x[1].current(), reverse=True)
        ]
