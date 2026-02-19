# Mycel — Elevator Pitch

## The One-Liner
Mycel is a personal AI assistant built to remember context, follow through on commitments, and recover cleanly when systems fail.

## What's Not Working
After using OpenClaw as a daily AI assistant, these are the friction points that keep coming up:

- **Memory is fragile.** Context gets lost between sessions. I repeat myself constantly.
- **Promises get dropped.** The agent says "I'll follow up" and never does. I have to track everything manually.
- **Errors are dead ends.** "Permission error" — and then nothing. No explanation, no suggested fix, no options.
- **One model for everything.** The same expensive model answers "what time is it" and "design my system." No sense of proportionality.
- **Too much I don't use.** OpenClaw supports 20+ channels, browser automation, canvas, skills marketplace. I use Telegram and shell commands.

## What Mycel Does Instead

**1. Durable execution and follow-through.**
Every conversation runs as a [Temporal](https://temporal.io) workflow — the same infrastructure Uber, Netflix, and DoorDash use for mission-critical processes. If the system crashes mid-sentence, it picks up exactly where it left off. If an API call fails, it retries automatically. If the assistant promises to remind you in an hour, a durable timer ensures it actually happens. Temporal doesn't forget. Neither does your assistant.

**2. Persistent graph memory.**
Every conversation feeds a living knowledge graph where nodes connect to nodes and meaning grows organically. Say "I prefer Python over TypeScript" once, and it becomes a linked, retrievable part of your network. Over weeks and months, Mycel builds a non-hierarchical web of your projects, preferences, and decisions. You never manage memory manually; it keeps growing through connection.

**3. Role-based model orchestration.**
The system runs like an organization. An intern handles background busywork — extracting facts, classifying tasks, parsing outputs — at $0.10/M tokens. A junior engineer handles daily conversation. A senior engineer comes in for knowledge linking, error recovery, and code review. An executive (the expensive reasoning model) only activates for architecture and complex planning. A specialist (coding agent) handles all code generation. Each activity in the system has a role assignment. The intern fires hundreds of times a day and costs pennies. The executive fires once or twice and it's worth it. Typical daily cost: ~$0.70. Compare to using the best model for everything: ~$4.50/day for zero quality gain on routine work.

## How It's Different

| | Generic AI Assistants | This |
|---|---|---|
| **Memory** | Starts fresh every session | Builds a knowledge graph from every interaction |
| **Reliability** | Crashes lose everything | Temporal replays from last checkpoint |
| **Errors** | "Sorry, permission error." | "Here's what failed, here are 3 ways to fix it. Pick one." |
| **Promises** | Forgotten immediately | Tracked as durable workflows with timers |
| **Model cost** | One model for everything | An organization: interns do busywork, executives only for hard problems (~$0.70/day vs $4.50) |
| **Scope** | Built for millions of users | Built for one person's exact workflow |

## The Stack
- **Python** — simple, readable, ownable
- **Temporal** — durable execution, retries, scheduling, observability
- **Mem0** — intelligent memory layer with auto-extraction and semantic search
- **OpenRouter** — one API for every LLM (GPT, Claude, Gemini, Grok)
- **Telegram** — the interface (for now)

## How It Actually Works — Real Examples

### Being Honest About Mistakes

![Transparency example](images/example-transparency.jpg)

When something goes wrong, you don't get corporate boilerplate. You get an honest assessment of what failed and an immediate fix. No hiding, no deflecting, no "I apologize for any inconvenience." Just "that's on me, here's what actually happened, fixing it now."

This is what reliable assistance looks like — not perfection, but transparency and follow-through.

---

## Where This Goes
An assistant that's been with me for a year. Knows my projects, my patterns, my decisions. When I ask "what should I work on today?" it doesn't give generic advice — it knows what's active, what's stalled, and that I tend to overcommit. It pushes back. It reminds me of things I decided months ago that matter now.

A second brain with durable memory and useful judgment. That's the goal.
