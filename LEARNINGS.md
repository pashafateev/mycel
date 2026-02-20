# TB3 Learnings — OpenRouter Activity Resilience

## Scope
- Implemented `call_llm` as a Temporal activity backed by async `httpx` calls to OpenRouter.
- Added `LLMTestWorkflow` with signal-driven prompt intake, activity retries, and per-request queryable result state.
- Added real-call resilience harness (`scripts/test_tb03_resilience.py`) and mocked integration tests (`tests/test_tb03_integration.py`).

## OpenRouter Reliability Observations
- Expected transient failure classes are now explicitly mapped: `rate_limit_error` (429), `server_error` (5xx), `timeout_error`, and `network_error`.
- Auth and request-shape failures are treated as non-retryable (`auth_error`, `invalid_request_error`, `validation_error`) to avoid wasted retries.
- Real reliability metrics depend on running the resilience script against a live API key and active Temporal server.

## Retry Behavior Through Temporal
- Retry policy is configurable at workflow start (`initial_interval_seconds`, `maximum_interval_seconds`, `backoff_coefficient`, `maximum_attempts`).
- Workflow stores retry count per request using the final activity attempt metadata.
- Mocked tests validate retry recovery paths for 429 and 500, plus exhausted retries for timeout.

## Latency Profile
- Activity returns per-attempt `latency_ms` measured around the OpenRouter HTTP call.
- Workflow stores an end-to-end latency value for failed requests.
- Resilience script prints summary latency stats (`p50`, `p95`, `max`) from successful calls.

## Error Handling Gaps
- No provider fallback chain yet (single provider path only).
- No circuit breaker / adaptive throttling for sustained 429 windows.
- No streaming path in TB3 (deferred to TB4).
- Retry count is derived from attempt metadata, not a separate durable metrics sink.

## Production Changes Needed
- Add structured telemetry export (OTel/log sink) for retries, status codes, and token/latency metrics.
- Add provider/model fallback policy (including emergency direct-provider adapters).
- Add per-model timeout budgets and adaptive retry tuning from observed failure rates.
- Add secret management + runtime config loading instead of direct env reads in activity.
- Add load/concurrency testing across multiple workflows/task queues.

## No API Key Behavior
- If `OPENROUTER_API_KEY` is unset, `scripts/test_tb03_resilience.py` skips real calls and runs only mocked integration tests:
  - `python -m pytest -q tests/test_tb03_integration.py`

# TB4 Learnings — Streaming + Transcript Hygiene

## Streaming Through Temporal Activities
- Implemented `stream_llm` in `src/tb04/activities.py` using OpenRouter `stream=true` and `httpx.AsyncClient.stream`.
- Activity uses an internal async generator to parse SSE `data:` lines, incrementally buffers deltas, and returns one complete result payload (`response_text`, `model_used`, `token_count`, `latency_ms`, `was_streamed=true`).
- This follows Temporal constraints: activities cannot stream partial chunks back to workflow callers, so buffering-then-return is required.

## Transcript Hygiene Findings
- Added `assert_no_orphan_reasoning(items)` in `src/tb04/transcript.py`.
- Validator removes trailing orphan `reasoning` items and logs a warning when dropping them.
- Validator also guards malformed transitions where `reasoning` is followed by an invalid item type.
- `LLMStreamTestWorkflow` runs `validate_transcript` before every LLM call so replay payloads remain GPT-5.2 safe.

## Interrupted Stream Recovery
- Mid-stream timeout/network failures are normalized into `stream_interrupted_error` and treated as retryable Temporal activity errors.
- Workflow persists either a successful final response or a clean recoverable error per request.
- Added coverage for interrupted streams in both script-level and pytest-level TB4 tests.

## Recommendation
- Ship streaming from day 1 behind a feature flag.
- Rationale: streaming path has distinct failure modes (chunk parse, SSE disconnect, partial token accounting) and transcript hygiene requirements that should be exercised continuously, while feature-flagging limits blast radius during rollout.

## No API Key Behavior (TB4)
- If `OPENROUTER_API_KEY` is not set, `scripts/test_tb04_streaming.py` runs with mocked `httpx` streaming responses.
- `tests/test_tb04_streaming.py` also uses mocked `httpx` streaming so CI can validate behavior without live provider credentials.
