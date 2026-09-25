from datetime import datetime, timezone

import pytest

from gateway.provision_execution import ProvisionExecutionDenied, ProvisionExecutionGate, ProvisionExecutionStatus
from gateway.provision_plan import ProvisionApprovalDigest, ProvisionPlanInputs, SealedProvisionPlan, TrustedProvisionPolicy
from gateway.resolved_resource_scope import ResolvedResourceScopeContext
from gateway.resource_scope_access import ResourceScopeAuthorizationDecision
from gateway.resource_scope_bindings import CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState
from gateway.resource_scope_governance import ResourceScopeGovernanceDecision
from gateway.resource_scope_registry import BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope, ResourceScopeState, Team


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, plan: SealedProvisionPlan) -> None:
        self.calls.append(plan.plan_digest)


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

    evidence = ProvisionExecutionGate(executor).execute(
        plan=plan, approval=ProvisionApprovalDigest.for_plan(plan), scope=scope, bindings=(binding,),
        now=datetime(2026, 9, 25, tzinfo=timezone.utc),
    )

    assert executor.calls == [plan.plan_digest]
    assert evidence.status is ProvisionExecutionStatus.SUCCEEDED
    assert evidence.binding_ids == (binding.binding_id,)
    assert not {"credential", "token", "provider_output"} & set(type(evidence).model_fields)


def test_execution_gate_denies_bad_approval_or_binding_drift_without_calling_executor():
    plan, scope, binding = _plan()
    executor = FakeExecutor()
    gate = ProvisionExecutionGate(executor)

    with pytest.raises(ProvisionExecutionDenied, match="approval"):
        gate.execute(
            plan=plan, approval=ProvisionApprovalDigest(plan_digest="0" * 64, approval_digest=plan.approval_digest),
            scope=scope, bindings=(binding,),
        )
    with pytest.raises(ProvisionExecutionDenied, match="context changed"):
        gate.execute(
            plan=plan, approval=ProvisionApprovalDigest.for_plan(plan), scope=scope,
            bindings=(binding.model_copy(update={"state": ProviderBindingState.SUSPENDED}),),
        )
    assert executor.calls == []
