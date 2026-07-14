"""Node functions for the drafting workflow's StateGraph -- mirrors
agents/orchestrator.py's routing shape (task 3.1) plus security_agent
as a separate graph node (task 3.2), reusing langgraph.prebuilt's
create_react_agent for the tool-calling loop rather than hand-rolling
one, consistent with "MCP tool support first-class" already established
for this migration.

DESIGN NOTE on toolchain routing: agents/provisioning_agent.py's
original instruction has an LLM sub-agent read the "provision-infra"
skill's Step 0 to decide cdk vs terraform. Made deterministic here
instead -- route_toolchain() reads an explicit spec["toolchain"] field
if present, defaulting to "cdk" (matching PlanRecord.toolchain's own
hardcoded "cdk" default in today's gateway/plan_request.py). A plain
field read doesn't need an LLM call; this is a deliberate simplification,
not an oversight -- flagged for confirmation as part of this apply run.
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from workflows.drafting.mcp_tools import get_cdk_provisioning_tools, get_terraform_provisioning_tools
from workflows.drafting.model_config import get_model
from workflows.drafting.security_tools import record_security_decision
from workflows.drafting.state import DraftingState
from workflows.drafting.tools import propose_tool_intent


def route_toolchain(state: DraftingState) -> dict:
    """Deterministic toolchain routing -- see module docstring."""
    toolchain = state["spec"].get("toolchain", "cdk")
    if toolchain not in ("cdk", "terraform"):
        toolchain = "cdk"
    return {"toolchain": toolchain}


def toolchain_edge(state: DraftingState) -> str:
    """Conditional-edge selector reading the state route_toolchain wrote."""
    return state["toolchain"]


async def cdk_provisioning_node(state: DraftingState, client: MultiServerMCPClient) -> dict:
    """Mirrors cdk_provisioning_agent: aws-iac-mcp-server (read-only) +
    ccapi-mcp-server minus mutating tools (mcp_tools.py) +
    propose_tool_intent -- never a direct create/update/delete call."""
    tools = await get_cdk_provisioning_tools(client)
    tools.append(propose_tool_intent)
    agent = create_react_agent(
        model=get_model("execution"),
        tools=tools,
        prompt=(
            "Follow the 'provision-infra' skill's Path A (cdk). Use "
            "aws-iac-mcp-server's tools to draft and validate a CloudFormation "
            "template (cfn-lint, cfn-guard) before proposing any change. "
            "Never call a ccapi-mcp-server create/update/delete tool directly -- "
            "propose every mutating operation via propose_tool_intent instead."
        ),
    )
    result = await agent.ainvoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


async def terraform_provisioning_node(state: DraftingState, client: MultiServerMCPClient) -> dict:
    """Mirrors terraform_provisioning_agent: terraform-mcp-server minus
    create_run (mcp_tools.py) + propose_tool_intent."""
    tools = await get_terraform_provisioning_tools(client)
    tools.append(propose_tool_intent)
    agent = create_react_agent(
        model=get_model("execution"),
        tools=tools,
        prompt=(
            "Follow the 'provision-infra' skill's Path B (terraform). "
            "Propose every mutating operation via propose_tool_intent -- "
            "never call create_run yourself, this workflow never applies "
            "Terraform directly."
        ),
    )
    result = await agent.ainvoke({"messages": state["messages"]})
    return {"messages": result["messages"]}


async def security_review_node(state: DraftingState) -> dict:
    """Mirrors security_agent: reviews every propose_tool_intent call
    made so far, tools=[] except record_security_decision (task 3.2 --
    a separate graph node, not a sub-agent; see security_tools.py's
    docstring for how its decision actually gates ToolIntent harvest)."""
    agent = create_react_agent(
        model=get_model("review"),
        tools=[record_security_decision],
        prompt=(
            "You review provisioning plans proposed in this conversation before "
            "they execute. Load the 'security-review-checklist' skill for the "
            "exact checks to run. Approve only plans that stay within the "
            "allow-listed actions and the cost ceiling. Call "
            "record_security_decision exactly once with approved=True or "
            "approved=False and a specific, actionable reason -- never approve "
            "silently."
        ),
    )
    result = await agent.ainvoke({"messages": state["messages"]})
    return {"messages": result["messages"]}
