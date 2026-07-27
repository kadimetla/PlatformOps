---
last_updated: 2026-07-26
owner: platformops-agent maintainers
scope: reframes FoundationRecord's fixed layer chain as a composable Resource+Stack model (Block dropped, Blueprint/PlatformRecord/"platform" superseded by Resource/Stack terminology verified against AWS/Azure/GCP/OpenStack/Terraform/Pulumi) — resolves docs/remaining_deep_dives.md item 10, tracks in-flight naming decisions ahead of code
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

**Parts G–L, added 2026-07-25 (a second, later explore-mode session):**
drops `Block` entirely — the model simplifies to `PlatformRecord`
(renamed from `FoundationRecord`, generalized past foundation-tier-only)
plus `Blueprint`, connected by a single required `blueprint_id` foreign
key, no catalog/wiring/matching-criteria layer. Settles four naming
decisions (`workflows/provision_infra_resource/`, `PlatformRecord`,
"platform" terminology, a third `workflow_hint` value) that are
**decided but not yet applied to code** — the working tree currently has
a broken, mid-rename intermediate state (Part G). Verifies, via fresh
web research, that only Azure natively solves what Blueprint is for
(its Resource Group); AWS and GCP don't. Connects Blueprint to two
previously-unconnected existing docs (`InfraRelationship`'s edge
vocabulary, the diagram-rendering-tier design) and finds
blueprint-to-blueprint relationships are a derived rollup of existing
resource-level edges, not a new mechanism. Sketches a persona-visibility
model (platform vs. app) built on the same `TeamMember.scope`/`bu_id`
gate already built and tested this session. Still not decided: the
Resource→Stack binding mechanism, the `InfraInventoryRecord`
merge question, and visibility-walk depth.

**Parts M–O, added 2026-07-26 (same-day continuation):** supersedes
Part G/H's `PlatformRecord`/`Blueprint`/"platform" naming with
`ResourceRecord`/`Stack` — verified against five real platforms/tools
(AWS CloudFormation, Azure Deployment Stacks, OpenStack Heat, Pulumi,
HashiCorp Terraform Stacks), not this project's own coinage. Finds
Azure independently deprecating a product literally named "Blueprints"
in favor of "Deployment Stacks" — the same rename this conversation
converged on, confirmed from the outside. Verifies (resolving a claim
`docs/creation_time_relationship_capture_and_diagrams.md` had explicitly
flagged unverified) that `terraform graph`/`pulumi stack graph` are
real, and that CloudFormation/Heat have no native equivalent — corrected
in that doc directly. Standardizes an operation vocabulary
(`describe_stack`/`list_resources`/`describe_resource`/`graph_stack`/
`generate_stack_template`/`create_stack`) against real platform verbs,
and finds "assembling" a Stack from new and existing resources is
`describe`/`list` feeding `create`, not a new operation — already the
shape `dispatch_and_execute_cluster()`/`generate_cluster_template()`
implement, needing renaming/generalizing, not re-architecting.

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

## Part G: Naming settled this session (2026-07-25) — decided, implementation in progress, tree currently mid-rename
Four renames, decided in sequence across one long explore-mode session,
none fully applied to code yet:

1. **`workflows/drafting/` → `workflows/provision_infra_resource/`.**
   "Drafting" named the mechanism (produce a draft plan pending
   approval); "provision" names the intent (what a requester actually
   asks for) — the module's own docstring already leaned this way
   (*"provisioning tool-calling nodes"*). **Tree state**: `git mv`
   already run: the directory is at its new path. Every internal
   import across the ~22 consuming files (`gateway/plan_request.py`'s
   re-export, `gateway/skill_matching.py`, `gateway/compliance_preflight.py`,
   `gateway/skill_template_agent.py`, `workflows/inquiry/`'s reuse
   references, 6+ test files) still says `workflows.drafting` —
   **broken imports, not yet fixed.** `DraftingState`/`build_drafting_graph`/
   `build_checkpointed_drafting_graph` also need renaming for internal
   consistency, not just the package path.
2. **`workflow_hint` value `"drafting"` → `"provision_infra_resource"`**
   in `workflows/intake/` (`WORKFLOW_CANDIDATES`, the Tier 2 prefix
   convention, the Tier 3 classification prompt) — decided, not applied.
3. **`FoundationRecord` → `PlatformRecord`** (superseding an
   intermediate `ResourceRecord` name floated earlier the same
   session — `PlatformRecord` is the setting instruction, not
   `ResourceRecord`) — decided, not applied. Still carries the
   `blueprint_id` requirement from Part H below.
4. **"foundation" scope/tier terminology → "platform"** —
   `TeamMember.scope` values (`"foundation"|"app"|"both"` →
   `"platform"|"app"|"both"`), `requester_has_foundation_scope()` →
   `requester_has_platform_scope()`, `gateway/kubernetes_foundation_dispatch.py`'s
   own name, and every `docs/foundation_*.md` doc's terminology (not
   necessarily their filenames — see the note below). Consistent with
   existing precedent, not inventing new language:
   `docs/personas_and_tool_blueprints.md` already names the persona
   **"Platform/Foundation Engineer,"** not just "Foundation Engineer" —
   "platform" was already the preferred word sitting right next to
   "foundation."

**Scope decision on doc filenames, stated explicitly so it isn't
silently inconsistent later**: this rename applies to *terminology*
(the words "foundation scope," "foundation tier," `TeamMember.scope`'s
literal value) — it does **not** rename existing doc files like
`docs/foundation_app_layering_and_iam_tiers.md`,
`docs/foundation_layer_decomposition.md`,
`docs/foundation_discovery_and_capability_matching.md`, or this doc's
own filename. Per `CLAUDE.md`'s "correct in place, with a note" rule,
those docs get a terminology note where they use "foundation" as a
scope/tier word, not a file rename — the same discipline already
applied to every other correction this session.

## Part H: Dropping `Block` — the model simplifies to Resource + Blueprint, no catalog layer
Superseded from Part C's original sketch: no separate `Block`
definition table, no wiring dict, no matching-criteria resolution
mechanism. Two things only:

```
PlatformRecord   — one provisioned thing (a VPC, a load balancer, a
                    Kubernetes cluster, an S3 bucket...) — what
                    FoundationRecord already represented, renamed and
                    generalized past foundation-tier-only scope

Blueprint         — the container a PlatformRecord belongs to; the
                    shape an app is or will be deployed onto/into
```

**The rule, stated by the user directly**: a resource *can* be
requested standalone — provisioning doesn't require pre-declaring a
blueprint, matching how a person actually thinks ("I need a VPC," not
"I need to declare a blueprint first"). But **a resource can never end
up with no Blueprint reference** — no dangling resources, ever. This
is a simpler, stronger version of `docs/foundation_layer_decomposition.md`'s
already-named gap (*"nothing today checks that the compute module's
inputs actually reference the network module's outputs"*) — instead of
a wiring graph between typed Blocks, it's a single required foreign
key every `PlatformRecord` must carry.

```python
class Blueprint(BaseModel):
    blueprint_id: str
    org_id: str
    bu_id: str
    name: str              # what an app team would recognize this as
    status: str = "active"

class PlatformRecord(BaseModel):
    ...                     # everything already built in FoundationRecord stays
    blueprint_id: str       # NEW, REQUIRED, never Optional/null
```

**Still genuinely open, not resolved across any of this session's later
turns**: *how* a standalone resource request gets bound to a Blueprint
at provisioning time. Three mechanisms named, none chosen:
1. Auto-create one Blueprint per resource, merge later if a dependent
   resource joins it.
2. Requester names the Blueprint explicitly in the request.
3. Inferred from dependency — a resource created *depending on*
   another inherits that resource's Blueprint automatically (mirrors
   `depends_on_foundation_id`'s existing shape); only a root resource
   (no dependency — typically network) needs the binding decided at all.

## Part I: What the cloud providers already give us — verified, not assumed, and the answer is genuinely mixed
Researched directly (web search, current docs) before designing
Blueprint further, since Azure/GCP/AWS might already solve this natively:

| Cloud | Billing/isolation boundary | Native sub-boundary resource-grouping construct |
|---|---|---|
| **Azure** | Subscription | **Resource Group** — every resource belongs to exactly ONE, a real, required, exclusive lifecycle container. Not a billing boundary itself — pure organizational/deployment unit. This is Blueprint, already built into the platform. |
| **AWS** | Account | **None this strong.** The service literally named "AWS Resource Groups" is tag-based/CFN-stack-based — a resource can belong to zero, one, or many groups, purely for cost-reporting/operational convenience, verified **not** a hard container. The closer real analog is a **CloudFormation stack** (a resource genuinely belongs to one, shared lifecycle, expressible dependencies) — worth noting `manage_eks_stacks` (already in use) is CFN-stack-shaped for exactly this reason. |
| **GCP** | Project | **None this strong either.** Labels are GCP's tag equivalent — same weak, optional, non-exclusive shape as AWS tags. |

**The finding that matters**: only Azure solves this natively. Building
`Blueprint` as a project-level concept isn't reinventing something
every cloud already has — it's what makes governance/audit/inventory
*consistent* across all three clouds, since without it an Azure BU
gets resource-group-level organization for free while an AWS or GCP BU
gets nothing structurally equivalent.

## Part J: Two hierarchy axes exist — don't conflate them
Verified alongside Part I, since GCP's Organization→Folder→Project
tree could easily be mistaken for the same concept as Blueprint. It
isn't:

```
AXIS 1 — billing/governance hierarchy (ALREADY DESIGNED, don't touch)
  AWS:    Organization → OU → Account
  GCP:    Organization → Folder → Project
  Azure:  Management Group → Subscription
  → homed in OrgRegistryEntry's aws_ou_id/gcp_folder_id/
    azure_management_group_id, and CloudAccountBinding
    (docs/org_registry_design.md, docs/multi_account_per_bu_design.md)

AXIS 2 — resource-grouping within one account/project/subscription
  → Blueprint, the new thing this Part H/I/J sequence designs
```

GCP Folders exist for policy/IAM inheritance across a company's org
structure — not for grouping one app's resources together. A GCP
"parent project" is Axis 1, not Axis 2. Conflating them would mean
trying to make Blueprint do a job `CloudAccountBinding` already does.

**One real consequence for Blueprint's shape**: it is not necessarily
1:1 with one `CloudAccountBinding`. The Shared VPC / cross-account RAM
research (`docs/cross_project_network_sharing.md`) already established
real resources legitimately spanning two accounts/projects — a
Blueprint describing "the resources one app actually uses" has to be
able to span accounts when that's the real topology, not be scoped to
exactly one.

## Part K: Blueprint-to-blueprint relationships are derived, not a new edge type
Traced against two existing design docs neither previously connected
to Blueprint: `docs/infra_graph_modeling_and_db_options.md` (the
`InfraRelationship` edge schema) and
`docs/creation_time_relationship_capture_and_diagrams.md` (when edges
get captured, and how diagrams get rendered from them). Both design
only, neither built — but the vocabulary already fits without
extension:

```python
InfraRelationship  # designed, not built
  (org_id, bu_id, subject_identifier, relationship_type,
   object_identifier, discovered_at, provenance)
relationship_type ∈ {contained_in, depends_on, shared_from,
                      workload_identity_binds_to}
```

**A Blueprint's topology diagram is the already-designed Tier 1
render** (`creation_time_relationship_capture_and_diagrams.md` Part D
— nodes + edges → Mermaid/DOT, zero LLM, the only rendering tier
concrete enough to build now; native toolchain graphs like
`terraform graph` are explicitly flagged **unverified**, LLM-narrated
diagrams explicitly rejected as lowest-confidence for exactly this
kind of "wrong answer is expensive" claim) — just scoped to
`WHERE blueprint_id = ?` instead of `WHERE bu_id = ?`.

**Blueprint-to-blueprint sharing needs no new edge type.** If Resource
X (in Blueprint A) has a `shared_from`/`depends_on` edge to Resource Y
(in Blueprint B), then "Blueprint A uses Blueprint B" is a **rollup
query over existing resource-level edges**, not a second fact to
maintain in parallel. This is the same move already made once in this
project — `resource_category` unifying "is this a network resource"
across three incompatible provider type vocabularies — applied a
level higher, to blueprints instead of resource types.

## Part L: Persona-based visibility — the same `TeamMember.scope`/`bu_id` gate, driving a query instead of a single check
`requester_has_foundation_scope()` (soon
`requester_has_platform_scope()`, Part G) is a yes/no gate today: can
this person create a cluster. The same fact — scope + BU membership —
should drive what each persona *sees*, not just what they can *do*:

```
platform persona (Bob)          app persona (Alice)
  sees: blueprints HIS bu_id       sees: blueprints HER bu_id owns
  owns, full topology,             (full topology) UNION blueprints
  drift/audit status,              reachable by walking
  create/extend affordances        shared_from/depends_on edges
                                    OUTWARD from those — read-only,
                                    for compatibility-checking
                                    (discovered_capabilities), no
                                    edit affordances
```

**Why app-persona visibility can't be strict `bu_id` ownership**: if
Alice's Payments BU owns an app-blueprint that's `shared_from` a
Platform BU's shared-network blueprint, she needs to see enough of
that shared blueprint (its `discovered_capabilities` — K8s version,
ingress class) to check her app is compatible, per
`docs/foundation_and_app_deploy_flow_example.md` step 11a — even
though she doesn't own it and can't edit it.

**Still open, not resolved**: does reachability stop at one hop, or
walk the full chain? `docs/foundation_layer_decomposition.md`'s
`_foundation_chain_active()` already walks the *entire* dependency
chain for the approval-gate case (a broken root network denies a
deploy even if the immediate layer looks active) — whether visibility
should follow that same "walk it all" rule, or a shallower one, isn't
decided.

## Part M: `Blueprint`/`FoundationRecord`/`platform` superseded — final vocabulary, grounded in industry precedent, not invented
Parts G–L settled on `PlatformRecord`/`Blueprint`/"platform" terminology.
This turn's research supersedes that with vocabulary verified against
five real platforms/tools rather than this project's own coinage:

```
Resource / ResourceRecord   — one resource (matches every tool's own word:
                               AWS "resource," Heat "resource," Pulumi
                               "resource")
Stack                        — the group (matches AWS CloudFormation
                               Stack, Azure Deployment Stack (GA),
                               OpenStack Heat Stack, Pulumi Stack,
                               HashiCorp's own newer Terraform Stacks)
```

`FoundationRecord` → `ResourceRecord` (not `PlatformRecord` — Part G's
intermediate name is now superseded). `Blueprint` → `Stack`. "Platform"
scope/tier terminology also retired — Part H's `risk_tier`/
`approval_tier`-as-a-resource-type-attribute question (does the
mandatory-human-approval behavior still need a name, just not a
top-level persona/module name) remains open, now phrased against
`Stack`/`Resource` instead of `Blueprint`/`Platform`.

**Independent, striking confirmation this is the right direction, not
just a preference**: Azure itself had a product literally named
**"Blueprints"** — and is deprecating it (2026-07-11) *in favor of*
**"Deployment Stacks."** The same rename this conversation converged on
across several turns is the exact direction the platform that
originated the word "Blueprint" as a product name is itself moving.

**What CloudFormation's real mechanics validate, not just name**:
nested stacks (a stack containing child stacks) and cross-stack
references (`Export`/`Fn::ImportValue`, one stack's resource referenced
by another) map exactly onto Part H's "resource can compose resources"
and Part K's "blueprint-to-blueprint sharing is a derived rollup" —
independently arrived at *before* this platform research, now confirmed
as the same shape real tools already use, not a bespoke mechanism.

## Part N: Inquiry and diagram-export capability, verified per platform — resolves a previously-flagged-unverified claim
`docs/creation_time_relationship_capture_and_diagrams.md` Part D
explicitly flagged native toolchain graph commands (`terraform graph`)
as **"unverified... recalled from training data, not confirmed against
current docs"** — this session's own stated discipline required closing
that before relying on it. Verified now, directly, per platform:

| Tool/Platform | Inquiry (real, verified) | Diagram/graph export (verified) |
|---|---|---|
| **Terraform** | `terraform show`, `terraform state list` | **`terraform graph`** — real, current, DOT format (`terraform graph \| dot -Tpng > graph.png`). Resolves the open question above: **real**, not hypothetical. |
| **Pulumi** | `pulumi stack` | **`pulumi stack graph`** — real, DOT format, includes parent/child edges. Generated from **deployed state**, not just plan/config — reflects actual drift automatically, a stronger property than Terraform's own (which defaults to plan-type unless given an apply-time plan file). |
| **AWS CloudFormation** | `DescribeStacks`, `DescribeStackResources`/`ListStackResources`, `DescribeStackResource` (singular) — all real, verified | **No native graph/diagram export found** — searched specifically, verified absent, not assumed absent. |
| **OpenStack Heat** | `openstack stack show`, `openstack stack resource list` — real, verified | Heat uses dependency graphs **internally** for orchestration ordering; **no exposed CLI command to view/export that graph found** — verified absent. |
| **Azure** | `az deployment stack show` (real, GA per Part I) | Not confirmed either way this pass — see Part M's Blueprints-deprecation finding as an adjacent, not equivalent, signal. |

**What this means for how this project builds the diagram, concretely**:
only 2 of 5 have a native graph export, and both are toolchain-specific
(useless for a Stack managed via CFN or Heat). This **reinforces**,
doesn't replace, `docs/creation_time_relationship_capture_and_diagrams.md`
Part D's Tier 1 mechanical render (`InfraRelationship` edges → Mermaid/DOT,
built from this project's own captured data) as the only mechanism that
works uniformly regardless of toolchain. `terraform graph`/`pulumi stack
graph` become legitimate, now-**verified** Tier 2 enhancements, usable
only when a Stack happens to be Terraform- or Pulumi-managed — that
doc's own table should be corrected in place to reflect this (done,
see that doc directly, not duplicated here).

## Part O: The operation vocabulary — verified verb families, and "assemble" is `describe`/`list` feeding `create`, not a new operation
Grounded in Part N's research, standardizing this project's own
operation names against what real platforms actually call these things,
not inventing fresh verbs:

| This project's operation | Verb family | Matches (verified, Part N) |
|---|---|---|
| `describe_stack(stack_id)` | Describe/Show | AWS `DescribeStacks`, Azure `az deployment stack show`, OpenStack `openstack stack show`, Pulumi `pulumi stack` |
| `list_resources(stack_id)` | List | AWS `DescribeStackResources`/`ListStackResources`, OpenStack `openstack stack resource list` |
| `describe_resource(stack_id, resource_id)` | Describe (singular) | AWS `DescribeStackResource` |
| `graph_stack(stack_id)` | Graph | Tier 2 where available (verified real, Part N); Tier 1 mechanical render universally |
| `generate_stack_template(...)` | Generate | non-mutating drafting step — **already built this session** as `generate_cluster_template()` |
| `create_stack(template)` | Create | the actual mutating call, gated by approval — **already built this session** as `dispatch_and_execute_cluster()` |

**The connecting insight**: "assembling" a new Stack from a mix of new
and existing resources isn't a new operation to design — it's
`describe_stack()`/`list_resources()` (the discovery-before-creation
check, `docs/foundation_discovery_and_capability_matching.md`'s
reuse/create-new/adopt-unmanaged branch, already designed) running
*before* `create_stack()`, every time, never skipped. CloudFormation's
nested-stacks/cross-stack-references precedent (Part M) is exactly this
in production use: a new stack's template can reference an *existing*
stack's exported resource (a `shared_from` edge, reused, not recreated)
while also defining genuinely new resources (`contained_in` edges,
newly created) — one `create_stack()` call, composing both.

**Naming consequence for already-built code**: `gateway/kubernetes_foundation_dispatch.py`'s
`dispatch_and_execute_cluster()` and `generate_cluster_template()`
already implement `create_stack`/`generate_stack_template`'s shape for
the Kubernetes-paradigm case specifically — they don't need
re-architecting, just renaming (Part G/M) and generalizing past
Kubernetes-only once a second compute paradigm needs the same verbs.

## Open questions / not yet decided

**Superseded by Part H (Block dropped entirely)** — no longer applicable:
- ~~Whether `Block` needs its own table~~ — moot, no `Block` table exists
  in the simplified model.
- ~~Q3's exact matching-criteria axis weights~~ — moot, no matching
  mechanism needed once there's no catalog of Blocks/Blueprints to
  resolve between; Blueprint selection (Part H) is now "which Blueprint
  does this resource attach to," not "which Blueprint template gets
  instantiated."

**Still open, carried forward:**
- **Part H's core mechanism**: how a standalone-requested resource
  actually gets bound to a Blueprint — auto-create / requester-named /
  inferred-from-dependency, three options named, none chosen.
- **Part I/G naming**: the `InfraInventoryRecord`-vs-`PlatformRecord`
  merge question from the turn before Part G — still fully open. Two
  concrete schema collisions block either resolution: `resource_type`
  format (`InfraInventoryRecord`'s provider-native strings vs.
  `FoundationRecord`'s inconsistent placeholders — `"gke_cluster"`
  matches neither CFN-style nor GCP's real
  `container.googleapis.com/Cluster` convention, a real bug to fix
  regardless of the merge decision) and `layer`'s two incompatible
  meanings (tier axis vs. network/compute/identity axis) across the two
  schemas.
- **Part L**: visibility depth for the app-persona blueprint query —
  one hop or full chain walk.
- **Part G's tree state**: the `workflows/drafting/` →
  `workflows/provision_infra_resource/` rename is mid-flight — `git mv`
  done, ~22 files' imports and the `Drafting*`-named identifiers not
  yet fixed. Broken until finished.
- The catalog/self-service presentation layer's actual UI/UX — separate
  follow-up, now reframed by Part L as "the app-persona blueprint view"
  specifically rather than an abstract catalog.
- The app-triggered-but-foundation-approved routing mechanism (originally
  Part E/F's Q6) still needs its own pass alongside review-policy design
  — shape borrowed from `SkillProposal`'s admission flow, wiring not
  designed.
- Whether Stage C/D (BU onboarding vs. account vending) should ever
  collapse for the common single-account case — not resolved, Google's
  own model keeps them separate even in the common case, suggestive but
  not conclusive.
- `docs/foundation_layer_decomposition.md` Part D's reverse-dependency
  decommission check, and that doc's other open items, are unaffected by
  anything in Parts G–L — not re-examined this session.

## What's real vs. designed
| Piece | Status |
|---|---|
| `FoundationRecord`, closed 3-layer chain | Design only (`docs/foundation_layer_decomposition.md`) — unchanged by this doc |
| `gateway/scope_gate.py`, `TeamMember.scope`, `FoundationRecord` (with `compute_paradigm`) | **Real, built and tested** this session, via `openspec/changes/provision-kubernetes-cluster` (27/35 tasks) — but named `FoundationRecord`/`requester_has_foundation_scope()`, **not yet renamed** to `PlatformRecord`/`requester_has_platform_scope()` per Part G |
| `gateway/kubernetes_foundation_dispatch.py` | **Real, built and tested** — AWS/GCP/Azure adapters against researched-not-live-verified tool names; not yet renamed per Part G; no `blueprint_id` field yet |
| Block/Blueprint/Matching-Criteria reframe (Parts B/C) | Superseded by Part H — Block dropped, matching-criteria dropped, replaced by a required `blueprint_id` foreign key |
| Blueprint (Part H, simplified) | New, exploratory — sketch only, resolution mechanism (Part H) undecided |
| `workflows/drafting/` → `workflows/provision_infra_resource/` rename | **Mid-flight, broken** — `git mv` done, imports not fixed (Part G) |
| Terraform Stacks / Humanitec research (Parts B/C) | Verified against current docs, still accurate |
| Azure/AWS/GCP native grouping-construct research (Part I) | Verified against current docs this session (see Sources) |
| `InfraRelationship`/diagram-rendering tiers (Part K) | Design only, unchanged, in their own docs — this doc just connects Blueprint to them |

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
- **Parts G–L, added 2026-07-25**: settles four naming decisions
  (`workflows/provision_infra_resource/`, `PlatformRecord`, "platform"
  terminology, `workflow_hint`) affecting `openspec/changes/provision-kubernetes-cluster`'s
  already-built code — that change's artifacts and shipped code are
  **not yet updated to match**, tracked here as the source of truth
  until they are. Drops `Block` entirely (Part H), superseding Parts B/C's
  matching-criteria mechanism. Connects Blueprint, for the first time, to
  `docs/infra_graph_modeling_and_db_options.md`'s `InfraRelationship`
  schema and `docs/creation_time_relationship_capture_and_diagrams.md`'s
  rendering tiers — neither doc previously referenced Blueprint or was
  referenced from here. Verifies (web research, Part I) that Azure's
  Resource Group is the only native equivalent to Blueprint across the
  three clouds, and disambiguates Blueprint (Part J) from the
  already-solved org/billing hierarchy (`docs/org_registry_design.md`,
  `docs/multi_account_per_bu_design.md`) so the two don't get conflated.
  Extends `docs/foundation_and_app_deploy_flow_example.md` step 11a's
  capability-matching read into a general persona-visibility model
  (Part L).
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

**Part I additions (2026-07-25, native cloud grouping constructs):**
- [Azure Management Groups, Subscriptions & RGs Explained — RedFoxSec](https://www.redfoxsec.com/blog/azure-management-groups-subscriptions-and-resource-groups-explained)
- [Design for subscriptions — Microsoft Learn](https://learn.microsoft.com/training/modules/design-governance/4-design-for-subscriptions)
- [Understand and work with Cost Management scopes — Microsoft Learn](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/understand-work-scopes)
- [Building a cost allocation strategy — AWS tagging best-practices whitepaper](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/building-a-cost-allocation-strategy.html)
- [AWS Resource Groups now supports 160 more resource types — AWS What's New](https://aws.amazon.com/about-aws/whats-new/2025/04/aws-resource-groups-160-resource-types)
- [About resource hierarchy — Resource Manager, Google Cloud Documentation](https://docs.cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Using resource hierarchy for access control — IAM, Google Cloud Documentation](https://docs.cloud.google.com/iam/docs/resource-hierarchy-access-control)
- [Create folders — Resource Manager, Google Cloud Documentation](https://cloud.google.com/resource-manager/docs/creating-managing-folders)

**Parts M/N/O additions (2026-07-26, Stack terminology and inquiry/graph API verification):**
- [Azure deployment stacks — MicrosoftDocs/azure-docs, GitHub](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/azure-resource-manager/bicep/deployment-stacks.md)
- [ARM Deployment Stacks now GA! — Microsoft Community Hub](https://techcommunity.microsoft.com/blog/azuregovernanceandmanagementblog/arm-deployment-stacks-now-ga/4145469)
- [Heat Orchestration Template (HOT) specification — OpenStack Heat docs](https://docs.openstack.org/heat/latest/template_guide/hot_spec.html)
- [Stacks | Pulumi Concepts — Pulumi Docs](https://www.pulumi.com/docs/iac/concepts/stacks/)
- [pulumi stack graph — CLI commands, Pulumi Docs](https://www.pulumi.com/docs/iac/cli/commands/pulumi_stack_graph/)
- [Automatic Diagram Generation for Always-Accurate Diagrams — Pulumi Blog](https://www.pulumi.com/blog/automating-diagramming-in-your-ci-cd/)
- [terraform graph command reference — Terraform, HashiCorp Developer](https://developer.hashicorp.com/terraform/cli/commands/graph)
- [DescribeStacks — AWS CloudFormation API Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStacks.html)
- [DescribeStackResources — AWS CloudFormation API Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackResources.html)
- [DescribeStackResource — AWS CloudFormation API Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/APIReference/API_DescribeStackResource.html)
- [Refer to resource outputs in another CloudFormation stack — AWS CloudFormation docs](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/walkthrough-crossstackref.html)
- [Google Cloud Deployment Manager documentation — Google Cloud (EOL notice)](https://docs.cloud.google.com/deployment-manager/docs)
- [OpenStack Orchestration (heat) command-line client — OpenStack Docs](https://docs.openstack.org/ocata/cli-reference/heat.html)
