"""How humans see/respond to workflow events -- TUI now, AG-UI/web
later. See docs/INTERACTION_LAYER.md for the design this implements.

Deliberately separate from gateway/ (request/auth/policy boundary) and
workflows/ (what should happen) -- see docs/AUTH_BOUNDARY.md's module
boundary and docs/INTERACTION_LAYER.md's correction moving HITLEvent
out of gateway/events.py into this package. Nothing in gateway/ or
workflows/ may import from here; this module imports from them, never
the other way.

PlatformOpsEvent and HITLEvent are siblings, not nested -- progress/
telemetry fits a generic kind+payload envelope, but a HITL pause needs
real typing (payload: IntakeDecision | ApprovalRequest), so it stays
its own model instead of being squeezed through PlatformOpsEvent's
generic dict payload.
"""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel

from gateway.approval import ApprovalRequest
from gateway.auth.schemas import ActorRef
from gateway.schemas import IntakeDecision


class EventKind(str, Enum):
    """Non-HITL telemetry events -- clarification.required and
    approval.required are HITLEvent's kinds, not these; see
    HITLEventKind below."""

    INTAKE_STARTED = "intake.started"
    ROUTE_RESOLVED = "route.resolved"
    PLAN_STARTED = "plan.started"
    PLAN_SUMMARY = "plan.summary"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_PROGRESS = "execution.progress"
    EXECUTION_COMPLETED = "execution.completed"


class PlatformOpsEvent(BaseModel):
    event_id: str
    request_id: str
    kind: EventKind
    payload: dict
    created_at: datetime


class HITLEventKind(str, Enum):
    CLARIFICATION_REQUIRED = "clarification.required"
    APPROVAL_REQUIRED = "approval.required"


class HITLStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class HITLVerdict(str, Enum):
    ANSWER = "answer"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"


class HITLEvent(BaseModel):
    """Wraps IntakeDecision/ApprovalRequest directly rather than
    redeclaring their fields -- see docs/INTERACTION_LAYER.md's "thin
    layer" rule. clarification_round isn't a field here either; it
    already lives on IntakeRequest and is read off the wrapped
    IntakeDecision. Duplicate-approval/self-approval/digest-match
    checks are not this model's job -- those are enforced in-graph
    (docs/EXECUTION_CREDENTIALS.md); this only surfaces status."""

    event_id: str
    request_id: str
    kind: HITLEventKind
    status: HITLStatus
    actor: ActorRef | None = None
    payload: IntakeDecision | ApprovalRequest
    resume_mode: Literal["reinvoke", "checkpoint_resume"]
    created_at: datetime
    expires_at: datetime | None = None


class HITLResponse(BaseModel):
    event_id: str
    request_id: str
    responder: ActorRef
    verdict: HITLVerdict
    value: str | None = None
    selected_choice: str | None = None
    approval_digest: str | None = None
    responded_at: datetime
