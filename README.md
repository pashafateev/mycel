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
| 🗺️ [Roadmap](docs/ROADMAP.md) | Phases, milestones, GitHub issues |
| 🎤 [Pitch](docs/PITCH.md) | What this is and why it matters |
| 🔬 [OpenClaw Analysis](docs/OPENCLAW-ANALYSIS.md) | What we learned from the framework we're replacing |
| 🧪 [Problem Cases](docs/PROBLEM-CASES.md) | Canonical eval failure cases rendered from JSONL |

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

### 2. Export required environment variables

```bash
export TELEGRAM_BOT_TOKEN="<telegram-bot-token>"
export MYCEL_ALLOWED_USER_ID="<telegram-user-id>"
export OPENROUTER_API_KEY="<openrouter-api-key>"
```

Optional:

```bash
export TEMPORAL_ADDRESS="localhost:7233"
export TEMPORAL_NAMESPACE="default"
export MYCEL_TASK_QUEUE="mycel-phase1"
export MYCEL_MODEL="openai/gpt-5.2"
export MYCEL_STREAMING_ENABLED="0"
export MYCEL_WORKSPACE_DIR="/path/to/workspace"
```

### 3. Start Temporal Server

Run your local Temporal dev server on `localhost:7233` before starting the bot.

### 4. Run the MVP bot + worker

```bash
PYTHONPATH=src python3 scripts/run_phase1_bot.py
```

Telegram commands:
- `/m_help`
- `/m_chat <text>`

The bot ignores non-`/m_*` commands to stay coexistence-safe.

### 5. Run tests

```bash
PYTHONPATH=src python3 -m pytest -q
```

---

<sub>*mycel* — from mycelium, the underground network that connects forests. also: *my cell* — your personal thinking space. 🍄</sub>
