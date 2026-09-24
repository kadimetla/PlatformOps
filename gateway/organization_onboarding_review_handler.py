"""Gateway composition for the protected review-resume command."""
import psycopg
from pydantic import BaseModel, ConfigDict, Field

from gateway.command_router import CommandInvocation
from gateway.organization_onboarding import (
    AuthenticatedApplicant, OrganizationOnboardingActivationService,
    OrganizationOnboardingReviewAuthorizer,
)
from gateway.organization_onboarding_postgres import PostgresOrganizationOnboardingRepository
from workflows.organization_onboarding.review_graph import build_organization_onboarding_review_graph


class ReviewOnboardingCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8)


def build_organization_onboarding_review_handler(
    connection: psycopg.Connection, *, authorizer: OrganizationOnboardingReviewAuthorizer
):
    repository = PostgresOrganizationOnboardingRepository(connection)
    graph = build_organization_onboarding_review_graph(
        repository=repository, authorizer=authorizer,
        activation=OrganizationOnboardingActivationService(store=repository),
    ).compile()

    async def handle(invocation: CommandInvocation):
        if invocation.principal is None:
            raise PermissionError("validated reviewer principal is required")
        command = ReviewOnboardingCommand.model_validate(invocation.payload)
        return await graph.ainvoke({
            "request_id": command.request_id,
            "reviewer": AuthenticatedApplicant(
                issuer=invocation.principal.issuer, subject=invocation.principal.subject
            ),
            "request": None, "proof": None, "approval": None, "organization": None,
        })

    return handle
