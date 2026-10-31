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
