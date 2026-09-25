"""Final deterministic gate before an injected provision executor."""
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.provision_plan import ProvisionApprovalDigest, SealedProvisionPlan
from gateway.resolved_resource_scope import requires_fresh_resolution
from gateway.resource_scope_bindings import CloudResourceContainerBinding
from gateway.resource_scope_registry import ResourceScope


class ProvisionExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"
    DENIED = "denied"


class ProvisionExecutionEvidence(BaseModel):
    """Terminal reference-only evidence; provider output and credentials are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProvisionExecutionStatus
    plan_digest: str = Field(min_length=64, max_length=64)
    approval_digest: str = Field(min_length=64, max_length=64)
    context_digest: str = Field(min_length=64, max_length=64)
    binding_ids: tuple[str, ...]
    recorded_at: datetime


class ProvisionExecutor(Protocol):
    """A separately provisioned worker capability; never a browser or graph input."""

    def execute(self, plan: SealedProvisionPlan) -> None: ...


class ProvisionExecutionDenied(PermissionError):
    pass


class ProvisionExecutionGate:
    """Revalidates approval and registry freshness before any executor call."""

    def __init__(self, executor: ProvisionExecutor) -> None:
        self._executor = executor

    def execute(
        self, *, plan: SealedProvisionPlan, approval: ProvisionApprovalDigest,
        scope: ResourceScope | None, bindings: tuple[CloudResourceContainerBinding, ...],
        now: datetime | None = None,
    ) -> ProvisionExecutionEvidence:
        if not approval.matches(plan):
            raise ProvisionExecutionDenied("approval does not match the sealed provision plan")
        if requires_fresh_resolution(plan.context, scope=scope, bindings=bindings):
            raise ProvisionExecutionDenied("resolved scope context changed; a fresh provision run is required")
        self._executor.execute(plan)
        return ProvisionExecutionEvidence(
            status=ProvisionExecutionStatus.SUCCEEDED, plan_digest=plan.plan_digest,
            approval_digest=plan.approval_digest, context_digest=plan.context.resolution_digest,
            binding_ids=plan.context.binding_ids, recorded_at=now or datetime.now(timezone.utc),
        )
