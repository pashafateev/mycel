# Mycel Architecture Invariants

This document captures the Phase 1 architecture contract for Mycel. It is narrower than the broader product vision in [docs/DESIGN.md](DESIGN.md): it defines the control-flow and safety rules contributors should preserve as the Telegram bot, Temporal workflow, memory layer, and tool system evolve.

## Scope

Mycel is a Temporal-native assistant with a hybrid interface:

- Natural-language chat for normal conversation.
- Explicit `/m_*` commands for deterministic tool entry points.

The Phase 1 target is not "agentic freedom." It is a durable, inspectable workflow that can safely call tools, recover from process crashes, and grow memory without handing control of the runtime to the model.

## 1. Temporal Workflow Owns Control Flow

Temporal is the source of truth for conversation state and orchestration. The workflow decides what step happens next, what activities run, when retries apply, and when a turn is complete.

That means:

- User input enters through Telegram and is handed to a Temporal workflow.
- The workflow records the durable history of the turn.
- LLM calls, tool execution, memory writes, and reply delivery happen as activities invoked by the workflow.
- Restart behavior must be replay-safe: a crash should resume from workflow history, not from ad hoc in-process state.

This keeps conversation logic durable and debuggable in Temporal UI instead of scattering control flow across bot handlers and model outputs.

Related issues: #3, #7, #8

## 2. LLM Proposes Actions, Workflow Validates

The model is allowed to suggest structured actions. It is not allowed to execute arbitrary control flow by itself.

Expected pattern:

1. The workflow asks the LLM for the next response or next action proposal.
2. The LLM returns either:
   - a user-facing reply, or
   - a structured request for one tool invocation.
3. Workflow-side validation checks that the proposal is legal for the current turn.
4. Only validated actions become Temporal activity calls.

Validation belongs outside the model so Mycel can enforce policy even when model behavior drifts. This is also where error classification, argument validation, and future allow/deny rules belong.

Related issues: #3, #6, #7

## 3. One Tool Call Per Turn

Phase 1 should allow at most one tool call per LLM turn. This is a deliberate constraint, not an implementation shortcut.

Why:

- It keeps the workflow history simple and easy to inspect.
- It avoids runaway tool chains and hidden loops.
- It makes user-visible behavior easier to explain and test.
- It narrows the surface area while the core tool/activity interfaces are still stabilizing.

If the assistant needs more than one operation, it should either:

- respond with the result of the single validated tool call and wait for the next user turn, or
- use an explicit future workflow pattern designed for multi-step plans.

Related issues: #6, #7

## 4. Max Tool Depth Guardrail

Mycel must enforce a maximum tool depth for a conversation turn or workflow branch. Even with one tool call per LLM turn, a system can still accidentally create loops across retries, nested calls, or follow-up turns if there is no depth accounting.

Guardrail requirements:

- Track tool depth in workflow state, not only in prompts.
- Reject or short-circuit requests that exceed the configured limit.
- Surface a clear user-facing error when the guardrail triggers.
- Emit enough logs/metadata to diagnose why the loop was attempted.

This is a safety invariant for both correctness and cost control.

Related issues: #3, #7

## 5. Hybrid Interface: Natural Language Plus `/m_*` Commands

Mycel supports two interaction modes on purpose:

- Natural language for conversation routed through the Temporal workflow.
- `/m_*` commands for deterministic actions such as `/m_fetch`, `/m_read`, or `/m_write`.

The command layer is not a temporary hack. It provides:

- predictable entry points for early capabilities,
- lower-latency paths for obvious tool requests,
- easier debugging when workflow and tool behavior disagree,
- a stable interface while the LLM-driven action protocol matures.

This hybrid model lets contributors build and test tools incrementally without forcing every capability through an unconstrained chat loop.

Related issues: #6, #41

## 6. Tool Registry Plus Activity Execution Pattern

Tools should be defined in a registry with a stable schema and executed via Temporal activities.

The intended split is:

- Registry layer: declares tool name, purpose, input schema, and validation rules.
- Workflow layer: decides whether a proposed tool call is allowed right now.
- Activity layer: performs the external side effect or fetch.
- Response layer: turns the result into a user-visible reply.

This pattern matters because tools are where side effects happen. Registry-backed dispatch keeps tool definitions inspectable and testable, while activity execution keeps retries, timeouts, and visibility inside Temporal.

Issue #41 is a concrete reminder that tool-specific behavior must stay explicit. For example, `/m_fetch` needs defined handling for pages that require JavaScript instead of silently returning garbage.

Related issues: #6, #7, #41

## 7. Why Temporal

Temporal is the right control plane for Mycel because it gives the system properties that are hard to bolt on later:

- Durability: workflow progress survives process crashes and restarts.
- Replay safety: deterministic workflow code can rebuild state from history.
- Visibility: each step is inspectable in Temporal UI and event history.
- Retries and timeouts: external calls live in activities with explicit failure policy.

Those properties fit Mycel's problem shape better than a stateless bot with ad hoc background jobs. Conversations, memory updates, and tool execution all benefit from durable orchestration rather than best-effort async tasks.

Related issues: #3, #7, #8

## Issue Map

Use this doc with the current issue set:

- #3 defines the Temporal conversation workflow.
- #6 defines the initial tool surface area.
- #7 defines validation, failure classification, and user-visible remediation.
- #8 defines memory work that should run beside, not replace, workflow-owned control flow.
- #41 is an example of tool-specific execution detail that should fit the registry + activity model instead of bypassing it.
