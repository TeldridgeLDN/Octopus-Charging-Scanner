"""Tests for Pushover Notification Client."""

import pytest
import requests
from unittest.mock import Mock, patch
from src.modules.pushover import PushoverClient


class TestPushoverClient:
    """Tests for PushoverClient."""

    def test_init_with_credentials(self):
        """Test initialization with explicit credentials."""
        client = PushoverClient(user_key="user123", api_token="token456")
        assert client.user_key == "user123"
        assert client.api_token == "token456"

    def test_init_from_env(self, monkeypatch):
        """Test initialization from environment variables."""
        monkeypatch.setenv("PUSHOVER_USER_KEY", "env_user")
        monkeypatch.setenv("PUSHOVER_API_TOKEN", "env_token")

        client = PushoverClient()
        assert client.user_key == "env_user"
        assert client.api_token == "env_token"

    def test_init_missing_credentials(self, monkeypatch):
        """Test initialization fails without credentials."""
        monkeypatch.delenv("PUSHOVER_USER_KEY", raising=False)
        monkeypatch.delenv("PUSHOVER_API_TOKEN", raising=False)

        with pytest.raises(ValueError, match="credentials required"):
            PushoverClient()

    def test_send_notification_success(self, mock_pushover_success_response):
        """Test successful notification send."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_pushover_success_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with patch.object(client, "_check_rate_limit", return_value=True):
                with patch.object(client, "_record_notification"):
                    result = client.send_notification(
                        title="Test", message="Test message"
                    )

                    assert result is True
                    mock_post.assert_called_once()

    def test_send_notification_with_priority(self, mock_pushover_success_response):
        """Test notification with custom priority."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_pushover_success_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with patch.object(client, "_check_rate_limit", return_value=True):
                with patch.object(client, "_record_notification"):
                    client.send_notification(
                        title="High Priority", message="Urgent", priority=1
                    )

                    call_data = mock_post.call_args.kwargs["data"]
                    assert call_data["priority"] == 1

    def test_send_notification_with_sound(self, mock_pushover_success_response):
        """Test notification with custom sound."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_pushover_success_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with patch.object(client, "_check_rate_limit", return_value=True):
                with patch.object(client, "_record_notification"):
                    client.send_notification(
                        title="Test", message="Test", sound="cashregister"
                    )

                    call_data = mock_post.call_args.kwargs["data"]
                    assert call_data["sound"] == "cashregister"

    def test_send_notification_message_too_long(self):
        """Test notification fails if message too long."""
        client = PushoverClient(user_key="user", api_token="token")

        with pytest.raises(ValueError, match="exceeds.*character limit"):
            client.send_notification(title="Test", message="x" * 1025)

    def test_send_notification_invalid_priority(self):
        """Test notification fails with invalid priority."""
        client = PushoverClient(user_key="user", api_token="token")

        with pytest.raises(ValueError, match="Priority must be"):
            client.send_notification(title="Test", message="Test", priority=5)

    def test_send_notification_rate_limit_exceeded(self):
        """Test notification blocked by rate limit."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch.object(client, "_check_rate_limit", return_value=False):
            result = client.send_notification(title="Test", message="Test")

            assert result is False

    def test_send_notification_api_error(self, mock_pushover_error_response):
        """Test handling of API error response."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_pushover_error_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with patch.object(client, "_check_rate_limit", return_value=True):
                result = client.send_notification(title="Test", message="Test")

                assert result is False

    def test_send_notification_request_exception(self):
        """Test handling of request exception."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch("requests.post", side_effect=requests.exceptions.RequestException()):
            with patch.object(client, "_check_rate_limit", return_value=True):
                result = client.send_notification(title="Test", message="Test")

                assert result is False

    def test_send_notification_with_attachment(
        self, mock_pushover_success_response, tmp_path
    ):
        """Test notification with image attachment."""
        client = PushoverClient(user_key="user", api_token="token")

        # Create a temporary image file
        image_path = tmp_path / "test.png"
        image_path.write_text("fake image data")

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = mock_pushover_success_response
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            with patch.object(client, "_check_rate_limit", return_value=True):
                with patch.object(client, "_record_notification"):
                    result = client.send_notification(
                        title="Test", message="Test", attachment=str(image_path)
                    )

                    assert result is True
                    assert "files" in mock_post.call_args.kwargs

    def test_send_notification_attachment_not_found(self):
        """Test notification with non-existent attachment."""
        client = PushoverClient(user_key="user", api_token="token")

        with patch.object(client, "_check_rate_limit", return_value=True):
            result = client.send_notification(
                title="Test", message="Test", attachment="/nonexistent/file.png"
            )

            assert result is False

    def test_get_today_notification_count(self, temp_data_dir):
        """Test getting today's notification count."""
        client = PushoverClient(user_key="user", api_token="token")
        client.RATE_LIMIT_FILE = str(temp_data_dir / "rate_limit.json")

        # Initially should be 0
        count = client.get_today_notification_count()
        assert count == 0

    def test_reset_rate_limit(self, temp_data_dir):
        """Test resetting rate limit."""
        client = PushoverClient(user_key="user", api_token="token")
        rate_file = temp_data_dir / "rate_limit.json"
        client.RATE_LIMIT_FILE = str(rate_file)

        # Create rate limit file
        rate_file.write_text('{"2025-12-07": 3}')

        client.reset_rate_limit()

        assert not rate_file.exists()
