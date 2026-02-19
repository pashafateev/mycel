# Temporal x OpenClaw Bridge (TypeScript PoC)

This PoC keeps OpenClaw as the Telegram-facing layer and runs conversation logic in Temporal TypeScript workflows.

Included components:
- Bridge server (`src/index.ts`)
- Conversation workflow with Update/query handlers + `ContinueAsNew` (`src/workflows/conversation.ts`)
- Mock LLM activity with routing simulation (`src/activities/mock-llm.ts`)
- Temporal worker (`src/worker.ts`)

## Endpoints

- `GET /healthz`
- `POST /session/start` with `{ "sessionId": "s1", "message": "hello" }`
- `POST /session/send` with `{ "sessionId": "s1", "message": "next message" }`
- `POST /reply` with `{ "sessionId": "s1", "text": "assistant text" }`

## Environment

Optional env vars:
- `TEMPORAL_HOST` (default `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default `default`)
- `TEMPORAL_TASK_QUEUE` (default `mycel-bridge`)
- `TEMPORAL_WORKFLOW_TYPE` (default `conversationWorkflow`)
- `CONTINUE_AS_NEW_TURN_LIMIT` (default `6`)
- `BRIDGE_PORT` (default `3001`)
- `OPENCLAW_WORKSPACE_ROOT` (default `/Users/admin/.openclaw/workspace`)

## Run

```bash
npm install
npm run dev:worker
npm run dev:bridge
```

Example test:

```bash
curl -s localhost:3001/session/start \
  -H 'content-type: application/json' \
  -d '{"sessionId":"demo","message":"Hello from bridge"}'

curl -s localhost:3001/session/send \
  -H 'content-type: application/json' \
  -d '{"sessionId":"demo","message":"Give me a one-line response"}'
```

Response includes mock routing info:

```json
{
  "turnId": "turn-2",
  "reply": "[mock:junior/simple] ...",
  "routing": {
    "complexity": "simple",
    "tier": "junior",
    "route_reason": "Simple but non-trivial request; route to junior tier."
  }
}
```
