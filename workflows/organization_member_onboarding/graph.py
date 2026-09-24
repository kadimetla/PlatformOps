"""No-LLM invitation validation → membership activation graph."""
from langgraph.graph import END, StateGraph

from gateway.organization_membership_postgres import PostgresOrganizationMembershipRepository
from workflows.organization_member_onboarding.state import OrganizationMemberOnboardingState


def build_organization_member_onboarding_graph(
    *, repository: PostgresOrganizationMembershipRepository,
):
    def validate_invitation(state: OrganizationMemberOnboardingState) -> dict:
        return {
            "organization_id": repository.inspect_invitation(
                token_digest=state["invitation_token_digest"], user_subject=state["user_subject"]
            )
        }

    def activate_membership(state: OrganizationMemberOnboardingState) -> dict:
        return {
            "membership": repository.accept_invitation(
                token_digest=state["invitation_token_digest"], user_subject=state["user_subject"]
            )
        }

    builder = StateGraph(OrganizationMemberOnboardingState)
    builder.add_node("validate_invitation", validate_invitation)
    builder.add_node("activate_membership", activate_membership)
    builder.set_entry_point("validate_invitation")
    builder.add_edge("validate_invitation", "activate_membership")
    builder.add_edge("activate_membership", END)
    return builder
