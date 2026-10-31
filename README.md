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
