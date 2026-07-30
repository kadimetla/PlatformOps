"""Gateway-level data contracts for request intake. See
docs/INTAKE_HITL_ROUTING.md and
openspec/changes/build-intake-workflow/design.md for the design this
implements -- routing/dispatch fields exist here for forward
compatibility but are not populated by this change's graph.

Scope lives here rather than in gateway/auth/ because it's shared by
both intake (project/workspace targeting) and auth (grant scoping) --
auth-specific models (Capability, ExecutionGrant, ApprovalGrant,
Actor) live in gateway/auth/schemas.py, kept separate as
security-boundary code, not agent workflow behavior.
"""
from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """Exactly these three -- audit/security_review are deliberately
    absent until a real workflow exists for them (no reserved,
    unreachable values; see design.md's C4)."""

    PROVISION = "provision"
    INQUIRY = "inquiry"
    COMPLIANCE_CHECK = "compliance_check"


class Scope(BaseModel):
    """Identifies org/bu/project/workspace. Does not itself assert
    that the org/bu is real or that a requester has access to it --
    that's a dispatcher's job, not this schema's."""

    org: str
    bu: str = "root"
    project: str | None = None
    workspace: str | None = None

    @property
    def org_bu(self) -> str:
        return f"{self.org}:{self.bu}"


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    choices: list[str] = Field(default_factory=list)


class IntakeRequest(BaseModel):
    """No identity field here on purpose -- org/bu come from an
    authenticated session in later changes, never parsed from
    raw_text."""

    raw_text: str
    clarification_round: int = 0


class IntakeDecision(BaseModel):
    """route/ready_to_route are inert in this change -- always None
    and False, regardless of intent. They exist now so the dispatcher
    change can extend this model instead of breaking it."""

    intent: Intent | None = None
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    route: str | None = None
    ready_to_route: bool = False
    evidence: list[str] = Field(default_factory=list)
