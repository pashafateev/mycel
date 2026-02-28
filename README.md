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

## Status

```
🚧 Phase 1 (MVP) — designing
```

See [issues](https://github.com/pashafateev/mycel/issues) for the full roadmap.

---

## TB10: Two-Bot Coexistence Demo

TB10 proves that two Telegram bots can coexist for the same user without command collisions by using explicit namespaces:

- Mycel bot commands: `/m_*` (`/m_help`, `/m_ping`)
- OpenClaw dummy bot commands: `/oc_*` (`/oc_help`, `/oc_ping`)

### Setup

```bash
export TELEGRAM_BOT_TOKEN_MY="<mycel-bot-token>"
export TELEGRAM_BOT_TOKEN_OC="<openclaw-dummy-token>"
export TEMPORAL_ADDRESS="localhost:7233"   # optional
```

### Run both bots for ~30 minutes

```bash
./scripts/run_tb10_dual_bot.sh
```

Defaults:

- Runtime is 1800 seconds (30 minutes)
- Override with `TB10_RUNTIME_SECONDS=<seconds>`

### Validate no accidental double handling

In a Telegram chat where both bots are present, send:

- `/m_help` -> only Mycel replies, prefixed with `[Mycel]`
- `/oc_help` -> only dummy OpenClaw replies, prefixed with `[OpenClaw Dummy]`
- `/m_ping hello` -> only Mycel replies
- `/oc_ping hello` -> only dummy OpenClaw replies
- `/ping hello` or plain text -> both bots ignore

<sub>*mycel* — from mycelium, the underground network that connects forests. also: *my cell* — your personal thinking space. 🍄</sub>
