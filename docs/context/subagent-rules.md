# Subagent Deployment Rules

## When to Use Subagent vs. Main Agent

| Situation | Approach | Why |
| ----------- | ---------- | ----- |
| Reading/analyzing documents | Subagent | Keeps source content out of main context |
| Research and competitive analysis | Subagent | Heavy reading, return summary only |
| Writing deliverables | Main agent | Needs full decision-making context |
| Schema/architecture design | Main agent | Needs holistic project understanding |
| Code generation | Subagent | Isolated implementation, return result |
| Review and QA | Subagent | Fresh perspective, no bias from writing |

## Output Requirements

Subagent output must be structured — exact numbers, file paths, decisions with rationale, and open items — not free-form prose.

Optimal subagent return size: 1,000-2,000 tokens of structured summary. Longer returns consume main agent context without proportional benefit.
