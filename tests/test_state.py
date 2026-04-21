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
    """Test that a user can make a request within limits."""
    mocker.patch("services.per_day_limit.check", return_value=mocker.MagicMock(limited=False))
    mocker.patch("services.per_minute_limit.check", return_value=mocker.MagicMock(limited=False))

    # Should succeed without sleeping
    assert check_quota() is True


def test_redis_rate_limiting_minute_throttle(mocker):
    """Test that if a user exceeds the minute limit, it sleeps/throttles."""
    mocker.patch("services.per_day_limit.check", return_value=mocker.MagicMock(limited=False))

    # Mock minute limit to return limited=True with a dummy reset time
    mock_rpm = mocker.MagicMock(limited=True)
    mock_rpm.reset_after.total_seconds.return_value = 1.5
    mocker.patch("services.per_minute_limit.check", return_value=mock_rpm)

    mock_sleep = mocker.patch("time.sleep")

    assert check_quota() is True

    mock_sleep.assert_called_once_with(1.5)


def test_redis_rate_limiting_daily_exceeded(mocker):
    """Test that if a user exceeds the daily limit, it raises LimitExceededError."""
    # Mock daily limit to return limited=True
    mock_rpd = mocker.MagicMock(limited=True)
    mocker.patch("services.per_day_limit.check", return_value=mock_rpd)

    with pytest.raises(LimitExceededError, match="The daily limit for requests has been exceeded"):
        check_quota()
