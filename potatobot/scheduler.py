"""Bounded, user-controlled message scheduler for PotatoBot automation mode."""
import threading
import time
from pathlib import Path

from googleapiclient.errors import HttpError

from potatobot.youtube_client import get_live_chat_id, send_chat_message

MIN_INTERVAL_SECONDS = 60
MAX_MESSAGES = 30

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
