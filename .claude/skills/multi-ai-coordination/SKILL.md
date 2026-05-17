---
name: multi-ai-coordination
description: |
  Inter-agent communication patterns for RAPTOR workflows that span Claude,
  GPT, and Gemini. Provides ActionTracer (causal chain across providers)
  and other coordination primitives. Auto-trigger when the user asks about
  multi-agent / multi-LLM coordination or ActionTracer usage.
---

# Multi-AI Coordination Skill

Inter-agent communication patterns for RAPTOR workflows that span Claude, GPT, and Gemini.

## Core Primitives

### ActionTracer — causal chain across providers
```python
from packages.governance.traceability import ActionTracer

tracer = ActionTracer()
tid = tracer.start_trace("claude-orchestrator", provider="claude")

# Record each agent's action with provider tag
tracer.record("gpt-analyst", "tool_call", "semgrep scan", provider="openai", trace_id=tid)
tracer.record("gemini-reviewer", "llm_response", "findings summary", provider="gemini", trace_id=tid)

# Retrieve ordered causal chain
for rec in tracer.causal_chain(tid):
    print(f"[{rec.provider}:{rec.agent_id}] {rec.action_type}: {rec.content[:80]}")

tracer.export_jsonl("out/trace.jsonl")
```

### CodeReviewer — automated review with approval gate
```python
from packages.governance.code_review import CodeReviewer

reviewer = CodeReviewer(model="claude-opus-4-7", require_human_for_high=True)
result = reviewer.review(code_diff, context="patch for CVE-2024-xxxx")

if reviewer.needs_human_approval(result):
    # Pause and request human sign-off
    result = reviewer.approve(result, approver="security-lead")

print(result.status.value, result.summary)
```

## Coordination Patterns

### Pattern 1: Claude orchestrates, GPT specialises
```
Claude (RAPTOR) → plan scan
Claude → run /sourcehunt
Claude → send findings to GPT-4 via tool call
GPT-4 → deeper analysis (optional, user-supplied)
Claude → merge results, write report
ActionTracer records every hop
```

### Pattern 2: Parallel scanning, Claude arbitrates
```
Agent A (Claude) → scan auth layer
Agent B (GPT/Gemini) → scan crypto layer  ← user provides credentials
Claude → trust-weighted merge via AgentTrustRegistry
CodeReviewer → approve merged findings before export
```

### Pattern 3: Review gate before patch
```
/sourcehunt finds vulnerability
CodeReviewer.review(patch_diff)  → needs_changes or approved
If needs_human_approval → pause, notify user
After approval → /patch applies diff
ActionTracer logs full chain
```

## Trust Thresholds

| Provider       | Default threshold | Notes                          |
|---------------|-------------------|--------------------------------|
| claude        | 0.8               | Primary orchestrator           |
| openai        | 0.6               | Specialised analysis           |
| gemini        | 0.6               | Specialised analysis           |
| unknown       | 0.3               | Sandboxed, review required     |

```python
from packages.governance.trust import AgentTrustRegistry

registry = AgentTrustRegistry(default_score=0.5)
registry.record_success("claude-1")
registry.record_failure("unknown-agent")

# Pick most trusted agent for sensitive task
best = registry.most_trusted(["claude-1", "gpt-1", "unknown-agent"])
```

## Governance Integration

Always wrap cross-agent actions with `AuditTrail`:
```python
from packages.governance import AuditTrail, GovernancePolicy, govern

policy = GovernancePolicy(
    name="cross-ai",
    blocked_tools=["rm", "format"],
    require_human_approval=["git_push", "patch_apply"],
)
trail = AuditTrail()

@govern(policy, audit_trail=trail)
async def run_external_agent(prompt: str) -> str:
    ...
```

## Output Schema

`ActionRecord.to_dict()` fields:
- `trace_id` — 8-char UUID prefix shared across a workflow
- `agent_id` — agent name (e.g. `"claude-orchestrator"`)
- `provider` — `"claude" | "openai" | "gemini" | "mistral" | "unknown"`
- `action_type` — `"tool_call" | "llm_response" | "human_input" | "approval" | "trace_start"`
- `content` — truncated to 500 chars
- `parent_id` — optional causal parent `trace_id`
- `timestamp` — Unix float
