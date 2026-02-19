# Temporal × OpenClaw Integration Plan

## 1. Architecture Overview

### Current State
```
[Telegram] → [OpenClaw Gateway (TypeScript)]
                    ↓
            [Agent Loop (TS)]
                    ↓
            [LLM Call + Tool Execution (TS)]
                    ↓
            [Response → Telegram]
```

### Target State
```
[Telegram] → [OpenClaw Gateway (TypeScript)] → [Temporal Server]
                                                      ↓
                                              [Go Worker]
                                              AgenticWorkflow
                                                ├── LLM Activity
                                                ├── Tool Activities
                                                └── Sub-agent (Child Workflows)
                                                      ↓
                                              [Signal back to TS]
                                                      ↓
                                              [OpenClaw → Telegram]
```

### Language Split
- **Go (harness)** = Brain: agentic loop, LLM calls, tool execution
- **TypeScript (OpenClaw)** = Body: Telegram, memory, skills, personality, system prompt
- **Temporal** = Nervous system: connects them, provides durability

---

## 2. Harness Architecture (What Exists in Go)

### Workflows (`internal/workflow/`)
- **AgenticWorkflow** — Main entry. Creates session state, registers handlers, runs multi-turn loop
- **AgenticWorkflowContinued** — Handles ContinueAsNew (keeps history bounded at 100 iterations)
- **runMultiTurnLoop** — Outer loop: waits for user input → runs turn → repeat
- **runAgenticTurn** — Inner loop: call LLM → execute tools → repeat until done

### Activities (`internal/activities/`)
- **ExecuteLLMCall** — Calls OpenAI or Anthropic, returns items + token usage
- **ExecuteCompact** — Summarizes conversation history when context overflows
- **GenerateSuggestions** — Generates next-prompt suggestions
- **ExecuteTool** — Dispatches to tool registry, returns output

### User Interaction (`internal/workflow/handlers.go`)
- **UpdateUserInput** — Temporal Update handler for new user messages
- **UpdateInterrupt** — Interrupt current turn
- **UpdateShutdown** — Graceful shutdown
- **QueryGetConversationItems** — Query handler for history

### Tools (`internal/tools/handlers/`)
- shell, read_file, write_file, apply_patch, list_dir, grep_files
- exec_command + write_stdin (interactive PTY sessions)

### Client (`cmd/client/`)
- CLI: start workflow, send messages, query history, interrupt, shutdown
- All via Temporal SDK client calls

---

## 3. OpenClaw Architecture (What Exists in TypeScript)

OpenClaw is distributed as a compiled npm package (dist/*.js). Source isn't directly available, but from docs and runtime behavior:

### Core Components
- **Gateway** — HTTP/WS server, manages sessions, routes messages
- **Sessions** — Conversation state, message history, compaction
- **Agent Loop** — System prompt → LLM call → tool dispatch → response
- **Channels** — Telegram, Discord, WhatsApp, Signal, etc.
- **Tools** — exec, read, write, edit, web_search, web_fetch, browser, memory_search, cron, message, etc.
- **Skills** — Plugin system (SKILL.md + scripts)
- **Memory** — MEMORY.md, memory/*.md, vector search via embeddings
- **Cron** — Scheduled jobs (systemEvent or agentTurn)
- **Sub-agents** — Isolated sessions for background tasks
- **Hooks** — Webhook integrations, internal event handlers

### What We Need From OpenClaw
- Telegram channel adapter (message in/out)
- System prompt builder (workspace files, SOUL.md, USER.md, etc.)
- Memory search (embeddings + vector store)
- Skill loading and routing
- Cron scheduler
- Session persistence layer

---

## 4. Integration Strategy

### Phase 1: Tracer Bullet (Proof of Concept)
**Goal:** Telegram message in → Temporal workflow → LLM response → Telegram message out

#### Components to Build:

**A. TypeScript Bridge (`temporal-bridge/`)**
```typescript
// 1. Temporal Client wrapper
//    - Starts ConversationWorkflow for new sessions
//    - Sends user messages as Updates to existing workflows
//    - Queries workflow for responses

// 2. OpenClaw Hook/Plugin
//    - Intercepts inbound messages before OpenClaw's agent loop
//    - Routes to Temporal instead
//    - Receives responses and sends via OpenClaw's channel layer
```

**B. Go Worker Modifications**
```go
// 1. Add "send_reply" activity
//    - HTTP callback to TypeScript bridge with response text
//    - Bridge forwards to Telegram via OpenClaw's message tool

// 2. System prompt injection
//    - WorkflowInput includes system prompt built by TypeScript side
//    - Contains SOUL.md, USER.md, workspace context, etc.
```

**C. Temporal Infrastructure**
- Temporal dev server (temporal server start-dev)
- Go worker process
- TypeScript bridge process (part of OpenClaw or standalone)

#### Sequence:
```
1. User sends Telegram message
2. OpenClaw receives it
3. Bridge intercepts → creates/signals Temporal workflow
4. Go worker picks up → calls LLM (Anthropic)
5. LLM responds (no tool calls for tracer)
6. Worker calls "send_reply" activity → HTTP to bridge
7. Bridge sends reply via OpenClaw → Telegram
```

### Phase 2: Tool Integration
- Port OpenClaw's tool definitions to Go tool specs
- Or: create a "proxy_tool" activity that calls back to TypeScript for tool execution
- The proxy approach is faster — TypeScript already has all tools working

### Phase 3: Full Integration
- Memory search as an activity
- Cron jobs as Temporal Schedules
- Sub-agents as Child Workflows
- Session history in Temporal (replace OpenClaw's session store)
- Heartbeats as Temporal timers

---

## 5. Gap Analysis

| Need | Harness Has | OpenClaw Has | Build |
|------|------------|-------------|-------|
| Telegram I/O | ❌ | ✅ | Bridge |
| Agentic loop | ✅ | ✅ | Use harness |
| LLM calls | ✅ (OpenAI + Anthropic) | ✅ | Use harness |
| Basic tools (shell, files) | ✅ | ✅ | Use harness |
| OpenClaw tools (web, browser, memory) | ❌ | ✅ | Proxy activity |
| System prompt (personality) | ❌ | ✅ | Inject from TS |
| Durability | ✅ | ❌ | Temporal |
| Observability | ✅ (Temporal Web UI) | ❌ | Temporal |
| Memory search | ❌ | ✅ | Activity wrapper |
| Cron/scheduling | ❌ | ✅ | Temporal Schedules |
| Sub-agents | ✅ (child workflows) | ✅ | Use harness |

---

## 6. Day 1 Game Plan

### Prerequisites (30 min)
1. Install Temporal CLI: `brew install temporal`
2. Verify Go is installed: `go version`
3. Build the harness: `cd /tmp/temporal-agent-harness && go build ./...`

### Step 1: Run the harness standalone (1 hour)
1. `temporal server start-dev` (terminal 1)
2. `ANTHROPIC_API_KEY=... ./worker` (terminal 2)
3. `./client start --message "Hello" --provider anthropic --model claude-sonnet-4-20250514` (terminal 3)
4. Verify it works end-to-end with basic chat
5. Try tool execution (shell commands, file read/write)

### Step 2: Build the TypeScript bridge (2-3 hours)
1. Create a minimal Node.js script using `@temporalio/client`
2. Start workflow, send user input update, poll for responses
3. Wire it to send a Telegram message via OpenClaw's message tool
4. Test: Telegram → bridge → Temporal → Go worker → LLM → bridge → Telegram

### Step 3: System prompt injection (1 hour)
1. Read SOUL.md, USER.md from workspace
2. Build system prompt in TypeScript
3. Pass as WorkflowInput.Config.BaseInstructions
4. Verify personality comes through in responses

### Step 4: Celebrate 🎉
At this point you have a durable AI agent responding in Telegram via Temporal.

---

## 7. Open Questions
- Do we run the bridge as an OpenClaw plugin/hook, or standalone?
- How do we handle streaming (partial responses to Telegram)?
- Should we use the harness's TUI client for local dev, or go straight to Telegram?
- Fork the harness repo or use it as a dependency?

---

## Status
- [x] Harness codebase analyzed
- [x] OpenClaw architecture mapped
- [x] Integration plan written
- [ ] Prerequisites installed
- [ ] Tracer bullet built
- [ ] Tools integrated
