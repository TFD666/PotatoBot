# PotatoBot — Controlled Message Scheduler — Design

## Purpose
Add a bounded, user-controlled automation mode to PotatoBot: send the same configured message at a fixed interval, up to a hard cap, with instant stop and no auto-retry. Existing single-send flow (auth.py, youtube_client.py, main.py's send-once path) stays untouched.

## Safety rails (hard requirements, non-negotiable)
- Hard minimum interval: 60 seconds. Reject/clamp anything lower.
- Hard maximum: 5 messages per session. Reject anything higher.
- Stop must take effect within ~1 second of request, stream ending, or any API error — never waits out a full interval sleep.
- No automatic retry of a failed send, ever.
- Only one scheduler instance may run at a time (lock file, catches separate OS processes too).

## Tech stack
Same as v1, plus Python's stdlib `threading` (`Thread`, `Event`) and a plain lock file — no new third-party dependencies.

## Project structure (additions only)
```
potatobot/
  scheduler.py      (new)
  main.py            (modified: add automation-mode menu branch)
scheduler.lock       (generated, gitignored)
```

## scheduler.py

### MessageScheduler class
**Constructor:** `MessageScheduler(youtube, live_chat_id, video_id, message, interval_seconds, max_messages)`
- Validates `interval_seconds >= 60` and `1 <= max_messages <= 5`; raises `ValueError` otherwise.

**State attributes (read by caller for display):**
- `status`: `"Running"` | `"Stopped"`
- `sent_count`: int
- `last_response`: the last API response dict, or a short error string
- `stop_reason`: `None` until stopped, then one of `"user"`, `"stream_ended"`, `"api_error"`, `"max_reached"`

**Methods:**
- `start()` — acquires the lock file (raises `RuntimeError` if already held by a live process), spawns the worker thread, sets `status = "Running"`.
- `stop()` — sets the internal `threading.Event`, joins the thread, releases the lock file.
- Internal `_run()` (worker thread body):
  1. Loop while `sent_count < max_messages` and stop event not set:
  2. Re-check the stream is still live via `get_live_chat_id` (reuses existing function); on `LookupError` → set `stop_reason="stream_ended"`, break.
  3. Call existing `send_chat_message` once. On success: increment `sent_count`, set `last_response`. On `HttpError`: set `last_response` to the mapped error (reuse `main.describe_http_error`), `stop_reason="api_error"`, break — no retry.
  4. Print one status line (`Status: Running | Sent: n/max | Last: ...`).
  5. If `sent_count == max_messages`: `stop_reason="max_reached"`, break.
  6. Sleep in 1-second ticks up to `interval_seconds`, re-checking the stop event each tick; break the sleep early if set.
  7. On loop exit (any reason): set `status = "Stopped"`, release lock file.

### Lock file
`scheduler.lock` at project root (`PROJECT_ROOT / "scheduler.lock"`, same root resolution as `auth.py`). Contains the PID. `start()`:
- If the file exists, read the PID and check it's still a live process (`psutil` not available — use a simple `os.kill(pid, 0)` try/except on POSIX, or on Windows check via `tasklist`-free approach: just attempt the check, and if it fails/unsupported, fall back to "file exists => refuse" which is safe-by-default, just slightly stricter). Simpler and sufficient here: if the file exists at all, refuse with a clear message telling the user to delete it if they're sure no other instance is running. Removed in a `finally` on both normal stop and crash paths.

## main.py changes
After existing auth + lookup (unchanged), add:
```
Mode: [1] Send once  [2] Automation mode
```
- `[1]` → existing code path, unchanged.
- `[2]` → prompt for message text, interval (validate ≥60, re-prompt on failure), count (validate 1-5, re-prompt on failure); construct and `start()` the scheduler; then `input("Press Enter to stop early...\n")` blocks the main thread — on return, call `stop()`. The worker thread prints its own status lines as it runs, so the user sees live progress while waiting at that prompt.
- On scheduler reaching `max_reached` or `stream_ended` or `api_error` on its own, the worker thread's final status line reports the reason; `main()` still calls `stop()` afterward (idempotent — no-op if already stopped) to clean up the lock file and join the thread.

## Testing
- Unit tests (no network) for `MessageScheduler.__init__` validation: interval < 60 raises, count > 5 raises, count 0 raises.
- Unit test for lock file: starting a second scheduler while `scheduler.lock` exists raises `RuntimeError`.
- Manual verification: run automation mode against a real stream with interval=60, count=2; confirm two sends ~60s apart, confirm Enter-to-stop works immediately mid-wait, confirm lock file is removed after stop, confirm a second automation-mode start while the first is "Running" (two terminals) is refused.
