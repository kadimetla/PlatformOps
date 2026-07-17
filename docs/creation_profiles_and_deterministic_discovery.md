---
last_updated: 2026-07-17
owner: platformops-agent maintainers
scope: stamping how a resource was created onto InfraInventoryRecord so later discovery is a direct lookup instead of a provider-wide search — extends docs/iac_based_discovery.md and openspec/changes/infra-inventory-discovery
reviewed_by: unreviewed (first draft)
---

# Creation Profiles, and Making Discovery a Lookup Instead of a Search

## Status
Design only. Nothing here is built. Grounded directly against real
schema code (`gateway/schemas.py`), not assumption — confirmed by grep
that `ToolIntent`, `PlanRecord`, and `InfraInventoryRecord` share zero
fields today; the association between "what created this resource" and
"the resource that got created" doesn't survive past plan execution.

## Part A: The gap — three profile-shaped things that don't talk to each other

Three pieces already exist that each partially answer "how was this
resource made," and none of them are linked to the resource itself:

| Piece | What it captures | Where |
|---|---|---|
| `Skill` | The creation template used (`provision-infra`, etc.) | `workflows/drafting/skill_loading.py:121` |
| `WorkspaceBundle` | Per-BU toolchain signals (`tfe_workspace`, `enable_tf_operations`) | `gateway/schemas.py:25-33` |
| `IacSourceRef` (designed, not built) | Where a BU's foundation IaC state actually lives (`terraform` / `config_connector` / `none`) | `docs/iac_based_discovery.md` Part B |

`gateway/skill_usage_store.py`'s `skill_usage_records` table comes
closest, but it's aggregate trust bookkeeping — `total_uses`,
`lifecycle_state`, keyed by `skill_path` — not a per-resource record.
Once a plan executes, the fact "resource X was created by skill Y,
toolchain Z" is discarded — `ToolIntent` (`gateway/schemas.py:62-77`)
and `PlanRecord` (`gateway/schemas.py:39-47`) carry no skill reference
at all, and `InfraInventoryRecord` (`gateway/schemas.py:80-113`) has no
field to receive one even if they did.

## Part B: Discovery today has to search; it shouldn't have to, for anything this harness created

`docs/iac_based_discovery.md` Part C already designed discovery's
fallback chain for *unknown-provenance* resources: check `IacSourceRef`
(BU-level, generic) first, cross-check live API second, fall back to
live-API-only if nothing's registered. That chain exists because, in
the general case, discovery doesn't know how a resource came to be.

But for any resource created *through this harness*, that's not true —
at creation time, the exact skill, toolchain, and (if applicable)
Terraform workspace are all already known values sitting in local
variables during `plan_request()`. Throwing them away means discovery
has to rediscover, by search, information the system already had
seconds earlier.

## Part C: Proposed shape — a `CreationProfile`, stamped onto `InfraInventoryRecord`

```python
class CreationProfile(BaseModel):
    skill_path: Optional[str] = None   # which skill created this, if any --
                                        # None for the LLM-driven drafting path
                                        # or for resources this harness didn't create
    toolchain: str                     # "cdk" | "terraform" | "config_connector" | "unmanaged"
    iac_source: Optional[IacSourceRef] = None  # exact IaC state address, if the
                                                # toolchain has one (e.g. tfe_workspace)
```

Added to `InfraInventoryRecord` as `created_via: Optional[CreationProfile] = None`
— `None` for anything discovered by a sweep with no known creation
history (pre-existing/ClickOps infra found via `docs/iac_based_discovery.md`'s
search chain), populated for anything this harness provisioned.

**This is a different axis from `provenance`, not a replacement for it.**
`provenance` (`"iac_state" | "live_api"`, `gateway/schemas.py:113`)
answers *how this specific inventory row was populated* — it's a fact
about the discovery sweep. `created_via` answers *how the underlying
cloud resource came to exist* — a fact about the resource's history.
A pre-existing bucket found by a bootstrap sweep has
`provenance="live_api"` and `created_via=None`. A bucket this harness
provisions later gets `created_via` populated at creation time, and
still eventually gets a `provenance` value once a sweep or the
incremental hook (Part D) writes its row.

## Part D: Where this hooks into real, already-planned code

`openspec/changes/infra-inventory-discovery/tasks.md` task 3.1 already
plans exactly the right moment to stamp this: *"Hook
`InfraInventoryStore.upsert()` into `BrokeredToolDispatcher`'s existing
`ALLOW` + successful-execution path."* At that point,
`BrokeredToolDispatcher` has the `ToolIntent` that just executed, and
`plan_request()`'s own state (which skill matched, if any; which
toolchain the graph routed to — `workflows/drafting/nodes.py`'s
`route_toolchain`) is reachable from the same call chain. Task 3.1's
scope should grow by one field: construct `CreationProfile` from that
state and pass it through to the `upsert()` call it already makes.

## Part E: Second-order effect — narrows the "never checked" ambiguity

This doesn't fully resolve the gap I flagged in the prior exchange
(`InquiryResult.found=False` can't currently distinguish "confirmed
absent" from "no sweep has ever run for this BU") — but it narrows it
meaningfully. For any resource this harness created, `created_via` is
populated the moment it's created, so `workflows/inquiry/` never has to
guess how to verify it later regardless of whether a bootstrap sweep
ever ran for that BU. The ambiguity becomes scoped to exactly the
resources this harness has no history of — pre-existing infra a
bootstrap sweep hasn't reached yet — a smaller, more honestly-labeled
gap than "every inquiry answer might be wrong."

## Open Questions
- **Explicit vs. inherited profile selection** — this doc assumes
  `CreationProfile` is inherited automatically from whichever skill
  matched (`check_structured_match()`) or whichever toolchain the
  LLM-driven graph routed to. An open alternative: let a user
  explicitly pick a profile/template up front, independent of skill
  matching. Not resolved here — raised, not decided.
- **LLM-driven drafting path's `skill_path`** — the deterministic
  skill-fill path has an obvious `skill_path` (the matched `Skill`).
  The LLM-driven graph (`workflows/drafting/graph.py`) has a
  `toolchain` (`route_toolchain`'s output) but no skill — does
  `CreationProfile.skill_path` stay `None` for that path, or does it
  need its own identifier (e.g. "freeform-cdk", "freeform-terraform")
  so discovery can still say *something* about how a freeform-drafted
  resource was made? Not resolved here.
- **Where `IacSourceRef` comes from for `CreationProfile.iac_source`**
  — presumably resolved the same BU-overrides-org order
  `docs/iac_based_discovery.md` already designed for foundation IaC,
  but that doc scoped `IacSourceRef` to the *foundation* layer
  specifically; whether app-layer resources (most of what
  `provision-infra` actually creates today) should carry the same
  reference, or a narrower one, isn't decided.
- **Retroactive backfill** — resources created before this existed
  would have `created_via=None` forever unless a migration stamps them
  after the fact from `skill_usage_records`' history, which doesn't
  carry a per-resource link either. Likely: don't bother, `None` simply
  means "predates this feature or wasn't tracked," same bucket as
  "not created by this harness."

## Real vs. designed
| Piece | Status |
|---|---|
| `Skill`, `WorkspaceBundle`, `skill_usage_records` | Built, real |
| `IacSourceRef` | Designed only (`docs/iac_based_discovery.md`) |
| `CreationProfile`, `InfraInventoryRecord.created_via` | Designed only, this doc |
| Stamping `CreationProfile` at `BrokeredToolDispatcher`'s ALLOW path | Designed only, extends `infra-inventory-discovery` task 3.1 |

## How this relates to the existing docs
- Extends `docs/iac_based_discovery.md` — reuses `IacSourceRef` as
  `CreationProfile`'s pointer to exact IaC state, doesn't redefine it.
- Extends `openspec/changes/infra-inventory-discovery`'s task 3.1 (the
  incremental-update hook) — same hook point, one more field to
  construct and pass through.
- Narrows, but doesn't resolve, the "never checked vs. confirmed
  absent" gap named when discussing `workflows/inquiry/`'s
  `InquiryResult.found: bool` (this session, not yet its own doc) — see
  Part E.
- Complements `docs/intent_routing_and_staged_confirmation.md` Part D's
  `workflows/inquiry/` design: doesn't change that workflow's own
  logic, changes what data `InfraInventoryStore` has available for it
  to read.
