"""Connection configs for the official, third-party MCP servers this project
routes to, instead of hand-rolling per-cloud provisioning code ourselves.

Superseded: this project previously shipped its own minimal AWS MCP server
(S3 + CloudFront via boto3). That's been replaced by routing to AWS Labs'
and HashiCorp's officially maintained servers below, which cover far more
surface area and are maintained independently of this project.

NOTE: exact launch commands/args are drawn from each project's published
docs as of the research done for this project. Verify against the current
docs before relying on them:
  - https://awslabs.github.io/mcp/servers/aws-iac-mcp-server
  - https://awslabs.github.io/mcp/servers/ccapi-mcp-server
  - https://developer.hashicorp.com/terraform/mcp-server
"""
import os

from google.adk.tools.mcp_tool.mcp_toolset import StdioServerParameters

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_PROFILE = os.environ.get("AWS_PROFILE", "platformops-sandbox")

# CDK-native path, part 1: read-only docs/validation/compliance-linting.
# Does NOT create or modify any AWS resource.
AWS_IAC_MCP_SERVER = StdioServerParameters(
    command="uvx",
    args=["awslabs.aws-iac-mcp-server@latest"],
    env={"AWS_PROFILE": AWS_PROFILE, "AWS_DEFAULT_REGION": AWS_REGION},
)

# CDK-native path, part 2: the actual execution engine — CRUDL on AWS
# resources via AWS Cloud Control API. This is the tool with real blast
# radius on this path; security review must scope its resource-type access.
CCAPI_MCP_SERVER = StdioServerParameters(
    command="uvx",
    args=["awslabs.ccapi-mcp-server@latest"],
    env={"AWS_PROFILE": AWS_PROFILE, "AWS_DEFAULT_REGION": AWS_REGION},
)

# Terraform path: HashiCorp's official server. Requires an HCP Terraform (or
# Terraform Enterprise) account and API token — see README.md setup.
# VERIFY the exact `command`/`args` against HashiCorp's current install docs
# before running; this project has not yet executed this integration.
TERRAFORM_MCP_SERVER = StdioServerParameters(
    command="terraform-mcp-server",
    args=["-transport=stdio"],
    env={
        "TFE_TOKEN": os.environ.get("TFE_TOKEN", ""),
        "TFE_ADDRESS": os.environ.get("TFE_ADDRESS", "https://app.terraform.io"),
        "ENABLE_TF_OPERATIONS": os.environ.get("ENABLE_TF_OPERATIONS", "false"),
    },
)
