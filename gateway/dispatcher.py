"""Trusted route IDs -> callables, plus the tenant policy gate --
INTAKE_HITL_ROUTING.md: "the current private _ROUTE_TABLE moves to
gateway/dispatcher.py: a registry of trusted route IDs to callables
plus tenant policy, never model-emitted module paths."

Two gates, deliberately kept separate (that doc's own framing):
  tenant route gate:  check_tenant_policy(org_bu, intent)
  target access gate: effective_access(...) -- gateway/policy/ceiling.py,
                       evaluated inside workflows/provision itself via
                       gateway.scope.resolve_scope's execution-grant
                       check, not duplicated here.

ROUTE_REGISTRY intentionally starts with only "provision" registered.
compliance_check keeps resolving a route (workflows/intake/nodes.py)
without a registered handler here -- harness/core.py must keep
reporting that case exactly as it does today (route resolved, nothing
invoked); reinterpreting "no registered handler" as unsupported would
regress a real, currently-passing behavior. Adding
spec/check_compliance.py's actual invocation is a separate, untouched
gap.
"""
from typing import Callable

from gateway.schemas import Intent, Scope
from workflows.provision.graph import prepare_provision_request

_ROUTE_TABLE: dict[Intent, str] = {
    Intent.COMPLIANCE_CHECK: "compliance_check",
    Intent.PROVISION: "provision",
}


def resolve_route_id(intent: Intent) -> str | None:
    return _ROUTE_TABLE.get(intent)


# Testable seam, not final schema -- same honesty already used for
# tests/workflows/provision/test_prepare_request.py's known_workspaces.
# Real shape lands with Phase 2's YAML-backed WorkspaceRecord registry.
_TENANT_POLICY: dict[tuple[str, Intent], bool] = {
    ("aiq:it", Intent.PROVISION): True,
}


def check_tenant_policy(org_bu: str, intent: Intent) -> bool:
    """Deny by default -- an absent (org_bu, intent) entry is never
    treated as allowed."""

    return _TENANT_POLICY.get((org_bu, intent), False)


# Same fixture-not-registry honesty as _TENANT_POLICY above.
KNOWN_WORKSPACES: list[Scope] = [
    Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
]


ROUTE_REGISTRY: dict[str, Callable] = {
    "provision": prepare_provision_request,
}
