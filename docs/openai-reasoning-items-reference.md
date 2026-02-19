# OpenAI Reasoning Items — Pairing Rules

## The Bug
GPT-5.2 returns `reasoning` items (id: `rs_...`) that must be paired with their following `message` or `function_call` item. If replayed orphaned (without the companion), OpenAI returns 400.

## Rules for Mycel LLM Adapter
1. **Never replay a trailing reasoning item** — if reasoning is last, drop it
2. **Preserve order**: reasoning → message/function_call (never reversed)
3. **If using manual state**: replay reasoning+companion pairs together, in order
4. **If using previous_response_id**: let OpenAI handle it (preferred for simplicity)
5. **Stateless (store: false)**: must include `reasoning.encrypted_content` in requests
6. **Validator**: before every API call, scan input items — no orphan `rs_` items allowed

## Validation Function (use in adapter)
```typescript
function assertNoOrphanReasoning(items: any[]) {
  for (let i = 0; i < items.length; i++) {
    if (items[i]?.type === "reasoning") {
      const next = items[i + 1];
      if (!next || (next.type !== "message" && next.type !== "function_call")) {
        // Drop the orphan or throw
        throw new Error(`Orphan reasoning item ${items[i].id}`);
      }
    }
  }
}
```

## Source
Pasha's deep research doc (2026-02-18). Filed as reference for mycel LLM adapter design.
