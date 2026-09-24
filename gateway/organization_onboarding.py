"""Deterministic organization-onboarding entry contracts.

This boundary accepts an already-authenticated applicant and creates only a
pending organization-onboarding record. It deliberately creates no membership,
tenant-admin grant, provider connection, cloud binding, or workflow route.
Identity-boundary verification and activation are separate lifecycle steps.
"""
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from threading import Lock
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _organization_id() -> str:
    return f"org_{uuid4().hex}"


def _onboarding_request_id() -> str:
    return f"orgreq_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrganizationState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class IdentityBoundaryKind(str, Enum):
    DOMAIN = "domain"
    IDP = "idp"


class AuthenticatedApplicant(BaseModel):
    """Trusted authentication projection; email is deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    issuer: str = Field(min_length=1)
    subject: str = Field(min_length=1)


class OrganizationIdentityBoundary(BaseModel):
    """A reviewed domain or IdP boundary awaiting deterministic verification."""

    model_config = ConfigDict(extra="forbid")

    kind: IdentityBoundaryKind
    reference: str = Field(min_length=1, max_length=512)

    @field_validator("reference")
    @classmethod
    def _normalize_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("identity boundary reference must be non-empty and whitespace-free")
        return normalized.lower() if "@" not in normalized else normalized


class OrganizationOnboardingStart(BaseModel):
    """Structured applicant input; intentionally not a free-text intake model."""

    model_config = ConfigDict(extra="forbid")

    organization_name: str = Field(min_length=1, max_length=200)
    identity_boundary: OrganizationIdentityBoundary

    @field_validator("organization_name")
    @classmethod
    def _normalize_organization_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("organization name must not be blank")
        return normalized


class OrganizationOnboardingRequest(BaseModel):
    """Pending request with no authority-bearing fields or provider material."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=_onboarding_request_id, min_length=8)
    organization_id: str = Field(default_factory=_organization_id, min_length=5)
    organization_name: str = Field(min_length=1, max_length=200)
    applicant: AuthenticatedApplicant
    identity_boundary: OrganizationIdentityBoundary
    state: OrganizationState = OrganizationState.PENDING
    created_at: datetime = Field(default_factory=_utc_now)


class OrganizationOnboardingAlreadyRequested(ValueError):
    """Raised for a duplicate pending/active organization-boundary request."""


class IdentityBoundaryVerificationEvidence(BaseModel):
    """Non-secret evidence returned by a deterministic identity verifier."""

    model_config = ConfigDict(extra="forbid")

    kind: IdentityBoundaryKind
    reference: str = Field(min_length=1, max_length=512)
    evidence_ref: str = Field(min_length=1, max_length=512)
    verified_at: datetime


class IdentityBoundaryVerifier(Protocol):
    """Injected boundary; a production verifier is deliberately not supplied."""

    def verify(
        self, request: OrganizationOnboardingRequest, *, now: datetime
    ) -> IdentityBoundaryVerificationEvidence | None:
        """Return proof evidence only when the requested identity boundary is controlled."""


class FakeIdentityBoundaryVerifier:
    """Scripted verifier for tests; performs no DNS, IdP, or network access."""

    def __init__(self, verified_boundaries: set[tuple[IdentityBoundaryKind, str]]) -> None:
        self._verified_boundaries = {
            (kind, reference.casefold()) for kind, reference in verified_boundaries
        }
        self.calls: list[str] = []

    def verify(
        self, request: OrganizationOnboardingRequest, *, now: datetime
    ) -> IdentityBoundaryVerificationEvidence | None:
        self.calls.append(request.request_id)
        boundary = request.identity_boundary
        if (boundary.kind, boundary.reference.casefold()) not in self._verified_boundaries:
            return None
        return IdentityBoundaryVerificationEvidence(
            kind=boundary.kind,
            reference=boundary.reference,
            evidence_ref=f"fake-identity-proof:{boundary.kind.value}:{boundary.reference}",
            verified_at=now,
        )


class IdentityBoundaryVerificationService:
    """Verify pending requests without changing organization authority state."""

    def __init__(self, *, verifier: IdentityBoundaryVerifier) -> None:
        self._verifier = verifier

    def verify_pending(
        self,
        request: OrganizationOnboardingRequest,
        *,
        now: datetime | None = None,
    ) -> IdentityBoundaryVerificationEvidence | None:
        if request.state is not OrganizationState.PENDING:
            return None
        return self._verifier.verify(request, now=now or _utc_now())


def onboarding_digest(request: OrganizationOnboardingRequest) -> str:
    """Seal the authority-relevant pending request fields for review."""
    payload = {
        "request_id": request.request_id,
        "organization_id": request.organization_id,
        "organization_name": request.organization_name,
        "applicant": {
            "issuer": request.applicant.issuer,
            "subject": request.applicant.subject,
        },
        "identity_boundary": {
            "kind": request.identity_boundary.kind.value,
            "reference": request.identity_boundary.reference,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class OrganizationOnboardingApproval(BaseModel):
    """Recorded review bound to exactly one pending organization request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=8)
    onboarding_digest: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    approved_by: AuthenticatedApplicant
    approved_at: datetime


class ActiveOrganization(BaseModel):
    """Activated organization record; provider connection is intentionally absent."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    organization_id: str = Field(min_length=5)
    organization_name: str = Field(min_length=1, max_length=200)
    identity_boundary: OrganizationIdentityBoundary
    identity_proof: IdentityBoundaryVerificationEvidence
    approval: OrganizationOnboardingApproval
    initial_tenant_admin: AuthenticatedApplicant
    state: OrganizationState = OrganizationState.ACTIVE
    activated_at: datetime


class OrganizationOnboardingActivationError(ValueError):
    """Raised when evidence or approval cannot activate the pending request."""


class OrganizationOnboardingReviewAccessDenied(PermissionError):
    """Raised unless an explicit control-plane reviewer permission exists."""


class OrganizationOnboardingReviewAuthorizer(Protocol):
    def may_review_onboarding(
        self, *, reviewer: AuthenticatedApplicant, request_id: str
    ) -> bool: ...


class FakeOrganizationOnboardingReviewAuthorizer:
    """Test-only explicit reviewer allow-list; production remains deny-by-default."""

    def __init__(self, allowed_subjects: set[str]) -> None:
        self._allowed_subjects = allowed_subjects

    def may_review_onboarding(
        self, *, reviewer: AuthenticatedApplicant, request_id: str
    ) -> bool:
        return reviewer.subject in self._allowed_subjects


class OrganizationOnboardingActivationService:
    """Activate only an approved request with matching identity-proof evidence."""

    def __init__(self, *, store: "OrganizationOnboardingStore") -> None:
        self._store = store

    def approve(
        self,
        request: OrganizationOnboardingRequest,
        *,
        approver: AuthenticatedApplicant,
        now: datetime | None = None,
    ) -> OrganizationOnboardingApproval:
        if request.state is not OrganizationState.PENDING:
            raise OrganizationOnboardingActivationError("only a pending request can be approved")
        return OrganizationOnboardingApproval(
            request_id=request.request_id,
            onboarding_digest=onboarding_digest(request),
            approved_by=approver,
            approved_at=now or _utc_now(),
        )

    def activate(
        self,
        request: OrganizationOnboardingRequest,
        *,
        identity_proof: IdentityBoundaryVerificationEvidence | None,
        approval: OrganizationOnboardingApproval | None,
        now: datetime | None = None,
    ) -> ActiveOrganization:
        if request.state is not OrganizationState.PENDING:
            raise OrganizationOnboardingActivationError("only a pending request can be activated")
        if identity_proof is None:
            raise OrganizationOnboardingActivationError("identity-boundary verification is required")
        if (
            identity_proof.kind != request.identity_boundary.kind
            or identity_proof.reference != request.identity_boundary.reference
        ):
            raise OrganizationOnboardingActivationError(
                "identity-proof evidence does not match the requested boundary"
            )
        if approval is None:
            raise OrganizationOnboardingActivationError("recorded approval is required")
        if approval.request_id != request.request_id or approval.onboarding_digest != onboarding_digest(request):
            raise OrganizationOnboardingActivationError(
                "approval does not match the pending onboarding request"
            )
        organization = ActiveOrganization(
            organization_id=request.organization_id,
            organization_name=request.organization_name,
            identity_boundary=request.identity_boundary,
            identity_proof=identity_proof,
            approval=approval,
            initial_tenant_admin=request.applicant,
            activated_at=now or _utc_now(),
        )
        self._store.activate(organization)
        return organization


class OrganizationOnboardingStore(Protocol):
    def save_pending(self, request: OrganizationOnboardingRequest) -> None: ...

    def record_identity_proof(
        self, request: OrganizationOnboardingRequest, proof: IdentityBoundaryVerificationEvidence
    ) -> None: ...

    def activate(self, organization: ActiveOrganization) -> None: ...

    def resolve_routable_organization(self, organization_id: str) -> ActiveOrganization | None: ...


class InMemoryOrganizationOnboardingStore:
    """Small development/test store; production persistence is a later task."""

    def __init__(self) -> None:
        self._requests_by_id: dict[str, OrganizationOnboardingRequest] = {}
        self._requests_by_identity: dict[tuple[str, IdentityBoundaryKind, str], str] = {}
        self._active_by_organization_id: dict[str, ActiveOrganization] = {}
        self._proof_by_request_id: dict[str, IdentityBoundaryVerificationEvidence] = {}
        self._lock = Lock()

    def save_pending(self, request: OrganizationOnboardingRequest) -> None:
        key = (
            request.organization_name.casefold(),
            request.identity_boundary.kind,
            request.identity_boundary.reference.casefold(),
        )
        with self._lock:
            if key in self._requests_by_identity:
                raise OrganizationOnboardingAlreadyRequested(
                    "an organization request already exists for this identity boundary"
                )
            self._requests_by_id[request.request_id] = request
            self._requests_by_identity[key] = request.request_id

    def record_identity_proof(
        self, request: OrganizationOnboardingRequest, proof: IdentityBoundaryVerificationEvidence
    ) -> None:
        if proof.kind != request.identity_boundary.kind or proof.reference != request.identity_boundary.reference:
            raise OrganizationOnboardingActivationError("identity proof does not match pending request")
        with self._lock:
            if request.request_id not in self._requests_by_id:
                raise OrganizationOnboardingActivationError("pending request does not exist")
            self._proof_by_request_id[request.request_id] = proof

    def activate(self, organization: ActiveOrganization) -> None:
        with self._lock:
            if organization.organization_id not in {
                request.organization_id for request in self._requests_by_id.values()
            }:
                raise OrganizationOnboardingActivationError(
                    "active organization has no pending onboarding request"
                )
            if organization.state is not OrganizationState.ACTIVE:
                raise OrganizationOnboardingActivationError(
                    "only an active organization can become routable"
                )
            self._active_by_organization_id[organization.organization_id] = organization

    def get(self, request_id: str) -> OrganizationOnboardingRequest | None:
        with self._lock:
            return self._requests_by_id.get(request_id)

    def resolve_routable_organization(self, organization_id: str) -> ActiveOrganization | None:
        """Return active organization context only; missing and pending deny by default."""
        with self._lock:
            return self._active_by_organization_id.get(organization_id)


class OrganizationOnboardingService:
    """Create an authority-free pending onboarding request."""

    def __init__(self, *, store: OrganizationOnboardingStore) -> None:
        self._store = store

    def start(
        self,
        *,
        applicant: AuthenticatedApplicant,
        onboarding: OrganizationOnboardingStart,
        now: datetime | None = None,
    ) -> OrganizationOnboardingRequest:
        request = OrganizationOnboardingRequest(
            organization_name=onboarding.organization_name,
            applicant=applicant,
            identity_boundary=onboarding.identity_boundary,
            created_at=now or _utc_now(),
        )
        self._store.save_pending(request)
        return request
