# Cross-Project/Account/Subscription Network Sharing — Per Provider

## Status
Research, verified via direct search (current provider docs cited, not
training-data recall) plus design analysis of what it breaks in this
project's existing model. Nothing built. Surfaced while exploring the
`infra-inventory-discovery` OpenSpec change's bootstrap-discovery design
— a BU with multiple cloud projects/accounts (already established as
normal, `docs/multi_account_per_bu_design.md`) commonly shares one
network across them, and this project's design never accounted for
that.

## Part A: Three different shapes, not one concept with three names
Unlike VPC/VNet terminology itself (which maps cleanly 1:1 across
providers), how a network gets *shared* across project/account/
subscription boundaries is genuinely different in each cloud — not a
naming difference, a structural one.

### GCP: Shared VPC — a strict two-tier permission model, host/service split
One project (the **host project**) owns the VPC; other projects
(**service projects**) get attached and can deploy resources — GKE
clusters, VMs, VPC-connected Cloud Functions — directly into the host
project's subnets using internal IPs, without owning the network
themselves. Two separate permission layers, confirmed from Google's own
docs:
1. **`roles/compute.xpnAdmin` (Shared VPC Admin) must be granted at the
   org or folder level** — granting it on the host project itself does
   nothing. This is the "can this project even become a host/service
   project" gate.
2. **`roles/compute.networkUser`, granted per-subnet** by the host
   project's admin — the "can this specific service project actually
   deploy into this specific subnet" gate.

There's no single place to check "who can use this network" — two
different scopes, checked separately.

### AWS: VPC sharing via RAM — subnet-level, owner/participant, same Organization required
The VPC owner shares individual **subnets** (not the VPC as one unit)
with participant accounts, both inside the same AWS Organization. The
owner manages networking (subnets, route tables, NACLs, gateways);
participants manage only their own resources inside the shared subnet.
Confirmed: *"participants cannot view, modify, or delete resources that
belong to other participants or the VPC owner"* — clean resource-level
isolation even while sharing network space. A shared subnet's owning
account (`OwnerId` via `DescribeSubnets`) stays explicitly queryable
even after sharing — the ownership boundary never gets ambiguous.

### Azure: VNet peering — no owner at all, peer-to-peer, non-transitive
Structurally different from the other two, not just differently named.
Peering connects two VNets as equals — there's no "host." Confirmed:
**peering is not transitive** — if Hub peers with Spoke-A and Hub peers
with Spoke-B, Spoke-A and Spoke-B still can't reach each other directly;
hub-spoke topologies need explicit routing through the hub (an NVA, VPN
gateway, or Azure Firewall). Cross-subscription and cross-tenant peering
both work, but the Azure Portal doesn't support setting either up
directly — CLI/PowerShell only. Cross-tenant peering specifically
requires the same user to exist in both tenants with `Network
Contributor` at the subscription level in *both*.

## Part B: Why this breaks an assumption already baked into this project's design
`docs/foundation_layer_decomposition.md`'s network→compute→identity
chain implicitly assumed a network resource and the compute resource
using it live in the same discoverable boundary — true for a
single-account BU, false the moment `docs/multi_account_per_bu_design.md`'s
already-established premise (*"a BU can hold multiple accounts"*) meets
any of the sharing patterns above. This isn't a hypothetical edge case —
sharing one network across multiple projects/accounts is the *idiomatic*
pattern in GCP specifically, common in AWS, and structurally how Azure's
hub-spoke model works at all.

## Part C: Concrete discovery implications per provider — each breaks differently
- **GCP**: *existence*-level discovery of network resources anywhere in
  scope is now covered in one call by Cloud Asset Inventory's
  `list_assets` (Part H below) — no host-project lookup required just to
  answer "does this network/subnet exist." But *resolving which host
  project a given service project is attached to*, the relationship this
  section is actually about, still needs the host-project lookup and
  `networkUser` binding check — Cloud Asset Inventory doesn't confirm
  covering that relationship type. So: one lookup for "what networks
  exist," still a separate two-step sequence (Part D) for "which host
  project is this service project's network actually in."
- **AWS**: a shared subnet's true owner account is always explicit in
  the resource itself (`OwnerId`) — the cross-boundary case is more
  mechanically discoverable than GCP's, still cross-account, but no
  separate "which project owns this" lookup needed first.
- **Azure**: not a two-party host/participant lookup at all — a **graph
  traversal problem** (which VNets does this one peer with, transitively
  through a hub). Topologically the hardest of the three, since there's
  no single authoritative owner to query — you have to walk the peering
  graph to know what's actually reachable.

## Part D: GCP's exact discovery API calls, verified
The internal API surface still calls Shared VPC by its old codename
**"XPN"** throughout, even though the user-facing product name is
"Shared VPC" — worth knowing before these method names look unrelated
to the feature.

**1. `compute.projects.getXpnHost`** — the host-project lookup itself:
```
GET https://compute.googleapis.com/compute/v1/projects/{project}/getXpnHost
```
Called *as the service project*. Returns the host project's full
`Project` resource it's linked to — empty if the project isn't attached
to any Shared VPC host at all.

**2. `compute.subnetworks.listUsable`** — the actual network-layer
discovery step, not just the relationship check:
```
GET https://compute.googleapis.com/compute/v1/projects/{HOST_PROJECT_ID}/aggregated/subnetworks/listUsable
```
(`gcloud compute networks subnets list-usable --project=HOST_PROJECT_ID
--service-project=SERVICE_PROJECT_ID` in CLI form.) Called *against the
host project*, scoped to a specific service project — returns every
subnet that service project can actually use, whether owned by the host
or shared into it. This is the call that would populate
`InfraInventoryRecord`'s network-layer rows for a service project.

**3. `compute.projects.getXpnResources`** — the reverse direction, for
top-down discovery starting from a known shared-network project rather
than per-service-project:
```
GET https://compute.googleapis.com/compute/v1/projects/{HOST_PROJECT_ID}/getXpnResources
```
Called *against a host project*, lists every service project attached
to it.

**The concrete sequence** for a GCP service project, now fully
specified rather than a named-but-unverified gap:
```
1. getXpnHost(service_project)               → host project ID, or empty
                                                 (not shared — discover normally)
2. listUsable(host_project,                  → the actual usable subnet list —
     service_project=service_project)           the InfraInventoryRecord write
```

## Part E: AWS's exact discovery API calls, verified
Simpler than GCP's, for the common case — no extra lookup needed at all
for per-BU discovery.

**`DescribeSubnets`, called in the participant/service account itself,
already returns shared subnets.** That's the whole point of RAM
resource sharing — the shared resource becomes visible in the
participant's own account context. Each subnet's `OwnerId` field shows
the *original* owning account; if it differs from the calling account's
own ID, that subnet is shared-in, not owned. For per-BU discovery
specifically, this confirms Part C's original claim precisely: no
separate "which account owns this" lookup is required before
`DescribeSubnets` — the ownership signal comes back on the same call.

The RAM-specific APIs matter for the **owner/network account's** view —
seeing the full sharing configuration and who it's shared with, the AWS
analog of GCP's `getXpnResources`:
1. **`GetResourceShares`** — find resource shares owned or shared with
   the caller
2. **`ListResources`** (`resource-type=ec2:Subnet`, scoped to a
   resource-share ARN) — get the actual shared subnet resources
3. **`GetResourceShareAssociations`** (`association-type=PRINCIPAL`) —
   which accounts have access to those shares

## Part F: Azure's exact discovery API calls, verified — and a better mechanism than naive graph-walking
**Per-VNet REST**, confirms the graph-traversal characterization from
Part C is real:
```
GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet}/virtualNetworkPeerings?api-version=2024-03-01
```
Returns one VNet's direct peers only — transitive reachability means
recursively following each peering's `remoteVirtualNetwork` reference,
VNet by VNet.

**But Azure Resource Graph (KQL) is the practical mechanism for
bootstrap-scale discovery, not per-VNet REST calls.** One query against
the `virtualNetworks` resource type, expanding the
`virtualNetworkPeerings` property, returns every VNet and its peering
edges **across every subscription the caller has Reader access to, in
one call** — Resource Graph runs cross-subscription by default, capped
at 1000 rows per response, paginated beyond that. The better design:
fetch the whole peering graph's edges in one (or a few, paginated)
Resource Graph query, then do the actual BFS/DFS traversal **locally, in
process**, against the already-fetched edge list — not recursive
per-VNet API calls. The same "bulk listing, then reason locally" shape
GCP's `listUsable` already gives for free, applied to a genuine graph
instead of a flat list.

**Cross-tenant is the one place this doesn't fully resolve**: Resource
Graph only sees what the calling identity itself has access to —
genuine cross-tenant discovery still needs Azure Lighthouse delegation,
confirming what Part A already flagged, not a new gap this narrows.

## Part G: Could Terraform itself abstract away Parts D–F? Verified — no, not for this
Worth checking directly rather than assuming, since `terraform-mcp-server`
is already integrated in this project: could an ad-hoc, data-source-only
Terraform configuration (`data "google_compute_shared_vpc_host_project"`,
`data "aws_subnets"`, `data "azurerm_virtual_network_peering"`) replace
Parts D–F's raw provider API calls with one consistent tool instead of
three provider integrations?

**Checked the real, current tool surface — it doesn't support this.**
`create_run`'s documented run types are exactly two: `plan_and_apply`
and `refresh_state`, both scoped to an **existing HCP Terraform/
Terraform Enterprise workspace** with configuration already associated
(VCS-linked or CLI-uploaded). There is no "evaluate these data sources
on demand, no existing workspace needed" capability anywhere in the
documented surface. Using Terraform for this would mean maintaining a
dedicated, pre-configured discovery workspace per BU/org with the right
data-source blocks already committed — a real, ongoing operational
burden, not the lightweight reuse this section originally floated. For
resources with no Terraform representation at all (exactly what the
live-listing pass exists to catch), there's nothing to attach that
discovery to in the first place.

**Corrected 2026-07-24 — the tool surface has since grown, still no
write path for the case this section cares about.**
`docs/composable_foundation_blueprints.md`'s Q5 re-checked the same
server against HashiCorp's current tool reference (not re-reading this
section's original claim from memory) and found `list_stacks`/
`get_stack_details` now exist — genuinely new since this was written.
Both are **read-only**, confirmed directly against the tool reference:
no create/deploy/plan/apply path for a Stack exists through this server
today. This doesn't change the conclusion below (raw provider APIs
remain necessary for cross-project sharing discovery specifically), but
the blanket "no Stacks capability at all" framing above is now stale —
the two new read tools are a real capability worth knowing about for a
different problem (verifying a Blueprint's declared wiring against a
real Stack's component graph, `docs/composable_foundation_blueprints.md`
Q2), just not this one.

**Conclusion**: raw provider APIs (Parts D–F) remain the verified,
necessary mechanism for cross-project sharing discovery. This doesn't
generalize away — don't design toward an ad-hoc-Terraform-discovery
shortcut for this specific problem.

One real, useful thing this check did surface: **`refresh_state`** — a
genuine, documented run type, *"refreshes state without making
changes"* — is the concrete Terraform-path mechanism for checking drift
on resources **already tracked** in a workspace's state. That's a
different problem than this doc covers (discovering resources with no
existing state at all), but it directly concretizes
`infra-inventory-discovery`'s nightly-drift-sweep design — see that
change's `design.md` and spec.

## Part H: Cloud Asset Inventory closes the GCP existence-level discovery gap — verified, and it's narrower than it first looks
`docs/gcp_azure_verification_pass.md` Section 6 originally stated a GCP
live-discovery gap as "confirmed still open" — that was incomplete
research, not a genuine absence. The original search only checked for
an MCP wrapper around `gcloud compute networks`/`subnets` commands and
the raw Compute Engine networking APIs directly; it never checked
Google's own **managed** Cloud Asset Inventory MCP server
(`cloudasset.googleapis.com`).

**Verified, directly, by inspecting the tool's documented parameters:**
Cloud Asset Inventory has a real `list_assets` tool with:
- `parent` (required) — scoped to an org, folder, or project, i.e.
  exactly the boundary this project's discovery already needs to
  respect per-BU.
- `assetTypes[]` — exact type strings or regex, confirmed to directly
  support `compute.googleapis.com/Network` and
  `compute.googleapis.com/Subnetwork` — the two asset types this
  project's `InfraInventoryRecord` network-layer rows need.
- `readTime` — point-in-time query, up to 35 days back.
- `pageSize`/`pageToken` — standard pagination.
- `contentType` — controls how much detail comes back per asset
  (resource metadata vs. IAM policy vs. relationship, see below).
- `relationshipTypes[]` — the parameter that matters for the Shared VPC
  question specifically.

**What this closes**: for the bootstrap-discovery-sweep's actual job —
"does a network/subnet resource exist in this project/org, list
everything of this type" — `list_assets` is a real, one-call, managed
answer. A GCP BU with no registered `IacSourceRef` is **not** left with
zero live-discovery path, contrary to what four docs in this project
previously stated.

**What this does NOT close, confirmed by the same inspection, not
assumed**: `relationshipTypes[]` queries require Security Command Center
Premium or Enterprise tier, and the specific relationship type that
would matter here — Shared VPC host/service attachment, GCP's internal
name for it is `XpnResource` per Part D's terminology note — was not
found documented as one of the supported relationship types even at
that tier. So Cloud Asset Inventory tells you a network *exists* and
roughly what project it's associated with, but doesn't reliably tell
you "this service project is attached to that host project via Shared
VPC" as a queryable relationship. Part D's `getXpnHost`/`listUsable`
sequence remains the verified, necessary mechanism for that specific
question — this doesn't replace Part D, it narrows what was missing
before Part D's calls even entered the picture.

**Net correction**: the original claim was "no live discovery path for
the GCP network layer at all." The corrected claim is "existence-level
discovery is covered by a real managed tool; host/service relationship
resolution specifically still requires the dedicated Shared VPC API
calls in Part D." A narrower, real gap — not the blanket absence
previously written into `docs/gcp_azure_verification_pass.md`,
`docs/iac_based_discovery.md`,
`docs/foundation_discovery_and_capability_matching.md`, and
`openspec/changes/infra-inventory-discovery/design.md`'s risk note, all
corrected alongside this doc.

## Open questions / not yet decided
- The exact Azure Lighthouse delegation setup required for cross-tenant
  Resource Graph queries specifically — named as the mechanism, not
  verified to API-call depth the way the same-tenant case now is. All
  three providers' *same-boundary* discovery mechanics (GCP, AWS, and
  Azure within one tenant) are now fully specified.
- The Azure peering-graph traversal algorithm for discovery purposes —
  flagged as harder than the other two, not designed.
- Whether `InfraInventoryRecord` needs a distinct field for "owning
  boundary" separate from "boundary it was discovered scanning" — a
  network resource's `org_id`/`bu_id` may not be the same as the compute
  resource referencing it. Flagged, not resolved — affects the schema
  `docs/config_storage_backend.md` already gave a home to.

## How this relates to the existing docs
- Extends `docs/foundation_layer_decomposition.md`'s network→compute→identity
  chain — that doc's dependency model assumed one discoverable boundary
  per layer; this doc shows that assumption breaks under any of the
  three sharing patterns above.
- Extends `docs/multi_account_per_bu_design.md`'s "a BU can hold
  multiple accounts" premise with the specific networking consequence of
  that premise nothing else in this project's design had worked through.
- Extends `docs/multi_cloud_foundation_and_iam.md`'s per-provider
  concept mapping (VPC/VPC-Network/VNet) with the one dimension that
  doesn't map 1:1 across providers — how sharing works, not what the
  thing being shared is called.
- Feeds directly into `openspec/changes/infra-inventory-discovery/`'s
  bootstrap-discovery-sweep design — its GCP network-discovery-gap risk
  note is corrected by Part H's finding, narrowed from "no discovery
  path" to "existence-level discovery covered, relationship resolution
  still gapped" (see that change's `design.md`).
- Part G's `refresh_state` finding concretizes that same change's
  nightly-drift-sweep native-drift-detection mechanism — a different
  problem (already-tracked resources) from the rest of this doc
  (resources with no tracking at all), captured there, not here.
- Part H corrects `docs/gcp_azure_verification_pass.md` Section 6,
  `docs/iac_based_discovery.md`'s GCP row, and
  `docs/foundation_discovery_and_capability_matching.md`'s original
  finding — all previously stated the gap as a blanket absence; this
  doc is the detailed verification backing the narrower correction made
  in each.
- Doesn't change the one required next step
  (`plan_request(envelope)`, already implemented — this is a discovery/
  inventory-side concern, unrelated to the drafting boundary).

## Sources
- [Shared VPC overview — Virtual Private Cloud, Google Cloud Documentation](https://docs.cloud.google.com/vpc/docs/shared-vpc)
- [Provision Shared VPC — Virtual Private Cloud, Google Cloud Documentation](https://docs.cloud.google.com/vpc/docs/provisioning-shared-vpc)
- [Share your VPC subnets with other accounts — Amazon Virtual Private Cloud docs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-sharing.html)
- [VPC sharing: A new approach to multiple accounts and VPC management — AWS Networking & Content Delivery Blog](https://aws.amazon.com/blogs/networking-and-content-delivery/vpc-sharing-a-new-approach-to-multiple-accounts-and-vpc-management/)
- [Shared subnet prerequisites — Amazon Virtual Private Cloud docs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-share-prerequisites.html)
- [Azure Virtual Network Peering overview — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview)
- [Create Virtual Network Peering Between Different Subscriptions — Microsoft Learn](https://learn.microsoft.com/en-us/azure/virtual-network/create-peering-different-subscriptions)
- [Virtual Network Connectivity Options and Spoke-To-Spoke Communication — Azure Architecture Center, Microsoft Learn](https://learn.microsoft.com/en-us/azure/architecture/reference-architectures/hybrid-networking/virtual-network-peering)
- [Method: projects.getXpnHost — Compute Engine, Google Cloud Documentation](https://docs.cloud.google.com/compute/docs/reference/rest/v1/projects/getXpnHost)
- [Method: subnetworks.listUsable — Compute Engine, Google Cloud Documentation](https://cloud.google.com/compute/docs/reference/rest/v1/subnetworks/listUsable)
- [Method: projects.getXpnResources — Compute Engine, Google Cloud Documentation](https://cloud.google.com/compute/docs/reference/rest/v1/projects/getXpnResources)
- [DescribeSubnets — Amazon Elastic Compute Cloud API Reference](https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSubnets.html)
- [ListResources — AWS Resource Access Manager API Reference](https://docs.aws.amazon.com/ram/latest/APIReference/API_ListResources.html)
- [GetResourceShares — AWS Resource Access Manager API Reference](https://docs.aws.amazon.com/ram/latest/APIReference/API_GetResourceShares.html)
- [GetResourceShareAssociations — AWS Resource Access Manager API Reference](https://docs.aws.amazon.com/ram/latest/APIReference/API_GetResourceShareAssociations.html)
- [Virtual Network Peerings - List — REST API (Azure Virtual Networks), Microsoft Learn](https://learn.microsoft.com/en-us/rest/api/virtualnetwork/virtual-network-peerings/list)
- [Azure Resource Graph sample queries for Azure networking — Microsoft Learn](https://learn.microsoft.com/en-us/azure/networking/resource-graph-samples)
- [How to Query Azure Resource Graph Across Multiple Subscriptions and Management Groups — OneUptime](https://oneuptime.com/blog/post/2026-02-16-how-to-query-azure-resource-graph-across-multiple-subscriptions-and-management-groups/view)
- [hashicorp/terraform-mcp-server — GitHub](https://github.com/hashicorp/terraform-mcp-server)
- [Terraform MCP server overview — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/mcp-server)
- [Terraform MCP server reference — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/mcp-server/reference)
- [Terraform MCP server updates: Stacks support, new tools, and tips — HashiCorp Blog](https://www.hashicorp.com/en/blog/terraform-mcp-server-updates-stacks-support-new-tools-and-tips)
- [Cloud Asset Inventory overview — Google Cloud Documentation](https://cloud.google.com/asset-inventory/docs/overview)
- [ListAssets — Cloud Asset API, Google Cloud Documentation](https://cloud.google.com/asset-inventory/docs/reference/rest/v1/assets/list)
- [Searching for relationships — Cloud Asset Inventory, Google Cloud Documentation](https://cloud.google.com/asset-inventory/docs/searching-relationships)
- [Supported asset types — Cloud Asset Inventory, Google Cloud Documentation](https://cloud.google.com/asset-inventory/docs/asset-types)
