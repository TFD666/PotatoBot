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
