"""Approval-gate payload and evidence shapes. See
docs/EXECUTION_CREDENTIALS.md's Payload/"Approval records are
persisted independently of graph state" sections for the design this
implements -- the approval gate node itself does not exist yet; this
is only the schema, added because interaction/events.py's HITLEvent
wraps ApprovalRequest and needs a real type to wrap.
"""
from datetime import datetime

from pydantic import BaseModel, Field

from gateway.auth.schemas import ActorRef, Capability
from gateway.schemas import Scope


class ApprovalRecord(BaseModel):
    """Evidence only -- no credentials, same rule as everywhere else in
    EXECUTION_CREDENTIALS.md."""

    request_id: str
    approver_id: str
    verdict: str
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
    required_approvals: int
    approval_expires_at: datetime | None = None
