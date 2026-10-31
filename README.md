# PotatoBot

A small CLI tool for sending chat messages to a YouTube livestream you're watching, using your own Google account.

## Why this exists

This is a personal learning project — a way to get hands-on with the YouTube Data API v3, Google OAuth2, and Python's `threading` module. It's not a product, not a growth-hacking tool, and not meant to run unattended. Treat it as a small, honest experiment rather than anything polished.

## Technologies

- Python 3.11+
- `google-api-python-client` — YouTube Data API v3 client
- `google-auth-oauthlib` — OAuth2 desktop-app flow
- Python stdlib `threading` — the automation mode's run loop

## Architecture

```
potatobot/
  auth.py             OAuth2 desktop flow, token caching
  youtube_client.py   video id extraction, live chat lookup, send-message call
  scheduler.py         bounded automated sending (MessageScheduler)
  main.py              CLI entry point, wires the above together
tests/                 unit tests for the pure/testable parts
docs/superpowers/       design specs and implementation plans written during development
```

Each module has one job:
- **auth.py** gets you an authenticated YouTube API client, nothing else.
- **youtube_client.py** wraps three raw API calls: find a video id in a URL, look up its live chat id, send one message.
- **scheduler.py** runs those same calls on a timer, inside hard limits.
- **main.py** is just a CLI prompt sequence — no API logic of its own.

## Google Cloud and OAuth setup

1. Create a project in the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **YouTube Data API v3** for that project.
3. Under "Credentials", create an OAuth 2.0 Client ID of type **Desktop app**.
4. Download the credentials JSON and save it as `credentials.json` in this project's root. **Never commit this file** — it's already in `.gitignore`.
5. On first run, PotatoBot opens your browser for Google sign-in and consent, using only the `youtube.force-ssl` scope (the minimum needed to read live chat details and post a message). A `token.json` is cached locally afterward so you don't have to sign in every run — this file is also gitignored and should never be shared or committed.

## Installation

```bash
py -3.11 -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

(Any Python 3.11+ interpreter works — adjust the `py -3.11` version selector to whatever you have installed.)

## Running it

```bash
venv\Scripts\python -m potatobot.main
```

You'll be prompted for:
1. **Livestream URL** — any `youtube.com/watch?v=...`, `youtube.com/live/...`, or `youtu.be/...` link.
2. **Mode** — `1` to send one message, or `2` for automation mode.
3. Depending on mode, a message (and interval/count for automation mode).

## How livestream discovery works

`extract_video_id()` parses the URL and pulls out the 11-character video id. `get_live_chat_id()` then calls the API's `videos.list` endpoint and reads `liveStreamingDetails.activeLiveChatId` — if the stream isn't currently live, or has chat disabled, this raises a clear error instead of guessing.

## How the scheduler works

Automation mode (`MessageScheduler` in `scheduler.py`) sends the same message repeatedly on a background thread, with real limits:

- **60-second minimum interval** — enforced in the constructor, not adjustable downwards.
- **5-message maximum per session** — also enforced in the constructor.
- **Instant stop** — pressing Enter, the stream ending, or any API error (403, 429, etc.) stops the loop within about a second, not at the end of the current interval. It checks a `threading.Event` every second instead of sleeping through the whole interval in one call.
- **No retries, ever** — a failed send just stops the scheduler; it never tries again automatically.
- **One instance at a time** — a `scheduler.lock` file (gitignored) prevents a second automation run from starting while one is already active, including from a separate terminal/process.

These limits exist specifically so this tool can't be turned into a spam bot. They are not configurable at runtime by design.

## Limitations and YouTube API restrictions

- The YouTube Data API has a **daily quota**; frequent lookups and sends will eventually hit `quotaExceeded` (surfaced as a 403 with a clear message, not retried).
- Sending to a live chat requires the account to have a YouTube channel in good standing; a brand-new or restricted account may get a 403 even with a valid token.
- There's no listening/reading of incoming chat messages — this tool only sends, it doesn't display what others are saying.
- Automation mode is capped at 5 messages per run on purpose; this is not a tool for sustained or high-frequency posting.
- No retry logic anywhere — if a send fails, you have to look at the error and decide what to do next, manually.
