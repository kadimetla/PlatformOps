"""Gateway-level data contracts for request intake. See
docs/INTAKE_HITL_ROUTING.md, openspec/changes/build-intake-workflow/design.md,
and openspec/changes/build-intake-dispatcher/design.md for the design this
implements. Routing/dispatch fields are populated by
workflows/intake/nodes.py's resolve_route for the compliance_check tier
only -- see IntakeDecision's docstring.

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


class TenantRef(BaseModel):
    """Per-run tenant selection. This is deliberately not session state."""

    org: str = Field(min_length=1)
    bu: str = Field(min_length=1)

    @property
    def org_bu(self) -> str:
        return f"{self.org}:{self.bu}"


class ScopeHint(BaseModel):
    """Structured target supplied by a trusted UI/CLI control."""

    tenant: TenantRef
    project: str | None = None
    workspace: str | None = None


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
    """route/ready_to_route are resolved by workflows/intake/nodes.py's
    resolve_route for the compliance_check tier only (the one real
    routable target -- see openspec/changes/build-intake-dispatcher/).
    mutation_requested/approval_required/unsupported_reason are new in
    that change; approval_required stays inert (always False) until a
    real mutating route exists to require approval for."""

    intent: Intent | None = None
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    route: str | None = None
    ready_to_route: bool = False
    mutation_requested: bool = False
    approval_required: bool = False
    unsupported_reason: str | None = None
    evidence: list[str] = Field(default_factory=list)
