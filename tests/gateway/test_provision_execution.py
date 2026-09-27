from datetime import datetime, timezone

import pytest

from gateway.provision_execution import ProvisionExecutionDenied, ProvisionExecutionGate, ProvisionExecutionStatus
from gateway.provision_plan import ProvisionApprovalDigest, ProvisionPlanInputs, SealedProvisionPlan, TrustedProvisionPolicy
from gateway.resolved_resource_scope import ResolvedResourceScopeContext
from gateway.resource_scope_access import PrincipalKind, PrincipalReference, ResourceScopeAuthorizationDecision
from gateway.resource_scope_bindings import CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState
from gateway.resource_scope_governance import (
    InMemoryResourceScopeGovernancePolicyStore,
    ResourceScopeGovernanceDecision,
    ResourceScopeGovernanceEvaluator,
    ResourceScopeGovernancePolicy,
)
from gateway.resource_scope_registry import BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope, ResourceScopeState, Team


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, plan: SealedProvisionPlan) -> None:
        self.calls.append(plan.plan_digest)


class ApprovalReceipts:
    def __init__(self, approval: ProvisionApprovalDigest | None) -> None:
        self.approval = approval

    def find_active_by_plan_digest(self, *, plan_digest: str) -> ProvisionApprovalDigest | None:
        return self.approval if self.approval and self.approval.plan_digest == plan_digest else None


def _governance(*policies: ResourceScopeGovernancePolicy) -> ResourceScopeGovernanceEvaluator:
    return ResourceScopeGovernanceEvaluator(InMemoryResourceScopeGovernancePolicyStore(policies))


def _approval(plan: SealedProvisionPlan) -> ProvisionApprovalDigest:
    return ProvisionApprovalDigest.for_plan(
        plan, approved_by=PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_bob")
    )


def _scope_and_binding() -> tuple[ResourceScope, CloudResourceContainerBinding]:
    state = ResourceScopeState.ACTIVE
    scope = ResourceScope(
        scope_id="scope_checkout_prod", organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(project_id="project_checkout", team_id="team_payments", slug="checkout", state=state),
        environment=Environment(environment_id="env_prod", project_id="project_checkout", slug="prod", state=state), state=state,
    )
    return scope, CloudResourceContainerBinding(
        binding_id="binding_checkout_prod", scope_id=scope.scope_id, provider=CloudProvider.AWS,
        container_type=CloudResourceContainerType.AWS_ACCOUNT, container_reference="123456789012",
        execution_identity_reference="iam-role:platformops-exec", state=ProviderBindingState.ACTIVE,
    )


def _plan() -> tuple[SealedProvisionPlan, ResourceScope, CloudResourceContainerBinding]:
    scope, binding = _scope_and_binding()
    context = ResolvedResourceScopeContext.seal(
        scope=scope, authorization=ResourceScopeAuthorizationDecision(allowed=True),
        governance=ResourceScopeGovernanceDecision(allowed=True), binding=binding,
    )
    return SealedProvisionPlan.seal(
        context=context, policy=TrustedProvisionPolicy(profile_id="aws-static-web", version=1),
        inputs=ProvisionPlanInputs(values={"frontend_hostname": "checkout.example.com"}),
    ), scope, binding


def test_execution_gate_calls_only_injected_executor_after_matching_approval_and_fresh_context():
    plan, scope, binding = _plan()
    executor = FakeExecutor()

    evidence = ProvisionExecutionGate(executor, governance=_governance(), approvals=ApprovalReceipts(_approval(plan))).execute(
        plan=plan, scope=scope, bindings=(binding,),
        now=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )

    assert executor.calls == [plan.plan_digest]
    assert evidence.status is ProvisionExecutionStatus.SUCCEEDED
    assert evidence.binding_ids == (binding.binding_id,)
    assert not {"credential", "token", "provider_output"} & set(type(evidence).model_fields)


def test_execution_gate_denies_bad_approval_or_binding_drift_without_calling_executor():
    plan, scope, binding = _plan()
    executor = FakeExecutor()
    gate = ProvisionExecutionGate(executor, governance=_governance(), approvals=ApprovalReceipts(None))

    with pytest.raises(ProvisionExecutionDenied, match="approval"):
        gate.execute(
            plan=plan, scope=scope, bindings=(binding,),
        )
    with pytest.raises(ProvisionExecutionDenied, match="context changed"):
        ProvisionExecutionGate(executor, governance=_governance(), approvals=ApprovalReceipts(_approval(plan))).execute(
            plan=plan, scope=scope,
            bindings=(binding.model_copy(update={"state": ProviderBindingState.SUSPENDED}),),
        )
    assert executor.calls == []


def test_execution_gate_rechecks_current_governance_with_the_recorded_approval_present():
    plan, scope, binding = _plan()
    executor = FakeExecutor()
    approval_policy = ResourceScopeGovernancePolicy(
        target_kind="environment",
        target_id=scope.environment.environment_id,
        require_approval_for_provision=True,
    )
    evidence = ProvisionExecutionGate(executor, governance=_governance(approval_policy), approvals=ApprovalReceipts(_approval(plan))).execute(
        plan=plan, scope=scope, bindings=(binding,),
    )

    assert evidence.status is ProvisionExecutionStatus.SUCCEEDED
    assert executor.calls == [plan.plan_digest]


def test_execution_gate_denies_when_current_governance_has_changed():
    plan, scope, binding = _plan()
    executor = FakeExecutor()
    denied_policy = ResourceScopeGovernancePolicy(
        target_kind="environment",
        target_id=scope.environment.environment_id,
        denied_actions=frozenset({"provision_request"}),
    )

    with pytest.raises(ProvisionExecutionDenied, match="current governance"):
        ProvisionExecutionGate(executor, governance=_governance(denied_policy), approvals=ApprovalReceipts(_approval(plan))).execute(
            plan=plan, scope=scope, bindings=(binding,),
        )

    assert executor.calls == []
