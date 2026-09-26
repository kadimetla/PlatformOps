from datetime import datetime, timezone

from gateway.onboarding_administrator import (
    OnboardingReviewOutcomeProjection, PendingOnboardingReviewProjection,
)
from gateway.organization_onboarding import (
    ActiveOrganization, AuthenticatedApplicant, IdentityBoundaryKind,
    IdentityBoundaryVerificationEvidence, OrganizationIdentityBoundary,
    OrganizationOnboardingApproval, OrganizationOnboardingRequest,
)


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
