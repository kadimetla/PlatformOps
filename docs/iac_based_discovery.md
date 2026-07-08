# IaC-Based Discovery — Closing the GCP Gap by Reusing What's Already Built

## Status
Design only. Closes the GCP VPC-discovery gap flagged in
`docs/foundation_discovery_and_capability_matching.md` Part B — not
with a new tool, but by using infrastructure this project already has
(`terraform-mcp-server`, `WorkspaceBundle.tfe_workspace`,
`kubernetes-mcp-server`) plus one new finding (GCP Config Connector).
Also corrects that doc's implicit discovery-priority assumption:
IaC state should be queried *before* live API discovery when a source
is registered, not treated as a GCP-only fallback.

## Part A: Three IaC-based discovery paths, ranked by existing support

### 1. Terraform state — zero new integration
This project already has `terraform-mcp-server` integrated
(`mcp_server/external_servers.py`) and `WorkspaceBundle.tfe_workspace`
(`harness/schemas.py:31`) already names a BU's HCP Terraform workspace.
If a BU's foundation is Terraform-managed, discovery is a query against
a workspace via a tool already in this codebase — not a new
integration, a new *use* of one that exists.

### 2. GCP Config Connector — new finding, reuses `kubernetes-mcp-server`
GCP Config Connector represents GCP resources as Kubernetes custom
resources, reconciled with a `.status` field reflecting live state,
queryable via standard K8s API calls
(`kubectl get <resource> -o jsonpath='{.status...}'`). Since this
project already plans `kubernetes-mcp-server` for Helm deploys
(`docs/eks_helm_mcp_integration.md`), the same server can read
Config Connector resource status for any BU using it — a natural fit
for GKE-centric BUs specifically, no new server required.

### 3. Everything else — genuinely unclosed
Deployment Manager, Pulumi, raw ClickOps: no integration exists for
any of these. Correctly falls back to the already-designed unmanaged-
foundation adoption-review flow
(`docs/foundation_discovery_and_capability_matching.md` Part D) —
"found, but no queryable IaC source" is risk-equivalent to "found but
unmanaged," same approval bar, not a new case to design.

## Part B: `IacSourceRef` — where a BU's foundation IaC lives
```python
class IacSourceRef(BaseModel):
    tool: str  # "terraform" | "config_connector" | "none"
    tfe_workspace: Optional[str] = None
    config_connector_cluster: Optional[str] = None  # cluster/namespace hosting the CRs
```
Added to `WorkspaceBundle` as `foundation_iac_source:
Optional[IacSourceRef]` — **kept distinct from the existing
`tfe_workspace` field**, which names the workspace used for *app-layer*
provisioning (the CDK-vs-Terraform toolchain choice in
`provision-infra`). The two may point at the same workspace in the
common case (a BU that uses Terraform for everything), but aren't
required to — a BU could provision new app resources via CDK while its
foundation was set up, once, via a different team's Terraform.

### Resolution order: reuse the skill-precedence pattern, don't invent a new one
Real orgs often centralize the foundation layer — one platform-team-
owned landing-zone Terraform/Config Connector setup that individual
BUs' foundations instantiate — the same platform-team/app-team split
already researched in `docs/infra_discovery_and_platform_app_split.md`.
This is structurally identical to what `docs/skills_and_workspace_design.md`
already solved for skills: "where's the authoritative source, checked
in override order." `IacSourceRef` resolves **BU-level overrides
org-level**, the same bundled→org→BU lookup order already established
for skill resolution — a BU can override its org's shared
landing-zone reference with its own, exactly like a BU can override an
org-level skill. (Org-level `IacSourceRef` storage depends on the
org-registry work already flagged as not-yet-built in
`docs/HARNESS_DESIGN.md`'s open questions — this doc doesn't add a new
dependency, just notes the existing one applies here too.)

## Part C: Discovery-priority correction — IaC first, live API second
`docs/foundation_discovery_and_capability_matching.md` Part B implicitly
treated live API discovery as primary and IaC state as a GCP-specific
fallback. **Corrected here**: IaC state carries *declared intent* —
module names, tags, comments explaining why a subnet exists — that live
API discovery can never recover; it only sees the resulting resource,
not the reasoning behind it. When an `IacSourceRef` is registered for a
BU, discovery should:
1. Query the IaC source first (Terraform state or Config Connector
   status) for the richer, intent-carrying result.
2. Cross-check against live API discovery second, reusing the exact
   drift-reconciliation pattern already designed in
   `docs/infra_discovery_and_platform_app_split.md` Part A (a
   mismatch is a finding to surface, not silently resolved).
3. Only fall back to live-API-only discovery when no `IacSourceRef` is
   registered at all.

This applies to AWS and Azure too, not just GCP — their live discovery
tooling is stronger (per
`docs/foundation_discovery_and_capability_matching.md` Part B's table),
but they still lose the "why" that IaC state carries. The GCP gap is
what surfaced this, but the fix generalizes.

## Updated per-provider discovery table
| Provider | IaC-based discovery | Live API discovery (now the cross-check, not primary) |
|---|---|---|
| **AWS** | Terraform state via `terraform-mcp-server`, if `IacSourceRef.tool == "terraform"` | `awslabs.eks-mcp-server` read tools + `ccapi-mcp-server list_resources` (unchanged from prior doc) |
| **GCP** | Terraform state, **or** Config Connector status via `kubernetes-mcp-server` (new) | GKE MCP (read-only, cluster-internal only) — VPC-level live discovery still has no dedicated tool, but is no longer the only option now that IaC-based paths exist |
| **Azure** | Terraform state, if used | AKS MCP server integration + `azure-resource-graph-mcp-server` (unchanged, already solid) |

## Open questions / not yet decided
- Whether `IacSourceRef` should also cover Pulumi given enough demand —
  not designed, `pulumi stack export` gives structured JSON that could
  follow the same pattern as Terraform state, but no integration point
  has been researched.
- Org-level `IacSourceRef` storage is blocked on the same org-registry
  gap `docs/HARNESS_DESIGN.md` already tracks as open — not a new
  blocker introduced here.
- Whether a mismatch between IaC-declared intent and live reality
  (e.g., a tag says "app-tier subnet" but nothing app-layer is actually
  there) should be surfaced differently from a plain existence-drift
  mismatch — not decided, likely the same audit-log treatment either
  way.

## How this relates to the existing docs
- Closes the GCP gap flagged in
  `docs/foundation_discovery_and_capability_matching.md` Part B, and
  corrects that doc's implicit live-API-primary assumption (Part C
  above) — that doc's table should be read alongside this one's updated
  version, not in isolation.
- Reuses `docs/skills_and_workspace_design.md`'s bundled→org→BU
  precedence pattern for `IacSourceRef` resolution, rather than
  inventing a new lookup order.
- Reuses `docs/infra_discovery_and_platform_app_split.md` Part A's
  drift-reconciliation mechanism unchanged, just reordered (IaC first,
  live API second) rather than replaced.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Config Connector overview — Google Cloud docs](https://cloud.google.com/config-connector/docs/overview)
- [How Config Connector compares for infrastructure management — Google Cloud blog](https://cloud.google.com/blog/products/devops-sre/how-config-connector-compares-for-infrastructure-management/)
- [GoogleCloudPlatform/k8s-config-connector — GitHub](https://github.com/GoogleCloudPlatform/k8s-config-connector)
