import pytest
from limits.util import WindowStats

from database import UsersOrm, check_auth
from exceptions import LimitExceededError
from services import check_quota


def test_db_authorized_user_permission(mock_db_session):
    """Test that an authorized user ID returns True."""
    # Setup mock user
    mock_user = UsersOrm(user_id=123, approved=True)
    mock_db_session.get.return_value = mock_user

    assert check_auth(123) is True
    mock_db_session.get.assert_called_once_with(UsersOrm, 123)


def test_db_unauthorized_user_permission(mock_db_session):
    """Test that an unauthorized user ID returns False."""
    # Setup mock user
    mock_user = UsersOrm(user_id=123, approved=False)
    mock_db_session.get.return_value = mock_user

    assert check_auth(123) is False
    mock_db_session.get.assert_called_once_with(UsersOrm, 123)


def test_db_unknown_user_permission(mock_db_session):
    """Test that an unknown user ID raises ValueError."""
    mock_db_session.get.return_value = None

    with pytest.raises(ValueError, match="User not found"):
        check_auth(999)
    mock_db_session.get.assert_called_once_with(UsersOrm, 999)


def test_redis_rate_limiting_success(mocker):
    """Test that a user within limits can proceed."""
    mocker.patch("services.rate_limiter.hit", return_value=True)

    assert check_quota(user_id=123, daily_limit=10) is True


def test_redis_rate_limiting_minute_throttle(mocker):
    """Test that if a user exceeds the minute limit, it sleeps/throttles."""
    fixed_now = 1_000_000.0
    mocker.patch("services.time.time", return_value=fixed_now)
    mocker.patch(
        "services.rate_limiter.hit",
        side_effect=[True, False, True],  # daily passes, per-minute blocked, retry ok
    )
    mocker.patch(
        "services.rate_limiter.get_window_stats",
        return_value=WindowStats(reset_time=fixed_now + 1.5, remaining=0),
    )
    mock_sleep = mocker.patch("services.time.sleep")

    assert check_quota(user_id=123, daily_limit=10) is True

    mock_sleep.assert_called_once_with(1.5)


def test_redis_rate_limiting_daily_exceeded(mocker):
    """Test that if a user's daily counter is exhausted, it raises LimitExceededError."""
    mocker.patch("services.rate_limiter.hit", return_value=False)

    with pytest.raises(LimitExceededError, match="The daily limit for requests has been exceeded"):
        check_quota(user_id=123, daily_limit=5)
