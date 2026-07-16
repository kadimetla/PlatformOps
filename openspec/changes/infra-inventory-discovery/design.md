## Context

`wire-plan-request-envelope` (archived-pending) built the request-time
skill-matching path but deliberately left resource-level discovery out
of scope. Working through it in chat afterward surfaced that this
project's only existing discovery design (`docs/foundation_discovery_and_capability_matching.md`)
covers foundation-tier reuse specifically — "does a usable network/
compute/identity chain already exist" — not "does the app-tier resource
this request describes already exist." That's a different, previously
undesigned question. Separately, drift (manual add/delete outside the
harness) has no detection mechanism at all today.

## Goals / Non-Goals

**Goals:**
- A persistent record of what app-tier infrastructure exists per BU,
  populated once and kept current cheaply.
- Detect drift — both "something the harness thinks exists is gone" and
  "something exists that the harness never knew about" — without a live
  API call on every request.
- Reuse existing storage/audit infrastructure rather than building a
  second one.

**Non-Goals:**
- Deciding reuse-vs-create automatically at request time. Chat working-through
  concluded exact-name matching is unreliable for that; the right design
  is surfacing candidates and letting the requester confirm, which needs
  `plan_request()` to support pausing mid-request — not designed yet,
  explicitly deferred to a follow-on change.
- Auto-remediating drift. Every mechanism in this change is read/report-only.
- Foundation-tier discovery — already designed and out of scope for this
  change; this is specifically the app-tier gap that design never covered.

## Decisions

**One schema, four population mechanisms, not four schemas.**
`InfraInventoryRecord` is the single shared data model; bootstrap,
incremental, and nightly sweeps all read/write the same table.
Alternative considered: a separate log per mechanism — rejected, same
reasoning `docs/config_storage_backend.md` already established
elsewhere in this project ("one storage system, not many").

```python
class InfraInventoryRecord(BaseModel):
    org_id: str
    bu_id: str
    resource_type: str          # provider-native type string, stored as the
                                 # discovery source returns it -- NOT normalized
                                 # to CFN-style. See "resource_type is
                                 # provider-native" decision below.
    resource_category: Optional[str] = None  # "network" | "compute" |
                                 # "identity" | "storage" | None if unclassified
    resource_identifier: str
    layer: Optional[str] = None # "foundation" | "app" | None if unclassified
    discovered_at: datetime
    provenance: str             # "iac_state" | "live_api"
```

**`resource_type` is provider-native, not CFN-style — corrected
(2026-07-13).** An earlier draft of this schema commented `resource_type`
as *"CFN-style, same convention as `ToolIntent.resource_type`"* — grounded
in `gateway/skill_matching.py`'s real `SPEC_TYPE_TO_CFN_TYPE` table and
`infra/allowed-resource-types.json`, but that convention is genuinely
AWS-only (2 entries, both `AWS::*`) and nothing in this codebase maps a
GCP Cloud Asset Inventory `assetType` (`compute.googleapis.com/Network`)
or an Azure ARM `type` (`Microsoft.Network/virtualNetworks`) into it —
confirmed by direct code search, not assumed. Three genuinely
incompatible namespacing schemes (`Service::Type`,
`service.googleapis.com/Type`, `Provider/type`), not one convention with
different casing.

Two options considered and rejected in favor of provider-native storage
plus a coarse `resource_category` field:
- **Force everything into CFN-style** via per-provider translation
  tables (`GCP_TYPE_TO_CFN_TYPE`, `AZURE_TYPE_TO_CFN_TYPE`, same shape as
  `SPEC_TYPE_TO_CFN_TYPE`) — rejected. Nothing that reads
  `InfraInventoryRecord` today needs full type equivalence:
  `normalize_resource_types()` (the only real consumer of the CFN-style
  convention) operates on `spec['resources']`, which is AWS-only today,
  and never reads `InfraInventoryRecord` at all. Building an exhaustive
  translation table solves a problem nothing currently has, and GCP/Azure
  have resource types with no CFN equivalent at all — an unresolvable
  asymmetry, not just missing entries.
- **Store provider-native with no categorization at all** — rejected
  too far the other way: `tasks.md` 2.3's network-before-compute-before-
  identity discovery ordering (`docs/foundation_layer_decomposition.md`'s
  dependency chain applied to discovery) genuinely needs *some*
  cross-provider comparison — "is this a network resource" — just not
  full type equivalence.

**Chosen: store `resource_type` exactly as the discovery source returns
it, add `resource_category` as a coarse, cheap-to-populate enum for the
one thing that actually needs cross-provider comparison.** Provenance
of the raw type string stays unambiguous (each convention's prefix
self-identifies the provider: `AWS::`, `*.googleapis.com/`,
`Microsoft.*/`), so no separate `cloud_provider` field is added here —
flagged as an open question below in case multi-account-per-BU querying
needs it explicitly rather than inferred from the prefix.

**`layer` is nullable and unreconciled with `FoundationRecord` on
purpose, for now.** Whether this table should eventually absorb
foundation-tier tracking too (a single inventory, not two parallel
ones) is a real question this design doesn't resolve — left as an open
question below rather than forcing a premature unification.

**Bootstrap uses the same IaC-state-first, live-API-second priority
already established** (`docs/iac_based_discovery.md`) — not a new
discovery algorithm, the existing one applied to app-tier resources for
the first time.

**Incremental updates ride on Step 8, not a separate trigger.** The
harness already knows exactly what it created at the moment it creates
it (`BrokeredToolDispatcher`'s existing audit write). Piggybacking the
inventory write onto that same code path costs nothing extra and can't
drift from reality the way a separate, later reconciliation pass could.

**Nightly sweep is ONE pass (live listing) for v1 — corrected
(2026-07-15) from an earlier "two passes" decision.** The original
reasoning was sound as far as it went — CloudFormation's own
`DetectStackDrift` docs confirm it *"only checks resource properties
explicitly defined in the stack template,"* so native drift detection
(CFN `DetectStackDrift`/`DescribeStackResourceDrifts`, Terraform's
`refresh_state` run type) genuinely can't discover a resource with no
IaC representation, which a live listing pass can. But that reasoning
assumed native drift detection's output — property-level drift — was
usable. It isn't yet: `InfraInventoryRecord` is existence-only, no
`properties` field, so even if native drift detection ran and found a
property mismatch, nothing in this schema could represent or surface
that finding. Running a pass whose output can't be stored is not a
mitigation, it's dead work. **Decided**: build the live listing pass
only for v1 — it already catches both "resource exists but harness
never knew" and, by comparing what `InfraInventoryRecord` expects
against what's actually live, "resource the harness tracked no longer
exists." Native drift detection (and the `refresh_state` mechanism
below, which stays a real, verified finding) becomes a genuinely
separate, additive follow-on, explicitly gated on a future
`properties` field being added to `InfraInventoryRecord` — not
something to build in parallel with a schema that can't hold its
output. See `docs/infra_discovery_triggers_and_extensibility.md` Part C
for why this is a safe, additive-schema deferral, not an unresolved
gap.

**The Terraform-path native drift check — for the deferred, future
follow-on pass, not v1 — is `create_run`'s `refresh_state` run type,
verified, not a generic "run `terraform plan`" description.**
`docs/cross_project_network_sharing.md` Part G checked
`terraform-mcp-server`'s real, current tool surface directly: `create_run`
supports exactly two run types, `plan_and_apply` and `refresh_state` —
the latter *"refreshes state without making changes,"* the precise
read-only semantics that future pass would need, scoped to a
workspace's already-tracked resources. That same check confirmed the tool has **no** ad-hoc,
data-source-only query capability — so it cannot be used for the live
listing pass or for discovering resources/relationships with no existing
workspace at all (including the cross-project network sharing case in
that doc); raw provider APIs remain necessary there. `refresh_state`
only concretizes the native-drift-detection half of this sweep.

**Drift findings write to the existing `audit_logs` table as a new
`DRIFT_DETECTED` decision value**, not a new findings store — same
reasoning as the inventory schema decision above, applied to the
existing dispatcher table instead of a new one.

**Report-only, never auto-remediate.** Consistent with this project's
established bias (a failed `SmokeTestResult` blocks and waits for a
human rather than auto-escalating; a drift mismatch is *"a finding to
surface, not silently resolved"*, already stated for a different
discovery case). Recreating a deleted resource or deleting an
unexpected one automatically is a materially different, higher-risk
decision this change doesn't make.

**Discovery walks network → compute → identity, the same order creation
already does — not one unordered pass.** `docs/foundation_layer_decomposition.md`
put network at the root of the creation dependency chain
(`depends_on_foundation_id = None`) precisely because everything else
depends on it; discovery inherits the same reason. Classifying a
discovered compute resource as part of a usable foundation requires
already knowing which VPC/VNet it sits in — discovering compute before
network produces a technically-complete-later but momentarily
uninterpretable inventory, not just a differently-ordered one.
Alternative considered: discover everything in one unordered pass,
classify relationships afterward — rejected, since a live listing call
returning resources in arbitrary order gives no way to tell a
dependency edge from two unrelated resources without the network
context already in hand. **This ordering is exactly what
`resource_category` exists to make cheap** — each provider's discovery
call classifies its own results (`compute.googleapis.com/Network` /
`compute.googleapis.com/Subnetwork` → `"network"`; `AWS::EC2::VPC` /
`AWS::EC2::Subnet` → `"network"`; `Microsoft.Network/virtualNetworks` →
`"network"`, and so on per category) at write time, so the ordering pass
filters on one coarse field instead of re-deriving "is this a network
resource" from three different provider-native type vocabularies at
read time.

## Risks / Trade-offs

- [Risk] The nightly sweep runs per org, inside that org's own isolated
  deployment (per `docs/saas_deployment_staging.md`'s isolation model) —
  cron scheduling mechanics aren't chosen yet (system cron vs.
  APScheduler vs. a scheduled workflow in whatever outer engine gets
  adopted) → [Mitigation] not a blocker for this change's core schema
  and bootstrap/incremental pieces; the nightly sweep's *logic* can be
  built and tested independent of *how* it gets triggered, and the
  trigger mechanism is a narrow, swappable piece.
- [Risk] `resource_identifier`-based lookups inherit the same
  naming-stability weakness already identified for request-time
  matching — two resources serving the same real-world purpose but
  named differently by different requests would show up as two separate
  inventory rows → [Mitigation] out of scope here; this change only
  builds the inventory itself, not the request-time matching logic that
  reads it (that's the deferred follow-on change), so the weakness
  doesn't compromise anything this change actually does.
- [Risk] Bootstrap sweeps at BU onboarding could be slow or rate-limited
  for accounts with a large existing resource footprint →
  [Mitigation] not addressed in this design; worth a follow-up if it
  proves real, not designed defensively against a hypothetical scale
  problem now.
- [Risk] `resource_type`'s provider self-identifies via its string
  prefix (`AWS::`, `*.googleapis.com/`, `Microsoft.*/`) rather than a
  dedicated `cloud_provider` field — cheap today, since
  `docs/multi_account_per_bu_design.md`'s per-account scoping means a
  bootstrap sweep already runs against one known-provider account at a
  time. Not yet checked: whether request-time or nightly-sweep querying
  across a BU's multiple accounts needs to filter/group by provider
  explicitly rather than parsing prefixes → [Mitigation] not addressed
  here; add `cloud_provider` as an explicit column later if prefix-
  parsing proves awkward in practice, rather than adding it defensively
  now with no confirmed caller.
- [Risk] **Corrected (2026-07-13)** — previously stated as "GCP has no
  live-API discovery path for the network layer at all," which was
  incomplete research, not a confirmed absence: the original check
  looked for an MCP wrapper around `compute.networks.list`/
  `subnetworks.list` specifically and never checked Google's own managed
  Cloud Asset Inventory MCP server (`list_assets`), which directly
  covers `compute.googleapis.com/Network` and
  `compute.googleapis.com/Subnetwork` asset types, verified by direct
  inspection of its documented parameters
  (`docs/cross_project_network_sharing.md` Part H). A GCP BU with no
  registered `IacSourceRef` **can** have its network layer's existence
  discovered by this change's bootstrap sweep. What remains genuinely
  gapped, narrower than originally stated: Cloud Asset Inventory doesn't
  confirm exposing Shared VPC host/service *relationship* data (the
  `XpnResource` relationship type isn't documented as supported even at
  Security Command Center Premium/Enterprise tier), so resolving *which
  host project* a service project's network actually lives in still
  requires the dedicated `getXpnHost`/`listUsable` calls
  (`docs/cross_project_network_sharing.md` Part D) → [Mitigation]
  bootstrap discovery SHALL use Cloud Asset Inventory for GCP
  existence-level network discovery regardless of whether `IacSourceRef`
  is registered, and SHALL flag explicitly, only for the Shared VPC
  relationship-resolution gap specifically, when a discovered GCP
  network resource's host-project attachment cannot be resolved via
  `getXpnHost` — *"network resource discovered, host-project
  relationship could not be resolved, register IaC state or provide it
  manually"* — narrower than the original "network layer could not be
  discovered" flag, since the layer itself is no longer undiscoverable.
- [Risk] **This gap is deeper than "no listing tool" once cross-project
  network sharing is in play** — `docs/cross_project_network_sharing.md`:
  even with a working `compute.networks.list` equivalent, a GCP service
  project's network genuinely lives in a *different* project (the
  Shared VPC host), discoverable only via a separate host-project lookup
  plus a `roles/compute.networkUser` binding check — not a single-project
  scan no matter how complete the tooling gets. AWS's subnet-sharing and
  Azure's non-transitive peering break the same single-boundary
  assumption differently (see that doc's Part C) → [Mitigation] out of
  scope for this change's first version — bootstrap discovery here
  assumes a single-project/account boundary per BU; multi-project/
  cross-account network discovery is real, sizable follow-on work, not
  silently folded into this one. Flagged explicitly rather than
  implied-covered by the GCP tooling-gap mitigation above.
