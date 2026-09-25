"""Typed IAM-style Resource Scope binding contracts; evaluation is separate."""
from enum import Enum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gateway.organization_membership import ActiveOrganizationMembershipLookup
from gateway.resource_scope_registry import ResourceScope, ReviewedResourceScopeRegistry


def _binding_id() -> str:
    return f"scopebind_{uuid4().hex}"


class PrincipalKind(str, Enum):
    USER = "user"
    IDENTITY_GROUP = "identity_group"
    SERVICE = "service"


class ResourceScopeAction(str, Enum):
    VIEW = "scope_view"
    REQUEST_PROVISION = "provision_request"
    APPROVE_PROVISION = "provision_approve"
    ADMIN = "scope_admin"


class ResourceScopeBindingState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ScopeBindingTargetKind(str, Enum):
    SCOPE = "scope"
    ORGANIZATION = "organization"
    BUSINESS_UNIT = "business_unit"
    TEAM = "team"
    PROJECT = "project"
    ENVIRONMENT = "environment"


class PrincipalReference(BaseModel):
    """An identity principal; `group` never means a business unit."""

    model_config = ConfigDict(extra="forbid")

    kind: PrincipalKind
    principal_id: str = Field(min_length=1)


class ScopeBindingTarget(BaseModel):
    """Exact Resource Scope or a named logical hierarchy ancestor."""

    model_config = ConfigDict(extra="forbid")

    kind: ScopeBindingTargetKind
    resource_id: str = Field(min_length=1)
    inherit_to_descendants: bool = False


class ResourceScopeBindingConditions(BaseModel):
    """Small explicit v1 condition surface; no free-form policy language."""

    model_config = ConfigDict(extra="forbid")

    environment_ids: tuple[str, ...] = ()


class ResourceScopeRoleBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: str = Field(default_factory=_binding_id, min_length=10)
    principal: PrincipalReference
    actions: frozenset[ResourceScopeAction] = Field(min_length=1)
    target: ScopeBindingTarget
    conditions: ResourceScopeBindingConditions = Field(default_factory=ResourceScopeBindingConditions)
    state: ResourceScopeBindingState = ResourceScopeBindingState.ACTIVE
    version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_inheritance(self) -> "ResourceScopeRoleBinding":
        if self.target.kind is ScopeBindingTargetKind.SCOPE and self.target.inherit_to_descendants:
            raise ValueError("a complete Resource Scope has no descendant Resource Scope")
        return self


class ResourceScopeRoleBindingStore(Protocol):
    def active_bindings(self) -> tuple[ResourceScopeRoleBinding, ...]: ...


class InMemoryResourceScopeRoleBindingStore:
    """Test-only binding store with explicit lifecycle state."""

    def __init__(self, bindings: tuple[ResourceScopeRoleBinding, ...] = ()) -> None:
        self._bindings = {binding.binding_id: binding for binding in bindings}

    def active_bindings(self) -> tuple[ResourceScopeRoleBinding, ...]:
        return tuple(
            binding for binding in self._bindings.values()
            if binding.state is ResourceScopeBindingState.ACTIVE
        )

    def replace(self, binding: ResourceScopeRoleBinding) -> None:
        self._bindings[binding.binding_id] = binding


class ResourceScopeAuthorizationRequest(BaseModel):
    """A request carries a logical scope, action, and authenticated principal only."""

    model_config = ConfigDict(extra="forbid")

    principal: PrincipalReference
    action: ResourceScopeAction
    scope_id: str = Field(min_length=8)
    identity_group_ids: frozenset[str] = Field(default_factory=frozenset)


class ResourceScopeAuthorizationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    matched_binding_ids: tuple[str, ...] = ()


class ResourceScopeAuthorizer:
    """Deterministic v1 allow evaluator; guardrails are evaluated separately."""

    def __init__(
        self, *, registry: ReviewedResourceScopeRegistry,
        bindings: ResourceScopeRoleBindingStore,
        memberships: ActiveOrganizationMembershipLookup,
    ) -> None:
        self._registry = registry
        self._bindings = bindings
        self._memberships = memberships

    def authorize(self, request: ResourceScopeAuthorizationRequest) -> ResourceScopeAuthorizationDecision:
        scope = self._registry.resolve_active(request.scope_id)
        if scope is None or not self._has_active_membership(request.principal, scope):
            return ResourceScopeAuthorizationDecision(allowed=False)
        matched = tuple(
            binding.binding_id for binding in self._bindings.active_bindings()
            if self._binding_allows(binding, request, scope)
        )
        return ResourceScopeAuthorizationDecision(allowed=bool(matched), matched_binding_ids=matched)

    def _has_active_membership(self, principal: PrincipalReference, scope: ResourceScope) -> bool:
        if principal.kind is not PrincipalKind.USER:
            return True
        return self._memberships.get_active_membership(
            user_subject=principal.principal_id, organization_id=scope.organization.organization_id
        ) is not None

    @staticmethod
    def _binding_allows(
        binding: ResourceScopeRoleBinding, request: ResourceScopeAuthorizationRequest, scope: ResourceScope
    ) -> bool:
        if request.action not in binding.actions or not _principal_matches(binding.principal, request):
            return False
        if binding.conditions.environment_ids and scope.environment.environment_id not in binding.conditions.environment_ids:
            return False
        return _target_matches(binding.target, scope)


def _principal_matches(binding_principal: PrincipalReference, request: ResourceScopeAuthorizationRequest) -> bool:
    if binding_principal == request.principal:
        return True
    return (
        binding_principal.kind is PrincipalKind.IDENTITY_GROUP
        and binding_principal.principal_id in request.identity_group_ids
    )


def _target_matches(target: ScopeBindingTarget, scope: ResourceScope) -> bool:
    if target.kind is ScopeBindingTargetKind.SCOPE:
        return target.resource_id == scope.scope_id
    if not target.inherit_to_descendants:
        return False
    ancestor_ids = {
        ScopeBindingTargetKind.ORGANIZATION: scope.organization.organization_id,
        ScopeBindingTargetKind.BUSINESS_UNIT: scope.business_unit.business_unit_id,
        ScopeBindingTargetKind.TEAM: scope.team.team_id,
        ScopeBindingTargetKind.PROJECT: scope.project.project_id,
    }
    return ancestor_ids.get(target.kind) == target.resource_id
