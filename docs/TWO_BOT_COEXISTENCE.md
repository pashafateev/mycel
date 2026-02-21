# TB10: Two-Bot Coexistence Contract

## Goal
Run Mycel and OpenClaw in parallel for the same Telegram user without duplicate handling.

## Command Namespace Contract
- Mycel-only commands:
  - `/m_ping`
  - `/m_remind <text>`
  - `/m_status`
- OpenClaw-only commands:
  - `/oc_ping`
  - `/oc_status`
- Shared bootstrap commands:
  - `/start`
  - `/help`
- Unprefixed plain text:
  - Claimed by Mycel as the new default during transition.

## Routing Rules
- Mycel bot behavior:
  - Responds to `/m_*` commands.
  - Responds to plain text (non-command).
  - Ignores `/oc_*` commands completely.
  - For `/start` and `/help`, responds only if it wins first-responder claim in shared state.
- OpenClaw bot behavior:
  - Responds only to `/oc_*` commands.
  - Ignores `/m_*` commands.
  - Ignores plain text.

## Shared Command Arbitration
- `/start` and `/help` are arbitrated by a shared JSON state file.
- First bot to claim one of those commands responds.
- Other bot must remain silent for that command.
- This guarantees at-most-one responder for shared bootstrap commands.

## Simulation Coverage (20 commands over 30 minutes)
- `5x /m_ping` -> Mycel only
- `5x /oc_ping` -> OpenClaw only
- `3x /m_remind "test"` -> Mycel only
- `3x /oc_status` -> OpenClaw only
- `2x "hello"` -> Mycel only
- `1x /start` -> one bot only
- `1x /help` -> one bot only

Success criterion: zero double-handled commands.

## Edge Cases and Resolution
- Edge case: user sends `/m_ping` and OpenClaw sees the update.
  - Resolution: OpenClaw ignores `/m_*`; only Mycel responds.
- Edge case: both bots in same group chat.
  - Resolution: namespaced commands prevent collision (`/m_*` vs `/oc_*`).
- Edge case: ambiguous non-command text.
  - Resolution: Mycel claims plain text as default, OpenClaw stays command-only.

## Transition Strategy
1. Phase A (parallel-safe): require prefixes (`/oc_*`, `/m_*`) for explicit ownership.
2. Phase B (migration): move active user flows from `/oc_*` to `/m_*`; keep `/oc_*` aliases read-only with deprecation hint.
3. Phase C (default shift): keep Mycel as plain-text default; maintain command namespace for admin/debug operations.
4. Phase D (retirement): disable `/oc_*` handlers once usage drops to zero for a defined window.

## Operational Notes
- If both bots use Telegram privacy mode off in group chats, both still receive updates; namespace remains the primary collision guard.
- If command overlap is introduced later, keep first-responder arbitration only for explicit shared commands and document each exception.
