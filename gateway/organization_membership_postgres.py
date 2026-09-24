"""PostgreSQL persistence for invitation-based organization membership.

This module creates tenant affiliation only. It does not create Resource Scope
grants, provider bindings, or cloud credentials.
"""
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gateway.organization_membership import (
    DuplicateActiveOrganizationMembership,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationMembershipSource,
    OrganizationMembershipState,
    OrganizationRoleReference,
)


_MIGRATION_PATH = Path(__file__).parent / "migrations" / "002_organization_membership.sql"


class OrganizationMembershipPersistenceError(ValueError):
    pass


class OrganizationInvitationNotUsable(OrganizationMembershipPersistenceError):
    pass


class OrganizationInvitationRecipientMismatch(OrganizationMembershipPersistenceError):
    pass


class OrganizationMembershipOrganizationInactive(OrganizationMembershipPersistenceError):
    pass


def apply_organization_membership_migrations(connection: psycopg.Connection) -> None:
    """Apply membership tables after user-registration and organization migrations."""
    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO platformops_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("002_organization_membership",),
        )


class PostgresOrganizationMembershipRepository:
    """Transaction-safe invitation and membership store for PlatformOps."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = dict_row

    def create_invitation(self, invitation: OrganizationInvitation) -> None:
        with self._connection.transaction():
            self._require_active_organization(invitation.organization_id)
            self._connection.execute(
                """INSERT INTO organization_invitations
                (invitation_id, organization_id, canonical_email, token_digest, expires_at, consumed_at)
                VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    invitation.invitation_id,
                    invitation.organization_id,
                    invitation.canonical_email,
                    invitation.token_digest,
                    invitation.expires_at,
                    invitation.consumed_at,
                ),
            )

    def accept_invitation(
        self, *, token_digest: str, user_subject: str, accepted_at: datetime | None = None
    ) -> OrganizationMembership:
        """Consume one valid invite and create one active tenant membership.

        The invitation remains unconsumed if the recipient does not match, the
        organization is inactive, or the active membership already exists.
        """
        now = accepted_at or datetime.now(timezone.utc)
        try:
            with self._connection.transaction():
                invitation = self._connection.execute(
                    """SELECT invitation_id, organization_id, canonical_email, token_digest,
                              expires_at, consumed_at
                       FROM organization_invitations WHERE token_digest = %s FOR UPDATE""",
                    (token_digest,),
                ).fetchone()
                if invitation is None or invitation["consumed_at"] is not None or invitation["expires_at"] <= now:
                    raise OrganizationInvitationNotUsable("invitation is expired, consumed, or unknown")
                organization = self._connection.execute(
                    "SELECT state FROM organizations WHERE organization_id = %s FOR UPDATE",
                    (invitation["organization_id"],),
                ).fetchone()
                if organization is None or organization["state"] != "active":
                    raise OrganizationMembershipOrganizationInactive("organization is not active")
                recipient = self._connection.execute(
                    """SELECT 1 FROM auth_verified_email_contacts
                       WHERE user_subject = %s AND canonical_email = %s""",
                    (user_subject, invitation["canonical_email"]),
                ).fetchone()
                if recipient is None:
                    raise OrganizationInvitationRecipientMismatch("invitation recipient does not match user")
                membership = OrganizationMembership(
                    user_subject=user_subject,
                    organization_id=invitation["organization_id"],
                    source=OrganizationMembershipSource.INVITATION,
                    state=OrganizationMembershipState.ACTIVE,
                    created_at=now,
                )
                self._connection.execute(
                    """INSERT INTO organization_memberships
                    (membership_id, user_subject, organization_id, source, role_ids, state, version, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        membership.membership_id,
                        membership.user_subject,
                        membership.organization_id,
                        membership.source.value,
                        [role.role_id for role in membership.role_refs],
                        membership.state.value,
                        membership.version,
                        membership.created_at,
                    ),
                )
                self._connection.execute(
                    "UPDATE organization_invitations SET consumed_at = %s WHERE invitation_id = %s",
                    (now, invitation["invitation_id"]),
                )
                return membership
        except psycopg.errors.UniqueViolation as error:
            raise DuplicateActiveOrganizationMembership("active membership already exists") from error

    def inspect_invitation(self, *, token_digest: str, user_subject: str) -> str:
        """Validate current invitation eligibility without consuming it.

        Consumption is deliberately repeated by ``accept_invitation`` under a
        transaction and row lock, so this preflight cannot authorize a race.
        """
        now = datetime.now(timezone.utc)
        with self._connection.transaction():
            invitation = self._connection.execute(
                """SELECT organization_id, canonical_email, expires_at, consumed_at
                   FROM organization_invitations WHERE token_digest = %s""",
                (token_digest,),
            ).fetchone()
            if invitation is None or invitation["consumed_at"] is not None or invitation["expires_at"] <= now:
                raise OrganizationInvitationNotUsable("invitation is expired, consumed, or unknown")
            self._require_active_organization(invitation["organization_id"])
            recipient = self._connection.execute(
                """SELECT 1 FROM auth_verified_email_contacts
                   WHERE user_subject = %s AND canonical_email = %s""",
                (user_subject, invitation["canonical_email"]),
            ).fetchone()
            if recipient is None:
                raise OrganizationInvitationRecipientMismatch("invitation recipient does not match user")
            return invitation["organization_id"]

    def get_active_membership(
        self, *, user_subject: str, organization_id: str
    ) -> OrganizationMembership | None:
        row = self._connection.execute(
            """SELECT membership_id, user_subject, organization_id, source, role_ids, state, version, created_at
               FROM organization_memberships
               WHERE user_subject = %s AND organization_id = %s AND state = 'active'""",
            (user_subject, organization_id),
        ).fetchone()
        if row is None:
            return None
        return OrganizationMembership(
            membership_id=row["membership_id"],
            user_subject=row["user_subject"],
            organization_id=row["organization_id"],
            source=OrganizationMembershipSource(row["source"]),
            role_refs=[OrganizationRoleReference(role_id=role_id) for role_id in row["role_ids"]],
            state=OrganizationMembershipState(row["state"]),
            version=row["version"],
            created_at=row["created_at"],
        )

    def _require_active_organization(self, organization_id: str) -> None:
        row = self._connection.execute(
            "SELECT state FROM organizations WHERE organization_id = %s", (organization_id,)
        ).fetchone()
        if row is None or row["state"] != "active":
            raise OrganizationMembershipOrganizationInactive("organization is not active")
