"""Final deterministic gate before an injected provision executor."""
from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.provision_plan import ProvisionApprovalDigest, SealedProvisionPlan
from gateway.resolved_resource_scope import requires_fresh_resolution
from gateway.resource_scope_access import PrincipalReference, ResourceScopeAction
from gateway.resource_scope_bindings import CloudResourceContainerBinding
from gateway.resource_scope_governance import (
    ResourceScopeGovernanceEvaluator,
    ResourceScopeGovernanceRequest,
)
from gateway.resource_scope_registry import ResourceScope


class ProvisionExecutionStatus(str, Enum):
    SUCCEEDED = "succeeded"


class ProvisionExecutionEvidence(BaseModel):
    """Terminal reference-only evidence; provider output and credentials are excluded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ProvisionExecutionStatus
    plan_digest: str = Field(min_length=64, max_length=64)
    approval_digest: str = Field(min_length=64, max_length=64)
    context_digest: str = Field(min_length=64, max_length=64)
    binding_ids: tuple[str, ...]
    approved_by: PrincipalReference
    recorded_at: datetime


class ProvisionExecutor(Protocol):
    """A separately provisioned worker capability; never a browser or graph input."""

    def execute(self, plan: SealedProvisionPlan) -> None: ...


class ProvisionExecutionDenied(PermissionError):
    pass


class ProvisionApprovalReceiptRepository(Protocol):
    """Trusted persistence boundary; execution never accepts receipt input."""

    def find_active_by_plan_digest(self, *, plan_digest: str) -> ProvisionApprovalDigest | None: ...


class ProvisionExecutionGate:
    """Revalidates approval and registry freshness before any executor call."""

    def __init__(
        self, executor: ProvisionExecutor, *, governance: ResourceScopeGovernanceEvaluator,
        approvals: ProvisionApprovalReceiptRepository,
    ) -> None:
        self._executor = executor
        self._governance = governance
        self._approvals = approvals

    def execute(
        self, *, plan: SealedProvisionPlan,
        scope: ResourceScope | None, bindings: tuple[CloudResourceContainerBinding, ...],
        now: datetime | None = None,
    ) -> ProvisionExecutionEvidence:
        approval = self._approvals.find_active_by_plan_digest(plan_digest=plan.plan_digest)
        if approval is None or not approval.matches(plan):
            raise ProvisionExecutionDenied("approval does not match the sealed provision plan")
        if requires_fresh_resolution(plan.context, scope=scope, bindings=bindings):
            raise ProvisionExecutionDenied("resolved scope context changed; a fresh provision run is required")
        if scope is None:
            raise ProvisionExecutionDenied("resolved scope context is unavailable")
        binding_by_id = {binding.binding_id: binding for binding in bindings}
        if len(plan.context.binding_ids) != 1:
            raise ProvisionExecutionDenied("execution requires exactly one resolved provider binding")
        selected_binding = binding_by_id.get(plan.context.binding_ids[0])
        if selected_binding is None:
            raise ProvisionExecutionDenied("resolved provider binding is unavailable")
        governance = self._governance.evaluate(ResourceScopeGovernanceRequest(
            scope=scope,
            provider=selected_binding.provider.value,
            action=ResourceScopeAction.REQUEST_PROVISION,
            approval_present=True,
        ))
        if not governance.allowed:
            raise ProvisionExecutionDenied(
                "current governance does not permit execution; a fresh provision run is required"
            )
        self._executor.execute(plan)
        return ProvisionExecutionEvidence(
            status=ProvisionExecutionStatus.SUCCEEDED, plan_digest=plan.plan_digest,
            approval_digest=plan.approval_digest, context_digest=plan.context.resolution_digest,
            binding_ids=plan.context.binding_ids, approved_by=approval.approved_by,
            recorded_at=now or datetime.now(timezone.utc),
        )
