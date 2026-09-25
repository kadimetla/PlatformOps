"""Checkpointed deterministic HITL approval for an already sealed provision plan."""
from typing import TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, ConfigDict

from gateway.provision_plan import ProvisionApprovalDigest, SealedProvisionPlan
from gateway.resource_scope_access import (
    PrincipalReference, ResourceScopeAction, ResourceScopeAuthorizationRequest, ResourceScopeAuthorizer,
)


class ProvisionApprovalResponse(BaseModel):
    """Untrusted resume body; reviewer identity comes from trusted graph state."""

    model_config = ConfigDict(extra="forbid")

    verdict: str
    plan_digest: str
    approval_digest: str


class ProvisionApprovalState(TypedDict):
    plan: SealedProvisionPlan
    requester: PrincipalReference
    reviewer: PrincipalReference | None
    approved: bool | None


class ProvisionApprovalDenied(PermissionError):
    pass


def build_provision_approval_graph(*, authorizer: ResourceScopeAuthorizer):
    """Pause for review, then deterministically validate an authenticated resume."""
    def review(state: ProvisionApprovalState) -> dict:
        plan = state["plan"]
        response = ProvisionApprovalResponse.model_validate(interrupt({
            "plan_digest": plan.plan_digest,
            "approval_digest": plan.approval_digest,
            "scope_id": plan.context.scope_id,
        }))
        reviewer = state["reviewer"]
        if reviewer is None:
            raise ProvisionApprovalDenied("gateway-authenticated reviewer is required")
        if reviewer == state["requester"]:
            raise ProvisionApprovalDenied("requester cannot approve their own provision plan")
        if response.verdict != "approve":
            return {"approved": False}
        if not ProvisionApprovalDigest(
            plan_digest=response.plan_digest, approval_digest=response.approval_digest,
        ).matches(plan):
            raise ProvisionApprovalDenied("approval does not match the sealed provision plan")
        decision = authorizer.authorize(ResourceScopeAuthorizationRequest(
            principal=reviewer, action=ResourceScopeAction.APPROVE_PROVISION,
            scope_id=plan.context.scope_id,
        ))
        if not decision.allowed:
            raise ProvisionApprovalDenied("reviewer lacks provision approval permission")
        return {"approved": True}

    builder = StateGraph(ProvisionApprovalState)
    builder.add_node("review_plan", review)
    builder.set_entry_point("review_plan")
    builder.add_edge("review_plan", END)
    return builder
