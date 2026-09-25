"""Restrictive, typed governance guardrails for a Resource Scope hierarchy."""
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.resource_scope_access import ResourceScopeAction, ScopeBindingTargetKind
from gateway.resource_scope_registry import ResourceScope


class ResourceScopeGovernancePolicy(BaseModel):
    """A fixed v1 guardrail surface; children may only narrow effective policy."""

    model_config = ConfigDict(extra="forbid")

    target_kind: ScopeBindingTargetKind
    target_id: str = Field(min_length=1)
    allowed_providers: frozenset[str] = Field(default_factory=frozenset)
    denied_actions: frozenset[ResourceScopeAction] = Field(default_factory=frozenset)
    require_approval_for_provision: bool = False


class ResourceScopeGovernancePolicyStore(Protocol):
    def applicable_policies(self, scope: ResourceScope) -> tuple[ResourceScopeGovernancePolicy, ...]: ...


class InMemoryResourceScopeGovernancePolicyStore:
    def __init__(self, policies: tuple[ResourceScopeGovernancePolicy, ...] = ()) -> None:
        self._policies = policies

    def applicable_policies(self, scope: ResourceScope) -> tuple[ResourceScopeGovernancePolicy, ...]:
        hierarchy = {
            (ScopeBindingTargetKind.ORGANIZATION, scope.organization.organization_id),
            (ScopeBindingTargetKind.BUSINESS_UNIT, scope.business_unit.business_unit_id),
            (ScopeBindingTargetKind.TEAM, scope.team.team_id),
            (ScopeBindingTargetKind.PROJECT, scope.project.project_id),
            (ScopeBindingTargetKind.ENVIRONMENT, scope.environment.environment_id),
            (ScopeBindingTargetKind.SCOPE, scope.scope_id),
        }
        return tuple(policy for policy in self._policies if (policy.target_kind, policy.target_id) in hierarchy)


class ResourceScopeGovernanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: ResourceScope
    provider: str = Field(min_length=1)
    action: ResourceScopeAction
    approval_present: bool = False


class ResourceScopeGovernanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    matched_policy_targets: tuple[str, ...] = ()


class ResourceScopeGovernanceEvaluator:
    def __init__(self, policies: ResourceScopeGovernancePolicyStore) -> None:
        self._policies = policies

    def evaluate(self, request: ResourceScopeGovernanceRequest) -> ResourceScopeGovernanceDecision:
        policies = self._policies.applicable_policies(request.scope)
        matched = tuple(f"{policy.target_kind.value}:{policy.target_id}" for policy in policies)
        if any(request.action in policy.denied_actions for policy in policies):
            return ResourceScopeGovernanceDecision(allowed=False, matched_policy_targets=matched)
        restrictions = [policy.allowed_providers for policy in policies if policy.allowed_providers]
        if restrictions and request.provider not in set.intersection(*map(set, restrictions)):
            return ResourceScopeGovernanceDecision(allowed=False, matched_policy_targets=matched)
        if (
            request.action is ResourceScopeAction.REQUEST_PROVISION
            and any(policy.require_approval_for_provision for policy in policies)
            and not request.approval_present
        ):
            return ResourceScopeGovernanceDecision(allowed=False, matched_policy_targets=matched)
        return ResourceScopeGovernanceDecision(allowed=True, matched_policy_targets=matched)
