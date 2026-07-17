---
last_updated: 2026-07-14
owner: platformops-agent maintainers
scope: when discovery must precede drafting (both foundation- and app-tier requests), and how the resulting semantic model gets presented to a user — connects openspec/changes/infra-inventory-discovery, docs/infra_graph_modeling_and_db_options.md, and docs/request_intent_taxonomy_and_workflow_routing.md
reviewed_by: unreviewed (first draft)
---

# Discovery Before Drafting, and the Presentation Layer

## Status
Design/analysis only. Nothing here is built. Connects several
previously-separate docs into one loop, and corrects a framing error
from earlier in the same exploration thread (Part A). Verified against
the actual text of the docs it cites by direct source inspection, not
recalled from memory.

**Note (2026-07-17)**: `workflows/discovery/` below refers to the same
package now named `workflows/inquiry/` — renamed once it became clear
"discovery" already named the separate background sweep system this
doc describes, distinct from the request-time query workflow.
References below have been updated to the new name; see
`openspec/changes/build-discovery-workflow/design.md`'s rename note.

## Part A: Correction — "discovery-before-drafting" is not persona-based, it's request-shape-based

An earlier framing in this exploration split use of this system into
two personas — "infra/platform team creates foundation from a
blueprint" (assumed to skip discovery) vs. "app developer deploys code
onto existing infra" (assumed to always need discovery first). That
framing is wrong in a way worth stating precisely: **the axis that
actually determines whether discovery must precede drafting is whether
the request is genuinely new/isolated creation, or extends, modifies,
or references something that already exists** — and that axis cuts
across both tiers, not along the persona line.

|                        | Genuinely new, isolated creation | Extends / modifies / references existing infra |
|---|---|---|
| **Foundation-tier** | Rare — first BU ever, a truly greenfield sandbox with nothing to relate to | Common — a new node pool on an existing cluster, a new subnet on an existing VPC, "clone BU X's setup for BU Y" → **needs discovery** |
| **App-tier** | Doesn't really occur — an app deploy always targets something | Always — `deploy-to-k8s`'s own step 1 (`docs/foundation_app_layering_and_iam_tiers.md:147-149`) requires confirming the target cluster "is an approved foundation for this BU" before proceeding → **needs discovery**, unconditionally |

Only the top-left cell skips discovery, and it's the rare case. This
means `workflows/drafting/` (real, built in `migrate-to-langgraph`)
having no discovery-integration point at all is a gap for a
meaningfully larger slice of real usage than "just app-tier deploys" —
it's also missing for the common foundation-tier case of extending or
cloning existing infrastructure.

**Genuinely new, not yet designed anywhere**: "clone BU X's setup as a
starting template for BU Y." This needs discovery of a *reference* BU
(read-only, informing a new BU's draft) as distinct from discovery of a
*target* BU (checked as a precondition for deploying onto it) — the
existing org-level `default_iac_source`/override-precedence pattern
(`docs/org_registry_design.md`) is about where a BU's *own* IaC config
lives, not about using another BU's already-created infrastructure as a
template. No lookup for this exists in any doc.

## Part B: The full loop — background discovery, a queryable semantic model, and presentation

```
┌─────────────────────────────────────────────────────────────────┐
│  BACKGROUND, always running, nobody waiting on it                  │
│                                                                     │
│  bootstrap (once, BU onboarding)  ─┐                               │
│  incremental (rides Step 8)        ├─▶  InfraInventoryRecord        │
│  nightly drift sweep               ─┘   (nodes)                     │
│                                          +                          │
│                                     InfraRelationship (edges —      │
│                                     contained_in, depends_on,       │
│                                     shared_from — schema in         │
│                                     docs/infra_graph_modeling_       │
│                                     and_db_options.md, design only) │
│                                                                     │
│  = a continuously warm semantic model of "what actually exists"     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │  queried, NOT freshly scanned — the
                              │  whole point of keeping it warm in
                              │  the background is avoiding a live
                              │  cloud API round-trip per request
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  workflows/inquiry/ (design only, docs/request_intent_taxonomy_   │
│  and_workflow_routing.md)                                          │
│                                                                     │
│  "Extend/clone" query: target (or reference) BU's foundation        │
│  subgraph — network → compute → identity, with relationship detail  │
│                                                                     │
│  "Deploy" query: target foundation's discovered_capabilities        │
│  specifically — namespace, ingress class, storage class,            │
│  workload-identity target (docs/foundation_discovery_and_           │
│  capability_matching.md)                                            │
│                                                                     │
│  Both also need the requester's authorization checked —             │
│  TeamMember(channel_user_id, role, scope) — role: "requester" |     │
│  "approver" | "admin", scope: "foundation" | "app" | "both"          │
│  (verified schema, docs/skills_and_workspace_design.md:78-82).      │
│  A role="admin", scope="app" member has full control over their     │
│  own app-layer deploys and zero access to foundation-layer          │
│  changes, regardless of role                                        │
│  (docs/infra_discovery_and_platform_app_split.md:152-154) — the     │
│  gate is two-axis (role × tier), not a single yes/no                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PRESENTED to the user — the genuinely new piece, Part C            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                 user decision seeds workflows/drafting/'s spec
```

## Part C: Presentation — two surfaces, one underlying model

A discovery response is naturally graph-shaped (nodes + edges), which
fits the generative-UI mechanism already established for this
project's chat channel far better than a text wall — `docs/ui_and_
multitenancy_deep_dive.md`'s A2UI (a JSON UI-rendering format riding on
AG-UI, verified real in this session's CopilotKit research) can render
a subgraph as an actual card/diagram inline in the conversation.

Two distinct presentation surfaces worth naming separately, not
conflating — both reading the *same* `InfraInventoryRecord`/
`InfraRelationship` data, differing only in lifetime and scope:

- **Ephemeral, chat-native (A2UI card)** — scoped to one request's
  context, answers "show me before I act," disappears with the
  conversation. Example: a requester asking "what's BU X's foundation
  look like, I want to add a node pool" gets a rendered subgraph with
  an actionable next step, not a flat listing.
- **Persistent, browsable (a Control UI view)** — for "let me look
  around BU X's whole footprint" independent of any one request.
  `docs/control_ui_approval_queue_design.md`'s existing "Config
  health" view is the closest precedent shape for this — a dedicated
  view, not a one-off response.

## Open Questions
- The exact serialization format for a presented subgraph — raw
  graph structure, a pre-summarized tree, something else — not
  designed, this doc only establishes that A2UI is the right rendering
  mechanism, not the payload shape.
- The "clone from a reference BU" query pattern (Part A) — needs its
  own lookup shape, distinct from "discover my own target BU," not
  designed anywhere yet.
- Where exactly the `TeamMember` role×scope check gets enforced —
  inside `workflows/inquiry/` itself, or as a separate gate before
  it's invoked (mirrors binding resolution, `spec/flow_steps/02`) —
  not decided.

## How this relates to the existing docs
- Corrects this same exploration's own earlier persona-based framing
  (chat history, not a prior doc) — the axis is request-shape
  (new-isolated vs. extends/references), not persona.
- Connects `openspec/changes/infra-inventory-discovery` (bootstrap/
  incremental/nightly mechanisms, `InfraInventoryRecord`) and
  `docs/infra_graph_modeling_and_db_options.md` (`InfraRelationship`
  edges, still design-only) as the data layer underneath
  `docs/request_intent_taxonomy_and_workflow_routing.md`'s
  `workflows/inquiry/` workflow.
- Extends `docs/foundation_discovery_and_capability_matching.md`'s
  `discovered_capabilities` matching and `docs/foundation_app_layering_
  and_iam_tiers.md`'s foundation/app-tier approval-bar distinction with
  the specific finding that discovery-before-drafting isn't scoped to
  app-tier alone.
- Reuses `docs/skills_and_workspace_design.md`'s `TeamMember` schema and
  `docs/infra_discovery_and_platform_app_split.md`'s role×scope
  authorization model directly, not a new mechanism.
- Names `docs/ui_and_multitenancy_deep_dive.md`'s A2UI and
  `docs/control_ui_approval_queue_design.md`'s existing view precedent
  as the two real presentation surfaces, without designing the payload
  format itself.
- Doesn't change `openspec/changes/migrate-to-langgraph`'s scope —
  `workflows/drafting/` (real, built) still has no discovery-
  integration point; this doc names that gap precisely but doesn't
  close it.
