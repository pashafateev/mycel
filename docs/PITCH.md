# Personal Assistant — Elevator Pitch

## The One-Liner
A personal AI assistant that never forgets, never drops the ball, and gets smarter every time you talk to it.

## The Problem
Today's AI assistants are stateless, fragile, and generic. They forget what you told them yesterday. They promise to follow up and never do. They crash and lose your conversation. They throw cryptic errors and leave you stranded. They use the most expensive model for "what's the weather?" and the cheapest for "design my system architecture." And they're built for everyone, which means they're optimized for no one.

## The Solution
A Telegram-based AI assistant built on three ideas:

**1. Nothing is ever lost.**
Every conversation runs as a [Temporal](https://temporal.io) workflow — the same infrastructure Uber, Netflix, and DoorDash use for mission-critical processes. If the system crashes mid-sentence, it picks up exactly where it left off. If an API call fails, it retries automatically. If the assistant promises to remind you in an hour, a durable timer ensures it actually happens. Temporal doesn't forget. Neither does your assistant.

**2. It builds a second brain — yours.**
Every conversation quietly feeds a living knowledge graph. Say "I prefer Python over TypeScript" once, and it's stored, linked, and retrievable forever. Over weeks and months, the system builds a non-hierarchical web of everything it knows about you, your projects, your preferences, your decisions — a personal Zettelkasten that grows smarter with every interaction. You never manage memory manually. It just learns.

**3. A whole company, not one employee.**
The system runs like an organization. An intern handles background busywork — extracting facts, classifying tasks, parsing outputs — at $0.10/M tokens. A junior engineer handles daily conversation. A senior engineer comes in for knowledge linking, error recovery, and code review. An executive (the expensive reasoning model) only activates for architecture and complex planning. A specialist (coding agent) handles all code generation. Each activity in the system has a role assignment. The intern fires hundreds of times a day and costs pennies. The executive fires once or twice and it's worth it. Typical daily cost: ~$0.70. Compare to using the best model for everything: ~$4.50/day for zero quality gain on routine work.

## How It's Different

| | Generic AI Assistants | This |
|---|---|---|
| **Memory** | Starts fresh every session | Builds a knowledge graph from every interaction |
| **Reliability** | Crashes lose everything | Temporal replays from last checkpoint |
| **Errors** | "Sorry, permission error." | "Here's what failed, here are 3 ways to fix it. Pick one." |
| **Promises** | Forgotten immediately | Tracked as durable workflows with timers |
| **Model cost** | One model for everything | An organization: intern ($0.10/M) for background, executive ($15/M) only when it matters |
| **Scope** | Built for millions of users | Built for one person's exact workflow |

## The Stack
- **Python** — simple, readable, ownable
- **Temporal** — durable execution, retries, scheduling, observability
- **Mem0** — intelligent memory layer with auto-extraction and semantic search
- **OpenRouter** — one API for every LLM (GPT, Claude, Gemini, Grok)
- **Telegram** — the interface (for now)

## Who It's For
Right now? One person — a developer who wants an AI assistant that actually works like a reliable colleague, not a fancy autocomplete that forgets everything and panics when things go wrong.

But the architecture is general. Anyone who wants a personal AI that truly knows them, keeps its promises, and doesn't break could use this. The "personal" in Personal Assistant isn't a limitation — it's the point. Generic tools optimize for the average user. This optimizes for *you*.

## The Vision
Imagine an assistant that's been with you for a year. It knows your coding style, your project history, your decision-making patterns, your schedule preferences. It's read every conversation, extracted every lesson, linked every idea. When you ask "what should I work on today?" it doesn't give generic productivity advice — it knows your active projects, your energy patterns, your deadlines, and your tendency to overcommit. It pushes back when you take on too much. It reminds you of decisions you made three months ago that are relevant now. It's not just an assistant — it's an extension of your thinking.

That's what a second brain with perfect memory and zero ego looks like.
