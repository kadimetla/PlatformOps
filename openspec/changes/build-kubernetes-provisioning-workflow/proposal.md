## Why
`provision-kubernetes-cluster` built one real, tested, working piece —
`gateway/kubernetes_resource_dispatch.py`'s `dispatch_and_execute_cluster()`
(approval gate, three cloud adapters, `ResourceRecord` write) — but
nothing calls it except a manual test script that hand-constructs a
`PlanRecord`/`ToolIntent` with every field already known via CLI flags.
There is no workflow that takes "provision a Kubernetes cluster" from
an intake-resolved intent through to that dispatch call. This session's
exploration traced the full gap precisely, grounded in the actual code
at each step (not assumed), across several turns that kept surfacing
new detail — this proposal is the single consolidated flow to build
toward, chosen because it's the one case with a real, tested execution
target already sitting at the end of it.

**Corrects a wrong premise from `route-intake-by-persona-scope`**: that
change assumed bundle/scope resolution belongs inside intake's own
graph. Grounding `plan_request()`/`inquiry_request()` directly showed
both already take `WorkspaceBundle` as a parameter at their own
boundary, never intake's — this proposal places resolution there
instead, where the codebase's own established convention already puts
it.

## What Changes
- Add a Kubernetes-cluster provisioning workflow package
  (`workflows/provision_kubernetes_cluster/` or similar — exact
  location TBD in design.md) with its own entry point, parallel to
  `plan_request()`/`inquiry_request()`'s existing shape: a
  caller-constructed request + `WorkspaceBundle` in, a result out.
- At that workflow's entry: resolve `TeamMember.scope` for the
  requesting `channel_user_id` against the supplied bundle, and deny
  immediately (before any skill/LLM cost) if `scope` isn't `"stack"`/`"both"`
  — this is `gateway/scope_gate.py`'s `requester_has_stack_scope()`
  finally getting a real caller, unchanged itself.
- Add a `collect` phase: resolve which cloud provider, then which
  fields that cloud's cluster creation genuinely requires, then loop
  with the human (via LangGraph's `interrupt()`/`Command(resume=...)` —
  confirmed installed and importable, `langgraph==1.2.9`, currently
  unused anywhere in this repo) until everything required is gathered.
  Field lists per cloud come from EKS/GKE/AKS skills authored as
  procedural memory (same shape as `skills/provision-infra`'s
  `main.tf`/declared-variables mechanism) — **blocked on
  `provision-kubernetes-cluster/tasks.md` Task 1's live `get_tools()`
  verification**, not invented here from training-data recall.
- Wire the collected fields into a `ToolIntent` matching
  `dispatch_and_execute_cluster()`'s existing expectations, and call it
  — this function itself is unchanged.

**Explicitly NOT in scope** (each a real, separately-scoped gap
surfaced during exploration, not solved here):
- Fixing `check_structured_match()`'s spec-shape mismatch or the
  permanently-`"provisional"` skill-promotion wiring gap
  (`SkillUsageStore.record_skill_usage()` has zero production callers)
  — both real, both apply to the generic `provision_stack` path, and
  neither blocks this flow if the new EKS/GKE/AKS skills go through a
  parallel, correctly-shaped matching path rather than reusing the
  buggy one as-is. Flagged for a separate change.
- Episodic memory capture (`memory/YYYY-MM-DD.md`,
  `docs/harness_memory_design.md` — design only, zero code today).
- Live cloud-credential verification (same constraint every prior
  Kubernetes-cluster proposal in this repo has stated).
- Generalizing this shape to `inquiry`/a future `audit` workflow — the
  common `classify → collect → plan → execute` template this session
  identified is real, but this change builds one concrete instance of
  it, not the abstraction.

## Capabilities

### New Capabilities
- `kubernetes-cluster-provisioning-workflow`: an infra-scoped requester
  provisions a Kubernetes cluster (EKS/GKE/AKS) through a real,
  interactive collection flow — cloud provider and cloud-specific
  required fields resolved via skills-as-procedural-memory and a
  genuine HITL loop — feeding into the already-built, approval-gated
  `dispatch_and_execute_cluster()`.

### Modified Capabilities
<!-- None. dispatch_and_execute_cluster(), ResourceRecord, ScopeGate,
the three MCP server configs -- all consumed as-is, not changed. -->

## Impact
- **New code**: a new workflow package (LangGraph state/nodes/graph,
  mirroring `workflows/provision_stack/`'s and `workflows/inquiry/`'s
  existing shape), new EKS/GKE/AKS skills under `skills/` (blocked on
  live field verification), an entry function analogous to
  `plan_request()`/`inquiry_request()`.
- **Reused, unchanged**: `dispatch_and_execute_cluster()`,
  `ClusterDispatchResult`, `ResourceStore`/`ResourceRecord`,
  `requester_has_stack_scope()`, the three MCP server configs.
- **Supersedes**: `openspec/changes/route-intake-by-persona-scope/`
  (see that change's corrected design.md).
- **Not affected**: `workflows/intake/` (stays exactly as shipped —
  verb classification only), `workflows/provision_stack/` (app-tier,
  separate, its own real bugs tracked separately).
