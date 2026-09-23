from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gateway.organization_onboarding import (
    AuthenticatedApplicant,
    FakeIdentityBoundaryVerifier,
    IdentityBoundaryKind,
    IdentityBoundaryVerificationService,
    InMemoryOrganizationOnboardingStore,
    OrganizationIdentityBoundary,
    OrganizationOnboardingAlreadyRequested,
    OrganizationOnboardingActivationError,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingService,
    OrganizationOnboardingStart,
    OrganizationState,
    onboarding_digest,
)


def _applicant() -> AuthenticatedApplicant:
    return AuthenticatedApplicant(
        issuer="https://idp.acme.example",
        subject="oidc-subject-123",
    )


def _start() -> OrganizationOnboardingStart:
    return OrganizationOnboardingStart(
        organization_name="Acme Incorporated",
        identity_boundary=OrganizationIdentityBoundary(
            kind=IdentityBoundaryKind.DOMAIN,
            reference="Acme.Example",
        ),
    )


def test_authenticated_applicant_creates_only_a_pending_request():
    store = InMemoryOrganizationOnboardingStore()
    service = OrganizationOnboardingService(store=store)
    created_at = datetime(2026, 9, 23, tzinfo=timezone.utc)

    request = service.start(applicant=_applicant(), onboarding=_start(), now=created_at)

    assert request.state is OrganizationState.PENDING
    assert request.organization_id.startswith("org_")
    assert request.applicant.issuer == "https://idp.acme.example"
    assert request.applicant.subject == "oidc-subject-123"
    assert request.identity_boundary.reference == "acme.example"
    assert request.created_at == created_at
    assert store.get(request.request_id) == request
    assert "tenant_admin" not in request.model_fields_set
    assert "provider" not in request.model_fields_set


def test_entry_contract_rejects_free_text_and_provider_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OrganizationOnboardingStart.model_validate(
            {
                "organization_name": "Acme Incorporated",
                "identity_boundary": {"kind": "domain", "reference": "acme.example"},
                "raw_text": "please create my AWS organization",
            }
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OrganizationIdentityBoundary.model_validate(
            {
                "kind": "domain",
                "reference": "acme.example",
                "provider": "aws",
            }
        )


def test_duplicate_organization_identity_request_is_rejected():
    service = OrganizationOnboardingService(store=InMemoryOrganizationOnboardingStore())

    service.start(applicant=_applicant(), onboarding=_start())

    with pytest.raises(OrganizationOnboardingAlreadyRequested, match="already exists"):
        service.start(applicant=_applicant(), onboarding=_start())


def test_boundary_requires_a_structured_non_email_reference():
    with pytest.raises(ValidationError, match="whitespace-free"):
        OrganizationIdentityBoundary(
            kind=IdentityBoundaryKind.DOMAIN,
            reference="acme example",
        )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AuthenticatedApplicant.model_validate(
            {"issuer": "platformops", "subject": "usr_123", "email": "owner@acme.example"}
        )


def test_scripted_identity_verifier_returns_evidence_only_for_configured_boundary():
    onboarding = OrganizationOnboardingService(store=InMemoryOrganizationOnboardingStore())
    request = onboarding.start(applicant=_applicant(), onboarding=_start())
    verifier = FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
    verification = IdentityBoundaryVerificationService(verifier=verifier)
    checked_at = datetime(2026, 9, 23, tzinfo=timezone.utc)

    evidence = verification.verify_pending(request, now=checked_at)

    assert evidence is not None
    assert evidence.reference == "acme.example"
    assert evidence.evidence_ref == "fake-identity-proof:domain:acme.example"
    assert evidence.verified_at == checked_at
    assert request.state is OrganizationState.PENDING
    assert verifier.calls == [request.request_id]


def test_identity_verification_fails_closed_for_unconfigured_boundary_or_non_pending_request():
    onboarding = OrganizationOnboardingService(store=InMemoryOrganizationOnboardingStore())
    request = onboarding.start(applicant=_applicant(), onboarding=_start())
    verifier = FakeIdentityBoundaryVerifier(set())
    verification = IdentityBoundaryVerificationService(verifier=verifier)

    assert verification.verify_pending(request) is None
    assert verifier.calls == [request.request_id]

    active = request.model_copy(update={"state": OrganizationState.ACTIVE})
    assert verification.verify_pending(active) is None
    assert verifier.calls == [request.request_id]


def test_matching_proof_and_recorded_approval_activate_with_initial_tenant_admin():
    store = InMemoryOrganizationOnboardingStore()
    onboarding = OrganizationOnboardingService(store=store)
    request = onboarding.start(applicant=_applicant(), onboarding=_start())
    verification = IdentityBoundaryVerificationService(
        verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
    )
    proof = verification.verify_pending(request)
    lifecycle = OrganizationOnboardingActivationService(store=store)
    approval = lifecycle.approve(
        request,
        approver=AuthenticatedApplicant(
            issuer="https://platformops.review.example", subject="reviewer-456"
        ),
    )

    active = lifecycle.activate(request, identity_proof=proof, approval=approval)

    assert active.state is OrganizationState.ACTIVE
    assert active.initial_tenant_admin == request.applicant
    assert active.approval.onboarding_digest == onboarding_digest(request)
    assert not hasattr(active, "provider_connection")
    assert store.resolve_routable_organization(request.organization_id) == active


def test_activation_rejects_missing_or_mismatched_proof_or_approval():
    store = InMemoryOrganizationOnboardingStore()
    onboarding = OrganizationOnboardingService(store=store)
    request = onboarding.start(applicant=_applicant(), onboarding=_start())
    lifecycle = OrganizationOnboardingActivationService(store=store)
    approval = lifecycle.approve(request, approver=_applicant())

    with pytest.raises(OrganizationOnboardingActivationError, match="verification is required"):
        lifecycle.activate(request, identity_proof=None, approval=approval)

    bad_proof = IdentityBoundaryVerificationService(
        verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
    ).verify_pending(request)
    assert bad_proof is not None
    bad_proof = bad_proof.model_copy(update={"reference": "other.example"})
    with pytest.raises(OrganizationOnboardingActivationError, match="does not match"):
        lifecycle.activate(request, identity_proof=bad_proof, approval=approval)

    bad_approval = approval.model_copy(update={"onboarding_digest": "0" * 64})
    with pytest.raises(OrganizationOnboardingActivationError, match="approval does not match"):
        lifecycle.activate(request, identity_proof=bad_proof.model_copy(update={"reference": "acme.example"}), approval=bad_approval)

    assert store.resolve_routable_organization(request.organization_id) is None


def test_pending_organization_is_not_routable_until_activation():
    store = InMemoryOrganizationOnboardingStore()
    request = OrganizationOnboardingService(store=store).start(
        applicant=_applicant(), onboarding=_start()
    )

    assert store.resolve_routable_organization(request.organization_id) is None
    assert store.resolve_routable_organization("org_unknown") is None
