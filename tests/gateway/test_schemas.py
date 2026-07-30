from datetime import datetime, timezone

from gateway.schemas import ApprovalGrant, Capability, Actor, ExecutionGrant, Scope


def test_capability_order_matches_the_ladder():
    assert list(Capability) == [
        Capability.NONE,
        Capability.DESCRIBE,
        Capability.PLAN,
        Capability.PROPOSE_CHANGE,
        Capability.APPLY_LIMITED,
        Capability.APPLY_FULL,
        Capability.ADMIN,
    ]


def test_min_picks_the_lower_capability():
    assert min(Capability.APPLY_LIMITED, Capability.DESCRIBE) == Capability.DESCRIBE
    assert min(Capability.NONE, Capability.ADMIN) == Capability.NONE


def test_comparison_operators_are_rank_based_not_lexicographic():
    # admin < describe lexicographically ("a" < "d"), but admin is the
    # HIGHEST capability -- this is exactly the bug functools.total_ordering
    # silently produced when combined with the str mixin.
    assert Capability.APPLY_LIMITED >= Capability.PLAN
    assert not (Capability.ADMIN <= Capability.APPLY_FULL)
    assert Capability.DESCRIBE > Capability.NONE
    assert Capability.NONE < Capability.DESCRIBE


def test_capability_value_serializes_as_readable_string():
    assert Capability.APPLY_LIMITED.value == "apply_limited"
    assert isinstance(Capability.APPLY_LIMITED.value, str)


def test_execution_grant_nests_scope():
    grant = ExecutionGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        provider="aws",
        capability=Capability.APPLY_LIMITED,
    )
    assert grant.scope.org_bu == "aiq:it"
    assert grant.capability == Capability.APPLY_LIMITED


def test_approval_grant_has_no_provider_field():
    grant = ApprovalGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        max_capability=Capability.APPLY_LIMITED,
    )
    assert grant.scope.org_bu == "aiq:it"
    assert not hasattr(grant, "provider")


def test_actor_carries_both_grant_sets_independently():
    dev_grant = ExecutionGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
        provider="aws",
        capability=Capability.APPLY_LIMITED,
    )
    prod_approval = ApprovalGrant(
        scope=Scope(org="aiq", bu="it", project="invoices", workspace="prod"),
        max_capability=Capability.APPLY_LIMITED,
    )
    actor = Actor(
        user_id="00u1",
        email="alice@example.com",
        execution_grants=[dev_grant],
        approval_grants=[prod_approval],
        resolved_at=datetime.now(timezone.utc),
    )
    assert len(actor.execution_grants) == 1
    assert len(actor.approval_grants) == 1
    assert actor.execution_grants[0].scope.workspace == "dev"
    assert actor.approval_grants[0].scope.workspace == "prod"
