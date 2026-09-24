"""No-LLM organization-onboarding graph: pending → proof → review → active."""
from langgraph.graph import END, StateGraph

from gateway.organization_onboarding import (
    IdentityBoundaryVerificationService,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingService,
)
from workflows.organization_onboarding.nodes import (
    build_activate,
    build_create_pending,
    build_record_approval,
    build_verify_identity,
    proof_succeeded,
)
from workflows.organization_onboarding.state import OrganizationOnboardingState


def build_organization_onboarding_graph(
    *,
    onboarding: OrganizationOnboardingService,
    verification: IdentityBoundaryVerificationService,
    activation: OrganizationOnboardingActivationService,
):
    builder = StateGraph(OrganizationOnboardingState)
    builder.add_node("create_pending", build_create_pending(onboarding))
    builder.add_node("verify_identity", build_verify_identity(verification))
    builder.add_node("record_approval", build_record_approval(activation))
    builder.add_node("activate", build_activate(activation))
    builder.set_entry_point("create_pending")
    builder.add_edge("create_pending", "verify_identity")
    builder.add_conditional_edges(
        "verify_identity", proof_succeeded,
        {"continue": "record_approval", "pending_review": END, "stop": END},
    )
    builder.add_edge("record_approval", "activate")
    builder.add_edge("activate", END)
    return builder
