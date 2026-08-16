from gateway.auth.schemas import Capability, ExecutionGrant
from gateway.dispatcher import (
    KNOWN_WORKSPACES,
    ROUTE_REGISTRY,
    check_tenant_policy,
    resolve_route_id,
)
from gateway.policy.ceiling import resolve_execution_capability
from gateway.schemas import Intent, Scope


def test_authorized_tenant_and_registered_route_resolve_to_a_handler():
    assert resolve_route_id(Intent.PROVISION) == "provision"
    assert check_tenant_policy("aiq:it", Intent.PROVISION) is True
    assert "provision" in ROUTE_REGISTRY


def test_no_execution_grant_fails_the_target_access_gate():
    scope = KNOWN_WORKSPACES[0]
    capability = resolve_execution_capability(scope, grants=[])
    assert capability == Capability.NONE


def test_execution_grant_for_the_known_workspace_authorizes_it():
    scope = KNOWN_WORKSPACES[0]
    grant = ExecutionGrant(scope=scope, provider="aws", capability=Capability.APPLY_LIMITED)
    capability = resolve_execution_capability(scope, grants=[grant])
    assert capability == Capability.APPLY_LIMITED


def test_unregistered_route_has_no_handler():
    assert resolve_route_id(Intent.INQUIRY) is None  # no route table entry at all
    assert "inquiry" not in ROUTE_REGISTRY


def test_unknown_tenant_fails_closed_not_open():
    assert check_tenant_policy("efx:finance", Intent.PROVISION) is False


def test_compliance_check_route_has_no_registered_handler_by_design():
    """gateway/dispatcher.py's ROUTE_REGISTRY intentionally starts with
    only "provision" -- compliance_check resolves a route but must not
    be dispatched to automatically; see the module docstring."""
    assert resolve_route_id(Intent.COMPLIANCE_CHECK) == "compliance_check"
    assert "compliance_check" not in ROUTE_REGISTRY
