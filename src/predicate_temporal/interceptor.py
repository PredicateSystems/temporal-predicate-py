"""Predicate Authority interceptor for Temporal.io activities.

This module provides a pre-execution security gate for all Temporal Activities,
enforcing cryptographic authorization mandates before any activity code runs.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from predicate_authority import AuthorityClient
from predicate_contracts import (
    ActionRequest,
    ActionSpec,
    PrincipalRef,
    StateEvidence,
    VerificationEvidence,
)
from temporalio.worker import (
    ActivityInboundInterceptor,
    ExecuteActivityInput,
    Interceptor,
)


class PredicateActivityInterceptor(ActivityInboundInterceptor):
    """Inbound interceptor that enforces Predicate Authority authorization for activities.

    This interceptor sits in the Temporal activity execution pipeline and ensures
    that every activity is authorized before execution. If authorization is denied,
    a PermissionError is raised and the activity never executes.
    """

    def __init__(
        self,
        next_interceptor: ActivityInboundInterceptor,
        authority_client: AuthorityClient,
        principal: str,
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize the activity interceptor.

        Args:
            next_interceptor: The next interceptor in the chain.
            authority_client: The Predicate Authority client for authorization.
            principal: Principal ID used for authorization requests.
            tenant_id: Optional tenant ID for multi-tenant setups.
            session_id: Optional session ID for request correlation.
        """
        super().__init__(next_interceptor)
        self._authority_client = authority_client
        self._principal = principal
        self._tenant_id = tenant_id
        self._session_id = session_id

    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        """Execute activity with Predicate Authority authorization check.

        This method intercepts the activity execution, extracts the activity name
        and arguments, and requests authorization from Predicate Authority.
        If denied, raises PermissionError. If approved, proceeds with execution.

        Args:
            input: The activity execution input containing activity name and args.

        Returns:
            The result of the activity execution.

        Raises:
            PermissionError: If authorization is denied.
        """
        activity_name = input.fn.__name__
        activity_args = input.args

        args_json = json.dumps(
            [self._serialize_arg(arg) for arg in activity_args],
            sort_keys=True,
            default=str,
        )
        args_hash = hashlib.sha256(args_json.encode()).hexdigest()

        request = ActionRequest(
            principal=PrincipalRef(
                principal_id=self._principal,
                tenant_id=self._tenant_id,
                session_id=self._session_id,
            ),
            action_spec=ActionSpec(
                action=activity_name,
                resource="temporal:activity",
                intent=f"execute:{activity_name}",
            ),
            state_evidence=StateEvidence(
                source="temporal-worker",
                state_hash=args_hash,
                schema_version="v1",
            ),
            verification_evidence=VerificationEvidence(signals=()),
        )

        decision = self._authority_client.authorize(request)

        if not decision.allowed:
            raise PermissionError(
                f"Predicate Zero-Trust Denial: Activity '{activity_name}' not authorized. "
                f"Reason: {decision.reason.value}"
                + (f", violated rule: {decision.violated_rule}" if decision.violated_rule else "")
            )

        return await super().execute_activity(input)

    @staticmethod
    def _serialize_arg(arg: Any) -> Any:
        """Serialize an argument for hashing.

        Args:
            arg: The argument to serialize.

        Returns:
            A JSON-serializable representation of the argument.
        """
        if hasattr(arg, "__dict__"):
            return {k: v for k, v in arg.__dict__.items() if not k.startswith("_")}
        return arg


class PredicateInterceptor(Interceptor):
    """Top-level Temporal interceptor that injects Predicate Authority authorization.

    Use this interceptor when creating a Temporal Worker to enforce Zero-Trust
    authorization for all activities.

    Example:
        ```python
        from temporalio.worker import Worker
        from predicate_temporal import PredicateInterceptor
        from predicate_authority import AuthorityClient

        ctx = AuthorityClient.from_env()
        interceptor = PredicateInterceptor(
            authority_client=ctx.client,
            principal="temporal-worker",
        )

        worker = Worker(
            client=temporal_client,
            task_queue="my-task-queue",
            workflows=[MyWorkflow],
            activities=[my_activity],
            interceptors=[interceptor],
        )
        ```
    """

    def __init__(
        self,
        authority_client: AuthorityClient,
        principal: str = "temporal-worker",
        tenant_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize the Predicate interceptor.

        Args:
            authority_client: The Predicate Authority client for authorization.
            principal: Principal ID used for authorization requests (default: "temporal-worker").
            tenant_id: Optional tenant ID for multi-tenant setups.
            session_id: Optional session ID for request correlation.
        """
        self._authority_client = authority_client
        self._principal = principal
        self._tenant_id = tenant_id
        self._session_id = session_id

    def intercept_activity(
        self,
        next_interceptor: ActivityInboundInterceptor,
    ) -> ActivityInboundInterceptor:
        """Inject the Predicate activity interceptor into the pipeline.

        Args:
            next_interceptor: The next interceptor in the chain.

        Returns:
            The PredicateActivityInterceptor wrapping the next interceptor.
        """
        return PredicateActivityInterceptor(
            next_interceptor=next_interceptor,
            authority_client=self._authority_client,
            principal=self._principal,
            tenant_id=self._tenant_id,
            session_id=self._session_id,
        )
