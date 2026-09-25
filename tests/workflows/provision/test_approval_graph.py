import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from gateway.provision_plan import ProvisionPlanInputs, SealedProvisionPlan, TrustedProvisionPolicy
from gateway.resolved_resource_scope import ResolvedResourceScopeContext
from gateway.resource_scope_access import (
    InMemoryResourceScopeRoleBindingStore, PrincipalKind, PrincipalReference, ResourceScopeAction,
    ResourceScopeAuthorizer, ResourceScopeRoleBinding, ScopeBindingTarget, ScopeBindingTargetKind,
)
from gateway.resource_scope_bindings import (
    CloudProvider, CloudResourceContainerBinding, CloudResourceContainerType, ProviderBindingState,
)
from gateway.resource_scope_governance import ResourceScopeGovernanceDecision
from gateway.resource_scope_registry import (
    BusinessUnit, Environment, InMemoryReviewedResourceScopeRegistry, Organization,
    PlatformOpsProject, ResourceScope, ResourceScopeState, Team,
)
from gateway.resource_scope_access import ResourceScopeAuthorizationDecision
from workflows.provision.approval_graph import ProvisionApprovalDenied, build_provision_approval_graph


class Memberships:
    def get_active_membership(self, *, user_subject: str, organization_id: str):
        return object() if organization_id == "org_acme" and user_subject in {"usr_alice", "usr_bob"} else None


def _scope() -> ResourceScope:
    state = ResourceScopeState.ACTIVE
    return ResourceScope(
        scope_id="scope_checkout_prod", organization=Organization(organization_id="org_acme", slug="acme", state=state),
        business_unit=BusinessUnit(business_unit_id="bu_commerce", organization_id="org_acme", slug="commerce", state=state),
        team=Team(team_id="team_payments", business_unit_id="bu_commerce", slug="payments", state=state),
        project=PlatformOpsProject(project_id="project_checkout", team_id="team_payments", slug="checkout", state=state),
        environment=Environment(environment_id="env_prod", project_id="project_checkout", slug="prod", state=state), state=state,
    )


def _plan(scope: ResourceScope) -> SealedProvisionPlan:
    context = ResolvedResourceScopeContext.seal(
        scope=scope,
        authorization=ResourceScopeAuthorizationDecision(allowed=True, matched_binding_ids=("scopebind_request",)),
        governance=ResourceScopeGovernanceDecision(allowed=True),
        binding=CloudResourceContainerBinding(
            binding_id="binding_checkout_prod", scope_id=scope.scope_id, provider=CloudProvider.AWS,
            container_type=CloudResourceContainerType.AWS_ACCOUNT, container_reference="123456789012",
            execution_identity_reference="iam-role:platformops-exec", state=ProviderBindingState.ACTIVE,
        ),
    )
    return SealedProvisionPlan.seal(
        context=context, policy=TrustedProvisionPolicy(profile_id="aws-static-web", version=1),
        inputs=ProvisionPlanInputs(values={"frontend_hostname": "checkout.example.com"}),
    )


def _graph(*, approver_granted: bool = True):
    scope = _scope()
    registry = InMemoryReviewedResourceScopeRegistry()
    registry.register_reviewed(scope)
    bindings = () if not approver_granted else (ResourceScopeRoleBinding(
        binding_id="scopebind_bob_approve", principal=PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_bob"),
        actions=frozenset({ResourceScopeAction.APPROVE_PROVISION}),
        target=ScopeBindingTarget(kind=ScopeBindingTargetKind.SCOPE, resource_id=scope.scope_id),
    ),)
    authorizer = ResourceScopeAuthorizer(
        registry=registry, bindings=InMemoryResourceScopeRoleBindingStore(bindings), memberships=Memberships(),
    )
    return build_provision_approval_graph(authorizer=authorizer).compile(checkpointer=MemorySaver()), _plan(scope)


def _start(graph, plan, thread_id="approval-test"):
    return graph.invoke({
        "plan": plan, "requester": PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice"),
        "reviewer": None, "approved": None,
    }, config={"configurable": {"thread_id": thread_id}})


def test_approval_graph_checkpoints_then_accepts_distinct_authorized_reviewer():
    graph, plan = _graph()
    paused = _start(graph, plan)
    assert paused["__interrupt__"]

    resumed = graph.invoke(Command(
        resume={"verdict": "approve", "plan_digest": plan.plan_digest, "approval_digest": plan.approval_digest},
        update={"reviewer": PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_bob")},
    ), config={"configurable": {"thread_id": "approval-test"}})
    assert resumed["approved"] is True


def test_approval_graph_rejects_self_approval_and_mismatched_digest():
    graph, plan = _graph()
    _start(graph, plan, "self")
    with pytest.raises(ProvisionApprovalDenied, match="cannot approve"):
        graph.invoke(Command(
            resume={"verdict": "approve", "plan_digest": plan.plan_digest, "approval_digest": plan.approval_digest},
            update={"reviewer": PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_alice")},
        ), config={"configurable": {"thread_id": "self"}})

    graph, plan = _graph()
    _start(graph, plan, "digest")
    with pytest.raises(ProvisionApprovalDenied, match="does not match"):
        graph.invoke(Command(
            resume={"verdict": "approve", "plan_digest": "0" * 64, "approval_digest": plan.approval_digest},
            update={"reviewer": PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_bob")},
        ), config={"configurable": {"thread_id": "digest"}})


def test_approval_graph_rejects_reviewer_without_active_approver_grant():
    graph, plan = _graph(approver_granted=False)
    _start(graph, plan, "denied")

    with pytest.raises(ProvisionApprovalDenied, match="lacks provision"):
        graph.invoke(Command(
            resume={"verdict": "approve", "plan_digest": plan.plan_digest, "approval_digest": plan.approval_digest},
            update={"reviewer": PrincipalReference(kind=PrincipalKind.USER, principal_id="usr_bob")},
        ), config={"configurable": {"thread_id": "denied"}})
