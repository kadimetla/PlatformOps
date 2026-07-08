# Foundation Discovery & Capability Matching

## Status
Design only. Closes two related gaps in prior docs:
1. `docs/foundation_and_app_deploy_flow_example.md`'s Phase 1 only
   designed the "discovery finds nothing → create new" branch. The
   "discovery finds an existing foundation → use its details to pick a
   compatible app stack" branch never existed.
2. `FoundationRecord` (`docs/foundation_app_layering_and_iam_tiers.md`
   Part D) is an existence record only — no field captured *what a
   foundation can support*, so even a successful discovery had nothing
   for the app-layer skill to actually consume.

## Part A: Discovery is three branches, not two
Before either foundation-tier or app-tier action runs, for a given
`(org_id, bu_id, cloud_provider)`:

1. **`FoundationRecord` exists, live discovery confirms it** — reuse
   branch. Load `discovered_capabilities` (Part C), proceed to app-stack
   selection (Part E).
2. **Neither a `FoundationRecord` nor live discovery finds anything** —
   the already-designed "create new" branch
   (`docs/foundation_app_layering_and_iam_tiers.md` Part A,
   `docs/multi_cloud_foundation_and_iam.md` for the per-provider split).
3. **Live discovery finds a foundation, but no `FoundationRecord` exists
   for it** — an *unmanaged* foundation, provisioned outside this
   harness entirely (manually, by another tool, before this project
   existed). **New branch, not previously designed** — see Part D.

A fourth, already-designed case sits alongside these: `FoundationRecord`
says active but live discovery disagrees (the resource is gone) — the
drift-reconciliation case from
`docs/infra_discovery_and_platform_app_split.md` Part A, fails closed,
unchanged by this doc.

## Part B: Per-provider discovery tooling
**Updated by `docs/iac_based_discovery.md`** — that doc closes the GCP
gap below via IaC-based discovery (Terraform state, or Config Connector
status through the same `kubernetes-mcp-server` already planned for
Helm) rather than a new live-API tool, and corrects this table's
implicit "live API is primary" framing: when a BU has a registered
`IacSourceRef`, IaC state is queried first, live API discovery is the
cross-check — read that doc's Part C before treating "live API" as the
only or primary column here.

| Provider | Cluster-internal discovery | Network-level (VPC/VNet/subnet) discovery |
|---|---|---|
| **AWS** | `awslabs.eks-mcp-server`'s read tools (`list_k8s_resources`, `get_eks_insights`) | `get_eks_vpc_config` (same server) + `ccapi-mcp-server list_resources` for broader `AWS::EC2::VPC` detail — solid coverage |
| **GCP** | GKE MCP server — confirmed **read-only**, a clean fit for discovery specifically (no write-permission fight needed) | **No dedicated live-API tool** (GCE MCP server's scope is VM/compute primitives, not VPC networking) — **but see `docs/iac_based_discovery.md`**: Terraform state or GCP Config Connector status (via `kubernetes-mcp-server`) close this without one. Live-API-only discovery for a BU with no `IacSourceRef` registered remains genuinely unclosed. |
| **Azure** | AKS's own MCP server integration (`learn.microsoft.com/.../aks-model-context-protocol-server`) | **Confirmed, stronger than expected**: that same server retrieves *"VNets, Subnets, Network Security Groups (NSGs), and Route Tables"* tied to the cluster directly. A separate open-source `azure-resource-graph-mcp-server` (github.com/hardik-id) also exists for broader Resource Graph queries — concrete KQL sample queries exist for listing VNets+subnets+CIDR ranges across subscriptions. |

Worth stating plainly: **discovery capability and creation capability
don't track each other per provider.** AWS and Azure have solid native
discovery tooling; GCP's write path is also absent (per
`docs/multi_cloud_foundation_and_iam.md`) *and* its network-discovery
tooling is the weakest of the three. GCP is the provider needing the
most manual/custom tooling work on both axes.

## Part C: `discovered_capabilities` — what `FoundationRecord` was missing
```python
class FoundationRecord(BaseModel):
    foundation_id: str
    org_id: str
    bu_id: str
    cloud_provider: str
    resource_type: str
    resource_identifier: str
    approved_plan_id: str
    status: str = "active"
    discovered_capabilities: Dict[str, Any] = Field(default_factory=dict)
    # Shape (provider-dependent, not a fixed schema — see below):
    #   k8s_version: str
    #   installed_addons: list[str]         # e.g. ["aws-load-balancer-controller", "ebs-csi-driver"]
    #   ingress_classes_available: list[str]
    #   storage_classes_available: list[str]
    #   node_pool_shapes: list[dict]        # instance types / GPU presence per pool
    #   workload_identity_target: str       # AWS: OIDC provider ARN; GCP: Workload Identity Pool;
    #                                       # Azure: federated-credential issuer -- the ONE thing a
    #                                       # new app identity must bind to, never duplicate
    #   namespace_conventions: list[str]
    #   subnet_tags_for_app_placement: dict  # e.g. which subnets/security-groups are meant for app resources
```
Populated at discovery time (both the "reuse" and the "unmanaged, now
adopted" branches), refreshed periodically or on next discovery pass —
staleness handling not designed here, see Open Questions.

## Part D: Unmanaged foundations require adoption review, not automatic trust
The branch most likely to get the safety story wrong if skipped. Live
discovery finding a cluster does not mean this harness knows how it was
provisioned, what IAM hygiene it has, or whether its network layout is
sound — "found" is not "trusted."

**Rule**: an unmanaged foundation requires the same human-approval bar
as creating a new one before any app-layer deploy is allowed against
it — "found but unmanaged" is risk-equivalent to "not found," never a
shortcut past approval. Concretely:
1. Discovery finds a foundation with no matching `FoundationRecord`.
2. An adoption review is triggered — a human reviewer (a `TeamMember`
   with `role="approver"`/`"admin"`, `scope="foundation"` per
   `docs/infra_discovery_and_platform_app_split.md` Part C) examines
   what discovery found: node/cluster IAM role separation (the
   four-role model, `docs/infra_discovery_and_platform_app_split.md`
   Part B), whether a permissions-boundary-equivalent ceiling exists on
   any discoverable roles, network layout sanity — as much of the same
   bar a fresh creation would have been held to as can be determined
   after the fact.
3. **Approved**: a `FoundationRecord` is created retroactively,
   `status="active"`, `discovered_capabilities` populated — now
   reusable like any other foundation.
4. **Rejected**: no `FoundationRecord` is created. App-layer deploys
   against that foundation stay blocked. This project does not tear
   down or modify infrastructure it didn't create and wasn't asked to
   manage — rejection just means "not usable through this harness,"
   not "delete it."

## Part E: `deploy-to-k8s` gains a discovery-informed first step
Extends the procedure in `docs/foundation_app_layering_and_iam_tiers.md`
Part C with a new step 0, before the existing steps:

0. **Load the foundation's `discovered_capabilities`.** Select chart
   values, the workload-identity binding target, namespace, and
   storage/ingress class from what's actually available — reject or
   flag any requirement the foundation can't satisfy (e.g., a chart
   requesting an `ingress.className` the cluster doesn't have, or GPU
   scheduling against a foundation with no GPU node pool), rather than
   deploying something broken and finding out at runtime.

## Open questions / not yet decided
- `discovered_capabilities` staleness: how often does a foundation get
  re-discovered, and does a stale capability set block a deploy or just
  get logged as a warning? Not decided.
- Whether GCP's VPC-discovery gap gets solved by wrapping raw `gcloud`
  API calls in a custom tool, or by requiring GCP foundations to always
  be Terraform-managed (so state is always the discovery source) — not
  decided, the second option is lower-effort but constrains the
  creation-path choice for that one provider.
- Exact adoption-review checklist (Part D, step 2) — sketched at the
  level of "the same bar a fresh creation would have," not itemized
  into a concrete checklist yet.
- Whether `discovered_capabilities`' shape should be a typed
  per-provider schema (`AwsFoundationCapabilities`,
  `GcpFoundationCapabilities`, ...) rather than an untyped `Dict[str, Any]`
  — likely yes eventually, left untyped here since the exact fields
  needed are still being discovered themselves.

## How this relates to the existing docs
- Fills the gap in `docs/foundation_and_app_deploy_flow_example.md`'s
  Phase 1 — that doc's discovery step ("Discovery first, not blind
  creation... None found — proceeds to draft") only ever exercised the
  "not found" outcome; this doc is what the other outcomes require.
- Extends `FoundationRecord`
  (`docs/foundation_app_layering_and_iam_tiers.md` Part D) with
  `discovered_capabilities`, and `deploy-to-k8s`
  (same doc, Part C) with the new step 0.
- Extends `docs/infra_discovery_and_platform_app_split.md` Part A's
  AWS-only discovery findings to GCP/Azure, and its drift-reconciliation
  case is unchanged, referenced not repeated.
- Extends `docs/multi_cloud_foundation_and_iam.md`'s per-provider write-
  capability table with the complementary discovery-capability table
  (Part B) — the two don't track each other per provider, worth reading
  both tables side by side.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [AKS Model Context Protocol (MCP) server — Microsoft Learn](https://learn.microsoft.com/en-us/azure/aks/aks-model-context-protocol-server)
- [Azure Resource Graph sample queries for Azure networking — Microsoft Learn](https://learn.microsoft.com/en-us/azure/networking/fundamentals/resource-graph-samples)
- [hardik-id/azure-resource-graph-mcp-server — GitHub](https://github.com/hardik-id/azure-resource-graph-mcp-server)
- [VPC networks — Google Cloud docs](https://cloud.google.com/vpc/docs/vpc)
- [Subnets — Google Cloud docs](https://docs.cloud.google.com/vpc/docs/subnets)
