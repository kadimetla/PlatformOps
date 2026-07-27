## Context
This session worked out the shape of this flow across several
exploration passes: `docs/composable_foundation_blueprints.md` Part E
(the ordered stage sequence, the app-triggered-but-foundation-approved
gap), `docs/multi_cloud_foundation_and_iam.md` Part E (verified
hosted-vs-self-hosted status and self-hosted launch mechanism for all
three clouds), and `docs/compute_paradigm_layering.md` (Kubernetes as
one of four compute paradigms, each with a different-shaped
resource-provisioning chain). A second opinion (codex, web-verified)
produced a concrete 14-step approval-gated flow for the AWS path
specifically. This design turns that into one buildable,
provider-parameterized flow — for the Kubernetes paradigm specifically,
not a generic "Stack-tier" capability (originally "foundation" --
renamed per `docs/composable_foundation_blueprints.md` Parts G/M).

Nothing this design touches exists in code today: `TeamMember`/`scope`,
`ResourceRecord`, and all three clouds' cluster-creation MCP configs
are all currently absent from `gateway/schemas.py` /
`mcp_server/external_servers.py`.

## Goals / Non-Goals

**Goals:**
- One infra-scoped requester can create one Kubernetes cluster, on any
  of the three clouds, through the existing deny-by-default approval
  gate.
- Reuse everything already real: `BrokeredToolDispatcher`,
  `PlanRecord`/`ToolIntent`, the compliance preflight, the
  `StdioServerParameters` connection shape.
- Real tests against mocked MCP responses for all three clouds, in this
  environment.
- Record *which* compute paradigm this is on the schema itself
  (`ResourceRecord.compute_paradigm`), not only in doc prose, so a
  future VM/managed-container/serverless capability can't accidentally
  collide with or silently reuse this one's records.

**Non-Goals:**
- VM, managed-container, or serverless provisioning — three
  separate, future capabilities per `docs/compute_paradigm_layering.md`
  Part C's finding that each has a genuinely different (often lighter)
  resource-provisioning chain, not a variant of this one.
- The `Block`/matching-criteria model (`Blueprint` itself was renamed
  `Stack` and partially adopted -- see `stack_id` above -- but the
  catalog/matching-criteria machinery around it stays out of scope) —
  not needed for one requester creating one cluster with no topology
  choice to make yet.
- Network/compute/identity layer decomposition
  (`docs/foundation_layer_decomposition.md`) — one `ResourceRecord`
  per cluster, undecomposed, until a second real case needs the
  layers tracked separately.
- Org/BU/account onboarding (Stages A–D,
  `docs/composable_foundation_blueprints.md` Part E) — assumes an
  org/BU/account already exist, the same assumption every other real
  entry point in this codebase (`plan_request()`, `intake_request()`)
  already makes.
- Hosted MCP endpoints — self-hosted only this round. The
  connection-config layer is written so a later switch is a config
  change (per `docs/multi_cloud_foundation_and_iam.md` Part E's
  `StreamableHttpConnection` sketch), not built or exercised here.
- Live, real-cluster end-to-end testing — no cloud credentials exist in
  this environment; see Risks.
- Reconciling with `wire-dispatch-execution` (a separate, not-yet-applied
  app-tier proposal) into one shared execution module — flagged as a
  real follow-up, not solved here.

## Decisions

**`TeamMember`/`scope` reused exactly as already designed, not
redesigned.** `docs/skills_and_workspace_design.md` and
`docs/infra_discovery_and_platform_app_split.md` already specify this
field in full (`role: str`, `scope: "stack"|"app"|"both"`). This
change implements it as written — the design work is already done.

**The scope gate runs before skill/tool resolution, structurally, not
as a prompt instruction.** Matches
`docs/foundation_and_app_deploy_flow_example.md`'s Bob/Alice walkthrough:
a `scope="app"`-only requester is denied at this check, before any
drafting agent or MCP client is even constructed — a code-level gate,
consistent with this project's "deterministic checks stay deterministic"
rule (`AGENTS.md`).

**`ResourceRecord` carries `compute_paradigm` explicitly, not just
`layer` — and, per a later same-session rename
(`docs/composable_foundation_blueprints.md` Parts G/H/M), a required
`stack_id`.** One `ResourceRecord` per cluster, not the full layered
chain, self-describing about which of the four paradigms it is, and
never dangling (Part H's rule: a resource can be requested standalone,
but can never end up with no Stack reference):
```python
class ResourceRecord(BaseModel):
    resource_id: str
    stack_id: str                # required, never null -- Part H's
                                  # "never dangling" rule. Binding
                                  # mechanism (auto-create / requester-
                                  # named / inferred-from-dependency)
                                  # still undesigned -- see Open
                                  # Questions below and gateway/
                                  # kubernetes_resource_dispatch.py's
                                  # own docstring, which picks
                                  # auto-create as a stand-in, not a
                                  # considered resolution
    org_id: str
    bu_id: str
    cloud_provider: str          # "aws" | "gcp" | "azure"
    compute_paradigm: str = "kubernetes"
                                  # "kubernetes" | "vm" | "managed_containers" |
                                  # "serverless" -- field already designed in
                                  # docs/compute_paradigm_layering.md Part D,
                                  # wired into a concrete schema for the first
                                  # time here; this change only ever writes
                                  # "kubernetes"
    layer: str = "compute"       # fixed for this change; the full
                                  # network/compute/identity enum from
                                  # docs/foundation_layer_decomposition.md
                                  # is real design, deferred here
    resource_type: str           # "AWS::EKS::Cluster" | "gke_cluster" |
                                  # "azure_aks_cluster"
    resource_identifier: str
    approved_plan_id: str
    status: str = "active"       # "active" | "decommissioned"
    provenance: str = "created"
    discovered_capabilities: Dict[str, Any] = Field(default_factory=dict)
```
Deliberately the minimal slice of the canonical schema
(`docs/foundation_app_layering_and_iam_tiers.md` Part D +
`docs/compute_paradigm_layering.md` Part D) — every field here is
already specified in one of those two docs; nothing is invented, fields
not needed yet (`depends_on_foundation_id`, `cloud_account_binding_id`)
are simply not included this round. A future VM/managed-container/
serverless capability queries `ResourceRecord` filtered by
`compute_paradigm` rather than needing its own table.

**Generate/deploy split, reused from codex's verified AWS flow, applied
to all three clouds identically.** Template/manifest generation
(AWS: `manage_eks_stacks(operation="generate")`; GCP/Azure: the
equivalent dry-run/plan-shaped call, exact tool name pending Migration
Plan step 0) is non-mutating — allowed to run without approval, but
still recorded. The actual create call is always a `ToolIntent`, always
gated by `evaluate_intent()`. This is the same split
`workflows/provision_stack/`'s `propose_tool_intent` pattern already uses for
app-tier resources, applied one level up.

**One execution module, provider-parameterized — not three separate
ones.** `gateway/kubernetes_resource_dispatch.py`,
`dispatch_and_execute_cluster(plan, tool_intent, human_approved,
dispatcher, mcp_client, cloud_provider) -> ClusterDispatchResult`.
Internally branches to one of three small adapter functions
(`_execute_aws_eks`, `_execute_gcp_gke`, `_execute_azure_aks`) that each
know their own cloud's tool name and payload shape — the approval gate,
audit recording, and `ResourceRecord` write happen once, in the shared
function, not duplicated per cloud. Named distinctly from
`wire-dispatch-execution`'s (not-yet-built) `gateway/dispatch_execution.py`
deliberately — this module is scoped to the Kubernetes paradigm only,
always requires `human_approved=True` (no app-tier autonomous path
exists for Stack-tier resources, matching
`docs/foundation_app_layering_and_iam_tiers.md` Part A's "always human,
no exception" rule), and doesn't share the app-tier module's
partial-failure-across-multiple-intents concern since a cluster-creation
request is always exactly one `ToolIntent`.

**Per-cloud tool names are placeholders pending live verification, not
guesses committed to code.** AWS's are the most solid (codex
web-verified: `manage_eks_stacks`, `--allow-write`). GCP's (`gke-mcp`)
and Azure's (`aks-mcp`) exact tool names/parameters were confirmed to
*exist* (Part E research) but not confirmed field-by-field against a
live `get_tools()` call — Migration Plan step 0 is a hard blocker before
writing the GCP/Azure adapter functions for real, same discipline
`workflows/provision_stack/mcp_tools.py` already states for its own inferred
tool names.

## Risks / Trade-offs
- [Risk] No AWS/GCP/Azure credentials exist in this environment — every
  adapter function and every "live verification" Migration Plan step
  can be built and unit-tested against mocked MCP responses here, but
  none can be proven against a real cloud from this environment →
  [Mitigation] stated plainly, not glossed over; tasks.md ends with an
  explicit manual checklist for running this against real credentials
  wherever they're available, separate from the automated test suite
  built here.
- [Risk] GCP's and Azure's exact tool schemas are unverified — building
  the adapter against a wrong assumed shape could look correct in mocked
  tests and fail against the real server → [Mitigation] Migration Plan
  step 0 is sequenced first and treated as a hard gate, same as
  `wire-dispatch-execution`'s equivalent step; GCP/Azure adapter tasks
  are explicitly ordered after it, not in parallel.
- [Risk] One `ResourceRecord` per cluster (network+compute+roles
  bundled) will need re-decomposing the day a second cluster needs to
  share an existing VPC → [Mitigation] accepted deliberately, matches
  this project's stated principle of not building the registry before a
  real second case exists; `docs/foundation_layer_decomposition.md`
  already has the follow-up design ready when that day comes.
- [Risk] This change and `wire-dispatch-execution` build two separate,
  similarly-shaped execution modules → [Mitigation] accepted for now,
  flagged explicitly as a follow-up unification rather than either
  blocking on the other; both are real, working code either order.
- [Risk] A future VM/managed-container/serverless capability could still
  accidentally reuse this change's Kubernetes-specific adapter shape by
  copy-paste rather than genuinely redesigning for its own (lighter)
  chain → [Mitigation] `compute_paradigm` being a required, explicit
  field on every `ResourceRecord` at least makes the mismatch visible
  at read time, even if it doesn't prevent the write-time mistake.

## Migration Plan
0. **Blocking precondition, per cloud**: live-verify `eks-mcp-server`'s
   (already codex-verified, lower risk), `gke-mcp`'s, and `aks-mcp`'s
   exact tool names/parameters via `MultiServerMCPClient.get_tools()`
   against each running server. AWS can proceed with higher confidence;
   GCP/Azure adapters wait on this step specifically.
1. Add `TeamMember`/`scope` to `gateway/schemas.py` and the scope-gate
   check — independent of any cloud, testable alone.
2. Add `ResourceRecord` (including `compute_paradigm`) + its table —
   independent of any cloud, testable alone.
3. Add the three MCP server configs to `mcp_server/external_servers.py`.
4. Build `gateway/kubernetes_resource_dispatch.py`'s shared
   `dispatch_and_execute_cluster()` plus the AWS adapter (highest
   confidence tool names).
5. Build the GCP and Azure adapters, once step 0's live verification for
   each is done.
6. Tests: scope gate, `ResourceRecord` writes (including
   `compute_paradigm="kubernetes"`), generate/deploy split, approval
   gate, all three adapters against mocked MCP responses.
7. Manual, real-credential checklist (not automated here) for actually
   creating one real cluster per cloud, for whoever runs this with real
   access.

No cutover step — additive, new capability, nothing existing changes
behavior.

## Open Questions
- Whether `gateway/kubernetes_resource_dispatch.py` and (once built)
  `gateway/dispatch_execution.py` (`wire-dispatch-execution`) should
  converge into one module — flagged in Risks, not designed here.
- Exact GCP/Azure tool parameter shapes — genuinely unknown until
  Migration Plan step 0 runs against live servers.
- Whether `discovered_capabilities` should be populated at creation time
  (K8s version, node count) or left empty until a later discovery sweep
  — not decided, low-stakes either way for this first slice.
- Whether a future VM/managed-container/serverless capability should
  literally share `gateway/schemas.py`'s `ResourceRecord` (filtered by
  `compute_paradigm`) or eventually want its own record type once the
  fields diverge enough — not decided, `docs/compute_paradigm_layering.md`
  leaves this open too.
- **Added same session, still open**: `stack_id`'s real binding
  mechanism. `docs/composable_foundation_blueprints.md` Part H named
  three options (auto-create one Stack per resource / requester-named /
  inferred-from-dependency) and chose none. The shipped code
  (`gateway/kubernetes_resource_dispatch.py`) defaults to auto-creating
  a fresh, standalone `stack_id` when the caller doesn't supply one —
  explicitly flagged in that module's own docstring as a stand-in to
  keep the field non-null, not a considered resolution of this question.
