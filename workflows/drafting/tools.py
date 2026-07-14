"""propose_tool_intent -- the structured escape hatch a drafting/
provisioning node calls instead of a real mutating MCP tool. Its
*execution* is a pure no-op (never touches real infrastructure); the
point is the tool CALL itself, which plan_request() harvests from the
final graph state's message history after the run completes -- same
two-pass discipline gateway/plan_request.py already uses (collect raw
args, construct ToolIntent objects only once plan_hash is known).

See openspec/changes/migrate-to-langgraph/specs/langgraph-agent-runtime/
spec.md's "Provisioning nodes never call mutating MCP tools directly"
requirement -- this is the tool task 3.9's rewiring routes mutating
calls through, instead of CCAPI_MCP_SERVER/TERRAFORM_MCP_SERVER's
create/update/delete tools.
"""
from typing import Any, Dict

from langchain_core.tools import tool


@tool
def propose_tool_intent(
    intent_id: str,
    resource_type: str,
    resource_identifier: str,
    operation: str,
    region: str,
    estimated_monthly_cost: float,
    payload: Dict[str, Any],
) -> str:
    """Propose a single mutating cloud operation for later human/agent
    approval and dispatch. Does NOT create, update, or delete anything
    itself -- calling this tool is the entire action; it never reaches
    a real cloud API. resource_type must be a CloudFormation-style type
    (e.g. 'AWS::S3::Bucket'). operation must be 'CreateResource',
    'UpdateResource', or 'DeleteResource'.
    """
    return f"Proposed {operation} for {resource_type} '{resource_identifier}' (intent_id={intent_id})."
