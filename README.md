# Personal Assistant

A lean, Temporal-native personal AI assistant that never forgets, never drops the ball, and gets smarter every time you talk to it.

## What Is This?

A Telegram-based AI assistant built on three ideas:

1. **Nothing is ever lost.** Every conversation is a [Temporal](https://temporal.io) workflow. Crashes replay from the last checkpoint. Promises become durable timers. Retries are automatic.

2. **It builds a second brain.** Every conversation quietly feeds a living knowledge graph (Zettelkasten). Facts are extracted, linked, and searchable forever. You never manage memory — it just learns.

3. **A whole company, not one employee.** An intern handles background ops at $0.10/M tokens. A junior handles daily chat. A senior links knowledge and recovers from errors. An executive does architecture — rarely, and worth it. Every activity uses the cheapest model that can do the job. ~$0.70/day instead of ~$4.50.

## Stack

- **Python 3.12+** — simple, readable, ownable
- **Temporal** — durable execution, retries, scheduling, observability
- **Mem0** — intelligent memory layer with auto-extraction and semantic search
- **OpenRouter** — one API for every LLM (GPT, Claude, Gemini, Grok)
- **python-telegram-bot** — async Telegram interface

## Docs

- [Design Doc](docs/DESIGN.md) — full architecture, principles, decisions
- [Roadmap](docs/ROADMAP.md) — phased plan with milestones
- [Elevator Pitch](docs/PITCH.md) — the why, in plain English

## Status

🚧 **Pre-MVP** — Design complete, implementation starting. See [Issues](https://github.com/pashafateev/personal-assistant/issues) for the full backlog.

## License

Private project.
