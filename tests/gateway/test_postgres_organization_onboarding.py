import os
import asyncio

import psycopg
import pytest

from gateway.auth.postgres import PostgresUserRegistrationRepository, apply_user_registration_migrations
from gateway.command_router import ControlPlaneCommandRouter, ValidatedPrincipal
from gateway.organization_onboarding import (
    ActiveOrganization,
    AuthenticatedApplicant,
    FakeIdentityBoundaryVerifier,
    IdentityBoundaryKind,
    IdentityBoundaryVerificationService,
    OrganizationIdentityBoundary,
    OrganizationOnboardingActivationError,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingAlreadyRequested,
    FakeOrganizationOnboardingReviewAuthorizer,
    OrganizationOnboardingReviewAccessDenied,
    OrganizationOnboardingService,
    OrganizationOnboardingStart,
)
from gateway.organization_onboarding_postgres import apply_organization_onboarding_migrations
from gateway.organization_onboarding_postgres import PostgresOrganizationOnboardingRepository
from gateway.organization_onboarding_handler import build_organization_onboarding_handler
from gateway.organization_onboarding_review_handler import build_organization_onboarding_review_handler


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


def test_organization_onboarding_migration_creates_platformops_owned_tables():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)

        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename LIKE 'organization_%'
                   OR tablename = 'organizations'
                """
            ).fetchall()
        }
        assert {
            "organizations",
            "organization_onboarding_requests",
            "organization_identity_proofs",
            "organization_onboarding_approvals",
            "organization_identity_boundaries",
            "organization_initial_tenant_admin_memberships",
        } <= tables
    finally:
        connection.close()


def test_postgres_repository_activates_once_and_resolves_only_active_organization():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        for table in (
            "organization_initial_tenant_admin_memberships", "organization_identity_boundaries",
            "organization_onboarding_approvals", "organization_identity_proofs",
            "organization_onboarding_requests", "organizations",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
        users = PostgresUserRegistrationRepository(connection)
        applicant_account = users.create_or_recover_verified_user("owner@acme.example")
        reviewer_account = users.create_or_recover_verified_user("reviewer@platformops.example")
        repository = PostgresOrganizationOnboardingRepository(connection)
        onboarding = OrganizationOnboardingService(store=repository)
        request = onboarding.start(
            applicant=AuthenticatedApplicant(issuer="platformops", subject=applicant_account.subject),
            onboarding=OrganizationOnboardingStart(
                organization_name="Acme",
                identity_boundary=OrganizationIdentityBoundary(
                    kind=IdentityBoundaryKind.DOMAIN, reference="acme.example"
                ),
            ),
        )
        assert repository.resolve_routable_organization(request.organization_id) is None
        with pytest.raises(OrganizationOnboardingAlreadyRequested, match="already exists"):
            onboarding.start(
                applicant=AuthenticatedApplicant(
                    issuer="platformops", subject=applicant_account.subject
                ),
                onboarding=OrganizationOnboardingStart(
                    organization_name="Acme duplicate",
                    identity_boundary=OrganizationIdentityBoundary(
                        kind=IdentityBoundaryKind.DOMAIN, reference="acme.example"
                    ),
                ),
            )
        proof = IdentityBoundaryVerificationService(
            verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
        ).verify_pending(request)
        lifecycle = OrganizationOnboardingActivationService(store=repository)
        approval = lifecycle.approve(
            request,
            approver=AuthenticatedApplicant(issuer="platformops", subject=reviewer_account.subject),
        )
        assert proof is not None
        mismatched = ActiveOrganization(
            organization_id=request.organization_id,
            organization_name=request.organization_name,
            identity_boundary=request.identity_boundary,
            identity_proof=proof.model_copy(update={"reference": "other.example"}),
            approval=approval,
            initial_tenant_admin=request.applicant,
            activated_at=approval.approved_at,
        )
        with pytest.raises(OrganizationOnboardingActivationError, match="proof or approval"):
            repository.activate(mismatched)
        assert repository.resolve_routable_organization(request.organization_id) is None
        active = lifecycle.activate(request, identity_proof=proof, approval=approval)

        assert repository.resolve_routable_organization(request.organization_id) == active
        with pytest.raises(OrganizationOnboardingActivationError, match="only a pending"):
            lifecycle.activate(request, identity_proof=proof, approval=approval)
    finally:
        connection.close()


def test_gateway_route_starts_postgres_backed_graph_without_payload_principal_or_provider():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        for table in (
            "organization_initial_tenant_admin_memberships", "organization_identity_boundaries",
            "organization_onboarding_approvals", "organization_identity_proofs",
            "organization_onboarding_requests", "organizations",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
        account = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user(
            "route-owner@acme.example"
        )
        handler = build_organization_onboarding_handler(
            connection,
            verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")}),
        )
        router = ControlPlaneCommandRouter({"organization_onboarding": handler})

        state = asyncio.run(router.dispatch(
            "/onboard-org",
            {"organization_name": "Acme", "identity_boundary": {"kind": "domain", "reference": "acme.example"}},
            principal=ValidatedPrincipal(issuer="platformops", subject=account.subject),
        ))

        assert state["request"].applicant.subject == account.subject
        assert state["identity_proof"] is not None
        assert state["organization"] is None
        repository = PostgresOrganizationOnboardingRepository(connection)
        assert repository.get_pending_request(state["request"].request_id) == state["request"]
        assert repository.get_persisted_identity_proof(state["request"]) == state["identity_proof"]
        assert repository.resolve_routable_organization(state["request"].organization_id) is None
    finally:
        connection.close()


def test_authorized_review_resume_activates_once_and_denies_other_reviewers():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        for table in (
            "organization_initial_tenant_admin_memberships", "organization_identity_boundaries",
            "organization_onboarding_approvals", "organization_identity_proofs",
            "organization_onboarding_requests", "organizations",
        ):
            connection.execute(f"DELETE FROM {table}")
        connection.commit()
        users = PostgresUserRegistrationRepository(connection)
        applicant = users.create_or_recover_verified_user("resume-owner@acme.example")
        reviewer = users.create_or_recover_verified_user("resume-reviewer@platformops.example")
        initial = build_organization_onboarding_handler(
            connection, verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
        )
        router = ControlPlaneCommandRouter({"organization_onboarding": initial})
        pending = asyncio.run(router.dispatch(
            "/onboard-org",
            {"organization_name": "Acme", "identity_boundary": {"kind": "domain", "reference": "acme.example"}},
            principal=ValidatedPrincipal(issuer="platformops", subject=applicant.subject),
        ))
        review = build_organization_onboarding_review_handler(
            connection,
            authorizer=FakeOrganizationOnboardingReviewAuthorizer({reviewer.subject}),
        )
        reviewer_router = ControlPlaneCommandRouter({"organization_onboarding_review": review})
        with pytest.raises(OrganizationOnboardingReviewAccessDenied):
            asyncio.run(reviewer_router.dispatch(
                "/review-onboard-org", {"request_id": pending["request"].request_id},
                principal=ValidatedPrincipal(issuer="platformops", subject=applicant.subject),
            ))
        active = asyncio.run(reviewer_router.dispatch(
            "/review-onboard-org", {"request_id": pending["request"].request_id},
            principal=ValidatedPrincipal(issuer="platformops", subject=reviewer.subject),
        ))
        assert active["organization"].state.value == "active"
        with pytest.raises(OrganizationOnboardingActivationError, match="not found"):
            asyncio.run(reviewer_router.dispatch(
                "/review-onboard-org", {"request_id": pending["request"].request_id},
                principal=ValidatedPrincipal(issuer="platformops", subject=reviewer.subject),
            ))
    finally:
        connection.close()
