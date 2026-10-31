# PotatoBot — YouTube Live Chat Helper — Design

## Purpose
CLI tool for an authenticated ordinary viewer to look up a YouTube livestream's chat and manually send one chat message per explicit action. No automation, no loops.

## Tech stack
- Python 3.13 (via `py -3.13`), venv
- `google-api-python-client`, `google-auth-oauthlib`
- YouTube Data API v3

## Project structure
```
potatobot/
  main.py
  youtube_client.py
  auth.py
requirements.txt
.gitignore
credentials.json   (user-supplied, gitignored)
token.json          (generated, gitignored)
README.md
```

## Modules

### auth.py
- `get_authenticated_service()` — runs OAuth2 desktop flow via `InstalledAppFlow` if no valid cached token; else loads+refreshes `token.json`.
- Scope: `https://www.googleapis.com/auth/youtube.force-ssl` (minimum scope that permits `liveChatMessages.insert`).
- Token stored locally in `token.json`, excluded from git. Never printed/logged.

### youtube_client.py
- `extract_video_id(url: str) -> str` — parses/validates standard YouTube URL forms (`watch?v=`, `youtu.be/`, `live/`); raises `ValueError` on invalid input.
- `get_live_chat_id(youtube, video_id: str) -> str` — calls `videos.list(part="liveStreamingDetails")`; returns `activeLiveChatId`; raises clear error if stream ended / not live / chat disabled.
- `send_chat_message(youtube, live_chat_id: str, text: str) -> dict` — single `liveChatMessages.insert` call, textMessageDetails. Returns raw API response.

### main.py
CLI flow, one pass, no loops:
1. Prompt for livestream URL → validate → video_id.
2. Fetch liveStreamingDetails → liveChatId (or print error and stop).
3. Authenticate (`auth.get_authenticated_service()`).
4. Prompt for chat message text.
5. Require explicit confirmation ("Send this message? [y/N]") before the single send call.
6. Print API response or a clear, mapped error. No retry on rejection.

## Error handling
Catch `googleapiclient.errors.HttpError` and map by status/reason to plain messages:
- 403 → permission/quota/chat disabled (inspect reason string)
- 404 → video not found
- live chat ended/missing → "stream not currently live or chat has ended"
- rate limit (429 / quotaExceeded) → message, no auto-retry

## Safety constraints (hard requirements)
- No automatic/repeated sending, no background loops.
- No browser automation, no CAPTCHA bypass.
- Every message send requires one explicit user confirmation per attempt.
- OAuth tokens/credentials never printed or committed (`.gitignore` covers `credentials.json`, `token.json`, `venv/`, `__pycache__/`).

## Build order
1. `auth.py` — implement + manually verify OAuth + token caching.
2. `youtube_client.py` lookup functions — verify against a real live URL.
3. `main.py` send flow — verify one message send against a test stream.

## Testing
Manual verification only (small CLI, no test framework needed):
- Run auth flow twice — second run must reuse cached token without re-prompting browser.
- Run URL validation against a few malformed/valid URLs.
- Run against a real live video — confirm liveChatId retrieved or correct error for non-live video.
- Send one real test message, confirm response printed, confirm no retry on a forced error.
