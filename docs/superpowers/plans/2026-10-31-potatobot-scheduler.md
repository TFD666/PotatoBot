# PotatoBot Message Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bounded automation mode (`potatobot/scheduler.py` + a `main.py` menu branch) that sends a configured message at a fixed interval, capped at 5 messages, with instant stop and no retry.

**Architecture:** New `MessageScheduler` class running its loop on a background `threading.Thread`, gated by a `threading.Event` for instant stop and a disk lock file for cross-process single-instance enforcement. Reuses `auth.py` / `youtube_client.py` unchanged. `main.py` gets one new menu branch; the existing send-once path is untouched.

**Tech Stack:** Python stdlib only (`threading`, `time`, `os`, `pathlib`) — no new dependencies.

## Global Constraints
- Interval hard minimum: 60 seconds — reject lower in validation.
- Max messages hard cap: 5 — reject higher (and reject 0) in validation.
- Stop (user, stream-end, or API error) takes effect within ~1 second — sleep in 1s ticks, never one long blocking sleep.
- No automatic retry of a failed send, ever.
- Only one scheduler instance at a time, enforced via a lock file at `PROJECT_ROOT / "scheduler.lock"` (added to `.gitignore`).
- Reuse `youtube_client.send_chat_message`, `youtube_client.get_live_chat_id`, `main.describe_http_error` as-is — do not modify their signatures.

---

### Task 1: scheduler.py — MessageScheduler core + validation

**Files:**
- Create: `potatobot/scheduler.py`
- Test: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `youtube_client.get_live_chat_id(youtube, video_id) -> str`, `youtube_client.send_chat_message(youtube, live_chat_id, text) -> dict` (both already exist, unchanged).
- Produces: `MessageScheduler` class with constructor `MessageScheduler(youtube, video_id, live_chat_id, message, interval_seconds, max_messages, describe_error=None)`, attributes `status: str`, `sent_count: int`, `last_response`, `stop_reason`, methods `start()`, `stop()`.

- [ ] **Step 1: Write the failing validation tests**

`tests/test_scheduler.py`:
```python
import pytest
from potatobot.scheduler import MessageScheduler


def _make_scheduler(**overrides):
    kwargs = dict(
        youtube=object(),
        video_id="abcdefghijk",
        live_chat_id="chat123",
        message="potato",
        interval_seconds=60,
        max_messages=5,
    )
    kwargs.update(overrides)
    return MessageScheduler(**kwargs)


def test_rejects_interval_below_60():
    with pytest.raises(ValueError):
        _make_scheduler(interval_seconds=59)


def test_accepts_interval_of_60():
    scheduler = _make_scheduler(interval_seconds=60)
    assert scheduler.status == "Stopped"


def test_rejects_max_messages_above_5():
    with pytest.raises(ValueError):
        _make_scheduler(max_messages=6)


def test_rejects_max_messages_of_0():
    with pytest.raises(ValueError):
        _make_scheduler(max_messages=0)


def test_initial_state():
    scheduler = _make_scheduler()
    assert scheduler.status == "Stopped"
    assert scheduler.sent_count == 0
    assert scheduler.last_response is None
    assert scheduler.stop_reason is None
```

- [ ] **Step 2: Run tests to verify they fail (module doesn't exist yet)**

```bash
venv\Scripts\python -m pytest tests/test_scheduler.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'potatobot.scheduler'`.

- [ ] **Step 3: Write scheduler.py (core class + validation only, no threading yet)**

```python
"""Bounded, user-controlled message scheduler for PotatoBot automation mode."""
import threading
import time
from pathlib import Path

from googleapiclient.errors import HttpError

from potatobot.youtube_client import get_live_chat_id, send_chat_message

MIN_INTERVAL_SECONDS = 60
MAX_MESSAGES = 5

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCK_PATH = PROJECT_ROOT / "scheduler.lock"


def _default_describe_error(error: HttpError) -> str:
    return str(error)


class MessageScheduler:
    """Sends `message` to a live chat every `interval_seconds`, up to
    `max_messages` times, on a background thread. Stops instantly on
    request, stream end, or any API error. Never retries a failed send.
    """

    def __init__(
        self,
        youtube,
        video_id,
        live_chat_id,
        message,
        interval_seconds,
        max_messages,
        describe_error=None,
    ):
        if interval_seconds < MIN_INTERVAL_SECONDS:
            raise ValueError(
                f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}, got {interval_seconds}"
            )
        if not (1 <= max_messages <= MAX_MESSAGES):
            raise ValueError(
                f"max_messages must be between 1 and {MAX_MESSAGES}, got {max_messages}"
            )

        self._youtube = youtube
        self._video_id = video_id
        self._live_chat_id = live_chat_id
        self._message = message
        self._interval_seconds = interval_seconds
        self._max_messages = max_messages
        self._describe_error = describe_error or _default_describe_error

        self._stop_event = threading.Event()
        self._thread = None

        self.status = "Stopped"
        self.sent_count = 0
        self.last_response = None
        self.stop_reason = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv\Scripts\python -m pytest tests/test_scheduler.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add potatobot/scheduler.py tests/test_scheduler.py
git commit -m "feat: add MessageScheduler core with interval/count validation"
```

---

### Task 2: scheduler.py — threaded run loop, start/stop, lock file

**Files:**
- Modify: `potatobot/scheduler.py` (append to the class from Task 1)
- Test: `tests/test_scheduler.py` (append)

**Interfaces:**
- Consumes: `MessageScheduler.__init__` from Task 1 (unchanged signature).
- Produces: `MessageScheduler.start()`, `MessageScheduler.stop()`, internal `_run()`. Lock file at `scheduler.LOCK_PATH`.

- [ ] **Step 1: Write failing tests for lock file + stop semantics**

Append to `tests/test_scheduler.py`:
```python
from unittest.mock import MagicMock
import time

from potatobot import scheduler as scheduler_module


def test_start_raises_if_lock_file_exists(tmp_path, monkeypatch):
    lock_path = tmp_path / "scheduler.lock"
    lock_path.write_text("12345")
    monkeypatch.setattr(scheduler_module, "LOCK_PATH", lock_path)

    s = _make_scheduler(max_messages=1)
    with pytest.raises(RuntimeError):
        s.start()


def test_start_stop_sends_and_cleans_up_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "scheduler.lock"
    monkeypatch.setattr(scheduler_module, "LOCK_PATH", lock_path)
    monkeypatch.setattr(scheduler_module, "send_chat_message", lambda yt, cid, msg: {"ok": True})
    monkeypatch.setattr(scheduler_module, "get_live_chat_id", lambda yt, vid: "chat123")

    s = _make_scheduler(max_messages=5, interval_seconds=60)
    s.start()
    # give the worker thread a moment to send the first message and start sleeping
    for _ in range(50):
        if s.sent_count >= 1:
            break
        time.sleep(0.05)
    s.stop()

    assert s.sent_count == 1
    assert s.status == "Stopped"
    assert s.stop_reason == "user"
    assert not lock_path.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
venv\Scripts\python -m pytest tests/test_scheduler.py -v
```
Expected: FAIL — `AttributeError: 'MessageScheduler' object has no attribute 'start'`.

- [ ] **Step 3: Append start/stop/_run to scheduler.py**

Add to `potatobot/scheduler.py` (inside `MessageScheduler`, and module-level import of `get_live_chat_id`/`send_chat_message` already present from Task 1):

```python
    def start(self):
        if LOCK_PATH.exists():
            raise RuntimeError(
                f"Another scheduler instance appears to be running "
                f"(lock file found at {LOCK_PATH}). Delete it if you're "
                "sure no other instance is active."
            )
        LOCK_PATH.write_text(str(threading.get_ident()))
        self.status = "Running"
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self.status != "Running":
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

    def _run(self):
        try:
            while self.sent_count < self._max_messages and not self._stop_event.is_set():
                try:
                    get_live_chat_id(self._youtube, self._video_id)
                except LookupError:
                    self.stop_reason = "stream_ended"
                    break

                try:
                    self.last_response = send_chat_message(
                        self._youtube, self._live_chat_id, self._message
                    )
                except HttpError as e:
                    self.last_response = self._describe_error(e)
                    self.stop_reason = "api_error"
                    break

                self.sent_count += 1
                print(
                    f"Status: Running | Sent: {self.sent_count}/{self._max_messages} "
                    f"| Last: {self.last_response}"
                )

                if self.sent_count >= self._max_messages:
                    self.stop_reason = "max_reached"
                    break

                waited = 0
                while waited < self._interval_seconds and not self._stop_event.is_set():
                    time.sleep(1)
                    waited += 1

            if self.stop_reason is None:
                self.stop_reason = "user"
        finally:
            self.status = "Stopped"
            if LOCK_PATH.exists():
                LOCK_PATH.unlink()
            print(f"Status: Stopped | Reason: {self.stop_reason} | Sent: {self.sent_count}/{self._max_messages}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
venv\Scripts\python -m pytest tests/test_scheduler.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Add scheduler.lock to .gitignore**

Append to `.gitignore`:
```
scheduler.lock
```

- [ ] **Step 6: Commit**

```bash
git add potatobot/scheduler.py tests/test_scheduler.py .gitignore
git commit -m "feat: add scheduler run loop, instant stop, and single-instance lock file"
```

---

### Task 3: main.py — automation-mode menu branch

**Files:**
- Modify: `potatobot/main.py`

**Interfaces:**
- Consumes: `MessageScheduler` (Task 2), existing `describe_http_error`, existing `get_live_chat_id`/`extract_video_id`/`get_authenticated_service` calls already present in `main()`.
- Produces: no new exports; `main()` gains a mode branch after the existing lookup step.

- [ ] **Step 1: Modify main.py — add import and mode branch**

In `potatobot/main.py`, add to the imports at the top:
```python
from potatobot.scheduler import MessageScheduler
```

Replace the existing block from `message = input("Chat message to send: ").strip()` through the end of `main()` with:
```python
    mode = input("Mode: [1] Send once  [2] Automation mode: ").strip()

    if mode == "2":
        _run_automation_mode(youtube, video_id, live_chat_id)
        return

    message = input("Chat message to send: ").strip()
    if not message:
        print("Empty message, nothing to send.")
        return

    confirm = input(f'Send "{message}" now? [y/N]: ').strip().lower()
    if confirm != "y":
        print("Not sent.")
        return

    try:
        response = send_chat_message(youtube, live_chat_id, message)
    except HttpError as e:
        print(f"Error: {describe_http_error(e)}")
        return

    print("Sent. API response:")
    print(response)


def _run_automation_mode(youtube, video_id, live_chat_id) -> None:
    message = input("Message to send repeatedly: ").strip()
    if not message:
        print("Empty message, cancelling automation mode.")
        return

    try:
        interval = int(input("Interval in seconds (minimum 60): ").strip())
        count = int(input("Number of messages to send (max 5): ").strip())
    except ValueError:
        print("Invalid number entered. Cancelling automation mode.")
        return

    try:
        scheduler = MessageScheduler(
            youtube=youtube,
            video_id=video_id,
            live_chat_id=live_chat_id,
            message=message,
            interval_seconds=interval,
            max_messages=count,
            describe_error=describe_http_error,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return

    try:
        scheduler.start()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    input("Automation running. Press Enter at any time to stop early...\n")
    scheduler.stop()
```

- [ ] **Step 2: Manual smoke test — import check**

```bash
venv\Scripts\python -c "import potatobot.main; print('IMPORT_OK')"
```
Expected: `IMPORT_OK` with no errors.

- [ ] **Step 3: Run the full test suite**

```bash
venv\Scripts\python -m pytest tests/ -v
```
Expected: all tests (7 from v1 + 7 from Tasks 1-2) PASS.

- [ ] **Step 4: Commit**

```bash
git add potatobot/main.py
git commit -m "feat: add automation-mode menu branch to CLI"
```

---

### Task 4: End-to-end manual verification (requires a live stream)

**Files:** none created — verification only.

- [ ] **Step 1: Run automation mode with interval=60, count=2 against a real live stream the user can post to**

```bash
venv\Scripts\python -m potatobot.main
```
Choose mode `2`, enter a test message, interval `60`, count `2`.
Expected: first message sends immediately, a `Status: Running | Sent: 1/2 | Last: ...` line prints, ~60s later a second send happens and prints `Sent: 2/2`, then `Status: Stopped | Reason: max_reached`.

- [ ] **Step 2: Verify Enter-to-stop works immediately mid-wait**

Run again, choose mode `2`, count `5`, interval `60`. After the first send, press Enter during the wait.
Expected: stops within ~1 second (not up to 60s), prints `Status: Stopped | Reason: user`, `sent_count` reflects only what was actually sent.

- [ ] **Step 3: Verify lock file prevents a second concurrent instance**

While one automation-mode run is `Running` (from Step 2, before pressing Enter), open a second terminal and run `potatobot.main` through to mode `2` again.
Expected: second instance's `scheduler.start()` raises, printed as `Error: Another scheduler instance appears to be running...`.

- [ ] **Step 4: Verify scheduler.lock is cleaned up after stop**

```bash
dir scheduler.lock
```
Run after any completed/stopped session.
Expected: file not found (removed in `_run`'s `finally`).

- [ ] **Step 5: Verify git status — no stray lock file tracked**

```bash
git status
```
Expected: `scheduler.lock` not listed (even if present, it's gitignored).
