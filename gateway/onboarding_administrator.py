"""Safe browser projections for organization-onboarding administration."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from gateway.organization_onboarding import (
    ActiveOrganization,
    IdentityBoundaryVerificationEvidence,
    OrganizationOnboardingRequest,
)


class OnboardingReviewStatus(str, Enum):
    PENDING = "pending"
    ACTIVATED = "activated"


class PendingOnboardingReviewProjection(BaseModel):
    """Allow-listed data a future wizard may render; no applicant or secret data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=8)
    organization_name: str = Field(min_length=1)
    identity_boundary_kind: str = Field(min_length=1)
    identity_boundary_reference: str = Field(min_length=1)
    identity_proof_recorded: bool
    status: OnboardingReviewStatus = OnboardingReviewStatus.PENDING

    @classmethod
    def from_pending(
        cls, request: OrganizationOnboardingRequest,
        proof: IdentityBoundaryVerificationEvidence | None,
    ) -> "PendingOnboardingReviewProjection":
        return cls(
            request_id=request.request_id, organization_name=request.organization_name,
            identity_boundary_kind=request.identity_boundary.kind.value,
            identity_boundary_reference=request.identity_boundary.reference,
            identity_proof_recorded=(proof is not None),
        )


class OnboardingReviewOutcomeProjection(BaseModel):
    """Allow-listed terminal outcome; no approval digest or identity records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: str = Field(min_length=5)
    organization_name: str = Field(min_length=1)
    status: OnboardingReviewStatus = OnboardingReviewStatus.ACTIVATED

    @classmethod
    def from_active(cls, organization: ActiveOrganization) -> "OnboardingReviewOutcomeProjection":
        return cls(organization_id=organization.organization_id, organization_name=organization.organization_name)
