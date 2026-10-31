"""PotatoBot CLI: look up a livestream's chat and send one manual message."""
from googleapiclient.errors import HttpError

from potatobot.auth import get_authenticated_service
from potatobot.scheduler import MessageScheduler
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


if __name__ == "__main__":
    main()
