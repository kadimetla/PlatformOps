"""Gateway-level data contracts for request intake, session grants,
and the capability ladder. See docs/INTAKE_HITL_ROUTING.md,
docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md,
openspec/changes/build-intake-workflow/design.md, and
openspec/changes/build-login-schemas/design.md for the designs this
implements -- routing/dispatch fields on IntakeDecision exist for
forward compatibility but are not populated by this change's graph.
"""
from datetime import datetime
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


_CAPABILITY_ORDER = (
    "none",
    "describe",
    "plan",
    "propose_change",
    "apply_limited",
    "apply_full",
    "admin",
)


class Capability(str, Enum):
    """The capability ladder, in order. Deliberately NOT
    functools.total_ordering: that decorator's "is this comparison
    already defined" detection gets confused by str's own inherited
    __ge__/__le__/__gt__, silently leaving those lexicographic instead
    of rank-based (verified while implementing this -- apply_limited
    >= plan came back False under total_ordering). All four dunders
    defined explicitly instead. See
    openspec/changes/build-login-schemas/design.md for str-Enum vs.
    IntEnum vs. bare rank-dict reasoning."""

    NONE = "none"
    DESCRIBE = "describe"
    PLAN = "plan"
    PROPOSE_CHANGE = "propose_change"
    APPLY_LIMITED = "apply_limited"
    APPLY_FULL = "apply_full"
    ADMIN = "admin"

    @property
    def _rank(self) -> int:
        return _CAPABILITY_ORDER.index(self.value)

    def __lt__(self, other: "Capability") -> bool:
        if not isinstance(other, Capability):
            return NotImplemented
        return self._rank < other._rank

    def __le__(self, other: "Capability") -> bool:
        if not isinstance(other, Capability):
            return NotImplemented
        return self._rank <= other._rank

    def __gt__(self, other: "Capability") -> bool:
        if not isinstance(other, Capability):
            return NotImplemented
        return self._rank > other._rank

    def __ge__(self, other: "Capability") -> bool:
        if not isinstance(other, Capability):
            return NotImplemented
        return self._rank >= other._rank


class ExecutionGrant(BaseModel):
    """From provider discovery -- authoritative source is the cloud,
    never a second, parallel PlatformOps-native source (see
    ACCESS_POLICY_AND_IAM_DISCOVERY.md's precedence rule)."""

    scope: Scope
    provider: str
    capability: Capability


class ApprovalGrant(BaseModel):
    """From PlatformOps's own approval_groups policy, never from cloud
    IAM -- approving is a governance act, not a provider API
    capability. No provider field: approval authority is
    provider-agnostic by design."""

    scope: Scope
    max_capability: Capability


class Actor(BaseModel):
    """Session identity. execution_grants and approval_grants are two
    independently-sourced sets -- see ACCESS_POLICY_AND_IAM_DISCOVERY.md's
    "Two Grant Sets". resolved_at is what any staleness/TTL policy
    keys off; this change does not implement one."""

    user_id: str
    email: str
    execution_grants: list[ExecutionGrant] = Field(default_factory=list)
    approval_grants: list[ApprovalGrant] = Field(default_factory=list)
    resolved_at: datetime
