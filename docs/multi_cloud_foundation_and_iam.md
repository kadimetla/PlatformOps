# Multi-Cloud: Foundation Layer, App Layer, and IAM Across AWS/GCP/Azure

## Status
Research + design — extends `docs/foundation_app_layering_and_iam_tiers.md`,
`docs/eks_helm_mcp_integration.md`, and
`docs/infra_discovery_and_platform_app_split.md` (all AWS-only) to GCP and
Azure. Verified against live Google Cloud, Microsoft Learn, and GitHub
docs (see Sources). Nothing here is built — this project provisions AWS
only today (`README.md:255-257`).

## Part A: The same concepts, different concrete resources per provider

| Concept | AWS | GCP | Azure |
|---|---|---|---|
| Network | VPC | VPC Network | Virtual Network (VNet) |
| Managed K8s | EKS | GKE | AKS |
| Cluster identity | EKS cluster service role | Less prominent as a standalone role than AWS's | AKS control-plane managed identity (system- or user-assigned) |
| Node identity | Node IAM role — **must** be separate from the cluster role (AWS hard rule, `docs/infra_discovery_and_platform_app_split.md` Part B) | Node pool service account — GCP's known anti-pattern is reusing the *default* Compute Engine SA broadly instead of a scoped one | Kubelet identity — Azure requires the **Managed Identity Operator** role explicitly when it's outside the default node resource group |
| Workload identity (IRSA-equivalent) | IRSA — IAM role assumed via OIDC federation by a K8s ServiceAccount | **Workload Identity Federation** — newer "direct resource access" mode binds an IAM role straight to the K8s ServiceAccount principal, no separate Google Service Account in the middle | **Azure AD Workload Identity** — a federated credential bound to a K8s ServiceAccount, same shape as IRSA |
| Operator's escalation-adjacent grant | `iam:PassRole` (must be ARN-scoped — `docs/infra_discovery_and_platform_app_split.md` Part B) | `roles/iam.serviceAccountUser` — binding a service account to a resource requires this; same escalation class as `PassRole` (not independently re-verified this session — verify before relying on it) | Managed Identity Operator role — same escalation class again |

**One row this table can't express**: "Network" mapping 1:1 (VPC/VPC
Network/VNet) is true for the *concept*, but how a network gets *shared*
across project/account/subscription boundaries is genuinely
provider-divergent, not a naming difference — GCP's Shared VPC
(host/service project split, two-tier IAM), AWS's subnet-level sharing
via RAM (owner/participant, same Organization), and Azure's non-transitive
VNet peering (no owner at all, a graph to traverse) are three different
shapes. See `docs/cross_project_network_sharing.md` for the full
comparison and what it breaks in `docs/foundation_layer_decomposition.md`'s
discovery model.

## Part B: The finding that actually changes the approach — write-capability isn't symmetric
This is the one result that should drive the design, not just fill in a
table:
- **AWS**: `awslabs.eks-mcp-server` has a real `--allow-write` path — full
  cluster create/describe/delete (`docs/eks_helm_mcp_integration.md`
  Part A).
- **GCP**: Google's own **GKE MCP server is read-only, full stop** —
  *"currently limited to read operations."* The GCE MCP server provisions
  Compute Engine VMs, which is compute, not GKE cluster creation. No
  confirmed native write path for GKE foundation-layer creation exists
  via Google's own MCP tooling today.
- **Azure**: the official Azure MCP Server's AKS tools are read/list/
  monitor-focused ("get or list clusters, manage node pool configs,
  monitor operations"). The actual write path is the separate **Azure
  Resource Manager MCP Server** (ARM template deployments at
  subscription/resource-group scope). A dedicated `Azure/aks-mcp`
  project exists but is public preview.

Three clouds, three different answers to "can an MCP server actually
create the foundation" — not one pattern to replicate three times.

**Corrected 2026-07-24 — the GCP and Azure write-capability findings
above are stale; the AWS finding still holds.** Verified directly
against current vendor docs/repos (web search, not recall — see Part E
below for the full research and its sourcing):
- **GCP**: no longer accurate. Google now hosts a real, write-capable
  remote GKE MCP endpoint (`https://container.googleapis.com/mcp`),
  and a separate unofficial local `GoogleCloudPlatform/gke-mcp` repo
  also has real write tools (`create_cluster`/`update_cluster`/
  `delete_cluster`). "No confirmed native write path" is no longer
  true — see Part E.
- **Azure**: the AKS-specific finding still holds (native AKS MCP tools
  remain read/list/monitor-only) — but the "separate Azure Resource
  Manager MCP Server" named as the real write path is now confirmed
  **hosted** by Microsoft (`https://mcp.management.azure.com`), not
  just a self-run project.
- **AWS**: unchanged, still accurate — `awslabs.eks-mcp-server`'s write
  path is real. New detail found: AWS has *also* since started hosting
  a managed version of this server (`https://eks-mcp.{region}.api.aws/mcp`,
  currently in preview) — see Part E for why that doesn't simply make
  AWS the obvious first choice.

This correction is about capability and hosting, not about Part C's
architectural conclusion below (route through Terraform) — see Part E's
own concluding note for whether the conclusion changes.

## Part C: Split the problem — don't try to unify all of it the same way

### Foundation layer → route through Terraform, not three divergent native integrations
This project's Terraform MCP server is already cloud-agnostic via
provider configs — `README.md:248`'s roadmap already said this
generically ("lowest-effort way to add a second/third cloud"). This
research confirms *why* that's specifically the right call for the
foundation layer: GCP's native write path doesn't exist yet, Azure's is
ARM-template-based (structurally similar to Terraform's declarative
model anyway), and only AWS has a mature native write-capable MCP
server. Three native integrations would mean building around three
different capability levels; one Terraform path with new provider
blocks does not.

### App layer → already provider-agnostic; correct a naming mistake from two docs ago
`containers/kubernetes-mcp-server`'s Helm tools talk directly to the
Kubernetes API server, not any cloud-specific control plane — the exact
same `helm_install`/`helm_list`/`helm_uninstall` calls work against EKS,
GKE, or AKS equally, as long as the kubeconfig context points at the
right cluster. **Correction**: the `deploy-to-eks` skill named in
`docs/foundation_app_layering_and_iam_tiers.md` Part C should be
`deploy-to-k8s`, parameterized by cluster/kubeconfig context — it was
never actually AWS-specific, it was just named that way before this
research existed.

### IAM → cannot be mechanically unified, but the *rule shape* can be
AWS roles+boundary+`PassRole`, GCP service accounts+Workload Identity
Federation+`serviceAccountUser`, and Azure managed identities+RBAC+
Managed Identity Operator are structurally different systems — no single
policy document covers all three. But the *abstract rules* from
`docs/iam_permissions_boundary_implementation.md` and
`docs/infra_discovery_and_platform_app_split.md` hold identically across
all three clouds:
1. The operator's escalation-adjacent grant must be scoped to specific
   resources, never wildcarded.
2. Workload identity must be least-privilege and boundary-capped.
3. Foundation identity and app/workload identity must never be the same
   object.

**Corrected by follow-up research (see `docs/spec_driven_development_scaling.md`'s
companion turn) — neither GCP nor Azure has anything that maps 1:1 onto
AWS's permissions boundary.** A boundary is a policy *attached to the
identity itself* that intersects with whatever else is attached. GCP and
Azure achieve the same ceiling effect through resource-hierarchy-scoped
guardrails instead — the method name below was renamed from
`validate_workload_identity_bounded` to `validate_ceiling_enforced` to
stop implying a per-identity artifact exists in all three clouds:

- **GCP**: no per-service-account boundary object. The ceiling comes
  from two project/org-scoped mechanisms instead: a custom Organization
  Policy constraint capping which roles are grantable at all within the
  project, and an IAM Deny policy (a distinct, newer feature — deny
  bindings always win over any Allow, regardless of role) denying
  dangerous actions (`iam.serviceAccountKeys.create`,
  `iam.serviceAccounts.setIamPolicy`) to any service account matching
  this BU's naming convention. Verified: GCP "does not support 'Deny' in
  custom role definitions the way AWS policies do" — Deny policies are a
  separate mechanism layered on top, not part of the role itself.
- **Azure**: no per-identity boundary either. Azure RBAC has no
  intersection concept — a role assignment grants exactly what the role
  defines. The ceiling comes from (a) always assigning a **custom role**
  with a tightly scoped `Actions`/`NotActions` list, never a broad
  built-in role, and (b) an **Azure Policy** at management-group/
  subscription/resource-group scope, with a `deny` effect, backstopping
  anything broader than the approved custom-role allow-list.

```python
class CloudIAMAdapter(Protocol):
    """One implementation per cloud_provider. Enforces the three rules
    above through provider-specific mechanisms — see Part A and the
    correction note above for what each provider's mechanism actually
    is; AWS's is identity-attached, GCP/Azure's are resource-hierarchy-
    scoped, not directly equivalent shapes."""

    def validate_escalation_grant_scoped(self, operator_policy: dict) -> bool:
        """AWS: iam:PassRole ArnEquals condition (docs/iam_permissions_boundary_implementation.md).
        GCP: the operator's roles/iam.serviceAccountUser binding must carry
        an IAM Condition scoping it to the approved SA name prefix, e.g.
        resource.name.startsWith('projects/P/serviceAccounts/platformops-demo-').
        Azure: the Managed Identity Operator role assignment's `scope` field
        must reference the specific managed identity resource ID, not a
        subscription- or resource-group-wide scope."""
        ...

    def validate_ceiling_enforced(self, workload_identity: dict) -> bool:
        """AWS: IRSA role has a PermissionsBoundary attached (identity-level check).
        GCP: check for (a) a custom Org Policy constraint at this project
        capping which roles are grantable at all, AND (b) an IAM Deny
        policy denying key-creation/setIamPolicy to any SA matching this
        BU's naming convention -- there is no per-identity object to check.
        Azure: check that (a) the workload's role assignment references a
        custom role, not a built-in broad one, AND (b) an Azure Policy at
        a higher scope denies assigning anything broader to identities
        matching this BU's naming convention."""
        ...
```
This is the pattern this multi-cloud problem actually needs: one
interface, one implementation per provider, the same three rules
enforced everywhere — not a single policy document, and not three
unrelated ad hoc designs either.

### `TeamMember.scope` needs no change at all
`"foundation"|"app"|"both"` (`docs/infra_discovery_and_platform_app_split.md`
Part C) was designed at the harness level, above any provider specifics.
This research is a useful check that it was pitched at the right
altitude the first time — nothing about GCP or Azure requires touching
it.

## Part D: Schema changes

### `WorkspaceBundle` gains a provider discriminator
```python
class WorkspaceBundle(BaseModel):
    ...
    cloud_provider: str = Field(
        default="aws",
        description="'aws' | 'gcp' | 'azure' -- determines which "
                     "provider-specific fields apply and which "
                     "CloudIAMAdapter implementation is used",
    )
    # AWS-specific (existing): aws_region, aws_profile
    # GCP-specific (new, only meaningful if cloud_provider == "gcp"):
    gcp_project_id: Optional[str] = None
    gcp_region: Optional[str] = None
    # Azure-specific (new, only meaningful if cloud_provider == "azure"):
    azure_subscription_id: Optional[str] = None
    azure_resource_group: Optional[str] = None
```
Same conditional-field shape `tfe_workspace` already uses today
(meaningful only when `toolchain == "terraform"`), applied to cloud
choice instead of tool choice.

### `FoundationRecord` gains the same discriminator
`cloud_provider` was added here first, then merged into the canonical
schema in `docs/foundation_app_layering_and_iam_tiers.md` Part D
alongside `discovered_capabilities`
(`docs/foundation_discovery_and_capability_matching.md`) — see that doc
for the current, single-source-of-truth version rather than a second
copy here.

## Part E: Hosted vs. self-hosted is a second axis, independent of write-capability — researched 2026-07-24
Part B asked "does a write path exist." A different question, never
asked until an explore-mode session pushed on it: **is the server
something you run yourself, or something already running that you just
authenticate to?** This project's entire existing integration
(`mcp_server/external_servers.py`) is self-hosted — every server
launched as a local stdio subprocess via `uvx <package>@latest` (AWS)
or a standalone binary (`terraform-mcp-server`). That was never
evaluated against vendor-hosted alternatives.

### Verified hosting status, per server (web search against current vendor docs, sourced)
| Server | Vendor-hosted remote endpoint? | Detail |
|---|---|---|
| GCP GKE MCP | **Yes** | `https://container.googleapis.com/mcp` (+`/read-only`, +`/delete-tools`) — OAuth 2.0 + Google Cloud IAM, **no local proxy needed**. Scope-tiered: the default `/mcp` scope excludes cluster/node-pool deletion entirely; that capability is a *separate* OAuth-scoped endpoint (`/delete-tools`). [GKE remote MCP guide](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/use-gke-mcp), [GKE MCP reference](https://docs.cloud.google.com/kubernetes-engine/docs/reference/mcp) |
| Azure Resource Manager MCP (AKS's real write path) | **Yes** | `https://mcp.management.azure.com` — OAuth via Entra, Azure RBAC-scoped. [Microsoft MCP catalog](https://github.com/microsoft/mcp), [ARM MCP repo](https://github.com/Azure/Azure-Resource-Manager-MCP) |
| AWS EKS MCP | Yes, with a caveat | `https://eks-mcp.{region}.api.aws/mcp` — hosted, but still requires running a local SigV4-translating proxy (`mcp-proxy-for-aws`) unless the client speaks AWS SigV4 natively, and AWS's own docs mark this **"in preview."** [AWS EKS managed MCP](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-tool-configurations.html) |
| AWS `ccapi-mcp-server` / `aws-iac-mcp-server` | No | Self-run only (`uvx`/Docker) |
| Azure AKS-specific MCP / general Azure MCP Server | No | Self-hosted only — Microsoft's own catalog marks it `Local` |
| HashiCorp `terraform-mcp-server` | No | HashiCorp's "remote" deployment docs mean *you* deploy the binary/container somewhere remote — HCP Terraform supplies APIs/tokens, not a hosted MCP endpoint. [Deploy overview](https://developer.hashicorp.com/terraform/mcp-server/deploy), [Remote deploy](https://developer.hashicorp.com/terraform/mcp-server/deploy/remote) |

**GCP's hosted GKE MCP is the cleanest hosted story of the three
clouds** — no local process at all (unlike AWS's, which still needs a
local proxy), not flagged preview (unlike AWS's), and its capability
tiering happens at the OAuth-scope level rather than client-side tool
filtering. That last point is a real structural safety property this
project's own current pattern doesn't have: `workflows/drafting/mcp_tools.py`
filters mutating tool names out in application code — a soft cutoff a
bug could bypass. GCP's `/delete-tools` being a *separate* OAuth scope
means a credential can be structurally incapable of deleting a cluster,
independent of any application-level filter.

**This doesn't overturn Part C's "route through Terraform" conclusion**
for the general multi-cloud foundation problem — three different hosted
maturity levels/parameter surfaces is still not one pattern to unify.
But it does mean **"start with AWS because it's most mature" is no
longer the clean default it looked like** when this document was first
written — on the hosted-and-mature axis specifically, GCP now has a
real claim to being the better starting cloud for a single-cluster
proof, independent of which cloud a real deployment eventually targets.

### Self-hosting is still fully viable today for all four servers — verified launch mechanism per server
| Server | Self-hosted launch | Matches this project's existing `uvx` pattern? |
|---|---|---|
| AWS `eks-mcp-server` | `uvx awslabs.eks-mcp-server@latest --allow-write ...` | **Yes** — identical shape to `ccapi-mcp-server`/`aws-iac-mcp-server` already in `mcp_server/external_servers.py` |
| GCP `gke-mcp` (local) | **Go binary** — `go install`, run the compiled executable directly | No — not uvx/npx, a plain executable, but fits the same `command`/`args`/`env` shape `StdioServerParameters` already uses |
| Azure `aks-mcp` | **Go binary** — GitHub release download or Docker, `--transport stdio` | Same as GCP — plain executable, same `StdioServerParameters` shape |
| HashiCorp `terraform-mcp-server` | Standalone binary — already how this project's own code configures it today (`command="terraform-mcp-server"`) | Never was uvx, even in the existing integration |

`StdioServerParameters` (`mcp_server/external_servers.py`) was never
uvx-specific — it's a generic `command`/`args`/`env` shape, and the
existing Terraform entry already proves it handles a plain binary.
Self-hosting all four servers today requires zero new mechanism, just
four config entries in the shape already there.

### The plumbing for a hosted override already exists in the library this project depends on — verified by direct introspection, not assumed
```python
# Confirmed via `python3 -c "import langchain_mcp_adapters.client as c; ..."`
# against the actual installed package:
MultiServerMCPClient.__init__(
    connections: dict[str, StdioConnection | SSEConnection
                       | StreamableHttpConnection | WebsocketConnection]
)
```
`langchain-mcp-adapters` — already a real dependency, already imported
in `workflows/drafting/mcp_tools.py` — natively supports mixing local
(`Stdio`) and remote (`StreamableHttp`/`SSE`) connections in the same
client, per server. `StreamableHttpConnection`'s fields (confirmed by
introspecting the actual class): `url: str`, `headers: dict | None`,
`auth: httpx.Auth` — exactly the shape GCP's OAuth-scoped endpoint or
Azure's Entra-secured one would need. The plumbing to call an
externally configured MCP endpoint instead of a self-hosted one isn't
something to build — it's something to configure:

```python
# mcp_server/external_servers.py, sketch — self-hosted default,
# hosted override when configured, no change needed to
# workflows/drafting/mcp_tools.py's connection-building logic either way
GKE_MCP_SERVER = (
    StreamableHttpConnection(url=hosted_url, auth=oauth_credentials)
    if (hosted_url := os.environ.get("GKE_MCP_HOSTED_URL"))
    else StdioServerParameters(command="./gke-mcp", args=["--transport", "stdio"])
)
```

### Recommendation, given both findings together
Self-host all four servers today, in the existing `StdioServerParameters`
shape (AWS via `uvx`, GCP/Azure/Terraform via their own binaries) — no
new mechanism needed, consistent with what's already built and tested.
Design the connection-config layer with the hosted-override branch above
from the start, even though nothing exercises it yet, so switching any
one server (most plausibly GCP's, given Part E's maturity finding) to
its hosted endpoint later is a config change, not a rewrite.

## Open questions / not yet decided
- **Resolved in `docs/gcp_azure_verification_pass.md`**: `roles/iam.serviceAccountUser`/
  `serviceAccountTokenCreator`'s escalation risk is confirmed real and
  chainable, and the mitigation (scope to a specific SA, never
  project-level) matches what was designed here by analogy — plus a new
  finding this doc didn't have: every impersonation is logged in Cloud
  Audit Logs, and VPC Service Controls add an independent containment
  layer worth folding into `CloudIAMAdapter`.
- Whether `deploy-to-k8s` (the renamed skill) needs per-provider
  variations in its procedure beyond the kubeconfig context — e.g.,
  different namespace-allow-list conventions per cloud — not decided.
- Whether a BU can span multiple clouds (one BU, multiple
  `WorkspaceBundle`s with different `cloud_provider` values) or is
  strictly one-cloud-per-BU — not decided; the current one-bundle-per-BU
  model implies the latter, not confirmed as intentional.
- **Resolved**: `CloudIAMAdapter`'s GCP and Azure mechanisms are now
  specified (custom Org Policy constraint + IAM Deny policy for GCP;
  custom RBAC role + Azure Policy deny for Azure) — see the correction
  above. Still open: the actual policy/constraint JSON equivalents (like
  `docs/iam_permissions_boundary_implementation.md` produced for AWS)
  haven't been drafted for GCP/Azure yet, just the mechanism they'd use.
- **New from Part E**: the exact shape of the hosted-override config
  knob (a plain env var per server, a `WorkspaceBundle` field, or an
  org-level default with BU override following the same precedence
  pattern used for skills/`IacSourceRef`) — sketched as an env var
  above for concreteness, not decided as the real mechanism.
- **New from Part E**: whether GCP's OAuth-scope-level capability
  tiering (separate endpoints for read-only/mutate/delete) should
  influence how this project's *own* dispatcher-level checks are
  designed generally — i.e. whether "structural, credential-level
  incapability" is a pattern worth pursuing for AWS/Azure too, not just
  something GCP happens to offer — flagged, not designed.
- **New from Part E**: AWS's hosted EKS MCP is explicitly "in preview"
  per AWS's own docs — whether that maturity gap closes soon enough to
  matter for a real deployment timeline isn't something this research
  can answer, only monitor.

## How this relates to the existing docs
- **Extends** `docs/foundation_app_layering_and_iam_tiers.md`,
  `docs/eks_helm_mcp_integration.md`, and
  `docs/infra_discovery_and_platform_app_split.md` from AWS-only to
  three providers — see those docs for the AWS-specific detail this
  doesn't repeat.
- **Corrects** `docs/foundation_app_layering_and_iam_tiers.md` Part C's
  `deploy-to-eks` skill name to `deploy-to-k8s`, since the underlying
  tool was never AWS-specific.
- **Part E, added 2026-07-24**: corrects this doc's own Part B
  write-capability table (GCP and Azure findings were stale; AWS's
  held) and adds a second, previously unexamined axis — hosted vs.
  self-hosted — verified by web search against current vendor docs plus
  direct introspection of `langchain_mcp_adapters`'s actual installed
  API (`StdioConnection`/`SSEConnection`/`StreamableHttpConnection`/
  `WebsocketConnection` are all real, confirmed types on
  `MultiServerMCPClient`, not assumed from the library's marketing).
  Feeds `docs/composable_foundation_blueprints.md`'s exploration of the
  same single-cluster-creation flow, which reuses this doc's
  hosted-vs-self-hosted table and self-hosted-launch-mechanism table
  directly rather than re-deriving them.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [About Workload Identity Federation for GKE — Google Cloud docs](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Configure Workload Identity Federation with Kubernetes — Google Cloud docs](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-kubernetes)
- [Overview of Managed Identities in AKS — Microsoft Learn](https://learn.microsoft.com/en-us/azure/aks/use-managed-identity)
- [Concepts - Access and identity in AKS — Microsoft Learn](https://learn.microsoft.com/en-us/azure/aks/concepts-identity)
- [Google Cloud MCP servers overview — Google Cloud docs](https://docs.cloud.google.com/mcp/overview)
- [Organization policy constraints — Google Cloud docs](https://docs.cloud.google.com/organization-policy/reference/org-policy-constraints)
- [Use custom organization policies for allow policies — Google Cloud docs](https://docs.cloud.google.com/iam/docs/org-policy-custom-constraints)
- [Deny access to resources — Google Cloud docs](https://cloud.google.com/iam/docs/deny-access)
- [When and where to use IAM permissions boundaries — AWS Security Blog](https://aws.amazon.com/blogs/security/when-and-where-to-use-iam-permissions-boundaries/)
- [Use the GKE remote MCP server — Google Cloud docs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/use-gke-mcp)
- [Azure Kubernetes Service Tools — Azure MCP Server docs](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/tools/azure-kubernetes)
- [Azure/Azure-Resource-Manager-MCP — GitHub](https://github.com/Azure/Azure-Resource-Manager-MCP)
- [Azure/aks-mcp — GitHub](https://github.com/Azure/aks-mcp)

**Part E additions (2026-07-24):**
- [GKE MCP reference — Google Cloud docs](https://docs.cloud.google.com/kubernetes-engine/docs/reference/mcp)
- [GoogleCloudPlatform/gke-mcp — GitHub](https://github.com/GoogleCloudPlatform/gke-mcp)
- [microsoft/mcp catalog — GitHub](https://github.com/microsoft/mcp)
- [Azure MCP Server get started — Microsoft Learn](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/get-started)
- [Deploy a remote Azure MCP Server — Microsoft Learn](https://learn.microsoft.com/en-us/azure/developer/azure-mcp-server/how-to/deploy-remote-mcp-server-microsoft-foundry)
- [Azure-Resource-Manager-MCP FAQ — GitHub](https://github.com/Azure/Azure-Resource-Manager-MCP/blob/main/docs/FAQ.md)
- [Amazon EKS MCP tool configurations — AWS docs](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-tool-configurations.html)
- [Amazon EKS MCP getting started — AWS docs](https://docs.aws.amazon.com/eks/latest/userguide/eks-mcp-getting-started.html)
- [awslabs.eks-mcp-server — PyPI](https://pypi.org/project/awslabs.eks-mcp-server/)
- [Amazon EKS MCP Server — AWS Labs MCP docs](https://awslabs.github.io/mcp/servers/eks-mcp-server)
- [Terraform MCP server deploy overview — HashiCorp Developer](https://developer.hashicorp.com/terraform/mcp-server/deploy)
- [Terraform MCP server remote deploy — HashiCorp Developer](https://developer.hashicorp.com/terraform/mcp-server/deploy/remote)
