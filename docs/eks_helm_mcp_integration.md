# EKS + Helm MCP Server Integration — Research Findings

## Status
Research, not a build — resolves the flagged-but-unresearched question
in `docs/foundation_app_layering_and_iam_tiers.md` Part C ("which MCP
server fronts Helm... no such integration has been researched yet").
Verified against live AWS docs, GitHub, and PyPI (see Sources), matching
this project's own habit of verifying third-party MCP server claims
before relying on them (`mcp_server/external_servers.py`'s header
comment does the same for the AWS Labs/HashiCorp servers already
integrated).

## Bottom line: two servers, not one
No single MCP server covers both the foundation layer (EKS cluster
lifecycle) and app-layer Helm deploys. Confirmed directly: **the
official Amazon EKS MCP server has no Helm support at all.** The
realistic integration is:
- **`awslabs.eks-mcp-server`** — foundation-layer cluster lifecycle
  (Part A of `docs/foundation_app_layering_and_iam_tiers.md`)
- **`containers/kubernetes-mcp-server`** — app-layer Helm deploys
  (Part C's `deploy-to-k8s` skill — named `deploy-to-eks` when this doc
  was written; renamed in `docs/multi_cloud_foundation_and_iam.md` once
  research confirmed the Helm execution backend isn't AWS-specific)

## Part A: `awslabs.eks-mcp-server` — foundation-layer fit

| Tool | What it does | Write-gated? |
|---|---|---|
| `manage_eks_stacks` | CloudFormation-based cluster create/describe/delete, embedding the cluster name into the generated template | Yes — `--allow-write` |
| `manage_k8s_resource` | CRUD on individual K8s resources, namespaced or cluster-scoped | Yes |
| `apply_yaml` | Applies multi-document K8s YAML manifests, with force-update | Yes |
| `list_k8s_resources`, `list_api_versions` | Read-only cluster inspection | No |
| `generate_app_manifest` | Generates deployment/service YAML (raw manifests, **not Helm**) | Yes |
| `get_pod_logs`, `get_k8s_events`, `get_cloudwatch_logs`, `get_cloudwatch_metrics`, `get_eks_insights` | Troubleshooting/observability | `--allow-sensitive-data-access` |
| `search_eks_troubleshoot_guide`, `get_eks_vpc_config` | Read-only docs/VPC inspection | No |
| `get_policies_for_role`, `add_inline_policy` | IAM policy management **on existing roles** | latter: Yes |

Two things worth pulling out for this project specifically:

1. **The server already has a native write/read/sensitive-data gating
   flag scheme** (`--allow-write`, `--allow-sensitive-data-access`) —
   directly analogous to the `ENABLE_TF_OPERATIONS` operator-controlled
   switch this project already uses for the Terraform path
   (`skills/provision-infra/SKILL.md`'s Path B, step 5). Foundation-tier
   provisioning's "always human-approved, never autonomous" rule
   (`docs/foundation_app_layering_and_iam_tiers.md` Part A) can lean on
   this existing flag rather than inventing a new gate — the same
   pattern this project already trusts for exactly this purpose.
2. **No IAM role *creation* tool, and no confirmed IRSA/OIDC tool.**
   `add_inline_policy` only attaches a policy to a role that already
   exists. This means `AWS::IAM::Role` creation — with the
   permissions-boundary requirement `docs/foundation_app_layering_and_iam_tiers.md`
   Part B specifies — still has to go through the existing CCAPI/
   Terraform path. This research doesn't change that design; it
   confirms it's still necessary, not superseded by this server.

Two deployment modes exist:
- **Self-hosted, open source** — `awslabs.eks-mcp-server` (PyPI
  package), same `uvx`-launched pattern as this project's existing
  AWS Labs servers.
- **Fully managed, AWS-hosted (preview)** — a SigV4-signed proxy to a
  hosted endpoint, with **CloudTrail audit logging built in**. Worth
  weighing against this project's own audit-log emphasis
  (`gateway/tool_dispatcher.py`'s `audit_logs` table) — this mode gets
  you cloud-side audit trail "for free," at the cost of the same kind
  of vendor-coupling `docs/HARNESS_DESIGN.md` already declined once,
  for a different reason, when it rejected registering PlatformOps as
  an MCP tool source on a live OpenClaw Gateway ("ties PlatformOps to
  OpenClaw's roadmap/licensing"). Not decided here either — flagged as
  the same category of tradeoff, not resolved.

## Part B: `containers/kubernetes-mcp-server` — app-layer Helm fit

Real Helm tools, confirmed: `helm_install` (deploy chart + optional
values to a namespace), `helm_list` (view releases), `helm_uninstall`.
Go-native, talks directly to the Kubernetes API — not a wrapper around
the `helm`/`kubectl` binaries. Apache-2.0, actively maintained (63
releases, 1.8k stars).

Two findings that matter directly for this project's design:

1. **Namespace scoping is a first-class parameter on the tools
   themselves**, not just something to check in a prompt. This turns
   `docs/foundation_app_layering_and_iam_tiers.md` Part C's "confirm the
   target namespace is allow-listed for this BU" from a
   security-review-checklist prompt instruction into something that can
   actually be validated against the call parameters before dispatch —
   the same shape as `gateway/tool_dispatcher.py` checking a
   `ToolIntent`'s `resource_type` against `allowed_resource_types`,
   applied to a namespace string instead.
2. **New cross-BU isolation risk this research surfaces, not previously
   named anywhere**: the server supports multiple clusters via
   kubeconfig contexts, by design, for convenience. A single kubeconfig
   handed to one running MCP server instance could reach *any* context
   in it. If one shared kubeconfig covered multiple BUs' clusters,
   that's the exact cross-tenant leakage class already flagged twice
   elsewhere in this project — `agent_id` must never be shared across
   BUs (`docs/HARNESS_DESIGN.md`), and a session key must be
   channel/thread-scoped, never a bare DM fallback
   (`docs/session_memory_design.md`). The same rule needs a third
   instance here: **the kubeconfig given to a BU's MCP server instance
   must be scoped to exactly that BU's cluster context, never a
   multi-BU kubeconfig relying on the agent to pick the right one.**
   This is a new validation rule to add wherever `WorkspaceBundle` ends
   up specifying which cluster a BU deploys to — not designed yet, just
   surfaced.

Launch options (multiple, per the project's existing multi-method
pattern for MCP servers): `npx kubernetes-mcp-server@latest`, a native
binary, a Docker image, a pip package, or — notably — its own Helm
chart for running the MCP server itself inside a cluster. Supports
stdio (default) or Streamable HTTP/SSE when a port is specified.

**Not confirmed, needs hands-on verification before relying on it**:
whether `helm_install` supports pinning a chart to an exact repo +
version strongly enough to satisfy the supply-chain/version-pinning
concern `docs/skills_and_workspace_design.md` already requires for
promoted skills, applied here to chart versions
(`docs/foundation_app_layering_and_iam_tiers.md` Part C, step 2).

## Part C: Config sketch (not yet implemented — matches `mcp_server/external_servers.py`'s style)
```python
# EKS foundation-layer lifecycle: cluster create/describe/delete, K8s
# resource CRUD, troubleshooting. NOT a Helm tool — see HELM_MCP_SERVER.
# VERIFY exact command/args against current awslabs.eks-mcp-server docs
# before relying on them; this project has not yet run this integration.
EKS_MCP_SERVER = StdioServerParameters(
    command="uvx",
    args=["awslabs.eks-mcp-server@latest", "--allow-write"],
    env={"AWS_PROFILE": AWS_PROFILE, "AWS_DEFAULT_REGION": AWS_REGION},
)

# App-layer Helm deploys onto an already-provisioned, approved EKS
# foundation. kubeconfig MUST be scoped to exactly one BU's cluster
# context — never a shared, multi-BU kubeconfig (see cross-BU risk above).
# VERIFY exact launch command/args before relying on them; not yet run.
HELM_MCP_SERVER = StdioServerParameters(
    command="npx",
    args=["kubernetes-mcp-server@latest"],
    env={"KUBECONFIG": "<per-BU-scoped kubeconfig path>"},
)
```

## What this resolves and what it changes in prior design
- **Resolves** `docs/foundation_app_layering_and_iam_tiers.md` Part C's
  open research question — a real, maintained server exists for Helm,
  it's just not the same server as EKS cluster lifecycle management.
- **Refines, doesn't replace**, that doc's Part A assumption that
  foundation-layer provisioning goes through generic CCAPI/Terraform the
  same way app-layer resources do — EKS cluster lifecycle has a
  purpose-built tool (`manage_eks_stacks`) instead. Whether VPC creation
  specifically still needs the generic CCAPI/Terraform path (if
  `manage_eks_stacks`'s CFN template doesn't cover custom VPC
  requirements) is not confirmed — flagged as open, not assumed either
  way.
- **Confirms, unchanged**, Part B's `AWS::IAM::Role`
  permissions-boundary design — neither new server creates IAM roles,
  so that path still runs through CCAPI/Terraform as designed.
- **Surfaces a new isolation risk** (kubeconfig context scoping across
  BUs) that none of the tenancy docs previously named, because none of
  them had a reason to think about Kubernetes-side multi-cluster access
  until this research.

## Open questions / not yet decided
- Self-hosted vs. fully-managed `awslabs.eks-mcp-server` — the managed
  mode's built-in CloudTrail audit is attractive given this whole
  project's audit-log emphasis, but raises the same vendor-coupling
  tradeoff already weighed once for a different integration. Not
  decided.
- Whether kubeconfig-context scoping needs a new validation rule in
  `gateway/config_engine.py`, the same shape as the existing
  `agent_id` uniqueness check — likely yes, not designed.
- **Resolved in `docs/gcp_azure_verification_pass.md`**: `helm_install`
  confirmed to support OCI registry references plus a `--version` flag
  for pinning — matches the supply-chain requirement already in
  `docs/foundation_app_layering_and_iam_tiers.md` Part C.
- IRSA/OIDC provider association — not confirmed as covered by
  `manage_eks_stacks`'s CFN defaults or requiring separate handling.

## How this relates to the existing docs
- Directly resolves the open research item in
  `docs/foundation_app_layering_and_iam_tiers.md` Part C.
- Extends the binding/session-key specificity principle already
  established in `docs/HARNESS_DESIGN.md` and
  `docs/session_memory_design.md` to a third concept (kubeconfig
  context scoping) that surfaced only from this research, not from
  prior design work.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Amazon EKS Model Context Protocol (MCP) Server — AWS docs](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-introduction.html)
- [Accelerating application development with the Amazon EKS MCP server — AWS blog](https://aws.amazon.com/blogs/containers/accelerating-application-development-with-the-amazon-eks-model-context-protocol-server/)
- [Introducing the fully managed Amazon EKS MCP Server (preview) — AWS blog](https://aws.amazon.com/blogs/containers/introducing-the-fully-managed-amazon-eks-mcp-server-preview/)
- [awslabs.eks-mcp-server — PyPI](https://pypi.org/project/awslabs.eks-mcp-server/)
- [awslabs/mcp — GitHub (AWS Labs MCP servers)](https://github.com/awslabs/mcp)
- [containers/kubernetes-mcp-server — GitHub](https://github.com/containers/kubernetes-mcp-server)
