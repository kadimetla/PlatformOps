"""Approval-gate payload and evidence shapes. See
docs/EXECUTION_CREDENTIALS.md's Payload/"Approval records are
persisted independently of graph state" sections for the design this
implements -- the approval gate node itself does not exist yet; this
is only the schema, added because interaction/events.py's HITLEvent
wraps ApprovalRequest and needs a real type to wrap.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import Scope


class ApprovalVerdict(str, Enum):
    """gateway/ must not import interaction/ (see AUTH_BOUNDARY.md), so
    this is a separate, gateway-local enum from interaction/events.py's
    HITLVerdict -- not the same type, deliberately, even though the
    approve/reject/cancel values overlap. ANSWER (clarification-only)
    has no meaning for an approval record and isn't included here."""

    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


class ApprovalRecord(BaseModel):
    """Evidence only -- no credentials, same rule as everywhere else in
    EXECUTION_CREDENTIALS.md."""

    request_id: str
    approver_id: str
    verdict: ApprovalVerdict
    timestamp: datetime
    plan_digest: str
    approval_digest: str
    scope: Scope
    capability_required: Capability


class ApprovalRequest(BaseModel):
    request_id: str
    scope: Scope
    intent: str
    capability_required: Capability
    plan_digest: str
    approval_digest: str
    vibe_diff: str
    requester: ActorRef
    approvals_so_far: list[ApprovalRecord] = Field(default_factory=list)
    required_approvals: int = Field(ge=1)
    approval_expires_at: datetime | None = None
