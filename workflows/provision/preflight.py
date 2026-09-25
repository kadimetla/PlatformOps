"""Deterministic Resource Scope authorization and routing preflight."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from gateway.resolved_resource_scope import ResolvedResourceScopeContext
from gateway.resource_scope_access import (
    ResourceScopeAuthorizationRequest,
    ResourceScopeAuthorizer,
)
from gateway.resource_scope_bindings import (
    BindingResolutionStatus,
    ProvisioningBindingProfile,
    ResourceScopeBindingResolver,
)
from gateway.resource_scope_governance import (
    ResourceScopeGovernanceEvaluator,
    ResourceScopeGovernanceRequest,
)
from gateway.resource_scope_registry import ReviewedResourceScopeRegistry


class ProvisionPreflightStatus(str, Enum):
    READY = "ready"
    DENIED = "denied"
    NON_ROUTABLE = "non_routable"


class ProvisionPreflightRequest(BaseModel):
    """Only logical scope, authenticated principal, action, and trusted profile enter preflight."""

    model_config = ConfigDict(extra="forbid")

    authorization: ResourceScopeAuthorizationRequest
    profile: ProvisioningBindingProfile


class ProvisionPreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProvisionPreflightStatus
    resolved_context: ResolvedResourceScopeContext | None = None

    @model_validator(mode="after")
    def _validate_context(self) -> "ProvisionPreflightResult":
        if (self.status is ProvisionPreflightStatus.READY) != (self.resolved_context is not None):
            raise ValueError("only a ready preflight result contains a resolved context")
        return self


class ResourceScopeProvisionPreflight:
    """Evaluates one non-mutating provision request; every failure fails closed."""

    def __init__(
        self,
        *,
        scopes: ReviewedResourceScopeRegistry,
        authorizer: ResourceScopeAuthorizer,
        bindings: ResourceScopeBindingResolver,
        governance: ResourceScopeGovernanceEvaluator,
    ) -> None:
        self._scopes = scopes
        self._authorizer = authorizer
        self._bindings = bindings
        self._governance = governance

    def evaluate(self, request: ProvisionPreflightRequest) -> ProvisionPreflightResult:
        scope = self._scopes.resolve_active(request.authorization.scope_id)
        if scope is None:
            return ProvisionPreflightResult(status=ProvisionPreflightStatus.NON_ROUTABLE)

        authorization = self._authorizer.authorize(request.authorization)
        if not authorization.allowed:
            return ProvisionPreflightResult(status=ProvisionPreflightStatus.DENIED)

        binding = self._bindings.resolve(scope_id=scope.scope_id, profile=request.profile)
        if binding.status is not BindingResolutionStatus.RESOLVED:
            return ProvisionPreflightResult(status=ProvisionPreflightStatus.NON_ROUTABLE)

        governance = self._governance.evaluate(ResourceScopeGovernanceRequest(
            scope=scope,
            provider=binding.binding.provider.value,
            action=request.authorization.action,
            approval_present=False,
        ))
        if not governance.allowed:
            return ProvisionPreflightResult(status=ProvisionPreflightStatus.DENIED)
        return ProvisionPreflightResult(
            status=ProvisionPreflightStatus.READY,
            resolved_context=ResolvedResourceScopeContext.seal(
                scope=scope,
                authorization=authorization,
                governance=governance,
                binding=binding.binding,
            ),
        )
