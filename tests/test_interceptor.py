"""Tests for the Predicate Temporal interceptor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from predicate_temporal.interceptor import (
    PredicateActivityInterceptor,
    PredicateInterceptor,
)


@dataclass
class MockActivityInput:
    """Mock for ExecuteActivityInput."""

    fn: Any
    args: tuple[Any, ...]


def mock_activity_function(x: int, y: str) -> str:
    """Mock activity function for testing."""
    return f"{x}-{y}"


class MockAuthorizationDecision:
    """Mock authorization decision."""

    def __init__(self, allowed: bool, reason: str = "allowed", violated_rule: str | None = None):
        self.allowed = allowed
        self.reason = MagicMock(value=reason)
        self.violated_rule = violated_rule
        self.mandate = MagicMock() if allowed else None


class TestPredicateActivityInterceptor:
    """Tests for PredicateActivityInterceptor."""

    @pytest.fixture
    def mock_authority_client(self) -> MagicMock:
        """Create a mock authority client."""
        return MagicMock()

    @pytest.fixture
    def mock_next_interceptor(self) -> MagicMock:
        """Create a mock next interceptor."""
        interceptor = MagicMock()
        interceptor.execute_activity = AsyncMock(return_value="activity_result")
        return interceptor

    @pytest.fixture
    def interceptor(
        self, mock_next_interceptor: MagicMock, mock_authority_client: MagicMock
    ) -> PredicateActivityInterceptor:
        """Create the interceptor under test."""
        return PredicateActivityInterceptor(
            next_interceptor=mock_next_interceptor,
            authority_client=mock_authority_client,
            principal="test-worker",
            tenant_id="test-tenant",
            session_id="test-session",
        )

    @pytest.mark.asyncio
    async def test_execute_activity_allowed(
        self,
        interceptor: PredicateActivityInterceptor,
        mock_authority_client: MagicMock,
        mock_next_interceptor: MagicMock,
    ) -> None:
        """Test that allowed activities proceed to execution."""
        mock_authority_client.authorize.return_value = MockAuthorizationDecision(allowed=True)

        input_data = MockActivityInput(fn=mock_activity_function, args=(42, "hello"))

        result = await interceptor.execute_activity(input_data)  # type: ignore[arg-type]

        assert result == "activity_result"
        mock_authority_client.authorize.assert_called_once()
        mock_next_interceptor.execute_activity.assert_called_once_with(input_data)

    @pytest.mark.asyncio
    async def test_execute_activity_denied(
        self,
        interceptor: PredicateActivityInterceptor,
        mock_authority_client: MagicMock,
        mock_next_interceptor: MagicMock,
    ) -> None:
        """Test that denied activities raise PermissionError."""
        mock_authority_client.authorize.return_value = MockAuthorizationDecision(
            allowed=False,
            reason="explicit_deny",
            violated_rule="deny-dangerous",
        )

        input_data = MockActivityInput(fn=mock_activity_function, args=(42, "hello"))

        with pytest.raises(PermissionError) as exc_info:
            await interceptor.execute_activity(input_data)  # type: ignore[arg-type]

        assert "Predicate Zero-Trust Denial" in str(exc_info.value)
        assert "mock_activity_function" in str(exc_info.value)
        assert "explicit_deny" in str(exc_info.value)
        assert "deny-dangerous" in str(exc_info.value)

        mock_next_interceptor.execute_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_activity_denied_no_violated_rule(
        self,
        interceptor: PredicateActivityInterceptor,
        mock_authority_client: MagicMock,
    ) -> None:
        """Test denial message without violated rule."""
        mock_authority_client.authorize.return_value = MockAuthorizationDecision(
            allowed=False,
            reason="no_matching_policy",
            violated_rule=None,
        )

        input_data = MockActivityInput(fn=mock_activity_function, args=(42, "hello"))

        with pytest.raises(PermissionError) as exc_info:
            await interceptor.execute_activity(input_data)  # type: ignore[arg-type]

        assert "no_matching_policy" in str(exc_info.value)
        assert "violated rule" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authorization_request_structure(
        self,
        interceptor: PredicateActivityInterceptor,
        mock_authority_client: MagicMock,
        mock_next_interceptor: MagicMock,
    ) -> None:
        """Test that the authorization request has correct structure."""
        mock_authority_client.authorize.return_value = MockAuthorizationDecision(allowed=True)

        input_data = MockActivityInput(fn=mock_activity_function, args=(42, "hello"))

        await interceptor.execute_activity(input_data)  # type: ignore[arg-type]

        call_args = mock_authority_client.authorize.call_args
        request = call_args[0][0]

        assert request.principal.principal_id == "test-worker"
        assert request.principal.tenant_id == "test-tenant"
        assert request.principal.session_id == "test-session"
        assert request.action_spec.action == "mock_activity_function"
        assert request.action_spec.resource == "temporal:activity"
        assert "execute:mock_activity_function" in request.action_spec.intent
        assert request.state_evidence.source == "temporal-worker"
        assert request.state_evidence.state_hash  # Non-empty hash

    def test_serialize_arg_primitive(self) -> None:
        """Test serialization of primitive types."""
        assert PredicateActivityInterceptor._serialize_arg(42) == 42
        assert PredicateActivityInterceptor._serialize_arg("hello") == "hello"
        assert PredicateActivityInterceptor._serialize_arg(True) is True
        assert PredicateActivityInterceptor._serialize_arg(None) is None

    def test_serialize_arg_object(self) -> None:
        """Test serialization of objects with __dict__."""

        @dataclass
        class TestObject:
            name: str
            value: int
            _private: str = "hidden"

        obj = TestObject(name="test", value=123, _private="secret")
        serialized = PredicateActivityInterceptor._serialize_arg(obj)

        assert serialized == {"name": "test", "value": 123}
        assert "_private" not in serialized


class TestPredicateInterceptor:
    """Tests for PredicateInterceptor."""

    @pytest.fixture
    def mock_authority_client(self) -> MagicMock:
        """Create a mock authority client."""
        return MagicMock()

    def test_interceptor_creation(self, mock_authority_client: MagicMock) -> None:
        """Test interceptor creation with all parameters."""
        interceptor = PredicateInterceptor(
            authority_client=mock_authority_client,
            principal="custom-worker",
            tenant_id="tenant-123",
            session_id="session-456",
        )

        assert interceptor._authority_client == mock_authority_client
        assert interceptor._principal == "custom-worker"
        assert interceptor._tenant_id == "tenant-123"
        assert interceptor._session_id == "session-456"

    def test_interceptor_defaults(self, mock_authority_client: MagicMock) -> None:
        """Test interceptor creation with default parameters."""
        interceptor = PredicateInterceptor(authority_client=mock_authority_client)

        assert interceptor._principal == "temporal-worker"
        assert interceptor._tenant_id is None
        assert interceptor._session_id is None

    def test_intercept_activity(self, mock_authority_client: MagicMock) -> None:
        """Test that intercept_activity returns PredicateActivityInterceptor."""
        interceptor = PredicateInterceptor(
            authority_client=mock_authority_client,
            principal="test-worker",
            tenant_id="tenant-123",
        )

        mock_next = MagicMock()
        result = interceptor.intercept_activity(mock_next)

        assert isinstance(result, PredicateActivityInterceptor)
        assert result._authority_client == mock_authority_client
        assert result._principal == "test-worker"
        assert result._tenant_id == "tenant-123"


class TestIntegration:
    """Integration-style tests."""

    @pytest.mark.asyncio
    async def test_full_interceptor_chain(self) -> None:
        """Test the full interceptor chain from top-level to activity execution."""
        mock_client = MagicMock()
        mock_client.authorize.return_value = MockAuthorizationDecision(allowed=True)

        interceptor = PredicateInterceptor(
            authority_client=mock_client,
            principal="integration-worker",
        )

        mock_next = MagicMock()
        mock_next.execute_activity = AsyncMock(return_value="success")

        activity_interceptor = interceptor.intercept_activity(mock_next)

        input_data = MockActivityInput(fn=mock_activity_function, args=("arg1",))
        result = await activity_interceptor.execute_activity(input_data)  # type: ignore[arg-type]

        assert result == "success"
        mock_client.authorize.assert_called_once()
