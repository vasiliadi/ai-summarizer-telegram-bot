import pytest

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
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_cls.return_value.check.return_value = mocker.MagicMock(limited=False)
    mocker.patch("services.per_minute_limit.check", return_value=mocker.MagicMock(limited=False))

    assert check_quota(user_id=123, daily_limit=10) is True


def test_redis_rate_limiting_minute_throttle(mocker):
    """Test that if a user exceeds the minute limit, it sleeps/throttles."""
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_cls.return_value.check.return_value = mocker.MagicMock(limited=False)

    mock_rpm = mocker.MagicMock(limited=True)
    mock_rpm.reset_after.total_seconds.return_value = 1.5
    mocker.patch("services.per_minute_limit.check", return_value=mock_rpm)

    mock_sleep = mocker.patch("services.time.sleep")

    assert check_quota(user_id=123, daily_limit=10) is True

    mock_sleep.assert_called_once_with(1.5)


def test_redis_rate_limiting_daily_exceeded(mocker):
    """Test that if a user's daily counter is exhausted, it raises LimitExceededError."""
    mock_throttle_cls = mocker.patch("services.throttle.Throttle")
    mock_throttle_cls.return_value.check.return_value = mocker.MagicMock(limited=True)

    with pytest.raises(LimitExceededError, match="The daily limit for requests has been exceeded"):
        check_quota(user_id=123, daily_limit=5)
