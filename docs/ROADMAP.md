# Personal Assistant — Roadmap

Based on design doc: [docs/DESIGN.md](DESIGN.md)

---

## Phase 1: MVP (~1 week)
Goal: Telegram message in → Temporal workflow → OpenRouter LLM → reply out. Durable, restartable, useful.

### 1.1 Project scaffolding
- Python monorepo structure (src/, config/, tests/)
- pyproject.toml with deps: temporalio, python-telegram-bot, httpx, pyyaml
- Config loader (single YAML file, ~20 fields)
- README with setup instructions
- .env for secrets (TELEGRAM_BOT_TOKEN, OPENROUTER_API_KEY)

### 1.2 Telegram bot
- Async bot using python-telegram-bot
- Receive text messages from allowed user(s) only
- Send text replies back
- Inline keyboard support (for error remediation buttons)
- Graceful shutdown

### 1.3 Temporal conversation workflow
- ConversationWorkflow: long-running, one per user/session
- Signal handler for incoming messages
- Multi-turn loop: wait for message → process → reply → wait
- ContinueAsNew after N turns (keep history bounded)
- Workflow ID: `pa-{user_id}` (one conversation per user)

### 1.4 OpenRouter LLM adapter
- Single activity: call_llm(messages, model, config) → response
- OpenRouter API via httpx (async)
- Support system prompt + conversation history
- Handle streaming (optional, can defer)
- Retry policy on transient failures (429, 500, timeout)
- Pre-send validation: no orphan reasoning items (from design research)

### 1.5 System prompt builder
- Read workspace files (SOUL.md, USER.md, MEMORY.md, AGENTS.md)
- Build system prompt from templates
- Inject current date/time, user context
- Keep it simple — string concatenation, not a framework

### 1.6 Basic tools
- exec_command: run shell commands, return stdout/stderr
- read_file: read file contents
- write_file: write/create files
- web_search: Brave Search API (or similar)
- web_fetch: fetch URL → markdown
- Tool execution as Temporal activities (retryable)
- Tool dispatch: LLM returns tool calls → execute → feed results back

### 1.7 Error handling foundation
- Error classification: map common errors to categories (permission, auth, network, not_found, unknown)
- Remediation templates: each category has suggested fixes
- Surface to user with inline buttons: [Fix it] [Skip] [Remind me later]
- Temporal retry policy handles transient errors silently
- Only persistent failures surface to user

### 1.8 Memory (file-based, foundation)
- Read/write workspace markdown files
- Daily notes: memory/YYYY-MM-DD.md
- Long-term: MEMORY.md
- Mem0 integration: `pip install mem0ai` (self-hosted)
- After every conversation turn, background Temporal workflow extracts facts → Mem0
- Mem0 handles: fact extraction, deduplication, semantic search
- Agent has `memory_search` tool to query the knowledge base
- No manual memory management needed — it just learns

---

## Phase 2: Intelligence (~week 2-3)
Goal: Smart model routing, promises kept, coding agents, scheduled tasks.

### 2.1 Smart model routing (The Crew)
- Classify activity: lightweight LLM call to determine task tier
- Junior model: casual chat, lookups, simple tasks
- Senior model: complex reasoning, architecture, error recovery
- Specialist: coding tasks → spawn coding agent
- Self-escalation: if junior is low-confidence, auto-upgrade to senior
- User override: /junior, /senior commands
- Subtle indicator in replies showing which tier handled it

### 2.2 Promise Keeper
- Detect commitments in assistant responses ("I'll follow up", "let me check", "I'll remind you")
- Spawn FollowUpWorkflow: timer → reminder signal → nudge
- Max 3 nudges, then log as dropped + notify
- User can dismiss or snooze reminders

### 2.3 Coding agent integration
- CodingAgentWorkflow: child workflow that spawns Codex/Claude Code
- Monitor progress, relay results back to conversation
- Handle permissions cleanly (no more mystery failures)
- Git operations as activities (commit, push, PR)

### 2.4 Cron / scheduled tasks
- Temporal Schedules for recurring tasks
- User can say "remind me at 9am" → schedule created
- Heartbeat-style periodic checks (email, calendar) as scheduled workflows
- Simple schedule management: list, cancel, modify

### 2.5 Zettelkasten knowledge graph
- Non-hierarchical linking between memory nodes (Mem0 facts)
- Every interaction creates/updates nodes + edges
- Background Temporal workflow: after each conversation, analyze what was learned → create links to existing knowledge
- "What do I know about X?" traverses the graph, not just vector search
- Concept clustering: related ideas surface together
- Periodic consolidation workflow: merge duplicates, strengthen connections, prune stale nodes
- Visual exploration (future/Phase 3): graph UI to browse your knowledge spatially

---

## Phase 3: Polish (when needed)
Goal: Quality of life, expand capabilities.

### 3.1 Voice / TTS
- Car mode: auto-generate voice messages
- TTS via ElevenLabs or similar
- Voice input transcription

### 3.2 Sub-agents
- Child workflows for parallel background tasks
- Orchestrator pattern: main conversation spawns workers
- Results announced back to user on completion

### 3.3 GitHub integration
- Webhook receiver for PR notifications, CI status
- Proactive alerts: "Your PR just failed CI"
- PR review as a workflow

### 3.4 Self-modification
- Agent can edit its own config and prompts
- "Change your personality to be more concise" → updates SOUL.md
- Config changes via conversation

### 3.5 Deployment
- Dockerize for VPS/Pi/cloud
- Systemd service or docker-compose
- Health checks and auto-restart

---

## Milestone targets
| Milestone | Target | Definition of Done |
|-----------|--------|-------------------|
| MVP | ~1 week | Send Telegram msg, get LLM reply via Temporal, basic tools work, errors are actionable |
| Smart | ~2-3 weeks | Model routing automatic, promises tracked, coding agents spawn cleanly |
| Production | ~4-6 weeks | Fully replaces OpenClaw for Pasha's daily use |
