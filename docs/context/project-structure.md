# Project Structure

## Directory Tree

```
project-root/
├── AGENTS.md                          ← Core instructions (read every session)
├── templates/
│   └── claude-templates.md            ← Summary, handoff, decision, task, output contract templates
├── docs/
│   ├── discovery/                     ← Raw client inputs, briefs, requirements
│   ├── research/                      ← Market research, competitive analysis sources
│   ├── requirements/                  ← Structured requirements (from discovery)
│   ├── strategy/                      ← Positioning, value props, go-to-market
│   ├── context/                       ← Reusable domain knowledge (loaded on demand)
│   │   ├── client-briefs/             ← Per-client context files
│   │   ├── [your-domain].md           ← Your domain-specific context files
│   │   ├── [your-domain].md           ← (e.g., tech-stack.md, style-guide.md)
│   │   ├── processing-protocol.md     ← Document processing steps
│   │   ├── archive-rules.md           ← Summary lifecycle and file archival
│   │   ├── subagent-rules.md          ← When to use subagents vs. main agent
│   │   └── project-structure.md       ← This file
│   ├── archive/                       ← Processed raw files (DO NOT read unless told)
│   │   └── handoffs/                  ← Superseded session handoffs
│   └── summaries/                     ← ALL active session state lives here
│       ├── 00-project-brief.md        ← Initial project setup
│       ├── source-[filename].md       ← Per-document summaries
│       ├── analysis-[topic].md        ← Research outputs
│       ├── decision-[num]-[topic].md  ← Decision records
│       └── handoff-[date]-[topic].md  ← Latest session handoff ONLY
├── output/
│   ├── schemas/                       ← Data models, agent definitions
│   ├── prompts/                       ← System prompts for agents
│   ├── deliverables/                  ← Client-facing final outputs
│   └── presentations/                 ← Decks, workshop materials
└── .claude/
    ├── agents/                        ← Custom subagent definitions
    └── commands/                      ← Custom slash commands
```

## New Project Scaffold

```bash
mkdir -p docs/discovery docs/research docs/requirements docs/strategy docs/summaries docs/archive docs/archive/handoffs docs/context/client-briefs
mkdir -p output/schemas output/prompts output/deliverables output/presentations
mkdir -p templates .claude/agents .claude/commands
```
