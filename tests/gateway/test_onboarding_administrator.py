from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gateway.onboarding_administrator import (
    OnboardingAdministratorReadService, OnboardingReviewOutcomeProjection,
    PendingOnboardingReviewProjection,
)
from gateway.organization_onboarding import (
    ActiveOrganization, AuthenticatedApplicant, IdentityBoundaryKind,
    IdentityBoundaryVerificationEvidence, OrganizationIdentityBoundary,
    OrganizationOnboardingApproval, OrganizationOnboardingRequest,
    FakeOrganizationOnboardingReviewAuthorizer, OrganizationOnboardingReviewAccessDenied,
)
from gateway.organization_onboarding_review_handler import ReviewOnboardingCommand


def _request() -> OrganizationOnboardingRequest:
    return OrganizationOnboardingRequest(
        request_id="orgreq_checkout", organization_id="org_acme", organization_name="Acme",
        applicant=AuthenticatedApplicant(issuer="platformops", subject="usr_owner"),
        identity_boundary=OrganizationIdentityBoundary(kind=IdentityBoundaryKind.DOMAIN, reference="acme.example"),
    )


def test_pending_review_projection_is_allow_listed_and_secret_free():
    request = _request()
    projection = PendingOnboardingReviewProjection.from_pending(request, proof=None)

    assert projection.identity_proof_recorded is False
    assert projection.request_id == request.request_id
    assert not {"applicant", "token", "credential", "provider", "binding", "digest"} & set(
        PendingOnboardingReviewProjection.model_fields
    )


def test_review_outcome_projection_excludes_approval_and_identity_evidence():
    request = _request()
    now = datetime.now(timezone.utc)
    proof = IdentityBoundaryVerificationEvidence(
        kind=IdentityBoundaryKind.DOMAIN, reference="acme.example", evidence_ref="proof:acme", verified_at=now,
    )
    organization = ActiveOrganization(
        organization_id="org_acme", organization_name="Acme", identity_boundary=request.identity_boundary,
        identity_proof=proof,
        approval=OrganizationOnboardingApproval(
            request_id=request.request_id, onboarding_digest="a" * 64,
            approved_by=AuthenticatedApplicant(issuer="platformops", subject="usr_reviewer"), approved_at=now,
        ),
        initial_tenant_admin=request.applicant, activated_at=now,
    )

    assert OnboardingReviewOutcomeProjection.from_active(organization).organization_id == "org_acme"
    assert not {"approval", "identity_proof", "credential", "provider"} & set(
        OnboardingReviewOutcomeProjection.model_fields
    )


class PendingRepository:
    def __init__(self, request):
        self.request = request

    def get_pending_request(self, request_id):
        return self.request if request_id == self.request.request_id else None

    def get_persisted_identity_proof(self, request):
        return None


def test_read_service_rechecks_reviewer_and_fails_closed_for_stale_or_unauthorized_request():
    request = _request()
    reviewer = AuthenticatedApplicant(issuer="platformops", subject="usr_reviewer")
    service = OnboardingAdministratorReadService(
        repository=PendingRepository(request),
        authorizer=FakeOrganizationOnboardingReviewAuthorizer({reviewer.subject}),
    )

    assert service.get_pending_review(reviewer=reviewer, request_id=request.request_id).request_id == request.request_id
    with pytest.raises(OrganizationOnboardingReviewAccessDenied):
        service.get_pending_review(
            reviewer=AuthenticatedApplicant(issuer="platformops", subject="usr_other"), request_id=request.request_id,
        )
    with pytest.raises(ValueError, match="not found"):
        service.get_pending_review(reviewer=reviewer, request_id="orgreq_missing")


def test_wizard_commands_reject_provider_credential_and_browser_derived_authority_fields():
    from gateway.onboarding_administrator import OnboardingAdministratorReadCommand

    forbidden = {
        "provider": "aws", "account_id": "123456789012", "binding_id": "binding_prod",
        "credential": "secret", "approval_digest": "a" * 64,
    }
    for field, value in forbidden.items():
        payload = {"request_id": "orgreq_checkout", field: value}
        with pytest.raises(ValidationError, match="Extra inputs"):
            OnboardingAdministratorReadCommand.model_validate(payload)
        with pytest.raises(ValidationError, match="Extra inputs"):
            ReviewOnboardingCommand.model_validate(payload)
