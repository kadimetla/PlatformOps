import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from pydantic import ValidationError

from gateway.auth.postgres import PostgresUserRegistrationRepository, apply_user_registration_migrations
from gateway.command_router import ControlPlaneCommandRouter, ValidatedPrincipal
from gateway.organization_membership import (
    ActiveOrganizationMembershipLookup,
    DuplicateActiveOrganizationMembership,
    OrganizationInvitation,
)
from gateway.organization_membership_postgres import (
    OrganizationInvitationNotUsable,
    OrganizationInvitationRecipientMismatch,
    OrganizationMembershipOrganizationInactive,
    OrganizationMembershipNotActive,
    PostgresOrganizationMembershipRepository,
    apply_organization_membership_migrations,
)
from gateway.organization_member_onboarding_handler import build_organization_member_onboarding_handler
from gateway.organization_onboarding_postgres import apply_organization_onboarding_migrations


DATABASE_URL = os.environ.get("PLATFORMOPS_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="PLATFORMOPS_DATABASE_URL is not configured"),
]


def _invite(*, organization_id: str, email: str, digest: str, expires_at: datetime) -> OrganizationInvitation:
    return OrganizationInvitation(
        organization_id=organization_id,
        canonical_email=email,
        token_digest=digest,
        expires_at=expires_at,
    )


def _create_organization(connection: psycopg.Connection, organization_id: str, state: str) -> None:
    connection.execute(
        """INSERT INTO organizations (organization_id, organization_name, state, created_at, activated_at)
           VALUES (%s, %s, %s, %s, %s)""",
        (
            organization_id,
            organization_id,
            state,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) if state == "active" else None,
        ),
    )
    connection.commit()


def _clean(connection: psycopg.Connection, *organization_ids: str) -> None:
    connection.execute("DELETE FROM organization_memberships WHERE organization_id = ANY(%s)", (list(organization_ids),))
    connection.execute("DELETE FROM organization_invitations WHERE organization_id = ANY(%s)", (list(organization_ids),))
    connection.execute("DELETE FROM organizations WHERE organization_id = ANY(%s)", (list(organization_ids),))
    connection.commit()


def test_membership_migration_creates_platformops_owned_tables():
    connection = psycopg.connect(DATABASE_URL)
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        tables = {
            row[0] for row in connection.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename IN "
                "('organization_memberships', 'organization_invitations')"
            ).fetchall()
        }
        assert tables == {"organization_memberships", "organization_invitations"}
    finally:
        connection.close()


def test_invitation_acceptance_is_single_use_and_creates_membership_only_for_active_org():
    connection = psycopg.connect(DATABASE_URL)
    active_org, pending_org = "org_member_active", "org_member_pending"
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        _clean(connection, active_org, pending_org)
        _create_organization(connection, active_org, "active")
        _create_organization(connection, pending_org, "pending")
        users = PostgresUserRegistrationRepository(connection)
        invited = users.create_or_recover_verified_user("invited@acme.example")
        other = users.create_or_recover_verified_user("other@acme.example")
        repository = PostgresOrganizationMembershipRepository(connection)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        invitation = _invite(
            organization_id=active_org,
            email="invited@acme.example",
            digest="a" * 64,
            expires_at=expires_at,
        )
        repository.create_invitation(invitation)
        with pytest.raises(OrganizationInvitationRecipientMismatch):
            repository.accept_invitation(token_digest=invitation.token_digest, user_subject=other.subject)
        membership = repository.accept_invitation(token_digest=invitation.token_digest, user_subject=invited.subject)
        assert membership.user_subject == invited.subject
        assert membership.organization_id == active_org
        assert membership.role_refs == []
        assert repository.get_active_membership(user_subject=invited.subject, organization_id=active_org) == membership
        with pytest.raises(OrganizationInvitationNotUsable):
            repository.accept_invitation(token_digest=invitation.token_digest, user_subject=invited.subject)

        with pytest.raises(OrganizationMembershipOrganizationInactive):
            repository.create_invitation(_invite(
                organization_id=pending_org,
                email="invited@acme.example",
                digest="b" * 64,
                expires_at=expires_at,
            ))
        repository.create_invitation(_invite(
            organization_id=active_org,
            email="invited@acme.example",
            digest="f" * 64,
            expires_at=expires_at,
        ))
        connection.execute("UPDATE organizations SET state = 'pending', activated_at = NULL WHERE organization_id = %s", (active_org,))
        connection.commit()
        with pytest.raises(OrganizationMembershipOrganizationInactive):
            repository.accept_invitation(token_digest="f" * 64, user_subject=invited.subject)
    finally:
        _clean(connection, active_org, pending_org)
        connection.close()


def test_expired_invitation_and_duplicate_active_membership_are_rejected_without_consuming_new_invite():
    connection = psycopg.connect(DATABASE_URL)
    organization_id = "org_member_duplicates"
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        _clean(connection, organization_id)
        _create_organization(connection, organization_id, "active")
        user = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user("duplicate@acme.example")
        repository = PostgresOrganizationMembershipRepository(connection)
        now = datetime.now(timezone.utc)
        expired = _invite(
            organization_id=organization_id,
            email="duplicate@acme.example",
            digest="c" * 64,
            expires_at=now - timedelta(seconds=1),
        )
        repository.create_invitation(expired)
        with pytest.raises(OrganizationInvitationNotUsable):
            repository.accept_invitation(token_digest=expired.token_digest, user_subject=user.subject, accepted_at=now)

        first = _invite(
            organization_id=organization_id,
            email="duplicate@acme.example",
            digest="d" * 64,
            expires_at=now + timedelta(minutes=5),
        )
        repository.create_invitation(first)
        repository.accept_invitation(token_digest=first.token_digest, user_subject=user.subject, accepted_at=now)
        second = _invite(
            organization_id=organization_id,
            email="duplicate@acme.example",
            digest="e" * 64,
            expires_at=now + timedelta(minutes=5),
        )
        repository.create_invitation(second)
        with pytest.raises(DuplicateActiveOrganizationMembership):
            repository.accept_invitation(token_digest=second.token_digest, user_subject=user.subject, accepted_at=now)
        assert repository.get_active_membership(user_subject=user.subject, organization_id=organization_id) is not None
        with pytest.raises(DuplicateActiveOrganizationMembership):
            repository.accept_invitation(token_digest=second.token_digest, user_subject=user.subject, accepted_at=now)
    finally:
        _clean(connection, organization_id)
        connection.close()


def test_join_org_route_derives_user_from_principal_and_keeps_raw_token_out_of_result():
    connection = psycopg.connect(DATABASE_URL)
    organization_id = "org_member_join_route"
    raw_token = "x" * 48
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        _clean(connection, organization_id)
        _create_organization(connection, organization_id, "active")
        user = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user("join@acme.example")
        repository = PostgresOrganizationMembershipRepository(connection)
        repository.create_invitation(_invite(
            organization_id=organization_id,
            email="join@acme.example",
            digest=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
        router = ControlPlaneCommandRouter({
            "organization_member_onboarding": build_organization_member_onboarding_handler(connection)
        })
        with pytest.raises(ValidationError, match="Extra inputs"):
            asyncio.run(router.dispatch(
                "/join-org",
                {"invitation_token": raw_token, "user_subject": "attacker"},
                principal=ValidatedPrincipal(issuer="platformops", subject=user.subject),
            ))

        result = asyncio.run(router.dispatch(
            "/join-org",
            {"invitation_token": raw_token},
            principal=ValidatedPrincipal(issuer="platformops", subject=user.subject),
        ))

        assert result["membership"].user_subject == user.subject
        assert raw_token not in str(result)
    finally:
        _clean(connection, organization_id)
        connection.close()


def test_revoked_membership_is_not_active_and_user_can_join_two_independent_organizations():
    connection = psycopg.connect(DATABASE_URL)
    first_org, second_org = "org_member_first", "org_member_second"
    first_token, second_token = "m" * 48, "n" * 48
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        _clean(connection, first_org, second_org)
        _create_organization(connection, first_org, "active")
        _create_organization(connection, second_org, "active")
        user = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user("two-orgs@acme.example")
        repository = PostgresOrganizationMembershipRepository(connection)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        for organization_id, raw_token in ((first_org, first_token), (second_org, second_token)):
            repository.create_invitation(_invite(
                organization_id=organization_id,
                email="two-orgs@acme.example",
                digest=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                expires_at=expires_at,
            ))
        router = ControlPlaneCommandRouter({
            "organization_member_onboarding": build_organization_member_onboarding_handler(connection)
        })
        principal = ValidatedPrincipal(issuer="platformops", subject=user.subject)
        first = asyncio.run(router.dispatch("/join-org", {"invitation_token": first_token}, principal=principal))["membership"]
        second = asyncio.run(router.dispatch("/join-org", {"invitation_token": second_token}, principal=principal))["membership"]
        assert first.organization_id == first_org
        assert second.organization_id == second_org

        repository.revoke_active_membership(membership_id=first.membership_id)
        assert repository.get_active_membership(user_subject=user.subject, organization_id=first_org) is None
        assert repository.get_active_membership(user_subject=user.subject, organization_id=second_org) == second
        with pytest.raises(OrganizationMembershipNotActive):
            repository.revoke_active_membership(membership_id=first.membership_id)
    finally:
        _clean(connection, first_org, second_org)
        connection.close()


def test_active_membership_lookup_excludes_every_non_active_lifecycle_state():
    connection = psycopg.connect(DATABASE_URL)
    organization_id = "org_member_lookup_states"
    raw_token = "l" * 48
    try:
        apply_user_registration_migrations(connection)
        apply_organization_onboarding_migrations(connection)
        apply_organization_membership_migrations(connection)
        _clean(connection, organization_id)
        _create_organization(connection, organization_id, "active")
        user = PostgresUserRegistrationRepository(connection).create_or_recover_verified_user("lookup@acme.example")
        repository = PostgresOrganizationMembershipRepository(connection)
        assert isinstance(repository, ActiveOrganizationMembershipLookup)
        repository.create_invitation(_invite(
            organization_id=organization_id,
            email="lookup@acme.example",
            digest=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ))
        membership = repository.accept_invitation(
            token_digest=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(), user_subject=user.subject
        )
        assert repository.get_active_membership(
            user_subject=user.subject, organization_id=organization_id
        ) == membership
        for state in ("pending", "rejected", "revoked", "expired"):
            connection.execute(
                "UPDATE organization_memberships SET state = %s WHERE membership_id = %s",
                (state, membership.membership_id),
            )
            connection.commit()
            assert repository.get_active_membership(
                user_subject=user.subject, organization_id=organization_id
            ) is None
            connection.execute(
                "UPDATE organization_memberships SET state = 'active' WHERE membership_id = %s",
                (membership.membership_id,),
            )
            connection.commit()
    finally:
        _clean(connection, organization_id)
        connection.close()
