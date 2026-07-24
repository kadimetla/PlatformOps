---
last_updated: 2026-07-24
owner: platformops-agent maintainers
scope: reframes FoundationRecord's fixed layer chain as a composable Block/Blueprint model — resolves docs/remaining_deep_dives.md item 10
reviewed_by: unreviewed (first draft, captured from an explore-mode session)
---

# Composable Foundation Blueprints — Blocks, Not One Monolith Record

## Status
Design + research, exploratory. Nothing here is built, and nothing here is
decided — this is an explore-mode capture, one level less settled than this
project's usual design docs. It reframes a question `docs/remaining_deep_dives.md`
item 10 already flagged ("should a Crossplane-inspired Composition concept be
formalized?") using five systems not previously researched together in this
project (Terraform Stacks, Humanitec's Platform Orchestrator/Score,
Crossplane's own published reference platform, Google's Cloud Foundation
Toolkit, AWS Landing Zone Accelerator) alongside the existing abstract
Crossplane analysis. Part B/C answer *how* composable units wire together;
Part D/E, added later the same session, answer *along what axis* a
blueprint gets cut into units at all, and work that out concretely as an
ordered stage sequence for this project's own org→BU→account→foundation→app
shape. Part F, added 2026-07-24, deep-dives the open questions Parts A–E
left behind against precedent already sitting in this project's own
resolved decisions (`docs/config_storage_backend.md`,
`docs/control_ui_approval_queue_design.md`) — most narrow substantially,
one surfaces a genuine inconsistency between two existing docs (fixed in
place there, not here), and one required re-verifying a tool surface
directly rather than reasoning from an earlier doc's now-stale finding.
Resolves item 10's question with a concrete direction; doesn't resolve
the schema, which needs its own follow-up design pass before anything
here is buildable.

## Part A: The gap in today's design
`docs/foundation_layer_decomposition.md` models the foundation as a chain —
`network → compute → identity` — via `FoundationRecord.layer`, a **closed
three-value enum**, linked by `depends_on_foundation_id`, a **harness-side
bookkeeping claim** that a lower layer exists. Two things about this don't
hold up once you push on them:

1. **The chain isn't universal.** `docs/compute_paradigm_layering.md` already
   found the network→compute→identity shape is specifically Kubernetes's —
   VM/managed-container/serverless paradigms have shorter chains, and a
   future storage or service-mesh layer (flagged, not designed, in that
   doc's open questions) wouldn't fit a closed 3-value enum without another
   one-off schema edit.
2. **The dependency link isn't verified against anything real.**
   `docs/foundation_blueprint_authoring_coding_agent.md` Part D2 already
   named this precisely: `depends_on_foundation_id` is "a harness-level
   bookkeeping record, separate from the actual IaC" — nothing today checks
   that the compute module's Terraform inputs actually reference the network
   module's outputs. The claim and the real wiring could silently diverge.

Separately, last turn's exploration surfaced topology choices this schema
has no way to express at all: cluster-per-team vs. shared multi-tenant
cluster, and whether dev/staging/prod should be allowed *different*
topologies within the same BU. `FoundationRecord` as designed picks none of
these — it just records that *a* compute layer exists, not *which shape* of
compute layer, or why that shape was chosen for this BU/environment over
another.

The user's framing names the fix directly: **stop treating the foundation as
one monolith record with a fixed chain glued to it, and treat it as
Lego blocks that get assembled into a blueprint** — a small catalog of
reusable, independently-versioned units, composed differently per BU,
per environment, per topology choice.

## Part B: How three real systems already solve this
Crossplane's Composition/Claim model is already researched
(`docs/crossplane_comparison_and_pattern_reuse.md`) and independently
validates the platform-defines/app-consumes shape. Two more, researched this
session, each add something Crossplane's analysis didn't cover:

| System | The composable unit | How units wire together | How the right variant gets picked |
|---|---|---|---|
| **Crossplane** (already covered) | Managed Resource (1 CRD = 1 cloud resource) | Composition references other Managed Resources by field path inside one YAML | Multiple Compositions per XRD, selected by a label/field on the Claim |
| **Terraform Stacks** | **Component** — one `.tfcomponent.hcl`, sources one Terraform module, one lifecycle unit | Explicit `publish_output` (upstream) / `upstream_input` (downstream) blocks — the *wiring itself* is the dependency record; HCP Terraform auto-triggers downstream runs when an upstream output changes | **Deployment** — the same component set, instantiated per environment (dev/staging/prod/region/account) with different input values, grouped for orchestration via Deployment Groups |
| **Humanitec Platform Orchestrator** | **Resource** (typed: `dns`, `postgres`, `network`, ...), requested via the **Score** workload spec | A resource is added to the **Resource Graph** whenever the workload (or another resource) references it by placeholder — arbitrary depth, not a fixed chain | **Resource Definitions**, chosen by **Matching Criteria** ranked by specificity: `environment type < app ID < environment ID < resource ID < resource class` — the *same* resource type resolves to a different concrete implementation for dev vs. prod without a hardcoded branch anywhere |
| **Backstage** | Software Template (a golden path) | N/A — this is the catalog/self-service UX layer, not a composition engine | App team picks a template from a catalog; the template itself embeds whichever composition mechanism backs it |

Two findings matter more than the others:

**Terraform Stacks answers Part D2's exact open question.** The dependency
between components isn't a separate bookkeeping claim at all — `upstream_input`
literally *is* the data flowing from one component's declared output into
another's declared input, and HCP Terraform tracks staleness natively (an
upstream output change auto-triggers the downstream run). Applied to this
project: if `depends_on_foundation_id` were backed by real Terraform Stacks
components instead of a hand-maintained foreign key, "is the dependency
still accurate" stops being a question the harness has to separately verify
— it's the same fact the IaC tool already tracks.

**Humanitec's Matching Criteria answers last turn's topology question.**
"Should dev get a shared cluster and prod get cluster-per-team" isn't a
branch to hardcode — it's exactly what specificity-ranked matching criteria
is *for*. One resource type (`kubernetes-cluster`), multiple Resource
Definitions behind it (`shared-multi-tenant`, `dedicated-per-team`), selected
per BU/environment/purpose the same way `CloudAccountBinding.purpose` already
distinguishes prod from dev elsewhere in this project's design
(`docs/multi_account_per_bu_design.md`). The mechanism to pick a topology per
context already has a precedent in this project; it just hasn't been named
as the general resolution rule yet.

## Part C: What this suggests for `FoundationRecord` — direction, not schema yet
Reframing three things, each traceable to one system above:

**1. Blocks replace the closed `layer` enum.** A `Block` is a named, versioned
catalog entry — `network`, `k8s-cluster-shared`, `k8s-cluster-dedicated`,
`workload-identity`, and later `storage`/`service-mesh`/whatever a real case
demands — each one a Terraform module (or CDK construct) with declared
inputs and outputs, matching Terraform's own convention already confirmed
correct for this project (`docs/foundation_blueprint_authoring_coding_agent.md`
D1). This directly closes `docs/foundation_layer_decomposition.md`'s open
question about whether `layer` should stay a closed enum — it shouldn't be
an enum on `FoundationRecord` at all; it should be a reference into a Block
registry that can grow without a schema migration.

**2. A Blueprint is an assembled, wired set of Blocks — the actual Lego
model.** "Single-cluster shared-tenant AWS EKS" and "cluster-per-team AWS
EKS" become two different Blueprints, both built from the same `network` and
`workload-identity` Blocks but a different `k8s-cluster-*` Block, wired the
way Terraform Stacks wires components — real output→input references, not a
harness-side claim. `FoundationRecord.depends_on_foundation_id` becomes
derived from the Blueprint's own wiring graph, not maintained in parallel to
it.

**Correction (same session, see Part D below): Blocks aren't all equally
claimable.** This was written assuming a flat, symmetric catalog — any Block
wired into any Blueprint, all visible the same way. Checking Crossplane's own
*published* reference platform (`upbound/platform-ref-aws`, not just its
abstract Composition mechanism) found that's not how a real system does it:
network, node IAM, and cluster services are nested **inside** one claimable
composite (`XCluster`); nothing outside the platform team ever wires the
network Block directly. Only a small number of composites are ever
independently requestable. Part D's Finding 1 below folds this in as a
required property of `Blueprint`, not just `Block` — the sketch above is
missing an internal-vs-claimable distinction.

**3. Blueprint selection is Matching Criteria, not a hardcoded default.**
Which Blueprint backs a given BU's request resolves the way Humanitec ranks
specificity — org-level default, overridden per BU, overridden per
`CloudAccountBinding.purpose` (prod gets `dedicated-per-team`, dev gets
`shared-multi-tenant`), overridden per explicit request. This is additive to
`docs/multi_account_per_bu_design.md`'s existing `purpose` field, not a new
axis — it's the missing rule for *how* `purpose` (and BU, and org) actually
picks an implementation, generalized past the single "prod gets stricter
approval" use it has today.

**4. The catalog/self-service layer is separate from the composition engine
— and isn't designed yet.** Backstage's Software Templates are the precedent
for *what an app team actually sees* when they self-serve — a curated list
of golden paths, not raw Block/Blueprint internals. This project has
`IacSourceRef` and the skill-precedence system covering "which module backs
a request" at the resolution level, but nothing yet at the presentation
level (what does Alice, from the earlier Bob/Alice walkthrough, actually
pick from when she asks for infra — a Blueprint name she has to know, or a
menu?). Worth its own pass, not folded into this one.

## Sketch — not a committed schema
```python
class Block(BaseModel):
    block_id: str
    block_type: str          # "network" | "k8s-cluster" | "workload-identity" | ...
                              # open catalog, not a closed enum — extend on real need
    variant: str              # "shared-multi-tenant" | "dedicated-per-team" | ...
    module_ref: IacSourceRef  # reuses the existing module-resolution mechanism
    declared_inputs: list[str]
    declared_outputs: list[str]

class Blueprint(BaseModel):
    blueprint_id: str
    cloud_provider: str
    blocks: list[str]                    # ordered list of block_ids
    wiring: dict[str, dict[str, str]]     # block_id -> {input_name: "other_block_id.output_name"}
                                          # mirrors Terraform Stacks' publish_output/upstream_input shape

class BlueprintMatchingCriteria(BaseModel):
    org_id: str
    bu_id: Optional[str] = None
    purpose: Optional[str] = None        # ties into CloudAccountBinding.purpose
    blueprint_id: str
    specificity: int                     # computed the way Humanitec ranks matching criteria
```
This is a starting sketch to argue against, not a proposal to build from —
it hasn't been checked against `FoundationRecord`'s other fields
(`discovered_capabilities`, `provenance`, `status`), against
`docs/foundation_layer_decomposition.md` Part D's reverse-dependency
decommission check, or against whether `wiring` as a flat dict is expressive
enough for anything past a linear chain (a shared-VPC topology's host/service
split, `docs/cross_project_network_sharing.md`, is not obviously a simple
input→output edge).

## Part D: Three decomposition axes, verified against three more real systems
Part B compared *how* systems wire composable units together. This is a
different question — *along what axis* a real "blueprint" actually gets cut
into units in the first place. Three more systems, researched this session,
give three different, equally real answers:

| Axis | System | What it answers |
|---|---|---|
| **Consumer-claim boundary** | Crossplane's own published reference platform, `upbound/platform-ref-aws` | "What's the smallest thing a consumer independently asks for?" |
| **Deployment stage / blast radius** | Google's `terraform-example-foundation` (Cloud Foundation Toolkit) | "What has to exist before what, and how often does each part change?" |
| **Governance domain** | AWS Landing Zone Accelerator's config files | "Who's accountable for this slice, independent of build order?" |

**Finding 1 — consumer-claim boundary (Crossplane's real platform, not just
its mechanism).** `platform-ref-aws` exposes exactly two independently
claimable composites: `XCluster` ("give me a cluster") and `XSQLInstance`
("give me a database that can reach it"). Everything else — the EKS
cluster's node group, its IAM role, the network fabric, cluster services
like Prometheus — is nested **inside** the `XCluster` composition, never
separately requestable. This is the correction folded into Part C above: a
Blueprint isn't a flat bag of equally-visible Blocks, it's a narrow claim
surface with most of its Blocks hidden as internal plumbing.

**Finding 2 — deployment stage / blast radius (Google CFT).** The reference
foundation is five numbered, strictly ordered stages, each its own Terraform
root module and CI/CD pipeline stage, each consuming the prior stage's
outputs via remote state:
```
0-bootstrap → 1-org → 2-environments → 3-networks → 4-projects → (5-app-infra)
```
The detail that matters most for this project: **environments (stage 2) are
defined before networks (stage 3)** — dev/nonprod/prod boundaries get
decided first, because stage 3 then provisions one shared VPC *per
environment*, not one VPC total. `docs/foundation_layer_decomposition.md`'s
`network → compute → identity` chain never states where org-structure and
environment-boundary decisions sit relative to it — Google's answer is:
above it, and sequenced before it. See Part E below for what this means
concretely for this project's own org→BU→account→foundation shape.

**Finding 3 — governance domain (AWS LZA).** Landing Zone Accelerator's
`accounts-config.yaml`, `network-config.yaml`, `security-config.yaml`,
`organization-config.yaml`, and `iam-config.yaml` are flat, independently
owned files — the split is by *who's accountable* (security team owns
`security-config`, network team owns `network-config`), not by dependency
order. There's an implicit build order underneath (account creation has to
precede most of what the other files configure), but the file boundary
itself is domain-ownership, not a chain.

**None of the three is "more correct."** Real production foundations layer
at least two at once — Google's stages are blast-radius-ordered *and*
implicitly domain-separated (stage 1 is platform-team territory, stage 4
hands off toward BU-owned pipelines); AWS's config files are
domain-separated *and* Control Tower still enforces an implicit build order
underneath them. This project's existing `docs/personas_and_tool_blueprints.md`
persona catalog already has the domain-ownership axis (Foundation Engineer
vs. Application Developer, by `TeamMember.scope`) — what it's missing is
Google's ordering axis layered on top, worked out concretely in Part E.

## Part E: An ordered stage sequence for this project's org→BU→account→foundation→app shape
Grounded entirely in schemas and sequences already designed elsewhere —
`docs/org_registry_design.md` Part B already had a 5-step onboarding
sequence (org registration → cloud anchors → org defaults → BU onboarding →
account vending) but stopped before the foundation chain. This extends it
through `docs/foundation_layer_decomposition.md`'s chain and
`docs/foundation_and_app_deploy_flow_example.md`'s Bob/Alice walkthrough,
laid out Google-CFT-style as one ordered sequence — new synthesis, no new
schema:

```
STAGE A — org bootstrap (once/org, OUT-OF-BAND, human — not harness automation)
  AWS OU / GCP folder / Azure mgmt group + Entra tenant created.
  docs/org_bootstrap_privilege_boundary.md already found this can't be
  the harness's own automation identity — no org_id exists yet to route
  a request through, and it's the single highest-blast-radius action in
  this whole design.
        ↓
STAGE B — org registration (once/org, harness-tracked)
  OrgRegistryEntry created; org-level defaults set (skills, IacSourceRef,
  review_policy). docs/org_registry_design.md Part B, steps 1+3.
  WHO: Org Admin (docs/personas_and_tool_blueprints.md)
        ↓
STAGE C — BU onboarding (repeatable per team, harness-tracked)
  BOOTSTRAP.md ritual mints agent_id + WorkspaceBundle; BuMembership
  registered on OrgRegistryEntry; TeamMember roster (role × scope)
  established. NOTE: a BU can exist here with zero cloud footprint —
  this stage registers WHO is allowed to request, not WHERE anything
  runs yet. docs/org_registry_design.md Part B step 4.
  WHO: BU Admin
        ↓
STAGE D — account vending (repeatable per BU × environment purpose)
  CloudAccountBinding minted (purpose="dev"|"staging"|"prod"|"sandbox"),
  vended INTO the org anchor from Stage A via the AFT-shaped pipeline
  (docs/account_vending_machine_design.md), approval_mode="unanimous".
  This is Google's "environments" stage — but scoped per-BU, not
  org-wide, because "no account ever shared across two BUs" is already
  a hard rule (docs/multi_account_per_bu_design.md Part A).
  WHO: BU Admin requests, Org Admin or foundation-scope approver signs off
        ↓
STAGE E — foundation: network layer (per CloudAccountBinding)
  FoundationRecord(layer="network", depends_on_foundation_id=None).
  Discovery-before-creation first (reuse / create / adopt-unmanaged,
  docs/foundation_discovery_and_capability_matching.md). If this
  binding's network is SHARED rather than dedicated, this stage resolves
  to "attach to an existing host project/owner account" instead of
  creating one — docs/cross_project_network_sharing.md's three
  provider-specific shapes apply here specifically.
  WHO: Platform/Foundation Engineer (scope="foundation"), ALWAYS human-approved
        ↓
STAGE F — foundation: compute layer (per CloudAccountBinding, possibly 1:many)
  FoundationRecord(layer="compute", depends_on_foundation_id=network's id).
  THIS is where Blueprint selection happens (Part C.3) — specificity-ranked
  matching against BU/purpose picks shared-multi-tenant vs.
  dedicated-per-team, and which compute_paradigm
  (docs/compute_paradigm_layering.md: kubernetes | vm | managed_containers |
  serverless). Under a dedicated-per-team topology this stage runs once
  PER TEAM, not once per account — depends_on_foundation_id already
  supports many compute records pointing at one network record, no
  schema change needed, just worth stating as a real consequence of the
  topology choice.
  WHO: Platform/Foundation Engineer, ALWAYS human-approved (foundation tier,
  regardless of resource cost or requester)
        ↓
STAGE G — foundation: identity layer (only for shared-identity paradigms)
  FoundationRecord(layer="identity", depends_on_foundation_id=compute's id).
  Kubernetes only, per docs/compute_paradigm_layering.md Part C — OIDC/
  workload-identity federation setup. Collapses into Stage F as an
  attribute (no separate record) for VM/serverless/managed-container
  paradigms, since their identity is 1:1 with the compute resource, not
  shared.
  WHO: Platform/Foundation Engineer, ALWAYS human-approved
        ↓
STAGE H — app team can deploy (the point the user's framing names as the goal)
  TeamMember.scope="app" gate check → resolve_skill() (deploy-to-k8s or
  provision-infra, by compute_paradigm) → recursive foundation-chain-active
  check walking G→F→E (docs/foundation_layer_decomposition.md Part C) →
  Vibe Diff → dispatcher (app-tier CAN be autonomous, unlike A–G) → execute.
  docs/foundation_and_app_deploy_flow_example.md's Alice, phase 2, in full.
  WHO: Application Developer (scope="app")
```

**A real gap this ordering surfaces, not previously named.** Stage F can be
triggered two ways depending on the topology chosen in it: proactively by a
Foundation Engineer (shared-cluster topology — Bob sets it up once, before
any app team asks), or reactively, the *first time* an app team needs a
cluster under a dedicated-per-team topology. But `docs/infra_discovery_and_platform_app_split.md`
Part C's scope gate denies a `scope="app"` requester **before skill
resolution even runs** if the request needs a foundation-tier action — Bob's
own walkthrough states this explicitly ("a requester with `scope="app"`
only would be denied here"). Under dedicated-per-team, that means an app
team can never trigger their own team's first cluster — they'd have to file
a separate request to a foundation-scoped person and wait, even though the
*reason* the request exists is entirely their own app-layer need. Not a
contradiction in the existing design, but a workflow gap dedicated-per-team
topology specifically exposes that shared-cluster topology never would —
worth deciding whether Stage F needs an app-triggered-but-foundation-approved
request shape, distinct from a foundation-engineer-initiated one.

## Part F: Deep dive on the open questions — what narrows, what's still genuinely open
Each question below checked against precedent this project already has,
not reasoned from scratch. Most narrow substantially; two required new
verification rather than analysis alone.

**Q1 — new tables, or reshape `FoundationRecord`?** `docs/config_storage_backend.md`
already answered this exact class of question four times
(`SkillUsageRecord`, `SkillProposal`, `MemoryEntry`, `IacSourceRef`): a
concept gets its own table when it has independent identity referenced by
many parents; it stays nested inside an existing record when it only ever
exists attached to one parent (`IacSourceRef`'s resolution — "not its own
table"). `Block`/`Blueprint` are **definitions** (catalog-shaped, reusable
across many requests, like a `Skill`); `FoundationRecord` is an
**instance** (one row per actual thing built, like `SkillUsageRecord`) —
already a precedented split in this project, not a new one. **Narrows to**:
`FoundationRecord` keeps recording instances, gains `blueprint_id`
replacing `layer`; `Block`/`Blueprint` are new tables, same database,
same JSON-blob-column shape `workspace_bundles`/`orgs` already use. Still
open: whether `Block` needs its own table (it needs independent identity
for reuse across Blueprints, unlike `IacSourceRef`) or can ride inside
`Blueprint`'s blob.

**Q2 — harness metadata, or parsed from real `.tf` files?** Reframed by a
distinction this project already drew for a different reason:
`docs/foundation_blueprint_authoring_coding_agent.md` Part B split
**instantiating** an existing module (common case, deterministic, zero
LLM calls, `docs/deterministic_plan_drafting.md`) from **authoring** a new
one (rare, once per org). Applied here: parsing `variables.tf`/`outputs.tf`
only matters once, at Blueprint *registration*, verifying a newly-authored
Block's declared wiring matches its module — not on every instantiation.
**Narrows to**: harness metadata for the hot path (parse-free, deterministic,
matching the zero-LLM-for-instantiation finding), validated once at
registration time by parsing — not an either/or.

**Q3 — extend skill precedence, or a genuinely new mechanism?** Skill
precedence is a strict 3-level total order on one axis (tier). Blueprint
selection needs org, BU, `purpose`, and plausibly `cloud_provider` and
explicit override — four-plus independent axes that can combine, closer to
Humanitec's weighted-specificity shape than a strict tier. Forcing that
onto a mechanism built for exactly 3 fixed tiers breaks the first time two
axes disagree with no ordinal relationship between them (a BU-level
default vs. a purpose-level override, neither strictly "more specific").
**Narrows to**: genuinely a new mechanism, not an extension — exact axis
weights remain real, undone design work.

**Q4 — the catalog/self-service layer.** Less open once Part D Finding 1's
correction lands (only a few Blueprints are ever externally claimable —
most Blocks are internal plumbing): the catalog isn't a separate mechanism,
it's "list the Blueprints flagged claimable, filtered by requester's
BU/purpose." Backstage's Software Templates are the presentation precedent;
the underlying data is already the Blueprint records from Q1. **Narrows
to**: a `claimable: bool` field plus a listing view, not a new artifact —
still deferred, but smaller than "not designed at all" implied.

**Q5 — adopt real Terraform Stacks?** Needed re-verification, not just
reasoning, because the answer had gone stale.
`docs/cross_project_network_sharing.md` Part G (earlier in this project)
checked the integrated Terraform MCP server and found only
`plan_and_apply`/`refresh_state`, no Stacks capability at all. Re-checking
HashiCorp's current tool reference directly (not relying on that earlier
finding from memory): the server now exposes `list_stacks`/
`get_stack_details` — genuinely new since that doc was written — but both
are confirmed **read-only**; no create/deploy/plan/apply path for a Stack
exists through this server today. **Narrows to**: the write-path
conclusion is unchanged (not reachable through the existing integration),
but the blanket "no Stacks capability" framing was stale and is now
corrected in place, `docs/cross_project_network_sharing.md` Part G. The
two new read tools are a real, usable capability for a *different*
question — verifying a Blueprint's declared wiring against a real Stack's
actual component graph, if a BU's foundation happens to be Stacks-managed.

**Q6 — Stage F's app-triggered-but-foundation-approved gap.** Has a real
precedent already built for an analogous problem: `SkillProposal`'s
admission flow already lets an app-scoped actor *initiate* something they
can't unilaterally approve, gated by a required reviewer distinct from the
requester (`docs/control_ui_approval_queue_design.md` Part B's self-review-
prevention rule). **Narrows to**: Stage F shouldn't deny an app-scoped
requester outright at the scope gate — it should route the request to a
foundation-scope approver, never auto- or self-approved, reusing the same
mechanism already built for skill admission rather than inventing a new
approval concept.

**Q7 — should Stage C/D collapse? (Turned up something real, not just a UX
call.)** Checking rather than assuming found the docs already disagree
with each other and nobody had flagged it: `docs/skills_and_workspace_design.md`'s
`BOOTSTRAP.md` description said the BU onboarding ritual "collect[s] cloud
account" as a one-time input, but `docs/multi_account_per_bu_design.md`
(written later) explicitly corrects "one BU = one account" and makes
account vending its own repeatable, purpose-tagged Stage D — the account-
model correction never propagated back to fix `BOOTSTRAP.md`'s own
description. **Fixed in place**, `docs/skills_and_workspace_design.md`,
2026-07-24 — cloud account removed from that one-time ritual's description,
with a note pointing here. The original UX question (should they ever
collapse for the common single-account case) stays genuinely open.

## Open questions / not yet decided
- Whether `Block` needs its own table (for cross-Blueprint reuse-tracking)
  or can ride inside `Blueprint`'s JSON blob — the one piece of Q1 Part F
  didn't fully resolve.
- Q3's exact matching-criteria axis weights (org/BU/purpose/cloud_provider/
  explicit-override) — narrowed to "new mechanism needed," weights
  themselves undesigned.
- The catalog/self-service presentation layer's actual UI/UX (Q4 narrowed
  the data model, not the presentation) — separate follow-up.
- Q6's routing mechanism needs its own pass alongside the review-policy/
  approval design specifically (which foundation-scope approver, how they're
  selected) — the shape is borrowed from `SkillProposal`, the wiring isn't
  designed.
- Whether Stage C/D should ever collapse for the common single-account
  case — Q7 fixed the doc inconsistency but didn't resolve the underlying
  UX question; Google's own model keeps them separate even in the common
  case, suggestive but not conclusive here.
- `FoundationRecord` Part D's reverse-dependency decommission check and
  `docs/foundation_layer_decomposition.md`'s other open items are
  unaffected by any of the above — not re-examined this session.

## What's real vs. designed
| Piece | Status |
|---|---|
| `FoundationRecord`, closed 3-layer chain | Design only (`docs/foundation_layer_decomposition.md`) — unchanged by this doc |
| Block/Blueprint/Matching-Criteria reframe | New, exploratory — not designed to buildable detail, sketch only |
| Terraform Stacks / Humanitec research backing this reframe | Verified against current docs this session (see Sources) |
| Any of this wired into `gateway/schemas.py` or the dispatcher | Not built, not proposed as a next build step by this doc |

## How this relates to the existing docs
- Directly resolves `docs/remaining_deep_dives.md` item 10's question
  ("should a Crossplane-inspired Composition concept be formalized") — the
  answer this doc lands on is a qualified yes, generalized past Crossplane
  specifically using two more researched systems, with the schema shape
  still open.
- Extends `docs/crossplane_comparison_and_pattern_reuse.md`'s Part C
  (Composition/Claim as validation of the platform-defines/app-consumes
  shape) with two more independent confirmations of the same shape.
- Directly answers `docs/foundation_blueprint_authoring_coding_agent.md`
  Part D2's open "should correspond to real module wiring" question with a
  concrete mechanism (Terraform Stacks' `publish_output`/`upstream_input`),
  though not yet a committed implementation.
- Reframes, doesn't yet replace, `docs/foundation_layer_decomposition.md`'s
  `layer` enum and `depends_on_foundation_id` — that doc's approval-tier
  rule (foundation-tier always human-approved) and recursive chain-active
  check are unaffected by this reframe either way.
- Gives `docs/multi_account_per_bu_design.md`'s `CloudAccountBinding.purpose`
  field a second real use (Blueprint selection, not just approval routing)
  and a general mechanism (specificity-ranked matching) for picking between
  the topology choices surfaced in the prior session's exploration
  (cluster-per-team vs. shared cluster).
- **Part D/E, added same session**: extends `docs/org_registry_design.md`
  Part B's 5-step onboarding sequence through
  `docs/foundation_layer_decomposition.md`'s chain and
  `docs/foundation_and_app_deploy_flow_example.md`'s Bob/Alice walkthrough
  into one ordered stage sequence, Google-CFT-style. Surfaces a real,
  previously-unnamed gap in `docs/infra_discovery_and_platform_app_split.md`
  Part C's scope gate (app-scoped requesters can never trigger their own
  team's first foundation-tier resource under a dedicated-per-team
  topology). Reuses `docs/personas_and_tool_blueprints.md`'s persona
  catalog to name who acts at each stage, without changing that doc.
- **Part F, added 2026-07-24**: reuses `docs/config_storage_backend.md`'s
  storage-placement precedent for Q1, `docs/foundation_blueprint_authoring_coding_agent.md`
  Part B's instantiation-vs-authoring split for Q2, and
  `docs/control_ui_approval_queue_design.md` Part B's self-review-prevention
  rule for Q6. Corrects `docs/cross_project_network_sharing.md` Part G's
  now-stale "no Stacks capability" finding in place (Q5). Surfaces and
  fixes, in `docs/skills_and_workspace_design.md`, a real inconsistency
  between that doc's `BOOTSTRAP.md` description and
  `docs/multi_account_per_bu_design.md`'s later account-model correction
  (Q7) — the account-model fix never propagated back to the earlier doc's
  own wording until now.
- Doesn't change the one required next step
  (`plan_request(envelope)`, already implemented — this is foundation/
  app-layer design, unrelated to the drafting-path boundary).

## Sources
- [Stacks overview — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/language/stacks)
- [Design a Stack — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/language/stacks/design)
- [Pass data from one Stack to another — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/language/stacks/deploy/pass-data)
- [Component configuration overview for Terraform Stacks — HashiCorp Developer](https://developer.hashicorp.com/terraform/language/block/stack/tfcomponent)
- [Scaling Terraform with Stacks — HashiCorp Solutions Engineering Blog](https://medium.com/hashicorp-engineering/scaling-terraform-how-to-modularize-and-deploy-across-multiple-environments-regions-and-accounts-0b18b5472b61)
- [Platform Orchestrator: Overview — Humanitec](https://developer.humanitec.com/app-humanitec-io/docs/platform-orchestrator/overview/)
- [Resources: Resource Definitions — Humanitec](https://developer.humanitec.com/platform-orchestrator/docs/platform-orchestrator/resources/resource-definitions/)
- [Understand Humanitec's Resource Graph in detail — Humanitec blog](https://humanitec.com/blog/understand-humanitecs-resource-graph-in-detail)
- [Resources: Resource Classes — Humanitec](https://developer.humanitec.com/app-humanitec-io/docs/platform-orchestrator/resources/resource-classes/)
- [How to Build Golden Paths in Backstage IDP with Software Templates — The Platform Engineer](https://medium.com/@rameshavutu/how-to-build-golden-paths-in-backstage-idp-with-software-templates-170adce436fe)
- [Scaffolder: self-service for Cloud Native teams — Roadie.io](https://roadie.io/product/scaffolder/)
- [upbound/platform-ref-aws — GitHub](https://github.com/upbound/platform-ref-aws)
- [Crossplane v0.13: platform configuration support — Crossplane blog](https://blog.crossplane.io/crossplane-v0-13-paves-the-way-for-v1-0-with-platform-configuration-support-to-create-a-universal-cloud-api-for-your-app-teams/)
- [Building a Platform Abstraction for EKS Cluster Using Crossplane — DZone](https://dzone.com/articles/platform-abstraction-eks-cluster-crossplane)
- [terraform-google-modules/terraform-example-foundation — GitHub](https://github.com/terraform-google-modules/terraform-example-foundation)
- [terraform-example-foundation 1-org README — GitHub](https://github.com/terraform-google-modules/terraform-example-foundation/blob/main/1-org/README.md)
- [terraform-example-foundation 4-projects README — GitHub](https://github.com/terraform-google-modules/terraform-example-foundation/blob/main/4-projects/README.md)
- [Configuration files — Landing Zone Accelerator on AWS](https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/configuration-files.html)
- [awslabs/landing-zone-accelerator-on-aws — GitHub](https://github.com/awslabs/landing-zone-accelerator-on-aws)
- [Terraform MCP server reference — HashiCorp Developer](https://developer.hashicorp.com/terraform/mcp-server/reference)
- [Terraform MCP server updates: Stacks support, new tools, and tips — HashiCorp blog](https://www.hashicorp.com/en/blog/terraform-mcp-server-updates-stacks-support-new-tools-and-tips)
