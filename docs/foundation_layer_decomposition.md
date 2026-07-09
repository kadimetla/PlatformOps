# Foundation Layer Decomposition — Network, Compute, Identity as Separate Tracked Layers

## Status
Design only. "The foundation layer" has been treated as one atomic tier
throughout every prior doc (`docs/foundation_app_layering_and_iam_tiers.md`,
`docs/foundation_discovery_and_capability_matching.md`) — one
`FoundationRecord`, one approval, one discovery pass. This decomposes it
into the real dependency chain underneath that single record, since the
approval treatment being uniform across the tier doesn't mean the
*build order* or *discoverability* underneath it is uniform too.

## Part A: Four different kinds of "layer" — where this doc fits
This project has used "layer" for four distinct things; worth
disambiguating once rather than re-deriving it per doc:

| Category | The layers | What "dependency" means |
|---|---|---|
| **A. Infra provisioning** (what gets built) — **this doc** | Network → Compute/Cluster → Identity/IAM → App/Workload | Layer *n* can't be created until layer *n-1* exists in the real cloud account |
| **B. Harness architecture** (how a request is processed) | Channel/Gateway → Session/Routing → Agent → Dispatcher | Layer *n* can't run until layer *n-1* produced its output (the 8 flow-steps, `spec/flow_steps/`) |
| **C. Governance/config** (who's authorized, by what precedence) | Org → BU → Team; Bundled → Org → BU (skills); `role` × `scope` | Not build-order — an override order (more specific wins) |
| **D. This repo's documentation** | `AGENTS.md`/`CLAUDE.md` → `spec/` → `docs/` → code | Not enforced anywhere — a convention about where a decision lives |

Categories B–D are already designed elsewhere and unchanged by this
doc. This doc is entirely about decomposing category A's "foundation"
into its own internal dependency chain.

## Part B: `FoundationRecord` becomes layer-typed
```python
class FoundationRecord(BaseModel):
    foundation_id: str
    org_id: str
    bu_id: str
    cloud_provider: str
    layer: str  # NEW — "network" | "compute" | "identity"
    depends_on_foundation_id: Optional[str] = None  # NEW — points at the
                                                     # layer beneath this one;
                                                     # None for the network
                                                     # layer (the chain's root)
    resource_type: str
    resource_identifier: str
    approved_plan_id: str        # the creating OR adopting PlanRecord — unchanged
    status: str = "active"
    provenance: str = "created"  # NEW — "created" | "adopted"
    discovered_capabilities: Dict[str, Any] = Field(default_factory=dict)
```
Three layer values, forming a chain:
```
network   (depends_on_foundation_id = None)
   ↑
compute   (depends_on_foundation_id = network's foundation_id)
   ↑
identity  (depends_on_foundation_id = compute's foundation_id)
```
**App-tier resources stay outside `FoundationRecord` entirely** — an
app-layer `ToolIntent.depends_on_foundation_id` points at the
**compute** layer's `foundation_id` specifically (what an app actually
deploys onto), and the dispatcher check (Part C) walks the rest of the
chain from there. This keeps `FoundationRecord` scoped to what's
genuinely foundation-tier, per the tier definition already established
in `docs/foundation_app_layering_and_iam_tiers.md` Part A.

One modeling caveat worth stating plainly: in practice, a cluster and
its OIDC/workload-identity setup are often created in the same
Terraform apply or CFN stack, not as temporally separate operations.
Splitting them into separate `FoundationRecord`s isn't a claim that they
must be built in separate transactions — it's a claim that they can
independently **drift, be adopted, or be discovered** separately, which
is the actual reason to track them as distinct records.

## Part C: The dependency check has to be recursive, not one hop
`docs/foundation_app_layering_and_iam_tiers.md` Part D's dispatcher
check only ever verified *one* `FoundationRecord` was active. With a
chain, an app-layer dispatch has to confirm **every layer up the chain**
is active, not just the compute layer it directly points at:
```python
def _foundation_chain_active(self, foundation_id: str) -> bool:
    record = self._lookup_foundation(foundation_id)
    if not record or record.status != "active":
        return False
    if record.depends_on_foundation_id:
        return self._foundation_chain_active(record.depends_on_foundation_id)
    return True
```
Same deny-by-default shape as every other `BrokeredToolDispatcher`
check — a broken or decommissioned network layer denies an app deploy
even if the compute layer immediately above it still looks active,
which the flat, single-record check couldn't express at all.

## Part D: Decommissioning needs a reverse-dependency lookup
A new safety gap this decomposition surfaces: nothing today checks
whether decommissioning a network layer would orphan a compute layer
still actively serving app deploys. **New rule**: before
`FoundationRecord.status` can transition to `"decommissioned"`, query
for any *other* `FoundationRecord` whose `depends_on_foundation_id`
points at it and is still `"active"` — deny the decommission (or
require it to cascade explicitly) until nothing depends on it. This is
the same shape as `docs/foundation_app_layering_and_iam_tiers.md` Part
D's forward-dependency check, just walked in reverse.

## Part E: Discovery now runs per layer, not once for "the foundation"
`docs/foundation_discovery_and_capability_matching.md` Part A's three-
branch flow (reuse / create-new / adopt-unmanaged) applied to one
monolithic foundation. It now applies **independently to each layer**
— a BU's foundation can be genuinely mixed-provenance:

**Worked example**: a BU's network was set up years ago by a different
team, outside this harness (found live, no `FoundationRecord` — branch
3, requires adoption review, `docs/foundation_discovery_and_capability_matching.md`
Part D). Its compute layer (the EKS cluster) *was* created through this
harness last month (`FoundationRecord` exists, branch 1, reuse). Its
identity layer — say a second IAM OIDC provider for a newly-added
workload class — doesn't exist yet at all (branch 2, create new,
`depends_on_foundation_id` pointing at the compute layer's
`foundation_id`).

Three layers, three different discovery outcomes, in the same BU, at
the same time. The prior monolithic model had no way to express this at
all — it could only say "the foundation exists" or "it doesn't."

## Open questions / not yet decided
- Whether `layer` should be a closed three-value enum or allow future
  values (e.g., a separate "storage" layer for a shared EFS/Filestore
  mount) — leaning closed for now, extend when a real case appears.
- Whether the reverse-dependency check (Part D) should cascade
  automatically (decommission dependents too) or always require
  explicit, separate decommission requests per layer — leaning toward
  requiring explicit requests, consistent with this project's general
  bias against automatic destructive actions, not decided as a hard
  rule.
- Whether `discovered_capabilities` should also be layer-scoped (network
  capabilities vs. compute capabilities are different shapes) or stay
  one dict per record as already designed — likely already correct as
  designed, since each layer now has its own `FoundationRecord` and
  therefore its own `discovered_capabilities`; noted here only to
  confirm this doc doesn't need to change that schema further.

## How this relates to the existing docs
- Decomposes the single `FoundationRecord` concept from
  `docs/foundation_app_layering_and_iam_tiers.md` Part D into a chain,
  without changing that doc's approval-tier rule (foundation-tier is
  still always human-approved, uniformly across all three layers).
- Extends `docs/foundation_discovery_and_capability_matching.md`'s
  three-branch discovery flow from "once per foundation" to "once per
  layer," including a worked mixed-provenance example that doc's
  Bob/Alice walkthrough never covered.
- Extends the dispatcher check from
  `docs/foundation_app_layering_and_iam_tiers.md` Part D and
  `docs/iam_permissions_boundary_implementation.md` from a single-hop
  lookup to a recursive chain-walk.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
