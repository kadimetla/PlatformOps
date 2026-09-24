"""Gateway composition for the explicit `/onboard-org` command."""
import psycopg

from gateway.command_router import CommandInvocation
from gateway.organization_onboarding import (
    AuthenticatedApplicant,
    IdentityBoundaryVerificationService,
    IdentityBoundaryVerifier,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingService,
    OrganizationOnboardingStart,
)
from gateway.organization_onboarding_postgres import PostgresOrganizationOnboardingRepository
from workflows.organization_onboarding.graph import build_organization_onboarding_graph


def build_organization_onboarding_handler(
    connection: psycopg.Connection, *, verifier: IdentityBoundaryVerifier
):
    """Build one trusted handler; payload cannot choose applicant or reviewer."""
    repository = PostgresOrganizationOnboardingRepository(connection)
    onboarding = OrganizationOnboardingService(store=repository)
    activation = OrganizationOnboardingActivationService(store=repository)
    verification = IdentityBoundaryVerificationService(verifier=verifier)
    graph = build_organization_onboarding_graph(
        onboarding=onboarding, verification=verification, activation=activation
    ).compile()

    async def handle(invocation: CommandInvocation):
        if invocation.principal is None:
            raise PermissionError("validated principal is required")
        state = await graph.ainvoke(
            {
                "applicant": AuthenticatedApplicant(
                    issuer=invocation.principal.issuer, subject=invocation.principal.subject
                ),
                "onboarding": OrganizationOnboardingStart.model_validate(invocation.payload),
                "reviewer": None,
                "request": None,
                "identity_proof": None,
                "approval": None,
                "organization": None,
            }
        )
        return state

    return handle
