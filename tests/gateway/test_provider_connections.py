import pytest
from pydantic import ValidationError

from gateway.provider_connections import (
    CloudProvider,
    ContainerAttachmentState,
    FakeProviderAdapter,
    ProviderAdapterRegistry,
    ProviderContainerAttachmentService,
    ProviderConnectionAccessDenied,
    ProviderContainerCandidate,
    ProviderContainerInquiryService,
    ProviderConnection,
    ProviderConnectionState,
    ProviderConnectionUnavailable,
)


class FakeInquiryAuthorizer:
    def __init__(self, allowed_actor_ids: set[str]) -> None:
        self._allowed_actor_ids = allowed_actor_ids
        self.calls: list[tuple[str, str]] = []

    def may_inquire_provider_inventory(self, *, actor_id: str, organization_id: str) -> bool:
        self.calls.append((actor_id, organization_id))
        return actor_id in self._allowed_actor_ids


class FakeAttachmentAuthorizer:
    def __init__(self, requesters: set[str], reviewers: set[str]) -> None:
        self._requesters = requesters
        self._reviewers = reviewers

    def may_request_container_attachment(
        self, *, actor_id: str, organization_id: str, resource_scope_id: str
    ) -> bool:
        return actor_id in self._requesters

    def may_review_container_attachment(
        self, *, actor_id: str, organization_id: str, resource_scope_id: str
    ) -> bool:
        return actor_id in self._reviewers


def _connection(*, state: ProviderConnectionState = ProviderConnectionState.ACTIVE) -> ProviderConnection:
    return ProviderConnection(
        organization_id="org_acme",
        provider=CloudProvider.AWS,
        boundary_ref="aws-org:o-acme",
        discovery_identity_ref="secret://platformops/acme/aws-discovery",
        state=state,
    )


@pytest.mark.parametrize(
    "state",
    [
        ProviderConnectionState.PENDING,
        ProviderConnectionState.VERIFIED,
        ProviderConnectionState.SUSPENDED,
    ],
)
def test_non_active_connection_cannot_select_an_adapter(state):
    registry = ProviderAdapterRegistry([
        FakeProviderAdapter(CloudProvider.AWS, {"aws-org:o-acme"})
    ])

    with pytest.raises(ProviderConnectionUnavailable, match="not active"):
        registry.for_connection(_connection(state=state))


def test_connection_contract_rejects_credential_material():
    with pytest.raises(ValidationError):
        ProviderConnection(
            organization_id="org_acme",
            provider=CloudProvider.AWS,
            boundary_ref="aws-org:o-acme",
            discovery_identity_ref="secret://platformops/acme/aws-discovery",
            credentials={"access_key": "AKIA...", "secret": "not-stored"},
        )


def test_registry_selects_adapter_only_from_active_connection_provider():
    aws = FakeProviderAdapter(CloudProvider.AWS, {"aws-org:o-acme"})
    registry = ProviderAdapterRegistry([aws])

    selected = registry.for_connection(_connection())

    assert selected is aws
    assert selected.verify_boundary(_connection()) is True


def test_fake_adapter_requires_matching_provider_connection():
    adapter = FakeProviderAdapter(CloudProvider.AWS, {"aws-org:o-acme"})
    connection = _connection().model_copy(update={"provider": CloudProvider.GCP})

    with pytest.raises(ValueError, match="does not match"):
        adapter.verify_boundary(connection)


def test_fake_adapter_inquiry_returns_only_connection_boundary_candidates():
    adapter = FakeProviderAdapter(
        CloudProvider.AWS,
        {"aws-org:o-acme"},
        candidates=[
            ProviderContainerCandidate(
                provider=CloudProvider.AWS,
                boundary_ref="aws-org:o-acme",
                container_ref="account:123456789012",
                display_name="acme-production",
            ),
            ProviderContainerCandidate(
                provider=CloudProvider.AWS,
                boundary_ref="aws-org:o-other",
                container_ref="account:210987654321",
                display_name="other-production",
            ),
        ],
    )

    candidates = adapter.list_container_candidates(_connection())

    assert [candidate.container_ref for candidate in candidates] == ["account:123456789012"]


def test_inquiry_requires_an_organization_administrator_and_active_connection():
    adapter = FakeProviderAdapter(CloudProvider.AWS, {"aws-org:o-acme"})
    service = ProviderContainerInquiryService(
        adapters=ProviderAdapterRegistry([adapter]),
        authorizer=FakeInquiryAuthorizer(set()),
    )

    with pytest.raises(ProviderConnectionAccessDenied, match="administrator"):
        service.inquire(actor_id="usr_alice", connection=_connection())

    assert adapter.inquiry_calls == []


def test_inquiry_returns_only_candidates_within_the_connection_boundary():
    adapter = FakeProviderAdapter(
        CloudProvider.AWS,
        {"aws-org:o-acme"},
        candidates=[
            ProviderContainerCandidate(
                provider=CloudProvider.AWS,
                boundary_ref="aws-org:o-acme",
                container_ref="account:123456789012",
                display_name="acme-production",
            ),
            ProviderContainerCandidate(
                provider=CloudProvider.GCP,
                boundary_ref="aws-org:o-acme",
                container_ref="project:should-not-leak",
                display_name="wrong-provider",
            ),
        ],
    )
    service = ProviderContainerInquiryService(
        adapters=ProviderAdapterRegistry([adapter]),
        authorizer=FakeInquiryAuthorizer({"usr_alice"}),
    )

    candidates = service.inquire(actor_id="usr_alice", connection=_connection())

    assert [candidate.container_ref for candidate in candidates] == ["account:123456789012"]
    assert adapter.inquiry_calls


def test_candidate_contract_rejects_credential_material():
    with pytest.raises(ValidationError):
        ProviderContainerCandidate(
            provider=CloudProvider.AWS,
            boundary_ref="aws-org:o-acme",
            container_ref="account:123456789012",
            display_name="acme-production",
            access_token="not-stored",
        )


def test_attachment_requires_review_before_creating_an_active_binding():
    candidate = ProviderContainerCandidate(
        provider=CloudProvider.AWS,
        boundary_ref="aws-org:o-acme",
        container_ref="account:123456789012",
        display_name="acme-production",
    )
    service = ProviderContainerAttachmentService(
        authorizer=FakeAttachmentAuthorizer({"usr_alice"}, {"usr_bob"})
    )
    connection = _connection()

    request = service.request_attachment(
        actor_id="usr_alice",
        connection=connection,
        resource_scope_id="scope_checkout_prod",
        candidate=candidate,
    )

    assert request.state == ContainerAttachmentState.PENDING_REVIEW
    approved, binding = service.approve_attachment(
        actor_id="usr_bob", connection=connection, request=request
    )

    assert approved.state == ContainerAttachmentState.APPROVED
    assert approved.reviewed_by == "usr_bob"
    assert binding.attachment_request_id == request.request_id
    assert binding.resource_scope_id == "scope_checkout_prod"


def test_attachment_rejects_candidates_outside_the_connection_boundary():
    service = ProviderContainerAttachmentService(
        authorizer=FakeAttachmentAuthorizer({"usr_alice"}, {"usr_bob"})
    )
    candidate = ProviderContainerCandidate(
        provider=CloudProvider.AWS,
        boundary_ref="aws-org:o-other",
        container_ref="account:210987654321",
        display_name="other-production",
    )

    with pytest.raises(ValueError, match="outside the connection boundary"):
        service.request_attachment(
            actor_id="usr_alice",
            connection=_connection(),
            resource_scope_id="scope_checkout_prod",
            candidate=candidate,
        )


def test_attachment_cannot_be_approved_twice():
    candidate = ProviderContainerCandidate(
        provider=CloudProvider.AWS,
        boundary_ref="aws-org:o-acme",
        container_ref="account:123456789012",
        display_name="acme-production",
    )
    service = ProviderContainerAttachmentService(
        authorizer=FakeAttachmentAuthorizer({"usr_alice"}, {"usr_bob"})
    )
    connection = _connection()
    request = service.request_attachment(
        actor_id="usr_alice",
        connection=connection,
        resource_scope_id="scope_checkout_prod",
        candidate=candidate,
    )
    approved, _ = service.approve_attachment(
        actor_id="usr_bob", connection=connection, request=request
    )

    with pytest.raises(ValueError, match="only a pending"):
        service.approve_attachment(
            actor_id="usr_bob", connection=connection, request=approved
        )
