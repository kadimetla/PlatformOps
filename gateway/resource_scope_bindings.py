"""Registry-controlled Cloud Resource Container bindings for Resource Scopes."""
from enum import Enum
from threading import Lock
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _binding_id() -> str:
    return f"binding_{uuid4().hex}"


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class CloudResourceContainerType(str, Enum):
    AWS_ACCOUNT = "aws_account"
    GCP_PROJECT = "gcp_project"
    AZURE_SUBSCRIPTION = "azure_subscription"


class ProviderBindingState(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class CloudResourceContainerBinding(BaseModel):
    """Trusted mapping; callers never supply this routing authority."""

    model_config = ConfigDict(extra="forbid")

    binding_id: str = Field(default_factory=_binding_id, min_length=10)
    scope_id: str = Field(min_length=8)
    provider: CloudProvider
    container_type: CloudResourceContainerType
    container_reference: str = Field(min_length=1)
    execution_identity_reference: str = Field(min_length=1)
    provider_workspace: str | None = Field(default=None, min_length=1)
    state: ProviderBindingState = ProviderBindingState.DRAFT
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_provider_container_pair(self) -> "CloudResourceContainerBinding":
        expected = {
            CloudProvider.AWS: CloudResourceContainerType.AWS_ACCOUNT,
            CloudProvider.GCP: CloudResourceContainerType.GCP_PROJECT,
            CloudProvider.AZURE: CloudResourceContainerType.AZURE_SUBSCRIPTION,
        }[self.provider]
        if self.container_type is not expected:
            raise ValueError("provider must use its matching Cloud Resource Container type")
        return self


class ResourceScopeBindingRegistry(Protocol):
    def register_reviewed(self, binding: CloudResourceContainerBinding) -> None: ...

    def set_state(self, binding_id: str, state: ProviderBindingState) -> None: ...

    def active_bindings(self, scope_id: str) -> tuple[CloudResourceContainerBinding, ...]: ...


class InMemoryResourceScopeBindingRegistry:
    """Test registry. It stores no cloud credential and performs no cloud call."""

    def __init__(self) -> None:
        self._bindings: dict[str, CloudResourceContainerBinding] = {}
        self._lock = Lock()

    def register_reviewed(self, binding: CloudResourceContainerBinding) -> None:
        with self._lock:
            self._bindings[binding.binding_id] = binding

    def set_state(self, binding_id: str, state: ProviderBindingState) -> None:
        with self._lock:
            binding = self._bindings.get(binding_id)
            if binding is None:
                raise ValueError("Cloud Resource Container binding does not exist")
            self._bindings[binding_id] = binding.model_copy(update={"state": state})

    def active_bindings(self, scope_id: str) -> tuple[CloudResourceContainerBinding, ...]:
        return tuple(
            binding for binding in self._bindings.values()
            if binding.scope_id == scope_id and binding.state is ProviderBindingState.ACTIVE
        )


class BindingResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NON_ROUTABLE = "non_routable"


class ProvisioningBindingProfile(BaseModel):
    """Trusted profile policy; a request never selects a provider binding."""

    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1)
    eligible_providers: frozenset[CloudProvider] = Field(min_length=1)


class ProvisioningBindingRequest(BaseModel):
    """Untrusted request shape deliberately excludes cloud-routing values."""

    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(min_length=8)
    profile_id: str = Field(min_length=1)


class BindingResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: BindingResolutionStatus
    binding: CloudResourceContainerBinding | None = None

    @model_validator(mode="after")
    def _validate_result(self) -> "BindingResolution":
        if (self.status is BindingResolutionStatus.RESOLVED) != (self.binding is not None):
            raise ValueError("resolved status requires exactly one binding")
        return self


class ResourceScopeBindingResolver:
    """Selects one registry binding after the caller has authorized the scope."""

    def __init__(self, registry: ResourceScopeBindingRegistry) -> None:
        self._registry = registry

    def resolve(self, *, scope_id: str, profile: ProvisioningBindingProfile) -> BindingResolution:
        eligible = tuple(
            binding for binding in self._registry.active_bindings(scope_id)
            if binding.provider in profile.eligible_providers
        )
        if len(eligible) != 1:
            return BindingResolution(status=BindingResolutionStatus.NON_ROUTABLE)
        return BindingResolution(status=BindingResolutionStatus.RESOLVED, binding=eligible[0])
