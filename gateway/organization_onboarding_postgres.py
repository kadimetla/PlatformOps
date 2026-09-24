"""PostgreSQL schema boundary for organization onboarding.

PlatformOps owns these tables in its own database. Authentik is an external
identity provider and is never migrated or queried as an application datastore.
"""
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from gateway.auth.domain_discovery import ActiveOrganizationDomain
from gateway.organization_onboarding import (
    ActiveOrganization,
    AuthenticatedApplicant,
    IdentityBoundaryKind,
    IdentityBoundaryVerificationEvidence,
    OrganizationIdentityBoundary,
    OrganizationOnboardingApproval,
    OrganizationOnboardingActivationError,
    OrganizationOnboardingAlreadyRequested,
    OrganizationOnboardingRequest,
    OrganizationState,
    onboarding_digest,
)


_MIGRATION_PATH = Path(__file__).parent / "migrations" / "001_organization_onboarding.sql"


def apply_organization_onboarding_migrations(connection: psycopg.Connection) -> None:
    """Apply the idempotent organization-onboarding schema migration.

    User-registration migrations must run first because the applicant and
    initial-admin records reference PlatformOps user subjects.
    """
    with connection.transaction():
        connection.execute(_MIGRATION_PATH.read_text())
        connection.execute(
            "INSERT INTO platformops_schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING",
            ("001_organization_onboarding",),
        )


class PostgresOrganizationOnboardingRepository:
    """Transaction-safe PlatformOps organization lifecycle repository."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = dict_row

    def save_pending(self, request: OrganizationOnboardingRequest) -> None:
        try:
            with self._connection.transaction():
                self._connection.execute(
                    """INSERT INTO organizations
                    (organization_id, organization_name, state, created_at, activated_at)
                    VALUES (%s, %s, %s, %s, NULL)""",
                    (request.organization_id, request.organization_name, request.state.value, request.created_at),
                )
                self._connection.execute(
                    """INSERT INTO organization_onboarding_requests
                    (request_id, organization_id, applicant_issuer, applicant_subject,
                     boundary_kind, boundary_reference, state, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (request.request_id, request.organization_id, request.applicant.issuer,
                     request.applicant.subject, request.identity_boundary.kind.value,
                     request.identity_boundary.reference, request.state.value, request.created_at),
                )
        except psycopg.errors.UniqueViolation as error:
            raise OrganizationOnboardingAlreadyRequested(
                "an organization request already exists for this identity boundary"
            ) from error

    def activate(self, organization: ActiveOrganization) -> None:
        with self._connection.transaction():
            row = self._connection.execute(
                """SELECT request.request_id, request.organization_id, organization.organization_name,
                          request.applicant_issuer, request.applicant_subject,
                          request.boundary_kind, request.boundary_reference,
                          request.created_at, organization.state
                   FROM organization_onboarding_requests AS request
                   JOIN organizations AS organization ON organization.organization_id = request.organization_id
                   WHERE request.organization_id = %s FOR UPDATE""",
                (organization.organization_id,),
            ).fetchone()
            if row is None or row["state"] != OrganizationState.PENDING.value:
                raise OrganizationOnboardingActivationError("only a pending request can be activated")
            request = OrganizationOnboardingRequest(
                request_id=row["request_id"], organization_id=row["organization_id"],
                organization_name=row["organization_name"],
                applicant=AuthenticatedApplicant(issuer=row["applicant_issuer"], subject=row["applicant_subject"]),
                identity_boundary=OrganizationIdentityBoundary(
                    kind=IdentityBoundaryKind(row["boundary_kind"]), reference=row["boundary_reference"]
                ), state=OrganizationState.PENDING, created_at=row["created_at"],
            )
            if (organization.identity_boundary != request.identity_boundary
                    or organization.identity_proof.kind != request.identity_boundary.kind
                    or organization.identity_proof.reference != request.identity_boundary.reference
                    or organization.approval.request_id != request.request_id
                    or organization.approval.onboarding_digest != onboarding_digest(request)):
                raise OrganizationOnboardingActivationError("proof or approval does not match pending request")
            self._connection.execute(
                """INSERT INTO organization_identity_proofs
                (request_id, boundary_kind, boundary_reference, evidence_ref, verified_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (request.request_id, organization.identity_proof.kind.value,
                 organization.identity_proof.reference, organization.identity_proof.evidence_ref,
                 organization.identity_proof.verified_at),
            )
            self._connection.execute(
                """INSERT INTO organization_onboarding_approvals
                (request_id, onboarding_digest, approver_issuer, approver_subject, approved_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (organization.approval.request_id, organization.approval.onboarding_digest,
                 organization.approval.approved_by.issuer, organization.approval.approved_by.subject,
                 organization.approval.approved_at),
            )
            self._connection.execute(
                "UPDATE organizations SET state = 'active', activated_at = %s WHERE organization_id = %s",
                (organization.activated_at, organization.organization_id),
            )
            self._connection.execute(
                """INSERT INTO organization_identity_boundaries
                (organization_id, boundary_kind, boundary_reference, evidence_ref, verified_at)
                VALUES (%s, %s, %s, %s, %s)""",
                (organization.organization_id, organization.identity_boundary.kind.value,
                 organization.identity_boundary.reference, organization.identity_proof.evidence_ref,
                 organization.identity_proof.verified_at),
            )
            self._connection.execute(
                """INSERT INTO organization_initial_tenant_admin_memberships
                (organization_id, user_subject, issuer, created_at) VALUES (%s, %s, %s, %s)""",
                (organization.organization_id, organization.initial_tenant_admin.subject,
                 organization.initial_tenant_admin.issuer, organization.activated_at),
            )

    def resolve_routable_organization(self, organization_id: str) -> ActiveOrganization | None:
        row = self._connection.execute(
            """SELECT organization.organization_id, organization.organization_name,
                      organization.activated_at, boundary.boundary_kind,
                      boundary.boundary_reference, boundary.evidence_ref,
                      boundary.verified_at, approval.request_id, approval.onboarding_digest,
                      approval.approver_issuer, approval.approver_subject, approval.approved_at,
                      admin.user_subject, admin.issuer
               FROM organizations AS organization
               JOIN organization_identity_boundaries AS boundary
                 ON boundary.organization_id = organization.organization_id
               JOIN organization_onboarding_requests AS request
                 ON request.organization_id = organization.organization_id
               JOIN organization_onboarding_approvals AS approval
                 ON approval.request_id = request.request_id
               JOIN organization_initial_tenant_admin_memberships AS admin
                 ON admin.organization_id = organization.organization_id
               WHERE organization.organization_id = %s AND organization.state = 'active'""",
            (organization_id,),
        ).fetchone()
        if row is None:
            return None
        boundary = OrganizationIdentityBoundary(
            kind=IdentityBoundaryKind(row["boundary_kind"]), reference=row["boundary_reference"]
        )
        return ActiveOrganization(
            organization_id=row["organization_id"], organization_name=row["organization_name"],
            identity_boundary=boundary,
            identity_proof=IdentityBoundaryVerificationEvidence(
                kind=boundary.kind, reference=boundary.reference,
                evidence_ref=row["evidence_ref"], verified_at=row["verified_at"],
            ),
            approval=OrganizationOnboardingApproval(
                request_id=row["request_id"], onboarding_digest=row["onboarding_digest"],
                approved_by=AuthenticatedApplicant(
                    issuer=row["approver_issuer"], subject=row["approver_subject"]
                ), approved_at=row["approved_at"],
            ),
            initial_tenant_admin=AuthenticatedApplicant(
                issuer=row["issuer"], subject=row["user_subject"]
            ), activated_at=row["activated_at"],
        )

    def find_active_domain(self, canonical_domain: str) -> ActiveOrganizationDomain | None:
        row = self._connection.execute(
            """SELECT organization.organization_id, boundary.boundary_reference
               FROM organizations AS organization
               JOIN organization_identity_boundaries AS boundary
                 ON boundary.organization_id = organization.organization_id
               WHERE organization.state = 'active'
                 AND boundary.boundary_kind = 'domain'
                 AND lower(boundary.boundary_reference) = lower(%s)""",
            (canonical_domain,),
        ).fetchone()
        if row is None:
            return None
        return ActiveOrganizationDomain(
            organization_id=row["organization_id"], canonical_domain=row["boundary_reference"]
        )
