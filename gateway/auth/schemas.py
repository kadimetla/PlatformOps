"""Auth/session data contracts -- security-boundary code, deterministic,
no LangGraph. See docs/ACCESS_POLICY_AND_IAM_DISCOVERY.md,
docs/EXECUTION_CREDENTIALS.md's CloudAccessAdapter Protocol, and
openspec/changes/build-login-schemas/design.md for the designs this
implements. Split out of gateway/schemas.py (which keeps the intake-
general/shared models, including Scope) specifically to keep
authentication and grant resolution separate from agent workflow
behavior -- see the gateway/auth/ boundary decision this module is
part of.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from gateway.schemas import Scope

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
