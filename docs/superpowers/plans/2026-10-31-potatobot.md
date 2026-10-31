# PotatoBot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CLI tool letting an authenticated viewer look up a YouTube livestream's chat and manually send one chat message per explicit confirmation.

**Architecture:** Three flat modules (`auth.py`, `youtube_client.py`, `main.py`) under `potatobot/`. `main.py` orchestrates a single linear pass: validate URL → look up live chat id → authenticate → prompt → confirm → send once. No loops, no retries, no network mocking framework — verification against the real API/OAuth flow is manual since this is a thin wrapper around external services and unit tests would just re-test the Google client library.

**Tech Stack:** Python 3.13 (`py -3.13`), `google-api-python-client`, `google-auth-oauthlib`, venv.

## Global Constraints
- Python 3.11+ (using 3.13 via `py -3.13`).
- OAuth scope: `https://www.googleapis.com/auth/youtube.force-ssl` only — no broader scope.
- Never print, log, or commit `credentials.json` or `token.json`.
- No automatic/repeated send, no background loop, no retry on rejected send — every send is one explicit user-confirmed call.
- No browser automation, no CAPTCHA bypass.

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `potatobot/__init__.py` (empty)
- Create: `README.md`

**Interfaces:**
- Produces: a venv-ready project skeleton; nothing to import yet.

- [ ] **Step 1: Create venv and requirements.txt**

```bash
py -3.13 -m venv venv
```

`requirements.txt`:
```
google-api-python-client>=2.100.0
google-auth-oauthlib>=1.2.0
```

- [ ] **Step 2: Install deps**

```bash
venv\Scripts\python -m pip install -r requirements.txt
```
Expected: installs without error.

- [ ] **Step 3: Create .gitignore**

```
venv/
__pycache__/
*.pyc
credentials.json
token.json
```

- [ ] **Step 4: Create potatobot/__init__.py**

Empty file (makes `potatobot` importable as a package).

- [ ] **Step 5: Write README.md**

```markdown
# PotatoBot

CLI helper for sending a single manual chat message to a YouTube livestream you're watching, as yourself.

## Setup

1. Create a Google Cloud project, enable "YouTube Data API v3".
2. Create OAuth 2.0 credentials of type "Desktop app", download as `credentials.json`, place it in this project's root.
3. Create venv and install deps:
   ```bash
   py -3.13 -m venv venv
   venv\Scripts\python -m pip install -r requirements.txt
   ```
4. Run:
   ```bash
   venv\Scripts\python -m potatobot.main
   ```
   First run opens a browser for Google sign-in/consent; a `token.json` is cached locally afterward (never commit it).

## Usage

- Paste a live YouTube video URL when prompted.
- Type your chat message when prompted.
- Confirm with `y` to send. Each run sends at most one message — nothing is automatic or repeated.

## Scope / safety

No background sending, no retries, no CAPTCHA/browser automation. You trigger every send explicitly.
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore potatobot/__init__.py README.md
git commit -m "chore: scaffold PotatoBot project"
```

---

### Task 2: auth.py — OAuth2 desktop flow

**Files:**
- Create: `potatobot/auth.py`

**Interfaces:**
- Produces: `get_authenticated_service() -> googleapiclient.discovery.Resource` — a ready-to-use YouTube API client.
- Constants: `SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]`, `TOKEN_PATH`, `CREDENTIALS_PATH` (both resolved relative to project root via `pathlib.Path(__file__).resolve().parent.parent`).

- [ ] **Step 1: Write auth.py**

```python
"""OAuth2 desktop-flow authentication for PotatoBot."""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = PROJECT_ROOT / "credentials.json"
TOKEN_PATH = PROJECT_ROOT / "token.json"


def get_authenticated_service():
    """Return an authenticated YouTube Data API v3 client.

    Loads a cached token from TOKEN_PATH if present and valid (refreshing
    if expired), otherwise runs the OAuth2 desktop consent flow using
    CREDENTIALS_PATH and caches the resulting token.
    """
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Missing {CREDENTIALS_PATH}. Download OAuth Desktop "
                    "credentials from Google Cloud Console and place them there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)
```

- [ ] **Step 2: Manual verification (no credentials.json yet -> expect clean error)**

```bash
venv\Scripts\python -c "from potatobot.auth import get_authenticated_service; get_authenticated_service()"
```
Expected: `FileNotFoundError: Missing ...credentials.json...` (confirms path logic and error message work before real credentials exist).

- [ ] **Step 3: Commit**

```bash
git add potatobot/auth.py
git commit -m "feat: add OAuth2 desktop-flow authentication"
```

*(Full live verification — real browser consent + token reuse on second run — happens once the user supplies their own `credentials.json`; covered in Task 5's manual verification pass.)*

---

### Task 3: youtube_client.py — video ID + live chat id lookup

**Files:**
- Create: `potatobot/youtube_client.py`

**Interfaces:**
- Consumes: nothing from other tasks (pure functions + API calls via a passed-in `youtube` client object from Task 2).
- Produces:
  - `extract_video_id(url: str) -> str` — raises `ValueError(message)` on invalid URL.
  - `get_live_chat_id(youtube, video_id: str) -> str` — raises `LookupError(message)` if not live / chat disabled / not found.
  - `send_chat_message(youtube, live_chat_id: str, text: str) -> dict` — returns the API response dict.

- [ ] **Step 1: Write youtube_client.py**

```python
"""YouTube Data API v3 helpers: video id extraction, live chat lookup, send."""
import re
from urllib.parse import urlparse, parse_qs

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(url: str) -> str:
    """Extract and validate an 11-char YouTube video id from a URL.

    Supports youtube.com/watch?v=, youtube.com/live/, and youtu.be/ forms.
    Raises ValueError if no valid video id can be found.
    """
    url = url.strip()
    parsed = urlparse(url)

    video_id = None
    if parsed.netloc.endswith("youtu.be"):
        video_id = parsed.path.lstrip("/")
    elif "youtube.com" in parsed.netloc:
        if parsed.path == "/watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith("/live/"):
            video_id = parsed.path.split("/live/", 1)[1]

    if not video_id or not _VIDEO_ID_RE.match(video_id):
        raise ValueError(f"Could not extract a valid video id from URL: {url}")

    return video_id


def get_live_chat_id(youtube, video_id: str) -> str:
    """Look up the active liveChatId for a video id.

    Raises LookupError with a clear message if the video doesn't exist,
    isn't currently live, or has chat disabled.
    """
    response = (
        youtube.videos()
        .list(part="liveStreamingDetails,snippet", id=video_id)
        .execute()
    )
    items = response.get("items", [])
    if not items:
        raise LookupError(f"No video found for id {video_id}.")

    details = items[0].get("liveStreamingDetails", {})
    live_chat_id = details.get("activeLiveChatId")
    if not live_chat_id:
        raise LookupError(
            "This video has no active live chat (stream may have ended, "
            "not started, or chat is disabled)."
        )
    return live_chat_id


def send_chat_message(youtube, live_chat_id: str, text: str) -> dict:
    """Send a single text message to the given live chat. One call, no retry."""
    body = {
        "snippet": {
            "liveChatId": live_chat_id,
            "type": "textMessageEvent",
            "textMessageDetails": {"messageText": text},
        }
    }
    return youtube.liveChatMessages().insert(part="snippet", body=body).execute()
```

- [ ] **Step 2: Write unit tests for extract_video_id (pure function, no network)**

`tests/test_youtube_client.py`:
```python
import pytest
from potatobot.youtube_client import extract_video_id


def test_extract_video_id_from_watch_url():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_from_short_url():
    url = "https://youtu.be/dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_from_live_url():
    url = "https://www.youtube.com/live/dQw4w9WgXcQ"
    assert extract_video_id(url) == "dQw4w9WgXcQ"


def test_extract_video_id_rejects_invalid_url():
    with pytest.raises(ValueError):
        extract_video_id("https://example.com/not-youtube")
```

- [ ] **Step 3: Run tests, verify they fail first (module doesn't exist yet would fail; here module exists so run once written to confirm pass)**

```bash
venv\Scripts\python -m pip install pytest
venv\Scripts\python -m pytest tests/test_youtube_client.py -v
```
Expected: all 4 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add potatobot/youtube_client.py tests/test_youtube_client.py
git commit -m "feat: add video id extraction and live chat lookup/send helpers"
```

---

### Task 4: main.py — CLI orchestration

**Files:**
- Create: `potatobot/main.py`

**Interfaces:**
- Consumes: `auth.get_authenticated_service()` (Task 2), `youtube_client.extract_video_id`, `youtube_client.get_live_chat_id`, `youtube_client.send_chat_message` (Task 3).
- Produces: `main()` entry point; module runnable via `python -m potatobot.main`.

- [ ] **Step 1: Write main.py**

```python
"""PotatoBot CLI: look up a livestream's chat and send one manual message."""
from googleapiclient.errors import HttpError

from potatobot.auth import get_authenticated_service
from potatobot.youtube_client import (
    extract_video_id,
    get_live_chat_id,
    send_chat_message,
)


def describe_http_error(error: HttpError) -> str:
    """Map a googleapiclient HttpError to a plain-language message."""
    status = error.resp.status if error.resp else None
    reason = ""
    try:
        reason = error.error_details[0].get("reason", "") if error.error_details else ""
    except (AttributeError, IndexError, TypeError):
        reason = ""

    if status == 403:
        if "quota" in reason.lower():
            return "Quota exceeded for the YouTube API today. Try again later."
        return "Permission denied (403) — chat may be disabled or you lack access."
    if status == 404:
        return "Video not found (404) — check the URL."
    if status == 429 or "rateLimitExceeded" in reason:
        return "Rate limited by the API. Try again later (not retried automatically)."
    return f"YouTube API error (status {status}): {error}"


def main() -> None:
    url = input("Livestream URL: ").strip()
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        print(f"Error: {e}")
        return

    try:
        youtube = get_authenticated_service()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    try:
        live_chat_id = get_live_chat_id(youtube, video_id)
    except LookupError as e:
        print(f"Error: {e}")
        return
    except HttpError as e:
        print(f"Error: {describe_http_error(e)}")
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


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write unit test for describe_http_error (pure function, no network)**

`tests/test_main.py`:
```python
from unittest.mock import MagicMock

from potatobot.main import describe_http_error


def _make_error(status, reason=""):
    err = MagicMock()
    err.resp.status = status
    err.error_details = [{"reason": reason}] if reason else []
    err.__str__.return_value = f"HttpError {status}"
    return err


def test_describe_http_error_403_quota():
    err = _make_error(403, reason="quotaExceeded")
    assert "Quota exceeded" in describe_http_error(err)


def test_describe_http_error_404():
    err = _make_error(404)
    assert "not found" in describe_http_error(err).lower()


def test_describe_http_error_429():
    err = _make_error(429)
    assert "Rate limited" in describe_http_error(err)
```

- [ ] **Step 3: Run tests**

```bash
venv\Scripts\python -m pytest tests/test_main.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add potatobot/main.py tests/test_main.py
git commit -m "feat: add CLI orchestration with explicit confirm-to-send and error mapping"
```

---

### Task 5: End-to-end manual verification (requires user's real credentials.json)

**Files:** none created — verification only.

- [ ] **Step 1: User places their own `credentials.json` (OAuth Desktop type) in project root.**

- [ ] **Step 2: Run the CLI against a real live video, verify auth + lookup**

```bash
venv\Scripts\python -m potatobot.main
```
Paste a currently-live YouTube URL. Expected: browser opens for Google consent once, `token.json` is created, live chat id is found, prompts for a message.

- [ ] **Step 3: Confirm token reuse on second run**

Run the same command again with the same (or a different) live URL.
Expected: no browser prompt this time — cached `token.json` is reused silently.

- [ ] **Step 4: Send one real test message to a stream you control, confirm with `y`**

Expected: "Sent. API response:" printed with the message snippet echoed back from the API.

- [ ] **Step 5: Verify a declined send does nothing**

Run again, answer `n` (or anything but `y`) at the confirm prompt.
Expected: "Not sent." printed, no API call made (check your stream's chat — nothing new appears).

- [ ] **Step 6: Verify `token.json` and `credentials.json` are not tracked**

```bash
git status
```
Expected: neither file listed (gitignored).
