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
