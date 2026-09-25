"""Gateway composition for authenticated `/provision` graph startup."""
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from gateway.command_router import CommandInvocation
from gateway.resource_scope_access import PrincipalKind, PrincipalReference


class ProvisionCommand(BaseModel):
    """Untrusted command payload; cloud-routing values are intentionally absent."""

    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(min_length=8)


class ProvisionWorkflowInvocation(BaseModel):
    """Safe graph input derived by the authenticated gateway boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal: PrincipalReference
    scope_id: str = Field(min_length=8)


class ProvisionGraph(Protocol):
    async def ainvoke(self, input: dict[str, Any]) -> Any: ...


def build_provision_handler(graph: ProvisionGraph):
    """Build a handler that cannot pass session material or routing hints to a graph."""
    async def handle(invocation: CommandInvocation):
        if invocation.principal is None:
            raise PermissionError("validated principal is required")
        command = ProvisionCommand.model_validate(invocation.payload)
        workflow_input = ProvisionWorkflowInvocation(
            principal=PrincipalReference(
                kind=PrincipalKind.USER, principal_id=invocation.principal.subject,
            ),
            scope_id=command.scope_id,
        )
        return await graph.ainvoke({"invocation": workflow_input})

    return handle
