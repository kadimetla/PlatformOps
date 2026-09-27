"""Gateway composition for the authenticated `/join-org` command."""
from hashlib import sha256
import hmac

import psycopg
from pydantic import BaseModel, ConfigDict, Field

from gateway.command_router import CommandInvocation
from gateway.organization_membership_postgres import PostgresOrganizationMembershipRepository
from workflows.organization_member_onboarding.graph import build_organization_member_onboarding_graph


class OrganizationInvitationAcceptance(BaseModel):
    """Raw invitation input is accepted only at this gateway boundary."""

    model_config = ConfigDict(extra="forbid")

    invitation_token: str = Field(min_length=32, max_length=2048)


def _invitation_token_digest(token: str, *, hmac_key: bytes) -> str:
    """A high-entropy opaque token is represented downstream only by its digest."""
    return hmac.new(hmac_key, token.encode("utf-8"), "sha256").hexdigest()


def build_organization_member_onboarding_handler(
    connection: psycopg.Connection, *, invitation_hmac_key: bytes,
):
    """Build a trusted handler; payload cannot select the joining principal."""
    repository = PostgresOrganizationMembershipRepository(connection)
    graph = build_organization_member_onboarding_graph(repository=repository).compile()

    async def handle(invocation: CommandInvocation):
        if invocation.principal is None:
            raise PermissionError("validated principal is required")
        acceptance = OrganizationInvitationAcceptance.model_validate(invocation.payload)
        state = await graph.ainvoke(
            {
                "user_subject": invocation.principal.subject,
                "invitation_token_digest": _invitation_token_digest(
                    acceptance.invitation_token, hmac_key=invitation_hmac_key,
                ),
                "legacy_invitation_token_digest": sha256(
                    acceptance.invitation_token.encode("utf-8")
                ).hexdigest(),
                "organization_id": None,
                "membership": None,
            }
        )
        return {"membership": state["membership"]}

    return handle
