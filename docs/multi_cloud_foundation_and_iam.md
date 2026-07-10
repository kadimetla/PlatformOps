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

## How this relates to the existing docs
- **Extends** `docs/foundation_app_layering_and_iam_tiers.md`,
  `docs/eks_helm_mcp_integration.md`, and
  `docs/infra_discovery_and_platform_app_split.md` from AWS-only to
  three providers — see those docs for the AWS-specific detail this
  doesn't repeat.
- **Corrects** `docs/foundation_app_layering_and_iam_tiers.md` Part C's
  `deploy-to-eks` skill name to `deploy-to-k8s`, since the underlying
  tool was never AWS-specific.
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
