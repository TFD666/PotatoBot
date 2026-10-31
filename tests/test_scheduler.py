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
