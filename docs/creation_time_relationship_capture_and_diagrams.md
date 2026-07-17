---
last_updated: 2026-07-17
owner: platformops-agent maintainers
scope: capturing InfraRelationship edges at creation time instead of only inferring them later via discovery, and what's actually needed to render architecture diagrams vs. data flow diagrams from that data — extends docs/creation_profiles_and_deterministic_discovery.md and docs/infra_graph_modeling_and_db_options.md
reviewed_by: unreviewed (first draft)
---

# Creation-Time Relationship Capture, and What It Takes to Draw a Diagram

## Status
Design only. Nothing here is built. One claim below (native
toolchain-provided dependency graphs, e.g. `terraform graph`) is
explicitly flagged **unverified** — recalled from training data, not
confirmed against current docs the way this project's research
discipline requires (`docs/cross_project_network_sharing.md`,
`docs/iac_based_discovery.md`). It must not be treated as fact until
checked.

## Part A: Three profile-shaped concepts that should converge, and don't yet

```
CreationProfile                InfraRelationship               vibe_diff (built, real)
  "HOW it was made"              (designed, not built)            "WHAT changed" -- flat
  skill, toolchain,               "WHAT IT CONNECTS TO"            text today, not
  iac_source                      contained_in, depends_on,        structured data
  (docs/creation_profiles_         shared_from,
   and_deterministic_              workload_identity_binds_to
   discovery.md)                   (docs/infra_graph_modeling_
                                     and_db_options.md)
        │                                │                                │
        └────────────────┬───────────────┴────────────────────────────────┘
                          ▼
          creation-time capture: how, what-it-touches, and what
          changed, together -- renderable as a diagram, not just
          three disconnected records
```

`InfraRelationship` is currently scoped, in its own doc, as something a
*discovery sweep* infers after the fact from live API calls
(`getXpnHost`, `DescribeSubnets.OwnerId`). This doc proposes it can — and
for anything this harness creates, should — be populated earlier and
more reliably: at creation time.

## Part B: The core insight — creation-time capture beats discovery-time inference, for the same reason IaC state beats live API

`docs/iac_based_discovery.md` Part C already established: *"IaC state
carries declared intent live API discovery can never recover."* That
argument applies one step earlier, and more strongly. When
`cdk_provisioning_node` calls `propose_tool_intent` for a subnet
(`workflows/drafting/tools.py:20-37`), the call's `payload:
Dict[str, Any]` already contains the subnet's `vpc_id` — a
`contained_in` edge, known with certainty, before the resource even
exists. A later discovery sweep re-deriving the same fact from a live
API call isn't just redundant, it can be strictly worse: the exact GCP
Shared VPC case already found (`getXpnHost` not confirming the
relationship at Cloud Asset Inventory's Security Command Center tier)
is a live API call *failing* to answer a question the original
`propose_tool_intent` payload would have answered directly, had anyone
been extracting relationships from it.

**`payload` is untyped today** (`Dict[str, Any]`, confirmed by
`workflows/drafting/tools.py:28`) — nothing currently reads structure
out of it beyond what `ToolIntent` re-wraps verbatim
(`gateway/schemas.py:77`).

## Part C: Concrete mechanism — same hook as `CreationProfile`

`openspec/changes/infra-inventory-discovery/tasks.md` task 3.1 already
plans the moment: hooking `InfraInventoryStore.upsert()` into
`BrokeredToolDispatcher`'s `ALLOW` + successful-execution path.
`docs/creation_profiles_and_deterministic_discovery.md` Part D proposed
constructing `CreationProfile` at that same hook. `InfraRelationship`
rows should be constructed there too, from the same already-executed
`ToolIntent.payload` — one hook point, three things stamped
(inventory row, creation profile, relationship edges), not three
separate mechanisms.

This doesn't replace discovery-time relationship inference — it stays
the only source for pre-existing infra this harness didn't create,
same provenance split already established for `InfraInventoryRecord`.

## Part D: Rendering a diagram — three tiers, different confidence

| Approach | What it is | Confidence |
|---|---|---|
| **Mechanical graph render** | `InfraInventoryRecord` nodes + `InfraRelationship` edges → Mermaid/DOT syntax via plain code, zero LLM | High — a graph-to-text serializer, deterministic, same "start with the plain table" reasoning `docs/infra_graph_modeling_and_db_options.md` already used to reject a graph DB before the first plain table exists |
| **Native toolchain graph** | `terraform graph` (Terraform CLI subcommand emitting a DOT-format dependency graph) and a possible CDK/CloudFormation equivalent | **Unverified.** Recalled, not researched — needs the same current-docs check `docs/iac_based_discovery.md`/`docs/cross_project_network_sharing.md` applied to every other MCP-server capability claim in this project, before it's treated as available or goes into any implementation-facing doc |
| **LLM-narrated diagram** | Ask the model to describe/render a diagram from the spec | Lowest confidence — hallucination risk on exactly the kind of claim (topology, security boundaries) where being wrong is expensive, same caution already applied elsewhere in this project to unbounded LLM output for infra-affecting decisions |

Only the first tier is concrete enough to design toward now.

## Part E: Data flow diagrams are a separate, harder problem — don't conflate with architecture diagrams

An architecture diagram needs the *structural* graph — `InfraRelationship`'s
existing vocabulary (`contained_in`, `depends_on`, `shared_from`,
`workload_identity_binds_to`) is sufficient. A **data flow diagram**
needs *direction and content* — which resource sends what kind of data
to which, not just that a path exists between them. A security group
rule allowing port 443 from A to B is a structural edge; whether PII
actually flows across it is a materially harder claim, usually the
entire point of a real DFD (threat modeling, compliance review). None
of the existing relationship vocabulary captures this, and extending it
isn't obviously sufficient — resolving "what data" likely requires
either explicit user-declared data classification per resource (a new
input, not inferred) or LLM narration (Part D's lowest-confidence
tier). Treated here as a named, separate, harder problem — not
attempted.

## Open Questions
- Whether `ToolIntent.payload` needs a typed, per-resource-type schema
  (vs. today's `Dict[str, Any]`) to reliably extract relationship
  fields, or whether a separate per-resource-type extraction mapping
  (e.g. "for `AWS::EC2::Subnet`, `payload.vpc_id` → `contained_in`
  edge") is simpler — not designed here. Precedent exists for the
  mapping-table shape: `gateway/infra_inventory_store.py`'s
  `PROVIDER_TYPE_TO_CATEGORY`.
- Whether `terraform graph` (or a CDK/CloudFormation equivalent) is
  real, current, and usable via `terraform-mcp-server` — genuinely
  unresolved, flagged explicitly rather than assumed. Blocks Part D's
  second tier from being anything more than a hypothesis.
- DFD generation's data-classification/direction problem — not
  designed, not scoped into this change; named so it doesn't get
  silently folded into "diagram generation" as if it were the same
  difficulty as the architecture-diagram tier.
- Whether relationship extraction should run synchronously in the same
  `BrokeredToolDispatcher` hook, or asynchronously afterward — not
  decided; synchronous keeps everything in one transaction, async
  avoids adding latency to the dispatch path that approves real
  infrastructure changes.

## Real vs. designed
| Piece | Status |
|---|---|
| `InfraInventoryRecord`, `InfraInventoryStore` | Built, real |
| `CreationProfile` | Designed only (`docs/creation_profiles_and_deterministic_discovery.md`) |
| `InfraRelationship` (discovery-time population) | Designed only (`docs/infra_graph_modeling_and_db_options.md`) |
| `InfraRelationship` populated at creation time, from `ToolIntent.payload` | Designed only, this doc |
| Mechanical graph → Mermaid/DOT render | Designed only, this doc |
| Native toolchain graph command (`terraform graph` etc.) | **Unverified claim** — not yet researched |
| DFD generation | Not designed — named as a separate, harder problem |

## How this relates to the existing docs
- Extends `docs/creation_profiles_and_deterministic_discovery.md` —
  proposes `InfraRelationship` gets stamped at the same
  `infra-inventory-discovery` task 3.1 hook `CreationProfile` already
  targets, not a new mechanism.
- Extends `docs/infra_graph_modeling_and_db_options.md` — reuses its
  `InfraRelationship` schema and relationship vocabulary unchanged;
  adds *when* it gets populated (creation-time, not only discovery-time)
  and *what it's for* (diagram rendering) beyond that doc's own scope
  (in-process traversal queries).
- Applies `docs/iac_based_discovery.md` Part C's "declared intent beats
  live-API inference" principle one step earlier than that doc scoped
  it (creation, not just discovery).
- Doesn't change `workflows/inquiry/` — only affects what data would
  eventually be available for it, or a future presentation layer
  (`docs/discovery_before_drafting_and_presentation_layer.md` Part C),
  to read.
