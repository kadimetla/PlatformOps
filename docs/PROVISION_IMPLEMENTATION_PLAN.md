## Status

Implementation plan. Slices 1-5 and the structural-validation subset of
Slice 7 are represented in code. Runtime execution still stops after routing
to a handler that produces a typed, non-executable provision draft; the
profile registry/loader is not yet called by that graph. No topology compiler,
OpenTofu command, credential acquisition, approval gate, or provider mutation
is enabled.

## Delivery rule

Each slice must be independently testable and must leave the system fail-
closed. A provision route is added only after its handler exists and all
authorization checks before its first externally visible output are real.
Cloud credentials are introduced only with the plan/apply nodes that consume
them, never earlier.

## Incremental slices

| Slice | Build | Acceptance test | Status |
|---|---|---|---|
| 1 | `TenantRef`, `ScopeHint`, canonical scope parser, deterministic resolver against known workspaces and provider-derived execution grants | Exact authorized scope resolves; missing scope clarifies; unknown and unauthorized return the same public result | Implemented |
| 2 | Carry optional `ScopeHint` in per-run harness input and preserve it across intake clarification; add CLI `--scope` parsing | Two simultaneous calls can carry different hints; clarification cannot replace the original hint | Implemented for in-memory harness/CLI parsing; no durable run context |
| 3 | Minimal `workflows/provision/` graph: resolve scope, select one reviewed profile, extract its typed request, then stop | Static-web request becomes `AwsStaticWebProvisionRequest`; unresolved scope stops before the model; no provider/tool execution exists | Implemented |
| 4 | Register the provision handler and add deterministic dispatcher wiring | Intake routes provision only when a handler is registered; unsupported behavior remains unchanged otherwise | Implemented (`gateway/dispatcher.py`, `harness/core.py`) -- tenant-policy gate + `ROUTE_REGISTRY` fixture-backed pending Phase 2's real workspace registry; discovered a real cost while testing: resuming a provision clarification reruns the whole graph from `resolve_scope`, so `select_profile` is called again too, not just the node that asked |
| 5 | Trusted profile registry plus reviewed `topology.yaml` loader | Unknown profile/path fails closed; model can select only registered IDs | Implemented (`workflows/provision/profiles.py`, reviewed `aws-static-web/topology.yaml`, loader tests); not invoked by the request-preparation graph yet |
| 6 | Typed unit contracts and planning-only unit registry | Duplicate/unknown unit IDs and execution-capable registrations fail validation | Pending |
| 7 | Deterministic topology validator/compiler and first S3/CloudFront/OAC planning units | DAG joins run once; output bindings validate; no unit calls a provider | Partial: `TopologySpec` plus duplicate/unknown/self-edge/cycle structural validation and tests are implemented; exact binding contracts, compiler, registry, and planning units remain pending |
| 8 | Deterministic OpenTofu renderer from reviewed modules | Golden artifacts contain expected module blocks and no secrets | Pending |
| 9 | Read-only/current-state context plus plan credentials and `tofu init/validate/plan` | Fake runner verifies command/env boundary; real sandbox smoke test is opt-in | Pending |
| 10 | Plan JSON policy checks, topology digest, current-state fingerprint, approval request | Deletes/unlisted resources fail; any bound-input drift changes approval digest | Pending |
| 11 | Checkpointed approval, resume revalidation, fresh apply credentials, exact saved-plan apply | Resume cannot self-approve, use stale policy/grants, or modify `plan.bin` | Pending |
| 12 | Independent verification, evidence persistence, reporting, failure taxonomy | Applied resources are read back; partial failure records facts and requires a new plan | Pending |
| 13 | Optional: LangGraph-native free-composition planner (plain `create_agent`/`ToolNode` first, read-only catalog tools, `ToolStrategy(TopologyProposal)`) as an alternative `topology_revision` source alongside Slice 5's reviewed-`topology.yaml` loader; A/B against a stripped Deep Agent only if long-horizon context becomes a measured need | Unknown/forbidden unit proposals fail validation identically to a malformed reviewed profile; final visible tool set contains only reviewed read-only catalog tools; agent never reaches credentials, approval, or apply nodes; disabled by policy until its own acceptance decision; Deep Agent cannot be selected without equal-case measurements for correctness, requirement coverage, repair, calls/tokens/latency, deterministic revision output, and zero extra capability exposure | Pending, not a dependency of 5-12 — Pi/Node and Pydantic AI Harness rejected; Deep Agents conditionally retained because it shares LangGraph but is not yet justified for this bounded loop; see `COMPOSABLE_PROVISIONER.md` |
| 14 | Optional, after 13: resource-primitive authoring — per-provider resource registries (exact discriminated config schemas + reviewed renderers), immutable `TopologyRevision` chain, coding-agent architecture review plus compose/repair loop bounded at 2 automatic rounds, revision-scoped unit/artifact state, and seal/supersede lifecycle; Deep Agents is a separately accepted runtime implementation option | Unknown resource types and out-of-schema configurations fail closed; LLM output is typed resource data only, never HCL; every changed node/edge/config creates a successor revision and atomically invalidates compiled results/artifact/plan/policy/approval; a runtime Deep Agent has no filesystem/shell/default subagent/skills/memory/store/checkpointer and exposes only scoped read-only tools; approval binds one exact revision | Pending, strictest checks of any runtime composition level; see `COMPOSABLE_PROVISIONER.md`'s Deep Agents, resource-authoring, and fluid-lifecycle sections |
| 15 | Optional authoring-time track, after the module/renderer contract from Slices 6 and 8 is stable: isolated Deep Agent authors a new reviewed module/renderer plus contract tests, runs formatting, `tofu validate`, pytest, and deterministic compliance checks, then exports a patch or PR artifact | Sandbox receives no cloud credentials; only trusted reviewed skills/contracts are mounted; agent cannot merge, push, approve, or apply; generated output cannot enter a runtime registry until normal human review and merge; acceptance is independent of runtime Deep Agent decisions in Slices 13/14 | Pending, not a runtime workflow slice or dependency of Slices 13/14 — may be accepted even if both runtime evaluations reject Deep Agents; see `COMPOSABLE_PROVISIONER.md`'s "Offline use — Slice 15" and `PROVISION_WORKFLOW.md`'s Level 2 contract |

## Slice 1 contract

`ScopeHint` is structured transport input (`org:bu/project/workspace` in the
CLI), not text extracted by an LLM and not mutable `ActorSession` state. The
resolver checks both registry presence and a non-`none` provider-derived
execution grant. It intentionally does not expose which half failed.

The in-memory list of known `Scope` values is a testable seam, not the final
workspace registry schema. Slice 5 replaces its caller with the trusted
profile/workspace registries without changing scope-resolution behavior.

## Slice 3 boundary

The first graph returns only:

```text
resolved Scope
+ reviewed profile ID
+ validated AwsStaticWebProvisionRequest
= ProvisionDraft
```

The model may emit structured calls for profile selection and field
extraction. It cannot provide scope, topology units, edges, account/role IDs,
credentials, or IaC. The graph has no node capable of rendering or applying
infrastructure, and intake continues to report provision as unsupported until
Slice 4.

## Verification cadence

Run focused tests after each slice, then the full suite. Slices 8-12 also need
command-boundary tests with a fake process runner before any opt-in cloud
integration test. Real AWS/Azure/GCP tests use dedicated sandbox workspaces,
short-lived credentials, explicit budgets, and teardown evidence; they never
run in the default test suite.

## How this relates to the existing docs

[COMPOSABLE_PROVISIONER.md](COMPOSABLE_PROVISIONER.md) defines the target
graph-as-data architecture. [APPLICATION_PROVISIONING.md](APPLICATION_PROVISIONING.md)
defines the first AWS static-web and Kubernetes application contracts.
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md) owns plan/apply semantics and
[APPROVAL_GATE.md](APPROVAL_GATE.md) owns the checkpointed mutation gate. This
document only orders those designs into testable implementation slices.
