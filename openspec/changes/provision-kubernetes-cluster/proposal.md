## Why
Nothing in this codebase can create a Kubernetes cluster today, on any
cloud. `TeamMember`/`scope` (the field that distinguishes an
infra/foundation-scoped requester from an app-scoped one) doesn't exist
in `gateway/schemas.py`. `FoundationRecord` (what would represent "this
cluster exists, this plan approved it") doesn't exist either. No MCP
server config for AWS's `eks-mcp-server`, GCP's `gke-mcp`, or Azure's
`aks-mcp` exists in `mcp_server/external_servers.py`. This session's
exploration (`docs/composable_foundation_blueprints.md`,
`docs/multi_cloud_foundation_and_iam.md` Part E) worked out the shape of
this flow in detail, including a codex-verified step sequence for the
AWS path and a verified self-hosted launch mechanism for all three
clouds — this proposal is that design's smallest buildable slice: one
person, one cluster, one cloud at a time, approval-gated, real for all
three providers.

**Naming is deliberate**: this is Kubernetes-cluster provisioning
specifically, not "foundation provisioning" generically.
`docs/compute_paradigm_layering.md` already names Kubernetes as one of
**four** compute paradigms (Kubernetes, VM, managed-containers,
serverless) — each with a different-shaped foundation chain (serverless
doesn't even need a network layer by default). Calling this capability
something generic like "foundation-cluster-provisioning" would repeat
the exact conflation that doc already flagged as a recurring mistake in
this project's own prior docs. VM/managed-container/serverless
foundation provisioning are separate, future capabilities with lighter
chains — not covered here, and not assumed to share this capability's
code path.

## What Changes
- Add `TeamMember`/`scope` (`"foundation"` | `"app"` | `"both"`) to
  `gateway/schemas.py`, exactly as already designed in
  `docs/skills_and_workspace_design.md` and
  `docs/infra_discovery_and_platform_app_split.md` — reused, not
  redesigned here.
- Add a gate check: a request to create a Kubernetes cluster is denied
  before skill/tool resolution runs unless the requester's `scope`
  includes `"foundation"`.
- Add `FoundationRecord` to `gateway/schemas.py` and a matching SQLite
  table, same database `BrokeredToolDispatcher` already opens (per
  `docs/config_storage_backend.md`'s established convention), including
  `compute_paradigm: str = "kubernetes"` — a field
  `docs/compute_paradigm_layering.md` Part D already designed for
  exactly this purpose, wired into a concrete schema for the first time
  here. **Scoped down from the canonical multi-layer design**: one
  `FoundationRecord` per cluster for this change, `layer="compute"`,
  bundling network + compute + node/cluster roles as one unit — the
  network/compute/identity decomposition from
  `docs/foundation_layer_decomposition.md` is real design but
  explicitly deferred until a second case actually needs layer reuse
  (matches that doc's own stated principle: extend on a real case, not
  preemptively).
- Add self-hosted MCP server configs for all three clouds to
  `mcp_server/external_servers.py`: AWS `awslabs.eks-mcp-server` (via
  `uvx`, matching the existing pattern exactly), GCP `gke-mcp` and Azure
  `aks-mcp` (Go binaries, same `StdioServerParameters` shape, per
  `docs/multi_cloud_foundation_and_iam.md` Part E's verified launch
  mechanisms).
- Add a generate/deploy split per cloud: template/manifest generation is
  non-mutating (recorded, not gated); the actual cluster-creation call
  is a `ToolIntent`, gated by `BrokeredToolDispatcher.evaluate_intent()`
  exactly like any other mutating action.
- Add one execution module (provider-parameterized, not three unrelated
  ones) that, for an approved `ToolIntent` targeting a Kubernetes
  cluster resource type, calls the right cloud's mutating MCP tool.
- Add execution-outcome tracking (succeeded/failed/denied per attempt),
  and write the resulting `FoundationRecord` on success.

**Explicitly NOT in scope**: VM, managed-container, or serverless
foundation provisioning (separate future capabilities, per the naming
note above); the full `Block`/`Blueprint`/matching-criteria model
(`docs/composable_foundation_blueprints.md` — still exploratory, schema
not committed); the ordered org→BU→account onboarding stages (Stages
A–D from that same doc — this change assumes an org/BU/account already
exist, same assumption `plan_request()` itself already makes);
network/compute/identity layer decomposition; multi-account/multi-region
topology choices; hosted MCP endpoints (self-hosted only this round,
though the connection-config layer is designed to make a later switch a
config change, not a rewrite — `docs/multi_cloud_foundation_and_iam.md`
Part E).

## Capabilities

### New Capabilities
- `kubernetes-cluster-provisioning`: an infra-scoped requester creates a
  single Kubernetes cluster (EKS, GKE, or AKS) through this system,
  gated by the existing deny-by-default approval mechanism, with a
  `FoundationRecord` written on success — parameterized by
  `cloud_provider`, one flow, three execution backends, one compute
  paradigm.

### Modified Capabilities
<!-- None -- gateway/tool_dispatcher.py's evaluate_intent() and
gateway/schemas.py's PlanRecord/ToolIntent are consumed, not changed by
this proposal; this proposal's schema additions (TeamMember, FoundationRecord)
are new fields/tables, not changes to previously-specified requirements. -->

## Impact
- **New code**: `gateway/schemas.py` (`TeamMember`, `FoundationRecord`),
  a new `FoundationRecord` SQLite table, `mcp_server/external_servers.py`
  (three new server configs), a new execution module (exact location
  TBD in design.md), a new scope-gate check ahead of skill/tool
  resolution.
- **Verification required before implementation, per cloud**: live
  `get_tools()` calls against `eks-mcp-server`, `gke-mcp`, and `aks-mcp`
  to confirm exact tool names/parameters — none of the three has been
  connected to in this environment (no AWS/GCP/Azure credentials
  available here).
- **Testing constraint, stated plainly**: this environment cannot create
  a real cluster on any cloud — no live credentials. Implementation here
  means real code plus a real test suite against mocked/fake MCP
  responses (same pattern `tests/test_gateway.py` already uses).
  Live, real-cluster end-to-end testing has to happen wherever real
  cloud credentials exist — outside this environment.
- **Not affected**: `workflows/drafting/` (app-tier drafting), the
  `wire-dispatch-execution` change (a separate, app-tier proposal not
  yet applied) — this change builds its own minimal execution path
  scoped to foundation-tier resources rather than depending on that one
  landing first; the two share the same conceptual shape
  (approve → dispatch → execute → record) and should converge into one
  shared module later, flagged in design.md, not solved here.
