# Mycel — Design Doc v0.3

## Vision
A lean, Temporal-native AI assistant that manages ideas and code via Telegram while growing a living knowledge network from every interaction. Mycel works like mycelium: no rigid hierarchy, just durable connections that spread, link, and strengthen over time. Self-healing, promise-keeping, and small enough to fully understand, modify, and own.

## Core Principles

### 1. Errors Are Actionable
Every failure produces: (a) what went wrong, (b) why, (c) options to fix it. The assistant never says "permission error" and stops. It says "I can't write to /foo because X. Want me to: [fix permissions] [try a different path] [skip this]?" Temporal retries handle transient failures silently. Only persistent failures surface to the user — with context.

### 2. Promises Are Workflows
If the assistant says "I'll follow up on this," that spawns a Temporal workflow with a timer. It literally cannot forget. No more "I'll check on that" → silence. Every commitment becomes a durable, retryable unit of work.

### 3. The Organization — Cost-Effective Model Routing

Think of it as a company, not a single employee. Every role has the right person for the job — you don't send the CEO to take meeting notes.

```
┌─────────────────────────────────────────────────────────┐
│                   OpenRouter (single API)                 │
├─────────┬───────────┬────────────┬──────────────────────┤
│  Intern │  Junior   │   Senior   │    Executive         │
│  (nano) │  (fast)   │   (smart)  │    (reasoning)       │
│  ~$0.10 │  ~$0.50   │   ~$3.00   │    ~$15.00           │
│  /M tok │  /M tok   │   /M tok   │    /M tok            │
├─────────┼───────────┼────────────┼──────────────────────┤
│ Extract │ Chat      │ Link know- │ Architecture         │
│ facts   │ Classify  │ ledge      │ Complex reasoning    │
│ Summarize│ Lookups  │ Error      │ System design        │
│ Format  │ Simple    │ recovery   │ Multi-step planning  │
│ Parse   │ tools     │ Code review│ When it matters      │
│         │ Reminders │ Teach      │                      │
└─────────┴───────────┴────────────┴──────────────────────┘
         ↑                    ↑                  ↑
    Background ops      User-facing         On-demand only
    (high volume,       (daily driver)      (user requests
     must be cheap)                          or auto-escalation)
```

**The key insight:** Most of the system's work is invisible background ops — fact extraction, summarization, classification, parsing. These fire on *every turn* and must be dirt-cheap. The user-facing conversation model handles daily chat. The expensive models only activate for genuinely hard problems.

#### Role Definitions

| Role | Model Tier | Cost | Used For | Volume |
|------|-----------|------|----------|--------|
| **Intern** | Nano (gpt-4.1-nano, gemini-flash-lite) | ~$0.10/M | Fact extraction, summarization, formatting, parsing, classification | Every turn (background) |
| **Junior** | Fast (grok-fast, gemini-flash, gpt-4.1-mini) | ~$0.50/M | Daily chat, lookups, simple tool use, reminders | Most user messages |
| **Senior** | Smart (sonnet, gpt-4.1) | ~$3/M | Knowledge linking, error recovery, code review, teaching moments | When complexity warrants |
| **Executive** | Reasoning (opus, gpt-5.2, o3) | ~$15/M | Architecture, complex multi-step reasoning, system design | Rare, on-demand |
| **Specialist** | Coding agents (codex, claude-code) | Varies | Code generation, refactoring, debugging | When code work needed |

#### Activity → Role Mapping

Every activity in the system has a default role assignment:

```yaml
# Activity role assignments (configurable)
roles:
  intern:  # Background ops — high volume, must be cheap
    - extract_facts        # Pull facts from conversation turns
    - summarize_context    # Compress conversation history
    - classify_task        # Determine which role handles a message
    - format_response      # Clean up formatting
    - parse_tool_output    # Structure tool results
    - detect_promises      # Scan for commitments ("I'll follow up")

  junior:  # Daily driver — user-facing conversation
    - conversation_turn    # Default chat responses
    - simple_tool_use      # File read, web search, basic exec
    - memory_search        # Query knowledge base
    - generate_reminders   # Create reminder text

  senior:  # Complex work — activated when needed
    - link_knowledge       # Find connections in the Zettelkasten
    - error_recovery       # Diagnose and suggest fixes for failures
    - code_review          # Review PRs and code changes
    - teach                # Explain concepts, mentor
    - consolidate_memory   # Weekly knowledge graph maintenance
    - resolve_conflicts    # Handle contradicting memories

  executive:  # Heavy lifting — rare, expensive, worth it
    - architecture_design  # System design sessions
    - complex_reasoning    # Multi-step analysis
    - strategic_planning   # Project planning, roadmaps
    # Activated by: explicit user request, or senior self-escalation

  specialist:  # Code work — dedicated agents
    - code_generation      # New features, implementations
    - refactoring          # Code restructuring
    - debugging            # Complex bug investigation
```

#### Cost Projection

For a typical day (50 messages, 20 tool calls):

| Role | Calls/day | Avg tokens | Daily cost |
|------|----------|------------|------------|
| Intern | ~100 (background) | ~500 | ~$0.05 |
| Junior | ~50 (conversation) | ~2000 | ~$0.50 |
| Senior | ~5 (when needed) | ~3000 | ~$0.05 |
| Executive | ~1 (rare) | ~5000 | ~$0.08 |
| **Total** | | | **~$0.68/day** |

Compare to using Opus for everything: ~150 calls × 2000 avg tokens = ~$4.50/day. **6-7x more expensive** for no quality gain on routine tasks.

#### Evaluation Infrastructure

Model assignments aren't static — they need testing:
- **Benchmark suite**: Standard tasks per role (fact extraction, classification, linking, reasoning)
- **Quality gates**: If a cheaper model's output drops below threshold, auto-upgrade
- **A/B logging**: Track which model handled what, compare quality over time
- **Easy to tune**: Change role assignments in config, no code changes

### 4. Temporal Is the Skeleton
Not a plugin. Not an integration. Every interaction is a workflow.

```
User sends Telegram message
  → Signal to ConversationWorkflow (long-running, durable)
    → ClassifyTask activity [INTERN] (what tier handles this?)
    → ExecuteTurn activity [JUNIOR/SENIOR/EXECUTIVE] (think + respond)
    → If tool calls needed:
        → ToolExecution child workflow (retryable, observable)
        → If coding task:
            → CodingAgent child workflow [SPECIALIST]
    → If promise detected [INTERN scan]:
        → FollowUp child workflow (timer + check-in)
    → MemoryUpdate child workflow [INTERN extract → SENIOR link]
    → SendReply activity → Telegram
```

What this gives you:
- **Crash recovery**: Temporal replays from last checkpoint. Nothing lost.
- **Retries**: Transient failures retry automatically with backoff.
- **Observability**: Every step visible in Temporal Web UI (localhost:8233).
- **Promises kept**: Follow-ups are child workflows with timers. They fire.
- **Always learning**: Every turn feeds the knowledge graph in the background.
- **History bounded**: ContinueAsNew after N turns keeps things fast.
- **Cost-effective**: Each activity uses the cheapest model that can do the job.

### 5. Memory Is Central — The Second Brain
Memory isn't a feature. It's the foundation. The system builds a living knowledge graph from every interaction — a Zettelkasten that grows organically.

**How it works:**
```
You chat normally
  → Reply goes out immediately (no delay)
  → Background MemoryUpdateWorkflow fires asynchronously:
    → [INTERN] Extract facts from the conversation
    → Mem0 stores, deduplicates, indexes
    → [SENIOR] KnowledgeLinkWorkflow finds connections to existing knowledge
    → Graph grows. Links strengthen. The system gets smarter.
```

**Three layers:**
1. **Workspace files** (SOUL.md, MEMORY.md, daily notes) — human-readable, git-trackable, directly editable
2. **Mem0** (fact storage + semantic search) — automatic extraction, deduplication, retrieval
3. **Zettelkasten graph** (linked knowledge) — non-hierarchical connections between ideas, concept clustering, contradiction detection

You never manually manage memory. It just learns. Over time, "What do I know about X?" doesn't just keyword-search — it traverses a web of connected concepts built from months of conversations.

### 6. You Own It
Small codebase. Your code. You can change how it thinks, what it remembers, how it routes.

---

## Architecture

### Components

```
┌──────────┐     ┌──────────────┐     ┌─────────────────┐
│ Telegram  │────▶│  Bot (Python)│────▶│  Temporal Server │
│  (user)   │◀────│  async       │◀────│  (localhost)     │
└──────────┘     └──────────────┘     └────────┬────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │   Workers (Python)   │
                                    ├──────────────────────┤
                                    │ ConversationWorkflow  │
                                    │  ├─ ClassifyTask [I]  │
                                    │  ├─ ExecuteTurn [J/S/E]│
                                    │  ├─ ToolExecution     │
                                    │  ├─ CodingAgent [SP]  │
                                    │  ├─ FollowUp          │
                                    │  ├─ MemoryUpdate [I]  │
                                    │  ├─ KnowledgeLink [S] │
                                    │  └─ SendReply         │
                                    ├──────────────────────┤
                                    │ Activities            │
                                    │  ├─ LLMCall (OpenRouter)│
                                    │  ├─ ExecCommand      │
                                    │  ├─ ReadFile/WriteFile│
                                    │  ├─ WebSearch/Fetch  │
                                    │  ├─ MemorySearch (Mem0)│
                                    │  ├─ MemoryAdd (Mem0) │
                                    │  ├─ GitOps (gh CLI)  │
                                    │  └─ SpawnCodingAgent │
                                    └──────────────────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │   Memory Layer       │
                                    ├──────────────────────┤
                                    │ Workspace files (md) │
                                    │ Mem0 (facts + search)│
                                    │ Graph edges (SQLite) │
                                    └──────────────────────┘

[I]=Intern  [J]=Junior  [S]=Senior  [E]=Executive  [SP]=Specialist
```

### Stack
- **Language**: Python 3.12+
- **Telegram**: python-telegram-bot (async, mature, excellent docs)
- **Temporal**: temporalio Python SDK
- **LLM**: OpenRouter via httpx (async HTTP) — one API, all models
- **Memory**: Mem0 (self-hosted, `pip install mem0ai`) + workspace markdown files
- **Graph**: SQLite for edges (upgrade to Neo4j later if needed)
- **Config**: Single YAML file (~30 fields)

### Config
```yaml
telegram:
  token: ${TELEGRAM_BOT_TOKEN}
  allowed_users: [pasha_telegram_id]

llm:
  provider: openrouter
  api_key: ${OPENROUTER_API_KEY}

  # The Organization — model assignments by role
  roles:
    intern: google/gemini-2.5-flash-lite  # Background ops, high volume
    junior: xai/grok-4-1-fast             # Daily conversation
    senior: anthropic/claude-sonnet-4-5    # Complex tasks
    executive: anthropic/claude-opus-4     # Heavy reasoning (rare)

  # Which activities use which role (overridable)
  activity_roles:
    extract_facts: intern
    classify_task: intern
    summarize_context: intern
    detect_promises: intern
    conversation_turn: junior
    memory_search: junior
    link_knowledge: senior
    error_recovery: senior
    consolidate_memory: senior
    architecture_design: executive
    complex_reasoning: executive

  # Auto-escalation
  escalation:
    enabled: true
    confidence_threshold: 0.6  # Below this, escalate to next tier

temporal:
  address: localhost:7233
  namespace: mycel
  task_queue: main
  workflow_id_template: mycel-{user_id}

memory:
  workspace: ~/.mycel/workspace
  mem0:
    llm_provider: openrouter
    embeddings: openai:text-embedding-3-small
  graph:
    store: sqlite
    consolidation_schedule: weekly

tools:
  exec: true
  web_search: true
  web_fetch: true
  github: true
  coding_agents: [codex, claude-code]
```

---

## Error Handling Philosophy

### Today (OpenClaw)
```
Agent: "I'll push this to GitHub"
*permission error*
Agent: "Sorry, I failed due to a permission error."
User: ??? what do I do
```

### Tomorrow (Mycel)
```
Agent: "I'll push this to GitHub"
*permission error on git push*

[Temporal retries once with backoff — still fails]

Agent: "Push failed — git needs the `repo` scope on your GitHub token.
  Options:
  1. Run `gh auth refresh -s repo` (I'll walk you through it)
  2. I'll save the changes locally and you push manually
  3. Skip for now, I'll remind you in 1 hour

  [1] [2] [3]"
```

Implemented via:
- **Error classification activity** [INTERN]: Maps common errors to categories
- **Remediation selection** [SENIOR]: Picks the best fix path for context
- **Inline buttons**: Telegram keyboard for quick choices
- **FollowUp workflow**: "Remind me later" spawns a timer

---

## The "Promise Keeper"

When the assistant detects [INTERN] it's making a commitment:
- "I'll check on that"
- "Let me follow up"
- "I'll remind you"
- "We should revisit this"

It spawns a `FollowUpWorkflow`:
```
FollowUpWorkflow(promise, context, deadline)
  → Timer (sleep until deadline)
  → Signal ConversationWorkflow with reminder
  → If no response, escalate (nudge again after 2x)
  → Max 3 nudges, then log as dropped + notify once
```

---

## Memory Architecture — The Second Brain

### Layer 1: Workspace Files (Human Layer)
```
~/.mycel/workspace/
  ├── SOUL.md          # Personality, values, voice
  ├── USER.md          # About the human
  ├── MEMORY.md        # Curated long-term memory
  ├── AGENTS.md        # How the system operates
  └── memory/
      ├── 2026-02-18.md  # Daily notes
      └── ...
```

### Layer 2: Mem0 (Intelligence Layer)
- [INTERN] Auto-extracts facts from every conversation turn
- Deduplicates, semantic search, conflict resolution
- Self-hosted via `pip install mem0ai`

### Layer 3: Zettelkasten Graph (Connection Layer)
- [SENIOR] Links between knowledge nodes (non-hierarchical)
- Edge types: `related_to`, `contradicts`, `builds_on`, `example_of`, `part_of`
- [SENIOR] Weekly consolidation: merge duplicates, strengthen connections, prune stale
- [SENIOR] Contradiction detection: flags conflicting info for user decision

### Memory Flow
```
Conversation turn happens
  ↓
MemoryUpdateWorkflow (async, doesn't block reply)
  ├─ [INTERN] Extract facts
  ├─ [INTERN] Store in Mem0 (dedup, index)
  └─ KnowledgeLinkWorkflow
      ├─ [SENIOR] Search existing nodes for related concepts
      ├─ [SENIOR] Create typed edges
      └─ [SENIOR] Flag contradictions if found

Weekly ConsolidationWorkflow (Temporal Schedule)
  ├─ [SENIOR] Merge near-duplicate nodes
  ├─ [INTERN] Summarize clusters
  ├─ [SENIOR] Strengthen/prune links
  └─ [INTERN] Update workspace files with distilled insights
```

---

## Phases

### Phase 1: MVP (~1 week)
1. Project scaffolding (#1)
2. Telegram bot (#2)
3. Temporal conversation workflow (#3)
4. OpenRouter LLM adapter (#4)
5. System prompt builder (#5)
6. Basic tools (#6)
7. Error handling (#7)
8. Memory foundation with Mem0 (#8)

### Phase 2: Intelligence (~weeks 2-3)
9. Smart model routing / The Organization (#9)
10. Promise Keeper (#10)
11. Coding agent integration (#11)
12. Cron via Temporal Schedules (#12)
13. Memory embeddings refinement (#13)
14. Zettelkasten knowledge graph (#19)

### Phase 3: Polish (when needed)
15. Voice/TTS (#14)
16. Sub-agents (#15)
17. GitHub webhooks (#16)
18. Self-modification (#17)
19. Dockerize (#18)

---

## Decisions Made
1. **Language**: Python 3.12+
2. **Telegram**: python-telegram-bot
3. **Memory**: Mem0 (self-hosted) + Zettelkasten graph layer
4. **LLM gateway**: OpenRouter (one API, all models)
5. **Cost model**: Organization of roles (intern/junior/senior/executive/specialist)
6. **Repo**: Monorepo with docs/ in repo
7. **Runs on**: Mac for now, Dockerize later
8. **Name**: Mycel

---

## Status
- [x] Design doc v0.3
- [x] Roadmap + GitHub issues (#1-19)
- [x] Elevator pitch
- [ ] MVP implementation
- [ ] Testing with real Telegram
- [ ] Cut over from OpenClaw
