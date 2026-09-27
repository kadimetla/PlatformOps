from typing import TypedDict

from gateway.organization_onboarding import (
    ActiveOrganization,
    AuthenticatedApplicant,
    IdentityBoundaryVerificationEvidence,
    OrganizationOnboardingApproval,
    OrganizationOnboardingRequest,
    OrganizationOnboardingStart,
)


class OrganizationOnboardingState(TypedDict):
    applicant: AuthenticatedApplicant
    onboarding: OrganizationOnboardingStart
    reviewer: AuthenticatedApplicant | None
    request: OrganizationOnboardingRequest | None
    identity_proof: IdentityBoundaryVerificationEvidence | None
    approval: OrganizationOnboardingApproval | None
    organization: ActiveOrganization | None
