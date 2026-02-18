# Temporal x OpenClaw Bridge (Phase 1 Tracer)

Minimal TypeScript bridge that:
- starts/targets Temporal `AgenticWorkflow` on task queue `temporal-agent-harness`
- injects system prompt content from workspace docs (`SOUL.md`, `USER.md`, `AGENTS.md`, `MEMORY.md`)
- sends user messages via workflow Update `user_input`
- exposes a tracer webhook `POST /reply` to log outgoing reply payloads

## Endpoints

- `GET /healthz`
- `POST /session/start` with `{ "sessionId": "s1", "message": "hello" }`
- `POST /session/send` with `{ "sessionId": "s1", "message": "next message" }`
- `POST /reply` with `{ "sessionId": "s1", "text": "assistant text" }`

## Environment

Optional env vars:
- `TEMPORAL_HOST` (default `localhost:7233`)
- `TEMPORAL_NAMESPACE` (default `default`)
- `TEMPORAL_TASK_QUEUE` (default `temporal-agent-harness`)
- `TEMPORAL_WORKFLOW_TYPE` (default `AgenticWorkflow`)
- `BRIDGE_PORT` (default `3001`)
- `OPENCLAW_WORKSPACE_ROOT` (default `/Users/admin/.openclaw/workspace`)
- `AGENT_CWD` (default workspace root)
- `MODEL_PROVIDER` (default: `anthropic` if `ANTHROPIC_API_KEY` exists, else `openai`)
- `MODEL_NAME` (default based on provider)

## Run

```bash
npm install
npm run dev
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
