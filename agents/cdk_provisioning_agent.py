# Verify import paths/signatures against the installed google-adk version.
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from mcp_server.external_servers import AWS_IAC_MCP_SERVER, CCAPI_MCP_SERVER

cdk_provisioning_agent = Agent(
    name="cdk_provisioning_agent",
    model="gemini-2.5-flash",
    description="Provisions AWS infrastructure using CDK-native tooling: aws-iac-mcp-server for design/validation, ccapi-mcp-server for execution.",
    instruction=(
        "Follow the 'provision-infra' skill's Path A (cdk). Use "
        "aws-iac-mcp-server's tools to draft and validate a CloudFormation "
        "template (cfn-lint, cfn-guard) before proposing any change. Produce "
        "the plain-English Vibe Diff summary and wait for security_agent's "
        "approval before calling any ccapi-mcp-server tool that creates, "
        "updates, or deletes a resource."
    ),
    tools=[
        MCPToolset(connection_params=AWS_IAC_MCP_SERVER),
        MCPToolset(connection_params=CCAPI_MCP_SERVER),
    ],
)
