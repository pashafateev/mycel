# TB8 Learnings: Exec Safety Envelope

## Hardest commands to safely handle
- `python3 -c ...` was the hardest because a safe outer command can still execute dangerous nested shell operations.
- `yes` is high-risk for output flooding and requires hard output caps plus timeout-kill behavior.
- Shell redirection (`>`, `>>`, pipes) is deceptively dangerous and needed explicit token-level blocking.

## Is allowlist sufficient?
- Allowlist is necessary but not sufficient for robust safety.
- It blocks obvious unsafe binaries (`rm`, `curl`, `sudo`, `nc`), but nested execution inside allowed commands (especially Python) requires additional policy checks.
- Recommended next layer: argument-level policy per command, read/write mode restrictions, and optionally execution sandboxes (container/seccomp) for stronger isolation.

## Process cleanup reliability
- Timeout handling with process-group kill (`SIGKILL` on PGID) plus explicit `communicate()` reap was reliable in this spike.
- Post-timeout `ps` checks reported no lingering or zombie processes for tested timeout paths.
- Temporal activity timeout behavior was clean when kill/reap logic lived inside activity code.

## MVP recommendation
- Do **not** ship unrestricted generic `exec` in MVP.
- Ship only constrained tool execution with strict allowlist + path scope + timeout + output cap + non-retryable blocked errors.
- Prefer dedicated high-level tools (`read_file`, `list_files`, `git_status`) over free-form command execution for default assistant behavior.
