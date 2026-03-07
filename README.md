# 🍄 Mycel

> *Like mycelium — no hierarchy, just connections.*

A lean, Temporal-native AI assistant that grows a living knowledge network from every conversation.

---

🌱 **Always growing.** Every chat feeds a knowledge graph that links, strengthens, and never forgets.

🔁 **Self-healing.** Errors come with explanations and options, not dead ends. Temporal retries the rest.

🤝 **Keeps its word.** Every promise becomes a durable workflow. It literally can't forget.

🧠 **Right brain, right job.** An org of models — interns handle busywork, seniors think, executives only when it matters. ~$0.70/day, not $4.50.

🔬 **Yours to own.** Small codebase. Your code. Change how it thinks, what it remembers, how it works.

---

## Stack

| | |
|---|---|
| 🐍 **Python** | Simple, readable, ownable |
| ⏰ **Temporal** | Durable execution — crashes recover, promises keep |
| 🧫 **Mem0** | Intelligent memory — auto-extracts, deduplicates, searches |
| 🔀 **OpenRouter** | One API, every model |
| 📬 **Telegram** | The interface (for now) |

## Docs

| | |
|---|---|
| 📐 [Design](docs/DESIGN.md) | Architecture, principles, the Organization model |
| 🧭 [Architecture Invariants](docs/ARCHITECTURE.md) | Phase 1 control-flow rules, tool guardrails, and issue map |
| 🗺️ [Roadmap](docs/ROADMAP.md) | Phases, milestones, GitHub issues |
| 🎤 [Pitch](docs/PITCH.md) | What this is and why it matters |
| 🔬 [OpenClaw Analysis](docs/OPENCLAW-ANALYSIS.md) | What we learned from the framework we're replacing |
| 🧪 [Problem Cases](docs/PROBLEM-CASES.md) | Canonical eval failure cases rendered from JSONL |

New contributors should read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) before changing the workflow or tool execution path. It defines the current Phase 1 invariants: Temporal owns control flow, the LLM only proposes actions, and tool execution stays behind workflow validation.

## Problem Cases Workflow

Add a new line to `data/evals/problem_cases.jsonl` that matches `data/evals/problem_cases.schema.json`, then run:

```bash
python -m pip install jsonschema
python scripts/render_problem_cases.py
```

Commit both the JSONL and generated `docs/PROBLEM-CASES.md`.

## Status

```
🚧 Phase 1 (MVP) — designing
```

See [issues](https://github.com/pashafateev/mycel/issues) for the full roadmap.

## Phase 1 MVP Run (Telegram -> Temporal -> OpenRouter)

### 1. Install dependencies

```bash
python3 -m pip install -e .
```

### 2. Create a local `.env` file

```bash
cat > .env <<'EOF'
TELEGRAM_BOT_TOKEN="<telegram-bot-token>"
MYCEL_ALLOWED_USER_ID="<telegram-user-id>"
OPENROUTER_API_KEY="<openrouter-api-key>"
EOF
```

Use placeholder values locally and never commit real tokens.
Tip: if you do not know your Telegram user id yet, start the bot first and run `/m_whoami` to get it, then set `MYCEL_ALLOWED_USER_ID`.

Optional:

```bash
cat >> .env <<'EOF'
TEMPORAL_ADDRESS="localhost:7233"
TEMPORAL_NAMESPACE="default"
MYCEL_TASK_QUEUE="mycel-phase1"
MYCEL_MODEL="openai/gpt-5.2"
MYCEL_STREAMING_ENABLED="0"
MYCEL_WORKSPACE_DIR="/path/to/workspace"
EOF
```

### 3. Start local Mycel

Use the lifecycle script. It loads `.env`, checks `TEMPORAL_ADDRESS`, starts a local `temporal server start-dev` only when needed, then starts the combined bot + worker once.

```bash
./scripts/dev_up.sh
```

Runtime state is written under `.run/`. Logs go to `logs/mycel.log` and `logs/temporal.log`.

Useful commands:

```bash
./scripts/dev_status.sh
./scripts/dev_down.sh
```

Telegram commands:
- `/m_help`
- `/m_health`
- `/m_whoami` (works without allowlist so you can discover your user id)
- `/m_status`
- `/m_chat <text>`
- `/m_fetch <url>`
- `/m_note <text>`
- `/m_read <relative-path>`
- `/m_write <relative-path> <content>`

The bot ignores non-`/m_*` commands to stay coexistence-safe.

### 5. Run tests

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.11 -m pytest -q
```

---

<sub>*mycel* — from mycelium, the underground network that connects forests. also: *my cell* — your personal thinking space. 🍄</sub>
