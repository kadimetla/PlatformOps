"""Safe browser projections for organization-onboarding administration."""
from enum import Enum

import psycopg
from pydantic import BaseModel, ConfigDict, Field

from gateway.command_router import CommandInvocation
from gateway.organization_onboarding import (
    AuthenticatedApplicant,
    ActiveOrganization,
    IdentityBoundaryVerificationEvidence,
    OrganizationOnboardingRequest,
    OrganizationOnboardingReviewAccessDenied,
    OrganizationOnboardingReviewAuthorizer,
)
from gateway.organization_onboarding_postgres import PostgresOrganizationOnboardingRepository


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


class OnboardingAdministratorReadService:
    """Reloads pending state after an explicit reviewer authorization check."""

    def __init__(self, *, repository, authorizer: OrganizationOnboardingReviewAuthorizer) -> None:
        self._repository = repository
        self._authorizer = authorizer

    def get_pending_review(
        self, *, reviewer: AuthenticatedApplicant, request_id: str,
    ) -> PendingOnboardingReviewProjection:
        if not self._authorizer.may_review_onboarding(reviewer=reviewer, request_id=request_id):
            raise OrganizationOnboardingReviewAccessDenied("review permission is required")
        request = self._repository.get_pending_request(request_id)
        if request is None:
            raise ValueError("pending onboarding request was not found")
        return PendingOnboardingReviewProjection.from_pending(
            request, self._repository.get_persisted_identity_proof(request),
        )


class OnboardingAdministratorReadCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=8)


def build_onboarding_administrator_read_handler(
    connection: psycopg.Connection, *, authorizer: OrganizationOnboardingReviewAuthorizer,
):
    service = OnboardingAdministratorReadService(
        repository=PostgresOrganizationOnboardingRepository(connection), authorizer=authorizer,
    )

    async def handle(invocation: CommandInvocation) -> PendingOnboardingReviewProjection:
        if invocation.principal is None:
            raise PermissionError("validated reviewer principal is required")
        command = OnboardingAdministratorReadCommand.model_validate(invocation.payload)
        return service.get_pending_review(
            reviewer=AuthenticatedApplicant(
                issuer=invocation.principal.issuer, subject=invocation.principal.subject,
            ),
            request_id=command.request_id,
        )

    return handle
