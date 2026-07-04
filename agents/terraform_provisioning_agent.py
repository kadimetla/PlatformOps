# Verify import paths/signatures against the installed google-adk version.
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from mcp_server.external_servers import TERRAFORM_MCP_SERVER

from .model_config import get_model

terraform_provisioning_agent = Agent(
    name="terraform_provisioning_agent",
    model=get_model("execution"),
    description="Provisions AWS infrastructure using HashiCorp's official Terraform MCP Server against HCP Terraform.",
    instruction=(
        "Follow the 'provision-infra' skill's Path B (terraform). Requires "
        "TFE_TOKEN to be configured; if missing, tell the user this path "
        "needs HCP Terraform account setup and suggest cdk_provisioning_agent "
        "instead. Produce the plain-English Vibe Diff summary before "
        "creating a run, and wait for security_agent's approval before "
        "calling action_run to apply."
    ),
    tools=[MCPToolset(connection_params=TERRAFORM_MCP_SERVER)],
)
