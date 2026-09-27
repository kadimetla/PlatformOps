from gateway.organization_onboarding import (
    IdentityBoundaryVerificationService,
    OrganizationOnboardingActivationService,
    OrganizationOnboardingService,
    OrganizationOnboardingStore,
)
from workflows.organization_onboarding.state import OrganizationOnboardingState


def build_create_pending(service: OrganizationOnboardingService):
    def create_pending(state: OrganizationOnboardingState) -> dict:
        return {"request": service.start(applicant=state["applicant"], onboarding=state["onboarding"])}

    return create_pending


def build_verify_identity(service: IdentityBoundaryVerificationService):
    def verify_identity(state: OrganizationOnboardingState) -> dict:
        return {"identity_proof": service.verify_pending(state["request"])}

    return verify_identity


def build_persist_identity_proof(store: OrganizationOnboardingStore):
    def persist_identity_proof(state: OrganizationOnboardingState) -> dict:
        proof = state["identity_proof"]
        if proof is not None:
            store.record_identity_proof(state["request"], proof)
        return {}

    return persist_identity_proof


def build_record_approval(service: OrganizationOnboardingActivationService):
    def record_approval(state: OrganizationOnboardingState) -> dict:
        return {"approval": service.approve(state["request"], approver=state["reviewer"])}

    return record_approval


def build_activate(service: OrganizationOnboardingActivationService):
    def activate(state: OrganizationOnboardingState) -> dict:
        return {
            "organization": service.activate(
                state["request"],
                identity_proof=state["identity_proof"],
                approval=state["approval"],
            )
        }

    return activate


def proof_succeeded(state: OrganizationOnboardingState) -> str:
    if state["identity_proof"] is None:
        return "stop"
    return "continue" if state["reviewer"] is not None else "pending_review"
