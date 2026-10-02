import json
from datetime import datetime, timezone

from gateway.onboarding_administrator import PendingOnboardingReviewProjection
from gateway.organization_onboarding import (
    ActiveOrganization, AuthenticatedApplicant, IdentityBoundaryKind,
    IdentityBoundaryVerificationEvidence, OrganizationIdentityBoundary,
    OrganizationOnboardingApproval, OrganizationOnboardingRequest,
)
from interaction.a2ui import command_result_to_a2ui_messages, onboarding_review_to_a2ui_messages

_NOW = datetime.now(timezone.utc)
_BOUNDARY = OrganizationIdentityBoundary(kind=IdentityBoundaryKind.DOMAIN, reference="acme.example")
_APPLICANT = AuthenticatedApplicant(issuer="platformops", subject="usr_applicant_secret")
_REVIEWER = AuthenticatedApplicant(issuer="platformops", subject="usr_reviewer_secret")


def _request():
    return OrganizationOnboardingRequest(
        request_id="orgreq_checkout", organization_id="org_acme", organization_name="Acme",
        applicant=_APPLICANT, identity_boundary=_BOUNDARY,
    )


def _proof():
    return IdentityBoundaryVerificationEvidence(
        kind=IdentityBoundaryKind.DOMAIN, reference="acme.example",
        evidence_ref="proof:evidence-secret", verified_at=_NOW,
    )


def _organization():
    return ActiveOrganization(
        organization_id="org_acme", organization_name="Acme", identity_boundary=_BOUNDARY,
        identity_proof=_proof(),
        approval=OrganizationOnboardingApproval(
            request_id="orgreq_checkout", onboarding_digest="a" * 64,
            approved_by=_REVIEWER, approved_at=_NOW,
        ),
        initial_tenant_admin=_APPLICANT, activated_at=_NOW,
    )


def _components(messages):
    return messages[1]["updateComponents"]["components"]


def _buttons(messages):
    return [c for c in _components(messages) if c["component"] == "Button"]


def test_pending_review_with_proof_renders_detail_and_one_approve_action():
    projection = PendingOnboardingReviewProjection.from_pending(_request(), _proof())

    messages = onboarding_review_to_a2ui_messages("surf-1", projection)

    text = json.dumps(messages)
    assert "organization_name: Acme" in text
    assert "identity_boundary: domain acme.example" in text
    assert "identity_proof_recorded: True" in text
    (button,) = _buttons(messages)
    assert button["action"]["event"] == {
        "name": "/review-onboard-org", "context": {"request_id": "orgreq_checkout"},
    }


def test_pending_review_without_identity_proof_offers_no_approve_action():
    projection = PendingOnboardingReviewProjection.from_pending(_request(), None)

    assert _buttons(onboarding_review_to_a2ui_messages("surf-2", projection)) == []


def test_review_surfaces_never_render_identities_evidence_or_digest():
    pending = command_result_to_a2ui_messages(
        "s", "/onboarding-review", PendingOnboardingReviewProjection.from_pending(_request(), _proof())
    )
    activated = command_result_to_a2ui_messages(
        "s", "/review-onboard-org", {"organization": _organization(), "approval": object()}
    )

    for secret in ("usr_applicant_secret", "usr_reviewer_secret", "evidence-secret", "a" * 64):
        assert secret not in json.dumps(pending)
        assert secret not in json.dumps(activated)
    assert "Organization activated" in json.dumps(activated)
    assert "organization_id: org_acme" in json.dumps(activated)
    assert _buttons(activated) == []


def test_unrecognized_review_result_falls_back_to_generic_outcome():
    messages = command_result_to_a2ui_messages("s", "/review-onboard-org", {"organization": None})

    assert "status: completed" in json.dumps(messages)
