## Status

Implementation plan. Slices 1-3 are now represented in code; they stop
after producing a typed, non-executable provision draft. No intake route,
topology compiler, OpenTofu command, credential acquisition, approval gate,
or provider mutation is enabled by this slice.

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
| 4 | Register the provision handler and add deterministic dispatcher wiring | Intake routes provision only when a handler is registered; unsupported behavior remains unchanged otherwise | Pending |
| 5 | Trusted profile registry plus reviewed `topology.yaml` loader | Unknown profile/path fails closed; model can select only registered IDs | Pending |
| 6 | Typed unit contracts and planning-only unit registry | Duplicate/unknown unit IDs and execution-capable registrations fail validation | Pending |
| 7 | Deterministic topology validator/compiler and first S3/CloudFront/OAC planning units | DAG joins run once; output bindings validate; no unit calls a provider | Pending |
| 8 | Deterministic OpenTofu renderer from reviewed modules | Golden artifacts contain expected module blocks and no secrets | Pending |
| 9 | Read-only/current-state context plus plan credentials and `tofu init/validate/plan` | Fake runner verifies command/env boundary; real sandbox smoke test is opt-in | Pending |
| 10 | Plan JSON policy checks, topology digest, current-state fingerprint, approval request | Deletes/unlisted resources fail; any bound-input drift changes approval digest | Pending |
| 11 | Checkpointed approval, resume revalidation, fresh apply credentials, exact saved-plan apply | Resume cannot self-approve, use stale policy/grants, or modify `plan.bin` | Pending |
| 12 | Independent verification, evidence persistence, reporting, failure taxonomy | Applied resources are read back; partial failure records facts and requires a new plan | Pending |

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
