"""Organization-member onboarding contracts; membership is not scope access."""
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _membership_id() -> str:
    return f"member_{uuid4().hex}"


def _invitation_id() -> str:
    return f"invite_{uuid4().hex}"


class OrganizationMembershipState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class OrganizationMembershipSource(str, Enum):
    INVITATION = "invitation"
    TENANT_IDP = "tenant_idp"
    SCIM = "scim"


class OrganizationRoleReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_id: str = Field(min_length=1)


class OrganizationMembership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    membership_id: str = Field(default_factory=_membership_id, min_length=8)
    user_subject: str = Field(min_length=1)
    organization_id: str = Field(min_length=1)
    source: OrganizationMembershipSource
    role_refs: list[OrganizationRoleReference] = Field(default_factory=list)
    state: OrganizationMembershipState = OrganizationMembershipState.PENDING
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OrganizationInvitation(BaseModel):
    """Protected invite metadata; raw invite secrets are never stored."""

    model_config = ConfigDict(extra="forbid")

    invitation_id: str = Field(default_factory=_invitation_id, min_length=8)
    organization_id: str = Field(min_length=1)
    canonical_email: str = Field(min_length=3)
    token_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    expires_at: datetime
    consumed_at: datetime | None = None


@runtime_checkable
class ActiveOrganizationMembershipLookup(Protocol):
    """Authorization handoff for tenant affiliation, not Resource Scope access."""

    def get_active_membership(
        self, *, user_subject: str, organization_id: str
    ) -> OrganizationMembership | None: ...


class DuplicateActiveOrganizationMembership(ValueError):
    pass


class InMemoryOrganizationMembershipStore:
    """Unit-test double; it grants no Resource Scope or provider access."""

    def __init__(self) -> None:
        self._memberships: dict[str, OrganizationMembership] = {}
        self._active_by_user_organization: dict[tuple[str, str], str] = {}
        self._lock = Lock()

    def save(self, membership: OrganizationMembership) -> None:
        key = (membership.user_subject, membership.organization_id)
        with self._lock:
            if membership.state is OrganizationMembershipState.ACTIVE and key in self._active_by_user_organization:
                raise DuplicateActiveOrganizationMembership("active membership already exists")
            self._memberships[membership.membership_id] = membership
            if membership.state is OrganizationMembershipState.ACTIVE:
                self._active_by_user_organization[key] = membership.membership_id
