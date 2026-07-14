"""MCP tool binding for the drafting workflow, via langchain-mcp-adapters
instead of ADK's MCPToolset(StdioServerParameters(...)). Reuses the
exact command/args/env values from mcp_server/external_servers.py --
see openspec/changes/migrate-to-langgraph/design.md's "MCP tools bind
via langchain-mcp-adapters" decision.

Also implements task 3.9 (close the propose-vs-execute gap): the
create/update/delete tools on ccapi-mcp-server and terraform-mcp-server
are filtered out before binding to any LLM in this workflow, so a
provisioning node structurally cannot call them -- propose_tool_intent
(tools.py) is the only path to proposing a mutating operation.

VERIFICATION GAP, stated plainly rather than silently assumed: the
exact mutating tool names below (_CCAPI_MUTATING_TOOLS,
_TERRAFORM_MUTATING_TOOLS) are inferred from this project's prior
research (docs/*.md) on each server's documented tool surface, NOT
independently confirmed by connecting to a live server in this
environment (no AWS/TFE credentials here, same gap
mcp_server/external_servers.py already flags for the Terraform path).
Before this workflow is used against real infrastructure, call
MultiServerMCPClient.get_tools() against the live servers and diff the
result against these denylists.
"""
from typing import Sequence

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from mcp_server.external_servers import (
    AWS_IAC_MCP_SERVER,
    CCAPI_MCP_SERVER,
    TERRAFORM_MCP_SERVER,
)

# aws-iac-mcp-server's full tool surface is read-only/validation only
# (search/read docs, cfn-lint, cfn-guard, troubleshooting) -- verified
# in this project's prior research, no mutating tools exist on this
# server at all. Nothing to filter.
_AWS_IAC_MUTATING_TOOLS: frozenset[str] = frozenset()

# INFERRED, not live-verified (see module docstring). ccapi-mcp-server's
# real tool list is documented as get_resource, list_resources,
# get_resource_schema_information, create_template, get_aws_account_info,
# plus create/update/delete -- these three names are the standard MCP
# naming convention inferred from the other confirmed tool names, not
# independently confirmed.
_CCAPI_MUTATING_TOOLS = frozenset({"create_resource", "update_resource", "delete_resource"})

# terraform-mcp-server's create_run tool covers BOTH plan_and_apply
# (mutating) and refresh_state (read-only) via a run_type parameter --
# there's no clean way to allow one and deny the other at the
# tool-name-filtering level used here, so create_run is excluded
# entirely from this workflow. A future workflows/audit/ drift-sweep
# workflow (docs/request_intent_taxonomy_and_workflow_routing.md) is
# the right place to bind create_run scoped to refresh_state only, not
# this one.
_TERRAFORM_MUTATING_TOOLS = frozenset({"create_run"})


def _to_stdio_connection(server) -> dict:
    """Converts this project's existing StdioServerParameters (ADK) into
    langchain-mcp-adapters' StdioConnection TypedDict shape -- same
    command/args/env, no MCP-server-side changes."""
    return {
        "transport": "stdio",
        "command": server.command,
        "args": server.args,
        "env": server.env,
    }


def build_mcp_client() -> MultiServerMCPClient:
    return MultiServerMCPClient(
        {
            "aws_iac": _to_stdio_connection(AWS_IAC_MCP_SERVER),
            "ccapi": _to_stdio_connection(CCAPI_MCP_SERVER),
            "terraform": _to_stdio_connection(TERRAFORM_MCP_SERVER),
        }
    )


def _filter_mutating(tools: Sequence[BaseTool], mutating_names: frozenset[str]) -> list[BaseTool]:
    return [t for t in tools if t.name not in mutating_names]


async def get_cdk_provisioning_tools(client: MultiServerMCPClient) -> list[BaseTool]:
    """aws-iac-mcp-server (all read-only) + ccapi-mcp-server minus its
    mutating tools -- cdk_provisioning_agent's real tool set today,
    with the create/update/delete path closed per task 3.9."""
    aws_iac_tools = _filter_mutating(await client.get_tools(server_name="aws_iac"), _AWS_IAC_MUTATING_TOOLS)
    ccapi_tools = _filter_mutating(await client.get_tools(server_name="ccapi"), _CCAPI_MUTATING_TOOLS)
    return aws_iac_tools + ccapi_tools


async def get_terraform_provisioning_tools(client: MultiServerMCPClient) -> list[BaseTool]:
    """terraform-mcp-server minus create_run entirely (task 3.9) --
    every other tool on this server is retained."""
    return _filter_mutating(await client.get_tools(server_name="terraform"), _TERRAFORM_MUTATING_TOOLS)
