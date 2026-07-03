# Verify import paths/signatures against the installed google-adk version —
# ADK's MCP integration API has moved across releases.
from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters

AWS_MCP_SERVER = StdioServerParameters(
    command="python",
    args=["-m", "mcp_server.aws_mcp_server"],
)

provisioning_agent = Agent(
    name="provisioning_agent",
    model="gemini-2.5-flash",
    description="Provisions AWS infrastructure (S3 static site + CloudFront) from a structured spec.",
    instruction=(
        "You provision AWS infrastructure described in the user's spec. "
        "Load the 'provision-static-web-app' skill for the exact procedure. "
        "Before calling any MCP tool that creates or modifies AWS resources, produce a "
        "plain-English summary of what will happen (resources, cost estimate, region) and "
        "wait for the security_agent to approve it before proceeding."
    ),
    tools=[MCPToolset(connection_params=AWS_MCP_SERVER)],
)
