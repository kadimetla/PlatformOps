import pytest
from pydantic import ValidationError

from gateway.organization_membership import (
    ActiveOrganizationMembershipLookup,
    DuplicateActiveOrganizationMembership,
    InMemoryOrganizationMembershipStore,
    OrganizationMembership,
    OrganizationMembershipSource,
    OrganizationMembershipState,
)


def test_membership_contract_is_explicit_and_does_not_accept_scope_or_provider_fields():
    with pytest.raises(ValidationError, match="Extra inputs"):
        OrganizationMembership.model_validate({
            "user_subject": "usr_alice", "organization_id": "org_acme", "source": "invitation",
            "scope_id": "scope_prod",
        })


def test_duplicate_active_membership_is_rejected_but_other_organizations_are_independent():
    store = InMemoryOrganizationMembershipStore()
    first = OrganizationMembership(
        user_subject="usr_alice", organization_id="org_acme",
        source=OrganizationMembershipSource.INVITATION, state=OrganizationMembershipState.ACTIVE,
    )
    store.save(first)
    with pytest.raises(DuplicateActiveOrganizationMembership):
        store.save(first.model_copy(update={"membership_id": "member_second"}))
    store.save(first.model_copy(update={"membership_id": "member_contoso", "organization_id": "org_contoso"}))


def test_active_membership_lookup_contract_returns_tenant_affiliation_only():
    store = InMemoryOrganizationMembershipStore()

    assert isinstance(store, ActiveOrganizationMembershipLookup) is False
    assert "scope_id" not in OrganizationMembership.model_fields
    assert "provider_binding" not in OrganizationMembership.model_fields
    assert "cloud_credential" not in OrganizationMembership.model_fields
