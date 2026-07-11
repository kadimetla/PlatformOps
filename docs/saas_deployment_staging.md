---
last_updated: 2026-07-11
owner: platformops-agent maintainers
scope: hosted/SaaS deployment topology — from self-hosted single-org to shared multi-tenant infrastructure
reviewed_by: unreviewed (first draft)
---

# SaaS Deployment Staging — From Self-Hosted to Multi-Tenant

## Status
Design/analysis only, pure internal synthesis — grounds this conversation's
deployment-topology discussion against `docs/HARNESS_DESIGN.md`'s
isolation-levels table, `docs/config_storage_backend.md`'s storage
decision, and `docs/account_vending_machine_design.md`'s AFT precedent.
No new external research; nothing here is built. This is sequencing
guidance for a question that hasn't come up as a build priority yet —
the one required next step remains `plan_request(envelope)`
(`docs/planned_implementation.md` Phase 3), unaffected by anything below.

## Part A: Who actually uses this, and where it runs
Tracing the 8-step flow: Steps 1-2 (binding resolution) read
`bindings`/`agents`/`workspace_bundles`/`orgs` on **every** request, the
hottest path in the system, including requests that never mutate
anything. Step 4 adds a live read of `skill_usage_records.lifecycle_state`
(`docs/structured_match_rule_for_skills.md` Part F0c). Writes (`audit_logs`,
`approvals`, `skill_usage_records` UPSERTs, `skill_proposals` transitions,
`memory_entries` inserts) cluster around Steps 7-8, at lower frequency
than reads. Org onboarding is rare — once per org, ever.

**"Managed SaaS" does not mean one shared database serving many tenants'
concurrent traffic.** `docs/HARNESS_DESIGN.md` states this directly:
*"For a managed SaaS deployment, orgs should not share one Gateway trust
boundary. Use one Gateway or one hardened runtime namespace per tenant,
backed by separate cloud credentials and storage."* Managed SaaS here
means **many isolated deployments**, each shaped like the self-hosted
case, operated by PlatformOps instead of the customer — not one big
multi-tenant database absorbing every org's traffic.

## Part B: Cross-cloud provisioning is normal, not a blocker
Every tool this project routes through (`ccapi-mcp-server`,
`terraform-mcp-server`, the GCP/Azure MCP servers) is a control-plane API
client — HTTPS calls to public endpoints, not something requiring
physical proximity to the target cloud. This is standard practice: HCP
Terraform runs entirely in HashiCorp's own infrastructure and provisions
into customer AWS/GCP/Azure accounts constantly. Where PlatformOps hosts
itself is fully decoupled from which cloud(s) each tenant provisions
into.

**What's actually new and undesigned**: credential *delivery* — how a
tenant grants an externally-hosted harness access to their cloud account
at all. The standard patterns (AWS cross-account IAM role with
`ExternalId`, GCP workload identity federation, Azure federated
app-registration credential) are well-trodden, but none of it exists in
this project's design yet — everything so far (`WorkspaceBundle.aws_profile`
as *"a reference, not a secret"*) assumed credentials already configured
in the harness's own local environment, true only for self-hosting.

**This is the same shape as `docs/account_vending_machine_design.md`'s
AFT precedent** — a central automation account holding cross-account
roles into every vended account — already researched for a different
question (account vending) but structurally identical to hosting the
harness itself remotely from every tenant's cloud. Treat as confirmation
this is a proven pattern, not a new risk category.

**The real new risk is confused-deputy, sharpened by remoteness and
sharing.** One shared harness instance holding cross-account role ARNs
for many tenants means a bug could, in principle, assume the wrong
tenant's role — the same class of problem `ExternalId` scoping already
exists to prevent, now mattering more because the harness is physically
remote and (at some stages below) shared infrastructure across tenants.

## Part C: "Host scope" is emergent, not engineered
Isolation is fundamentally about *what else shares this boundary*. When
there's exactly one occupant — self-hosted, or a dedicated instance
PlatformOps operates for one customer — the answer to "what else shares
this host/cluster/database" is nothing, trivially, by construction.
**Host-scope isolation isn't a feature to build; it's what single-tenancy
gives you for free**, regardless of who operates it.

The real spectrum is tenant *count sharing a boundary*, not a menu of
three mechanisms:

| | BU scope | Org scope | Host scope |
|---|---|---|---|
| Gateway process | One, shared | Separate per org | Separate per tenant |
| Database | One, `WHERE org_id=? AND bu_id=?` filtering | Separate per org | Separate per tenant |
| Threat model | Cooperative — co-tenants are colleagues at one company, an accidental-bug risk | Adversarial — co-tenants might actively try to breach each other | Adversarial, but moot — nothing else is present to breach |
| Blast radius of one missing `WHERE` clause | Every BU sharing that Gateway | Contained to one org's process | N/A — no co-tenant |
| Blast radius of a shared-infra flaw (cluster escape, secrets-manager IAM gap) | Same as above — no extra shared layer beyond the process | **Potentially crosses org lines** — this is the actual engineering problem | N/A — no shared infra |
| New component required | None | Tenant router, secrets-path scoping, cluster/node isolation | None beyond "provision another dedicated copy" |

**BU scope and Org scope aren't a harder version of the same problem —
they're different problems.** BU scope's single line of defense (app-code
filtering) is an acceptable bar when nobody sharing the boundary is
trying to break it. Org scope needs defense-in-depth specifically
because the application code *will* eventually have a bug, and under an
adversarial threat model that can't be the only thing standing between
tenants.

### The three concrete Org-scope engineering problems
1. **Tenant router** — a new component that decides which org's Gateway
   instance an inbound request goes to, before that org's own binding
   resolution ever runs. A bug here breaches isolation regardless of how
   well everything downstream is isolated — the simplest, most heavily
   audited piece of the system, precisely because it's the one shared
   thing in front of every otherwise-isolated silo.
2. **Confused-deputy secrets access** — if credentials for all tenants
   live in one shared secrets manager differentiated by path, isolation
   depends entirely on each org's Gateway IAM policy being correctly
   scoped to *only* its own path. A too-broad policy lets org A read org
   B's secrets even with perfectly separate databases.
3. **Shared-cluster blast radius** — a container-escape exploit in one
   org's pod could reach the underlying node and, from there, other
   orgs' pods on that node if network policies have any gap. "Org scope"
   itself has a sub-spectrum: same-cluster-different-namespace (lighter,
   riskier) vs. dedicated-nodes-per-tenant (heavier, safer) vs. fully
   separate clusters (approaching Host-scope cost while still logically
   "Org scope" if PlatformOps operates shared routing above it).

## Part D: Deployment staging — build in this order, triggered by real need
Consistent with this project's own stated bias against designing for
hypothetical future requirements — each stage should be triggered by an
actual need, not built ahead of it.

**Stage 0 — self-hosted, single org (mostly already built).** One
process, SQLite with WAL mode, credentials as local env/profile
references, no tenant router, no outer workflow engine — pending
approvals just live in the `approvals` table `harness/tool_dispatcher.py`
already has, tested. The only real next step, unchanged by anything in
this doc: wire `plan_request(envelope)`.

**Stage 1 — PlatformOps hosts it, still single-tenant per instance.**
Identical architecture to Stage 0; the only difference is who operates
it. Cross-account IAM role trust (Part B) reaches the customer's cloud.
Trivially Host-scope isolated, same as self-hosting, because there's
still exactly one tenant on that infrastructure. Zero new architecture —
a hosting/ops change, not an engineering one.

**Stage 2 — a fleet of Stage-1 deployments, one per customer.** No
tenant router needed — a distinct subdomain per customer
(`acme.platformops.io`) lets DNS/ingress route directly to that
customer's own dedicated instance. The tenant-router problem only exists
when multiple tenants share *one* front door, which Stage 2 deliberately
avoids. This stage is a fulfillment/ops scaling problem (fleet rollout
complexity, linear per-tenant resource cost), not a new architecture
problem.

**Stage 3 — genuine shared-infrastructure multi-tenancy, only once
Stage 2's linear cost is the actual bottleneck.** This is where Part C's
three engineering problems get built for real. Given this system's
inherently low, human-gated request volume, Stage 2 can plausibly carry
a meaningful number of customers before Stage 3's cost/complexity is
justified — don't build it speculatively.

**Orthogonal to all four stages**: SQLite → Postgres, and/or adopting an
outer workflow engine (LangGraph/Temporal, `docs/langgraph_vs_adk_inner_layer.md`).
Neither is driven by tenant count — they're triggered by wanting to
horizontally scale *one* tenant's Gateway for availability, or wanting
real durable-wait semantics instead of polling for long approval waits.
Either could happen at any stage above, independently.

## Open questions / not yet decided
- Exact credential-delivery mechanics per cloud (the specific
  cross-account role/`ExternalId` flow for AWS, workload identity
  federation setup for GCP, federated app-registration credential for
  Azure) — named as the pattern, not designed in mechanical detail.
- Whether Stage 3's tenant router should be a new custom component or
  built on an existing ingress/API-gateway product — not explored.
- Billing/metering — a real requirement of an actual SaaS business,
  explicitly out of scope for this architecture doc.
- The bootstrap tension: does new-tenant provisioning at Stage 2/3 stay
  human-gated/semi-manual, matching `docs/org_bootstrap_privilege_boundary.md`'s
  precedent for the highest-blast-radius actions in this design, or does
  it get its own more-automatable pipeline specifically because spinning
  up an *empty* Gateway+DB (no cloud credentials attached yet) is
  lower-stakes than that precedent's cloud-hierarchy-anchor case? Flagged,
  not resolved.

## How this relates to the existing docs
- Extends `docs/HARNESS_DESIGN.md`'s isolation-levels table with the
  emergent-Host-scope insight and the cooperative-vs-adversarial
  threat-model distinction it implied but never stated explicitly.
- Reframes `docs/config_storage_backend.md`'s SQLite-vs-Postgres question
  as orthogonal to tenancy stage, not a "many orgs sharing one DB"
  scaling question — that framing was never actually this project's own
  design (per `docs/HARNESS_DESIGN.md`'s per-tenant-storage rule).
- Reuses `docs/account_vending_machine_design.md`'s AFT cross-account-role
  precedent as grounding for cross-cloud harness hosting.
- Connects to `docs/org_bootstrap_privilege_boundary.md`'s human-gated
  bootstrap precedent for the new-tenant-provisioning tension at Stage
  2/3.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  explicitly, Stage 0 doesn't depend on anything in this doc.
