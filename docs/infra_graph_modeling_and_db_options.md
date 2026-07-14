---
last_updated: 2026-07-14
owner: platformops-agent maintainers
scope: whether/how to model discovered infra relationships as a graph, and a verified survey of light/embedded graph and semantic-modeling databases — extends openspec/changes/infra-inventory-discovery
reviewed_by: unreviewed (first draft)
---

# Infra Graph Modeling and Database Options

## Status
Design/research only. Nothing here is built, and nothing here is yet
folded into `openspec/changes/infra-inventory-discovery`'s actual
`tasks.md` (0/22, not started). Every third-party tool claim below is
verified via direct web research against current sources (2026), not
training-data recall, per this project's standing rule for fast-moving
integrations — see Sources. Extends `infra-inventory-discovery` by
naming a real gap in `InfraInventoryRecord`'s schema (existence only,
no relationships) and surveying what would fill it, without deciding
to build anything yet.

## Part A: This project has already needed a graph, three times, without naming it

| Where | What it actually is | How it's modeled today |
|---|---|---|
| `docs/foundation_layer_decomposition.md` | `depends_on_foundation_id` — network→compute→identity dependency chain | One hardcoded parent-pointer column — a graph edge with exactly one relationship type baked in |
| `docs/cross_project_network_sharing.md` Part F | Azure VNet peering — *"not a two-party lookup... a graph to traverse"* | Recommends fetching the whole edge list via Resource Graph, then BFS/DFS **in process, in Python** — no database-level graph structure |
| Same doc, Parts D/E | GCP Shared VPC host↔service, AWS RAM subnet sharing | Two-hop lookups, hand-coded as specific per-provider API sequences |
| `InfraInventoryRecord` (`infra-inventory-discovery`) | Existence only | Flat rows: `(org_id, bu_id, resource_type, resource_identifier, resource_category, layer, ...)` — no relationship field at all |

Every time this project has hit a "how does X relate to Y" question,
it's solved it as bespoke, one-off traversal code, never as a general
concept.

## Part B: What a relationships concept would add — additive, not a replacement

```
InfraInventoryRecord (nodes, already designed) — unchanged
        +
InfraRelationship (edges, new)
  (org_id, bu_id, subject_identifier, relationship_type,
   object_identifier, discovered_at, provenance)
```

A small, extensible relationship vocabulary — `contained_in` (subnet ∈
VPC), `depends_on` (generalizing `depends_on_foundation_id`),
`shared_from` (unifying GCP Shared VPC / AWS RAM / Azure peering under
one edge type, the same move already made for `resource_category`
unifying "is this a network resource" across three provider-native type
vocabularies), `workload_identity_binds_to`. Nodes stay flat rows
exactly as already designed; only connections between them become
explicit and queryable instead of implicit knowledge buried in
per-provider application code.

**Where this actually pays for itself**: `docs/request_intent_taxonomy_and_workflow_routing.md`'s
`workflows/discovery/` capability-match branch (scenario #5 — "show
existing infra suitable to deploy a webapp") is the one place an LLM
already reasons over discovery output. Handing it an actual subgraph —
"here's the VPC, here's what's contained in it, here's what depends on
it" — is a better-shaped input than a flat list of unrelated existence
rows for exactly the judgment call that workflow needs to make.

## Part C: Paradigm question — property graph vs. RDF/semantic triple store

Two different things, not one spectrum:
- **Property graphs** (Kuzu, FalkorDB, Neo4j-style): nodes and edges
  both carry arbitrary properties, queried via Cypher or SQL/PGQ,
  optimized for traversal.
- **RDF/semantic triple stores** (RDFLib, Oxigraph): everything is a
  subject-predicate-object triple, queried via SPARQL, built around
  shared vocabularies/ontologies and formal logical inference
  (RDFS/OWL entailment).

**Property graphs fit this project's actual problem better**, for two
concrete reasons: `InfraRelationship` edges need properties on the edge
itself (`discovered_at`, `provenance`) — plain RDF triples don't carry
predicate properties without extra machinery (RDF-star, reification).
And nothing in `docs/request_intent_taxonomy_and_workflow_routing.md`'s
scenario catalog needs formal ontological inference — every scenario is
a concrete traversal ("what's in this VPC," "what depends on this
foundation"), not a subsumption-reasoning question.

## Part D: Verified survey — light/embedded options, both paradigms

| Tool | Paradigm | Embedded? | Verified status | Verdict |
|---|---|---|---|---|
| **KuzuDB** | Property graph | Yes — in-process, MIT-licensed, real Python bindings, Cypher | **Real maintenance red flag**: GitHub repo archived October 2025, final release `0.11.3`; Apple agreed to acquire Kùzu Inc. per a February 2026 EU DMA filing. Community fork exists, unproven. Independently corroborated by Graphiti's own docs, which mark Kuzu as *"Deprecated — upstream Kuzu project is no longer maintained."* | **Reject** — real, disqualifying risk for new adoption today |
| **FalkorDB** | Property graph | Mostly — `FalkorDBLite` self-manages an embedded Redis process | Actively maintained (RedisGraph's successor after its EOL), real `falkordb-py` client, Cypher support, explicit multi-tenancy design (*"10,000+ isolated graphs"* per instance) — fits this project's per-org/BU shape well | **Defer, not reject** — the concrete next step up if `workflows/discovery/`'s LLM branch needs real GraphRAG-style retrieval, or traversal volume genuinely outgrows in-process BFS/DFS |
| **DuckDB + DuckPGQ** | Property graph | Yes — DuckDB itself is embedded, no server, same category as SQLite | Real extension implementing SQL/PGQ (ISO-standard SQL property-graph syntax, not a new query language), loadable as a community extension since DuckDB v1.0.0 without special flags | **Defer, not reject** — a smaller step up than FalkorDB (standard SQL, still embedded), but a *second* embedded engine alongside the SQLite file already in use, not reusing it |
| **Graphiti** | Framework over a property-graph backend, LLM-mediated construction | **No, not by default** — verified from the real repo: standard path is `docker compose up` (Neo4j) or `docker compose --profile falkordb up` (FalkorDB), a genuine server requirement. One narrow exception: `graphiti-core[falkordblite]` gives an embedded variant, needs Python 3.12+, presented as a special case | Active development (v0.29.2, June 2026, 888 commits, 28.7k stars) — real and maintained, but **solves a different problem**: built to extract entities/relationships from unstructured, evolving data via LLM inference (*"Graphiti depends on structured (JSON) output for entity/edge extraction and deduplication"*), with bi-temporal fact invalidation for data that changes interpretation over time | **Reject** — not because it isn't real, but because every relationship this project has identified (GCP `getXpnHost`, AWS `DescribeSubnets.OwnerId`, Azure Resource Graph peering edges) is already structured and unambiguous the moment the API call returns. No extraction problem exists to justify an LLM-mediated construction layer |
| **RDFLib** | RDF/semantic | Yes — pure Python, in-memory or Berkeley-DB-backed | Actively maintained (v8 in development), mature, real SPARQL support | Not recommended — right paradigm question answered "no" in Part C, not a maintenance or reality concern |
| **Oxigraph / pyoxigraph** | RDF/semantic | Yes — Rust-backed, RocksDB storage, no server | Actively maintained (commits as recent as June 2026), SPARQL-compliant, can plug into RDFLib as a faster backend via `oxrdflib` | Not recommended, same reason as RDFLib — real and lightweight, wrong paradigm for this problem |
| **NetworkX** | Property graph, in-memory only | Yes — pure Python, no persistence at all | Not a database — a graph algorithms library. This is the "zero new infrastructure" traversal layer, used *on top of* whichever storage holds the edges | **Recommended for traversal**, paired with the plain-SQLite baseline below |

## Part E: Recommendation

**Start with a plain `InfraRelationship` edges table in the same SQLite
file `gateway/tool_dispatcher.py` already opens, traversed in-process
with NetworkX or a plain adjacency dict.** Zero new dependencies,
consistent with `docs/config_storage_backend.md`'s "one storage
system, not many" principle already established elsewhere in this
project, and consistent with `AGENTS.md`'s *"write the absolute minimum
code required... no speculative abstractions."* Nothing in
`infra-inventory-discovery` is built yet (0/22 tasks) — adding a
dedicated graph database before the first table exists would be
designing defensively against complexity that hasn't been proven real,
the same reasoning that doc's own design.md already applied to a
different risk (*"not addressed in this design; worth a follow-up if it
proves real, not designed defensively against a hypothetical scale
problem now"*).

Two named, conditional next steps, not open-ended "revisit later":
- **DuckPGQ** if plain recursive CTEs against the edges table genuinely
  get unwieldy, but a separate always-on server still isn't wanted.
- **FalkorDB** if `workflows/discovery/`'s capability-match branch needs
  real GraphRAG-style retrieval tooling, or graph-per-tenant isolation
  at a scale a hand-fetched subgraph can't comfortably serve.

KuzuDB, Graphiti, RDFLib, and Oxigraph are not on either escalation
path — the first for a real, current maintenance risk; the rest because
they solve a different-shaped problem than this one.

## Open Questions
- Whether `depends_on_foundation_id` should be retrofitted into the new
  `InfraRelationship` table (as a `depends_on` edge row) or left as its
  own dedicated column — not decided; the first concrete place the new
  concept and existing, already-designed schema would collide.
- Exact `relationship_type` vocabulary beyond the four named in Part B
  — sketched, not exhaustively designed.
- Whether NetworkX itself becomes a real dependency or whether a plain
  adjacency-dict traversal is sufficient given the shallow depth of
  every traversal identified so far (2–3 hops) — not benchmarked.

## How this relates to the existing docs
- Extends `openspec/changes/infra-inventory-discovery/design.md` and
  `specs/infra-inventory-record/spec.md` — `InfraInventoryRecord`'s
  existence-only schema is unchanged by this doc; `InfraRelationship`
  is a proposed sibling table, not a redesign.
- Generalizes `docs/cross_project_network_sharing.md` Part F's
  already-verified "fetch the edge list in bulk, traverse locally"
  recommendation for Azure specifically into a project-wide pattern,
  rather than introducing a new idea.
- Reuses `docs/config_storage_backend.md`'s "one storage system, not
  many" principle as the deciding argument against adopting a dedicated
  graph database before the plain-table approach is proven
  insufficient.
- Feeds `docs/request_intent_taxonomy_and_workflow_routing.md`'s
  `workflows/discovery/` capability-match branch — the concrete
  consumer that would benefit most from a real relationships model,
  named there as still undesigned.
- Doesn't change the one required next step
  (`plan_request(envelope)`, already implemented) — entirely a
  discovery/inventory-side concern.

## Sources
- [kuzudb/kuzu — GitHub](https://github.com/kuzudb/kuzu)
- [Kuzu's Legacy and the New Wave of Embedded Graph Databases](https://gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape/)
- [kuzu · PyPI](https://pypi.org/project/kuzu/)
- [FalkorDB — GitHub](https://github.com/FalkorDB/FalkorDB)
- [FalkorDB Docs](https://docs.falkordb.com/)
- [FalkorDBLite (Python) — FalkorDB Docs](https://docs.falkordb.com/operations/falkordblite/falkordblite-py.html)
- [RedisGraph EOL: FalkorDB Migration Guide](https://www.falkordb.com/blog/redisgraph-eol-migration-guide/)
- [getzep/graphiti — GitHub](https://github.com/getzep/graphiti)
- [Zep: A Temporal Knowledge Graph Architecture for Agent Memory (arXiv)](https://arxiv.org/abs/2501.13956)
- [Graphiti: Knowledge graph memory for an agentic world — Neo4j blog](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- [Zep Documentation — Graphiti overview](https://help.getzep.com/graphiti/getting-started/overview)
- [oxigraph/oxigraph — GitHub](https://github.com/oxigraph/oxigraph)
- [oxrdflib — PyPI](https://pypi.org/project/oxrdflib/)
- [RDFLib — GitHub](https://github.com/rdflib/rdflib)
- [rdflib · PyPI](https://pypi.org/project/rdflib/)
- [cwida/duckpgq-extension — GitHub](https://github.com/cwida/duckpgq-extension)
