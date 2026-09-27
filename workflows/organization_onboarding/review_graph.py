"""Deterministic reviewer-resume graph for a persisted pending request."""
from typing import TypedDict

from langgraph.graph import END, StateGraph

from gateway.organization_onboarding import (
    ActiveOrganization,
    AuthenticatedApplicant,
    IdentityBoundaryVerificationEvidence,
    OrganizationOnboardingActivationError,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingApproval,
    OrganizationOnboardingReviewAccessDenied,
    OrganizationOnboardingReviewAuthorizer,
    OrganizationOnboardingRequest,
)
from gateway.organization_onboarding_postgres import PostgresOrganizationOnboardingRepository


class ReviewState(TypedDict):
    request_id: str
    reviewer: AuthenticatedApplicant
    request: OrganizationOnboardingRequest | None
    proof: IdentityBoundaryVerificationEvidence | None
    approval: OrganizationOnboardingApproval | None
    organization: ActiveOrganization | None


def build_organization_onboarding_review_graph(
    *, repository: PostgresOrganizationOnboardingRepository,
    authorizer: OrganizationOnboardingReviewAuthorizer,
    activation: OrganizationOnboardingActivationService,
):
    def load(state: ReviewState) -> dict:
        request = repository.get_pending_request(state["request_id"])
        if request is None:
            raise OrganizationOnboardingActivationError("pending onboarding request was not found")
        proof = repository.get_persisted_identity_proof(request)
        if proof is None:
            raise OrganizationOnboardingActivationError("persisted identity proof is required")
        return {"request": request, "proof": proof}

    def authorize(state: ReviewState) -> dict:
        if not authorizer.may_review_onboarding(
            reviewer=state["reviewer"], request_id=state["request_id"]
        ):
            raise OrganizationOnboardingReviewAccessDenied("review permission is required")
        return {}

    def approve(state: ReviewState) -> dict:
        return {"approval": activation.approve(state["request"], approver=state["reviewer"])}

    def activate(state: ReviewState) -> dict:
        return {"organization": activation.activate(
            state["request"], identity_proof=state["proof"], approval=state["approval"]
        )}

    builder = StateGraph(ReviewState)
    builder.add_node("load_pending", load)
    builder.add_node("authorize_reviewer", authorize)
    builder.add_node("record_approval", approve)
    builder.add_node("activate", activate)
    builder.set_entry_point("load_pending")
    builder.add_edge("load_pending", "authorize_reviewer")
    builder.add_edge("authorize_reviewer", "record_approval")
    builder.add_edge("record_approval", "activate")
    builder.add_edge("activate", END)
    return builder
