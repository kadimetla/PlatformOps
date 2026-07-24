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

Kubernetes foundation-layer servers (openspec/changes/provision-kubernetes-cluster) --
self-hosted, all confirmed via docs/multi_cloud_foundation_and_iam.md Part E
(2026-07-24 research, not assumed):
  - AWS eks-mcp-server: uvx-launchable, same pattern as the AWS servers
    above (https://pypi.org/project/awslabs.eks-mcp-server/,
    https://awslabs.github.io/mcp/servers/eks-mcp-server). Tool name
    `manage_eks_stacks` codex-web-verified; exact operation/parameter
    names NOT live-verified against a running server in this
    environment (no AWS credentials here) -- provision-kubernetes-cluster
    tasks.md task 1.1 is the live-verification step, still open.
  - GCP gke-mcp: a Go binary (https://github.com/GoogleCloudPlatform/gke-mcp),
    NOT uvx/npx -- `command` below points at the compiled executable.
    Unofficial, "not an officially supported Google product" per its own
    docs. Tool names (`create_cluster` etc.) researched, not
    live-verified -- tasks.md task 1.2, still open. A real Google-hosted
    remote alternative exists (`https://container.googleapis.com/mcp`,
    OAuth-scoped) -- self-hosted only for this change, per design.md's
    Non-Goals; see the StreamableHttpConnection override sketch below.
  - Azure aks-mcp: a Go binary (https://github.com/Azure/aks-mcp), NOT
    uvx/npx -- binary or Docker, `--transport stdio`. Tool names
    (`az_aks_operations` etc.) researched, not live-verified -- tasks.md
    task 1.3, still open.

Hosted-override design (not implemented, sketched per
docs/multi_cloud_foundation_and_iam.md Part E -- langchain_mcp_adapters'
MultiServerMCPClient already supports StreamableHttpConnection/
SSEConnection, confirmed by direct introspection of the installed
package): a future change could branch each of the three configs below
on an env var, e.g.
    GKE_MCP_SERVER = (
        StreamableHttpConnection(url=hosted_url, auth=oauth_credentials)
        if (hosted_url := os.environ.get("GKE_MCP_HOSTED_URL"))
        else StdioServerParameters(command="./gke-mcp", args=["--transport", "stdio"])
    )
without any change to how workflows/drafting/mcp_tools.py-style
connection-building code consumes the result -- not built this change.
"""
import os
from dataclasses import dataclass, field


@dataclass
class StdioServerParameters:
    """Plain, framework-independent stdio server config -- replaces
    ADK's google.adk.tools.mcp_tool.mcp_toolset.StdioServerParameters
    at the migrate-to-langgraph cutover (task 7.2): the only real
    consumer left is workflows/drafting/mcp_tools.py's
    _to_stdio_connection(), which just reads .command/.args/.env --
    duck-typed, no ADK class needed to satisfy it."""

    command: str
    args: list[str]
    env: dict[str, str] = field(default_factory=dict)


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

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
AZURE_SUBSCRIPTION_ID = os.environ.get("AZURE_SUBSCRIPTION_ID", "")

# Kubernetes foundation-layer path, AWS: uvx-launchable, same pattern as
# AWS_IAC_MCP_SERVER/CCAPI_MCP_SERVER above. --allow-write is required for
# any mutating manage_eks_stacks call -- see module docstring.
EKS_MCP_SERVER = StdioServerParameters(
    command="uvx",
    args=["awslabs.eks-mcp-server@latest", "--allow-write", "--allow-sensitive-data-access"],
    env={"AWS_PROFILE": AWS_PROFILE, "AWS_DEFAULT_REGION": AWS_REGION},
)

# Kubernetes foundation-layer path, GCP: a Go binary, NOT uvx -- see module
# docstring. GKE_MCP_BINARY_PATH lets an operator point at wherever `go
# install`/the release download actually placed the executable, instead of
# assuming a fixed path.
GKE_MCP_SERVER = StdioServerParameters(
    command=os.environ.get("GKE_MCP_BINARY_PATH", "gke-mcp"),
    args=[],
    env={"GOOGLE_CLOUD_PROJECT": GCP_PROJECT_ID},
)

# Kubernetes foundation-layer path, Azure: a Go binary, NOT uvx -- see
# module docstring.
AKS_MCP_SERVER = StdioServerParameters(
    command=os.environ.get("AKS_MCP_BINARY_PATH", "aks-mcp"),
    args=["--transport", "stdio"],
    env={"AZURE_SUBSCRIPTION_ID": AZURE_SUBSCRIPTION_ID},
)
