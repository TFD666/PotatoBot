"""OAuth2 desktop-flow authentication for PotatoBot."""
import os
import stat
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
        os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)  # owner read/write only; best-effort on Windows

    return build("youtube", "v3", credentials=creds)
