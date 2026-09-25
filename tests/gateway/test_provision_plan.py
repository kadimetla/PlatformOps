import pytest
from pydantic import ValidationError

from gateway.provision_plan import (
    ProvisionApprovalDigest, ProvisionPlanInputs, SealedProvisionPlan, TrustedProvisionPolicy,
)
from gateway.resolved_resource_scope import ResolvedResourceScopeContext
from gateway.resource_scope_access import ResourceScopeAuthorizationDecision
from gateway.resource_scope_bindings import (
    CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState,
)
from gateway.resource_scope_governance import ResourceScopeGovernanceDecision
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, Organization, PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)


def _context() -> ResolvedResourceScopeContext:
    state = ResourceScopeState.ACTIVE
    scope = ResourceScope(
        scope_id="scope_checkout_prod",
        organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(
            business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state,
        ),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(
            project_id="project_checkout", team_id="team_payments", slug="checkout", state=state,
        ),
        environment=Environment(
            environment_id="env_prod", project_id="project_checkout", slug="prod", state=state,
        ),
        state=state,
    )
    binding = CloudResourceContainerBinding(
        binding_id="binding_checkout_prod", scope_id=scope.scope_id,
        provider=CloudProvider.AWS, container_type=CloudResourceContainerType.AWS_ACCOUNT,
        container_reference="123456789012", execution_identity_reference="iam-role:platformops-exec",
        state=ProviderBindingState.ACTIVE,
    )
    return ResolvedResourceScopeContext.seal(
        scope=scope,
        authorization=ResourceScopeAuthorizationDecision(allowed=True, matched_binding_ids=("scopebind_alice",)),
        governance=ResourceScopeGovernanceDecision(allowed=True), binding=binding,
    )


def _plan(*, policy_version: int = 1, hostname: str = "checkout.example.com") -> SealedProvisionPlan:
    return SealedProvisionPlan.seal(
        context=_context(),
        policy=TrustedProvisionPolicy(profile_id="aws-static-web", version=policy_version),
        inputs=ProvisionPlanInputs(values={
            "frontend_artifact_uri": "s3://releases/checkout.tar.gz",
            "frontend_hostname": hostname,
        }),
    )


def test_plan_seal_deterministically_binds_inputs_policy_and_resolved_context():
    first = _plan()
    second = _plan()

    assert first == second
    assert first.plan_digest != _plan(hostname="other.example.com").plan_digest
    assert first.plan_digest != _plan(policy_version=2).plan_digest
    assert set(SealedProvisionPlan.model_fields) == {
        "context", "policy", "inputs", "plan_digest", "approval_digest",
    }


def test_approval_must_match_the_exact_sealed_plan_and_policy_version():
    original = _plan()
    approval = ProvisionApprovalDigest.for_plan(original)

    assert approval.matches(original) is True
    assert approval.matches(_plan(policy_version=2)) is False
    assert approval.matches(_plan(hostname="other.example.com")) is False
    assert ProvisionApprovalDigest(
        plan_digest=original.plan_digest, approval_digest="0" * 64,
    ).matches(original) is False


def test_tampered_sealed_plan_is_rejected():
    plan = _plan()

    with pytest.raises(ValidationError, match="does not match"):
        SealedProvisionPlan.model_validate({**plan.model_dump(), "plan_digest": "0" * 64})
