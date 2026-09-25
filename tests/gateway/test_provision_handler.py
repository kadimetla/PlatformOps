import asyncio

import pytest
from pydantic import ValidationError

from gateway.command_router import (
    CommandAuthenticationRequired, ControlPlaneCommandRouter, ValidatedPrincipal,
)
from gateway.provision_handler import (
    ProvisionCommand, ProvisionWorkflowInvocation, build_provision_handler,
)
from gateway.resource_scope_access import PrincipalKind


class CaptureGraph:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def ainvoke(self, input: dict):
        self.calls.append(input)
        return {"started": True}


def _router(graph: CaptureGraph) -> ControlPlaneCommandRouter:
    return ControlPlaneCommandRouter({"provision": build_provision_handler(graph)})


def test_provision_route_requires_a_validated_session_before_graph_startup():
    graph = CaptureGraph()

    with pytest.raises(CommandAuthenticationRequired):
        asyncio.run(_router(graph).dispatch("/provision", {"scope_id": "scope_checkout_prod"}, principal=None))

    assert graph.calls == []


def test_provision_gateway_passes_only_safe_principal_reference_and_scope_id_to_graph():
    graph = CaptureGraph()

    result = asyncio.run(_router(graph).dispatch(
        "/provision", {"scope_id": "scope_checkout_prod"},
        principal=ValidatedPrincipal(issuer="platformops", subject="usr_alice"),
    ))

    assert result == {"started": True}
    workflow_input = graph.calls[0]["invocation"]
    assert workflow_input == ProvisionWorkflowInvocation(
        principal={"kind": PrincipalKind.USER, "principal_id": "usr_alice"},
        scope_id="scope_checkout_prod",
    )
    assert "issuer" not in type(workflow_input.principal).model_fields
    assert set(ProvisionWorkflowInvocation.model_fields) == {"principal", "scope_id"}


def test_provision_payload_rejects_session_material_and_client_cloud_routing_hints():
    forbidden = {
        "token": "browser-jwt", "credential": "secret", "provider": "gcp",
        "account_id": "attacker-account", "binding_id": "binding_attacker",
        "execution_identity_reference": "attacker-identity", "provider_workspace": "attacker-workspace",
    }
    for field, value in forbidden.items():
        with pytest.raises(ValidationError, match="Extra inputs"):
            ProvisionCommand.model_validate({"scope_id": "scope_checkout_prod", field: value})
