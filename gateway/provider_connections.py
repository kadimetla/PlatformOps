"""Provider-connection contracts at the cloud control-plane boundary.

These records deliberately contain references to approved identities, never
credential material.  They do not grant a Resource Scope access to a cloud
container; reviewed bindings are a later boundary.
"""
from enum import Enum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class ProviderConnectionState(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    ACTIVE = "active"
    SUSPENDED = "suspended"


def _connection_id() -> str:
    return f"pconn_{uuid4().hex}"


def _attachment_request_id() -> str:
    return f"attach_{uuid4().hex}"


def _binding_id() -> str:
    return f"binding_{uuid4().hex}"


class ProviderConnection(BaseModel):
    """Organization-owned, non-secret provider control-plane record."""

    model_config = ConfigDict(extra="forbid")

    connection_id: str = Field(default_factory=_connection_id, min_length=7)
    organization_id: str = Field(min_length=1)
    provider: CloudProvider
    boundary_ref: str = Field(min_length=1)
    discovery_identity_ref: str = Field(min_length=1)
    state: ProviderConnectionState = ProviderConnectionState.PENDING
    version: int = Field(default=1, ge=1)

    @property
    def is_active(self) -> bool:
        return self.state == ProviderConnectionState.ACTIVE

    def require_active(self) -> None:
        """Fail closed before any verification, inquiry, or attachment use."""
        if not self.is_active:
            raise ProviderConnectionUnavailable(
                f"provider connection {self.connection_id!r} is not active"
            )


class ProviderConnectionUnavailable(ValueError):
    """Raised when an unverified, inactive, or suspended connection is used."""


class ProviderConnectionAccessDenied(PermissionError):
    """Raised when an actor lacks the organization-admin inquiry permission."""


class ProviderContainerCandidate(BaseModel):
    """Read-only, non-authorizing container inventory result."""

    model_config = ConfigDict(extra="forbid")

    provider: CloudProvider
    boundary_ref: str = Field(min_length=1)
    container_ref: str = Field(min_length=1)
    display_name: str = Field(min_length=1)


class ContainerAttachmentState(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContainerAttachmentRequest(BaseModel):
    """A reviewed proposal to attach one candidate to one opaque scope."""

    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=_attachment_request_id, min_length=8)
    resource_scope_id: str = Field(min_length=1)
    connection_id: str = Field(min_length=7)
    candidate: ProviderContainerCandidate
    requested_by: str = Field(min_length=1)
    state: ContainerAttachmentState = ContainerAttachmentState.PENDING_REVIEW
    reviewed_by: str | None = None
    version: int = Field(default=1, ge=1)


class CloudResourceContainerBinding(BaseModel):
    """Active, versioned result of an approved attachment only."""

    model_config = ConfigDict(extra="forbid")

    binding_id: str = Field(default_factory=_binding_id, min_length=9)
    resource_scope_id: str = Field(min_length=1)
    connection_id: str = Field(min_length=7)
    candidate: ProviderContainerCandidate
    attachment_request_id: str = Field(min_length=8)
    version: int = Field(default=1, ge=1)


class ProviderAdapter(Protocol):
    """Narrow deterministic provider contract; implementations own I/O."""

    provider: CloudProvider

    def verify_boundary(self, connection: ProviderConnection) -> bool:
        """Return whether the connection's configured boundary is controlled."""

    def list_container_candidates(
        self, connection: ProviderConnection
    ) -> list[ProviderContainerCandidate]:
        """Return read-only inventory candidates within the connection boundary."""


class ProviderAdapterRegistry:
    """Select only an injected adapter using the trusted connection record."""

    def __init__(self, adapters: list[ProviderAdapter]) -> None:
        self._adapters = {adapter.provider: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError("only one provider adapter may be registered per provider")

    def for_connection(self, connection: ProviderConnection) -> ProviderAdapter:
        connection.require_active()
        try:
            return self._adapters[connection.provider]
        except KeyError as error:
            raise ProviderConnectionUnavailable(
                f"no adapter is configured for provider {connection.provider.value!r}"
            ) from error


class ProviderConnectionInquiryAuthorizer(Protocol):
    """Organization membership/role decision supplied by the auth boundary."""

    def may_inquire_provider_inventory(
        self, *, actor_id: str, organization_id: str
    ) -> bool:
        """Return whether this actor is an administrator of the organization."""


class ProviderContainerAttachmentAuthorizer(Protocol):
    """Organization and scope authorization supplied by later auth/bootstrap."""

    def may_request_container_attachment(
        self, *, actor_id: str, organization_id: str, resource_scope_id: str
    ) -> bool:
        """Return whether the actor can propose this scope attachment."""

    def may_review_container_attachment(
        self, *, actor_id: str, organization_id: str, resource_scope_id: str
    ) -> bool:
        """Return whether the actor can approve this scope attachment."""


class ProviderContainerInquiryService:
    """Perform a bounded, read-only inventory lookup.

    The service deliberately returns candidates only.  It neither persists nor
    creates a scope binding, grant, provider resource, or execution identity.
    """

    def __init__(
        self,
        *,
        adapters: ProviderAdapterRegistry,
        authorizer: ProviderConnectionInquiryAuthorizer,
    ) -> None:
        self._adapters = adapters
        self._authorizer = authorizer

    def inquire(
        self, *, actor_id: str, connection: ProviderConnection
    ) -> list[ProviderContainerCandidate]:
        if not self._authorizer.may_inquire_provider_inventory(
            actor_id=actor_id, organization_id=connection.organization_id
        ):
            raise ProviderConnectionAccessDenied(
                "organization administrator permission is required for provider inquiry"
            )

        adapter = self._adapters.for_connection(connection)
        candidates = adapter.list_container_candidates(connection)
        return [
            candidate
            for candidate in candidates
            if candidate.provider == connection.provider
            and candidate.boundary_ref == connection.boundary_ref
        ]


class ProviderContainerAttachmentService:
    """Create reviewed attachment records; never creates provider resources."""

    def __init__(self, *, authorizer: ProviderContainerAttachmentAuthorizer) -> None:
        self._authorizer = authorizer

    def request_attachment(
        self,
        *,
        actor_id: str,
        connection: ProviderConnection,
        resource_scope_id: str,
        candidate: ProviderContainerCandidate,
    ) -> ContainerAttachmentRequest:
        connection.require_active()
        self._require_connection_candidate(connection, candidate)
        if not self._authorizer.may_request_container_attachment(
            actor_id=actor_id,
            organization_id=connection.organization_id,
            resource_scope_id=resource_scope_id,
        ):
            raise ProviderConnectionAccessDenied(
                "scope administrator permission is required to request attachment"
            )
        return ContainerAttachmentRequest(
            resource_scope_id=resource_scope_id,
            connection_id=connection.connection_id,
            candidate=candidate,
            requested_by=actor_id,
        )

    def approve_attachment(
        self,
        *,
        actor_id: str,
        connection: ProviderConnection,
        request: ContainerAttachmentRequest,
    ) -> tuple[ContainerAttachmentRequest, CloudResourceContainerBinding]:
        connection.require_active()
        if request.state != ContainerAttachmentState.PENDING_REVIEW:
            raise ValueError("only a pending attachment request can be approved")
        if request.connection_id != connection.connection_id:
            raise ValueError("attachment request does not belong to this connection")
        self._require_connection_candidate(connection, request.candidate)
        if not self._authorizer.may_review_container_attachment(
            actor_id=actor_id,
            organization_id=connection.organization_id,
            resource_scope_id=request.resource_scope_id,
        ):
            raise ProviderConnectionAccessDenied(
                "scope administrator permission is required to approve attachment"
            )

        approved = request.model_copy(
            update={
                "state": ContainerAttachmentState.APPROVED,
                "reviewed_by": actor_id,
                "version": request.version + 1,
            }
        )
        return approved, CloudResourceContainerBinding(
            resource_scope_id=approved.resource_scope_id,
            connection_id=approved.connection_id,
            candidate=approved.candidate,
            attachment_request_id=approved.request_id,
        )

    @staticmethod
    def _require_connection_candidate(
        connection: ProviderConnection, candidate: ProviderContainerCandidate
    ) -> None:
        if (
            candidate.provider != connection.provider
            or candidate.boundary_ref != connection.boundary_ref
        ):
            raise ValueError("container candidate is outside the connection boundary")


class FakeProviderAdapter:
    """Scripted non-network adapter for deterministic contract tests."""

    def __init__(
        self,
        provider: CloudProvider,
        verified_boundaries: set[str],
        candidates: list[ProviderContainerCandidate] | None = None,
    ) -> None:
        self.provider = provider
        self._verified_boundaries = frozenset(verified_boundaries)
        self._candidates = tuple(candidates or [])
        self.verification_calls: list[str] = []
        self.inquiry_calls: list[str] = []

    def verify_boundary(self, connection: ProviderConnection) -> bool:
        if connection.provider != self.provider:
            raise ValueError("connection provider does not match adapter provider")
        self.verification_calls.append(connection.connection_id)
        return connection.boundary_ref in self._verified_boundaries

    def list_container_candidates(
        self, connection: ProviderConnection
    ) -> list[ProviderContainerCandidate]:
        if connection.provider != self.provider:
            raise ValueError("connection provider does not match adapter provider")
        self.inquiry_calls.append(connection.connection_id)
        return [
            candidate
            for candidate in self._candidates
            if candidate.provider == connection.provider
            and candidate.boundary_ref == connection.boundary_ref
        ]
