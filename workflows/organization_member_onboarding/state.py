from typing import TypedDict

from gateway.organization_membership import OrganizationMembership


class OrganizationMemberOnboardingState(TypedDict):
    """Safe graph state; the raw invitation token never enters this contract."""

    user_subject: str
    invitation_token_digest: str
    organization_id: str | None
    membership: OrganizationMembership | None
