from gateway.organization_onboarding import (
    AuthenticatedApplicant,
    FakeIdentityBoundaryVerifier,
    IdentityBoundaryKind,
    IdentityBoundaryVerificationService,
    InMemoryOrganizationOnboardingStore,
    OrganizationIdentityBoundary,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingService,
    OrganizationOnboardingStart,
    OrganizationState,
)
from workflows.organization_onboarding.graph import build_organization_onboarding_graph


def test_deterministic_graph_activates_only_after_configured_proof_and_review():
    store = InMemoryOrganizationOnboardingStore()
    graph = build_organization_onboarding_graph(
        onboarding=OrganizationOnboardingService(store=store), store=store,
        verification=IdentityBoundaryVerificationService(
            verifier=FakeIdentityBoundaryVerifier({(IdentityBoundaryKind.DOMAIN, "acme.example")})
        ),
        activation=OrganizationOnboardingActivationService(store=store),
    ).compile()

    state = graph.invoke(
        {
            "applicant": AuthenticatedApplicant(issuer="platformops", subject="usr_alice"),
            "reviewer": AuthenticatedApplicant(issuer="platformops", subject="usr_reviewer"),
            "onboarding": OrganizationOnboardingStart(
                organization_name="Acme", identity_boundary=OrganizationIdentityBoundary(
                    kind=IdentityBoundaryKind.DOMAIN, reference="acme.example"
                )
            ),
            "request": None, "identity_proof": None, "approval": None, "organization": None,
        }
    )

    assert state["organization"].state is OrganizationState.ACTIVE
    assert state["organization"].initial_tenant_admin.subject == "usr_alice"
