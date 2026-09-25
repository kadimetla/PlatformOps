"""Immutable authorization and routing snapshot for a provision operation."""
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from gateway.resource_scope_access import ResourceScopeAuthorizationDecision
from gateway.resource_scope_bindings import CloudResourceContainerBinding, ProviderBindingState
from gateway.resource_scope_governance import ResourceScopeGovernanceDecision
from gateway.resource_scope_registry import ResourceScope


class ResolvedBindingVersion(BaseModel):
    """The binding identity and version selected during one authorization decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    binding_id: str = Field(min_length=10)
    version: int = Field(ge=1)


class ResolvedResourceScopeContext(BaseModel):
    """Sealed, immutable context; it is not a reusable authorization grant."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str = Field(min_length=8)
    canonical_path: str = Field(min_length=1)
    scope_version: int = Field(ge=1)
    binding_versions: tuple[ResolvedBindingVersion, ...] = Field(min_length=1)
    matched_grant_ids: tuple[str, ...] = ()
    matched_guardrail_ids: tuple[str, ...] = ()
    resolution_digest: str = Field(min_length=64, max_length=64)

    @property
    def binding_ids(self) -> tuple[str, ...]:
        return tuple(binding.binding_id for binding in self.binding_versions)

    @model_validator(mode="after")
    def _validate_digest_and_binding_ids(self) -> "ResolvedResourceScopeContext":
        if len(set(self.binding_ids)) != len(self.binding_ids):
            raise ValueError("resolved binding IDs must be unique")
        if self.resolution_digest != _digest_context(self):
            raise ValueError("resolved context digest does not match its sealed contents")
        return self

    @classmethod
    def seal(
        cls,
        *,
        scope: ResourceScope,
        authorization: ResourceScopeAuthorizationDecision,
        governance: ResourceScopeGovernanceDecision,
        binding: CloudResourceContainerBinding,
    ) -> "ResolvedResourceScopeContext":
        """Capture only a successful current evaluation; failures cannot be sealed."""
        if not scope.is_complete_and_active:
            raise ValueError("only an active complete Resource Scope can be sealed")
        if not authorization.allowed or not governance.allowed:
            raise ValueError("only an allowed authorization and governance decision can be sealed")
        if binding.scope_id != scope.scope_id or binding.state is not ProviderBindingState.ACTIVE:
            raise ValueError("only an active binding for the resolved Resource Scope can be sealed")
        contents = {
            "scope_id": scope.scope_id,
            "canonical_path": scope.canonical_path,
            "scope_version": scope.version,
            "binding_versions": (ResolvedBindingVersion(binding_id=binding.binding_id, version=binding.version),),
            "matched_grant_ids": authorization.matched_binding_ids,
            "matched_guardrail_ids": governance.matched_policy_targets,
        }
        return cls(**contents, resolution_digest=_digest_values(**contents))


def requires_fresh_resolution(
    context: ResolvedResourceScopeContext,
    *,
    scope: ResourceScope | None,
    bindings: tuple[CloudResourceContainerBinding, ...],
) -> bool:
    """Return true when current registry records differ from a sealed context."""
    if scope is None or not scope.is_complete_and_active:
        return True
    if (
        scope.scope_id != context.scope_id
        or scope.canonical_path != context.canonical_path
        or scope.version != context.scope_version
    ):
        return True
    current_versions = {
        binding.binding_id: binding.version
        for binding in bindings
        if binding.scope_id == scope.scope_id and binding.state is ProviderBindingState.ACTIVE
    }
    return any(current_versions.get(snapshot.binding_id) != snapshot.version for snapshot in context.binding_versions)


def _digest_context(context: ResolvedResourceScopeContext) -> str:
    return _digest_values(
        scope_id=context.scope_id,
        canonical_path=context.canonical_path,
        scope_version=context.scope_version,
        binding_versions=context.binding_versions,
        matched_grant_ids=context.matched_grant_ids,
        matched_guardrail_ids=context.matched_guardrail_ids,
    )


def _digest_values(
    *,
    scope_id: str,
    canonical_path: str,
    scope_version: int,
    binding_versions: tuple[ResolvedBindingVersion, ...],
    matched_grant_ids: tuple[str, ...],
    matched_guardrail_ids: tuple[str, ...],
) -> str:
    values = (
        scope_id,
        canonical_path,
        str(scope_version),
        *(f"{binding.binding_id}:{binding.version}" for binding in binding_versions),
        *(f"grant:{grant_id}" for grant_id in matched_grant_ids),
        *(f"guardrail:{guardrail_id}" for guardrail_id in matched_guardrail_ids),
    )
    return sha256("\x1f".join(values).encode()).hexdigest()
