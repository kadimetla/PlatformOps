from gateway.organization_membership import (
    OrganizationMembership,
    OrganizationMembershipSource,
    OrganizationMembershipState,
)
from workflows.organization_member_onboarding.graph import build_organization_member_onboarding_graph


class RecordingMembershipRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def inspect_invitation(self, *, token_digest: str, user_subject: str) -> str:
        self.calls.append(("inspect", token_digest, user_subject))
        return "org_acme"

    def accept_invitation(self, *, token_digest: str, user_subject: str) -> OrganizationMembership:
        self.calls.append(("accept", token_digest, user_subject))
        return OrganizationMembership(
            membership_id="member_alice_acme",
            user_subject=user_subject,
            organization_id="org_acme",
            source=OrganizationMembershipSource.INVITATION,
            state=OrganizationMembershipState.ACTIVE,
        )


def test_graph_uses_only_a_digest_and_activates_membership_after_validation():
    repository = RecordingMembershipRepository()
    graph = build_organization_member_onboarding_graph(repository=repository).compile()
    raw_token = "raw-invitation-token-that-must-not-enter-graph-state"
    digest = "f" * 64

    state = graph.invoke(
        {
            "user_subject": "usr_alice",
            "invitation_token_digest": digest,
            "organization_id": None,
            "membership": None,
        }
    )

    assert repository.calls == [
        ("inspect", digest, "usr_alice"),
        ("accept", digest, "usr_alice"),
    ]
    assert state["membership"].organization_id == "org_acme"
    assert raw_token not in str(state)
