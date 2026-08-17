## Status

Implementation plan. Slices 1-5 and the structural-validation subset of
Slice 7 are represented in code. Runtime execution still stops after routing
to a handler that produces a typed, non-executable provision draft; the
profile registry/loader is not yet called by that graph. No topology compiler,
OpenTofu command, credential acquisition, approval gate, or provider mutation
is enabled. No Cloud Stack Registry/catalog, encrypted release store, or
promotion workflow exists; `PROFILE_REGISTRY` is its compatibility seed.

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
| 9 | Read-only/current-state context plus plan credentials and the local IaC runner (`opentofu_local` first, then `terraform_local` through the same contract) | Fake runner verifies closed engine dispatch, exact command/env boundary, and engine/version sealing; real sandbox smoke tests are opt-in | Pending |
| 10 | Plan JSON policy checks, topology digest, current-state fingerprint, approval request | Deletes/unlisted resources fail; any bound-input drift changes approval digest | Pending |
| 11 | Checkpointed approval, resume revalidation, fresh apply credentials, exact saved-plan apply | Resume cannot self-approve, use stale policy/grants, or modify `plan.bin` | Pending |
| 12 | Independent verification, evidence persistence, reporting, failure taxonomy | Applied resources are read back; partial failure records facts and requires a new plan | Pending |
| 13 | Optional: LangGraph-native free-composition planner (plain `create_agent`/`ToolNode` first, read-only catalog tools, `ToolStrategy(TopologyProposal)`) as an alternative `topology_revision` source alongside Slice 5's reviewed-`topology.yaml` loader; A/B against a stripped Deep Agent only if long-horizon context becomes a measured need | Unknown/forbidden unit proposals fail validation identically to a malformed reviewed profile; final visible tool set contains only reviewed read-only catalog tools; agent never reaches credentials, approval, or apply nodes; disabled by policy until its own acceptance decision; Deep Agent cannot be selected without equal-case measurements for correctness, requirement coverage, repair, calls/tokens/latency, deterministic revision output, and zero extra capability exposure | Pending, not a dependency of 5-12 — Pi/Node and Pydantic AI Harness rejected; Deep Agents conditionally retained because it shares LangGraph but is not yet justified for this bounded loop; see `COMPOSABLE_PROVISIONER.md` |
| 14 | Optional, after 13: resource-primitive authoring — per-provider resource registries (exact discriminated config schemas + reviewed renderers), immutable `TopologyRevision` chain, coding-agent architecture review plus compose/repair loop bounded at 2 automatic rounds, revision-scoped unit/artifact state, and seal/supersede lifecycle; Deep Agents is a separately accepted runtime implementation option | Unknown resource types and out-of-schema configurations fail closed; LLM output is typed resource data only, never HCL; every changed node/edge/config creates a successor revision and atomically invalidates compiled results/artifact/plan/policy/approval; a runtime Deep Agent has no filesystem/shell/default subagent/skills/memory/store/checkpointer and exposes only scoped read-only tools; approval binds one exact revision | Pending, strictest checks of any runtime composition level; see `COMPOSABLE_PROVISIONER.md`'s Deep Agents, resource-authoring, and fluid-lifecycle sections |
| 15 | Optional authoring-time track, after the module/renderer contract from Slices 6 and 8 is stable: isolated Deep Agent authors a new reviewed module/renderer plus contract tests, runs formatting, `tofu validate`, pytest, and deterministic compliance checks, then exports a patch or PR artifact | Sandbox receives no cloud credentials; only trusted reviewed skills/contracts are mounted; agent cannot merge, push, approve, publish, or apply; merge only makes output eligible for Slice 16 validation/signing/encryption and scoped publication—it does not enter the Cloud Stack Registry automatically; acceptance is independent of runtime Deep Agent decisions in Slices 13/14 | Pending, not a runtime workflow slice or dependency of Slices 13/14 — may be accepted even if both runtime evaluations reject Deep Agents; see `COMPOSABLE_PROVISIONER.md`'s "Offline use — Slice 15" and `PROVISION_WORKFLOW.md`'s Level 2 contract |
| 16 | Cloud Stack Registry/catalog track: adapt the real `PROFILE_REGISTRY` behind exact release lookup first; then immutable encrypted/signed artifacts, scoped publication (`org_bu`/organization before sector/global), promotion approval/evidence, full-text discovery, and only evaluation-justified semantic reranking | Existing `aws-static-web` selection is unchanged through the adapter; unauthorized releases never appear in results/counts; exact version/content/publication digests bind approval; revocation wins over a stale index; two workspaces reuse one release but always receive different fresh state-bound provider plans | Pending, independent of runtime composition Slices 13/14/15; structured lookup can land after Slice 5 and before full promotion infrastructure — canonical contract is `CLOUD_STACK_CATALOG.md` |

## Next implementation flow — contract-first vertical path

**Captured 2026-08-16 from a code-level trace.** The live route currently
ends at `ProvisionDraft`; the topology loader/validator exists but is not a
graph node. This section makes the next handoffs implementable without
pretending the designed downstream models already exist.

### Activation rule

Keep `ROUTE_REGISTRY["provision"]` pointed at the existing
`prepare_provision_request` behavior while Slices 6-12 are built. New code is
invoked through focused tests and an internal `build_provision_workflow`
entry point. Do not switch the public route from `ROUTE_RESOLVED` to a live
provision run until all of these are real together:

1. a durable parent-graph checkpointer;
2. deterministic plan policy checks;
3. persisted approval requests/records and authorized resume;
4. saved-plan digest revalidation plus fresh apply credentials; and
5. independent evidence persistence.

This avoids exposing a half-built route that can plan or mutate but cannot
pause, recover, revalidate, or prove what happened. It also keeps
`prepare_provision_request` as the tested clarification/preflight boundary;
the full workflow may reuse its nodes without changing its current public
return type.

### Canonical handoff ledger

| Stage | Input | Output | Status / owner |
|---|---|---|---|
| HTTP/harness | `ActorSession`, `request_id`, raw text, optional `ScopeHint` | `HITLEvent | PlatformOpsEvent` | Real; transport/harness |
| Intake/dispatch | `IntakeRequest` plus trusted route/policy tables | `IntakeDecision`, then `ProvisionInvocation` | Real; intake + harness |
| Provision preflight | `ProvisionInvocation`, model, known workspaces, `ExecutionGrant` list | `ProvisionDraft` containing resolved scope/profile/typed application request or one fail-closed outcome | Real; `prepare_provision_request` |
| Cloud Stack resolution | ready draft plus trusted org/BU/sector/provider/workspace and policy context | exact authorized `CloudStackPublicationRef` containing its immutable release; current `ProfileRegistration` adapter supplies the seed publication/release | Slice 16 contract; fixed parent only, structured lookup before semantic reranking |
| Trusted planning context | ready `ProvisionDraft` plus registry/auth/publication snapshots | `PlanningContext(run_id, scope, workspace, auth_context, cloud_stack_publication, application_request)` | New prerequisite; fixed parent only |
| Release topology | verified/decrypted release topology payload | request-local `TopologyRevision` plus `ValidatedTopology` | Loader/validator partly real; release adapter and revision wrapper/node new |
| Unit planning | current revision, validated topology, planning-only unit registry, fresh child state | `CandidateArtifacts(revision_id, unit_results)` | Slice 6-7 |
| Composition | current revision plus complete unit results | canonical `DeploymentPlan(revision_id, topology_digest, cloud_stack_publication, scope, resources, dependency_order, template_digests)` | Slice 7; designed, normalized here |
| Rendering | deployment plan plus reviewed registered modules | `RenderedArtifact` with controlled root path, per-file digests, and aggregate artifact digest | Slice 8 |
| Provider plan | rendered artifact, trusted workspace/toolchain context, least-privilege plan-phase access | closed `PlanResult`: local saved-plan result, HCP remote-run result, or CCAPI operation-set result; every branch supplies normalized changes/digests and no credential material | Slice 9 for local MVP; HCP/CCAPI adapters later |
| Policy + seal | current revision, deployment/artifact/plan digests, normalized changes, policy/allow-list snapshots | `PolicyResult`; on pass, immutable `SealedPlan` | Slice 10 |
| Approval | sealed plan, requester, current approval policy | extended `ApprovalRequest` and immutable `ApprovalRecord` values | Schema partly real; gate/store/resume are Slice 11 |
| Apply | approved sealed plan, resume-time revalidation, fresh apply credential | `ExecutionResult` for exactly the sealed local plan, HCP run, or CCAPI operation set | Slice 11; new contract |
| Verify/evidence | execution result, registered verifiers, immutable bound inputs | `VerificationResult` and persisted `ExecutionRecord` | Slice 12; new contracts |

`Scope` remains the user-visible target identifier. It is not sufficient
provider context for rendering or plan validation. `PlanningContext.workspace`
must be resolved from a trusted workspace registry and minimally pins provider,
provider account/subscription/project, region, state-backend coordinates, and
execution-identity references. It contains references and snapshots, never
credentials. Do not add those fields to `Scope` or ask the model to supply
them.

Cloud Stack discovery is not provider planning. The reusable release contributes
reviewed topology, schemas, module digests, and static certification; the target
still gets a fresh `CloudStackDeployment`, current-state read, `DeploymentPlan`,
provider `PlanResult`, approval, and evidence. Visibility and exact version are
resolved deterministically. No LLM-supplied organization, BU, sector,
publication scope, key reference, artifact reference, or version override is
accepted.

The workspace also pins one canonical toolchain—`ccapi`, `hcp_terraform`,
`opentofu_local`, or `terraform_local`. The two local values share one runner
protocol but have different sealed engine/version/state-owner identities.
Missing binaries, version mismatch, or state-owner mismatch fail closed; no
runtime fallback selects another toolchain. HCP and CCAPI retain their own
remote/API plan-result adapters and never receive a `LocalEngineIdentity`.

The fixed parent consumes a closed plan-result union rather than assuming
every toolchain has `plan.bin`:

```python
PlanResult = Annotated[
    LocalPlanResult | HcpTerraformPlanResult | CcapiPlanResult,
    Field(discriminator="toolchain"),
]
```

- `LocalPlanResult` carries controlled local paths/digests plus exact sealed
  engine identity. It is produced by either local adapter.
- `HcpTerraformPlanResult` carries trusted HCP workspace/run IDs, HCP plan
  status, normalized plan JSON/digest, and resolved HCP toolchain identity;
  provider credentials and local plan paths are absent.
- `CcapiPlanResult` carries PlatformOps's deterministic desired-vs-current
  operation list/snapshot digest and adapter identity. CCAPI's native dry-run
  gap remains verify-before-build; do not fake `plan.bin` semantics for it.

`validate_plan`, sealing, approval, execution, and evidence consume the union
through toolchain-specific adapters plus shared normalized `PlanChange`
values. Only the local branch executes a saved binary plan; HCP applies the
exact approved remote run, while CCAPI executes the exact approved operation
set. None may reinterpret another branch's artifact.

### Contract normalization before new graph nodes

The design previously defined `DeploymentPlan` twice. The canonical shape is
now the Step 8 shape in `COMPOSABLE_PROVISIONER.md`, corrected to carry
`resources: list[ResourceIntent]`, `revision_id`, `scope`, and an exact
`CloudStackPublicationRef` containing the exact release and authorized
publication. It does not
carry `units` (those remain revision-local `unit_results`) or
`policy_snapshot` (that is produced later by deterministic plan validation).

The first implementation should introduce only the concrete AWS-static-web
members needed now:

- exact input/output models for `aws.s3.private_bucket`,
  `aws.cloudfront.s3_distribution`, and
  `aws.s3.cloudfront_oac_policy`;
- a closed/discriminated `ResourceIntent` union for the resource intents
  those three units may emit;
- `RegisteredUnit`/`UnitRegistry`, rejecting duplicate IDs at startup and
  containing no credential, approval, executor, or evidence callable; and
- `TopologyRevision`, `CandidateArtifacts`, `DeploymentPlan`,
  `RenderedArtifact`, `LocalPlanResult`, `PolicyResult`, and `SealedPlan`
  only as the slice that first produces them lands.

Do not introduce `dict[str, Any]`, a generic provider-resource bag, or the
future Azure/GCP/resource-primitive unions in this path. Slices 13/14 extend
the closed unions only after the reviewed AWS path works.

### Incremental pull-request sequence

#### A. Trusted context and registry foundation — Slice 6

1. Resolve a `WorkspaceContext` after `ProvisionDraft.ready`, using trusted
   registry data and the already-resolved execution grant; fail with the same
   non-enumerating public result for absent/unauthorized targets.
2. Add the three exact unit registrations and input/output contracts.
3. Extend `validate_topology` from its current structural checks to verify
   profile membership, request/workspace field names, upstream output names,
   backing dependency edges, and exact unit input types.
4. Keep validation deterministic. A malformed reviewed profile is a repository
   defect and never enters an LLM repair loop.

Acceptance: malformed bindings, wrong output names, wrong provider/profile,
forbidden unit categories, duplicate registrations, and missing backing edges
all fail before any unit planner runs.

#### B. Revision handoff and stateless topology execution — Slice 7

1. Add `load_topology_revision(PlanningContext) -> TopologyRevision`; calculate
   its digest from normalized topology, exact Cloud Stack release/content/
   publication identity, unit versions, and template digests. The current
   profile adapter must produce that release reference before this node.
2. Compile only the validated DAG. Use one LangGraph list edge for joins so
   `origin_policy` runs once after both unequal-depth predecessors.
3. Invoke every revision with fresh `TopologyRunState(unit_results={})`; never
   merge results across revision IDs.
4. Require every expected unit to return one value validated by its registered
   output model. Convert conflicting/missing/extra results into a hard planning
   failure.
5. Persist a `TopologyExecutionRecord` before provider planning; no credentials
   are introduced in this slice.

Acceptance: the reviewed static-site topology runs `assets -> cdn` and
`[assets, cdn] -> origin_policy`, the join runs exactly once, and changing or
removing a unit creates a replacement candidate with no stale result leakage.

#### C. Canonical plan composition and deterministic rendering — Slice 8

1. `compose_plan` converts typed unit results into the one canonical
   `DeploymentPlan`; it does not render HCL and does not attach policy results.
2. Render one request-scoped root module containing only module blocks whose
   sources resolve from registrations. Never accept a module path or HCL body
   from model output.
3. Hash every reviewed source/template plus every emitted file and bind the
   aggregate artifact digest to the current revision.
4. Reject path escape, undeclared variables/outputs, credential-shaped values,
   unexplained files, and a revision/digest mismatch.

Acceptance: golden root-module output wires bucket and distribution outputs
into the OAC-policy module, contains no raw model-authored resource block or
secret, and changes digest whenever topology/template/rendered content changes.

#### D. Local IaC runner and saved-plan contract — Slice 9

1. Introduce a subprocess-runner protocol and fake runner before invoking a
   real binary. Its closed adapters are `opentofu_local -> tofu` and
   `terraform_local -> terraform`; pin and probe each supported version and
   required command set. OpenTofu lands first, Terraform reuses the same
   lifecycle rather than adding a second graph.
2. Render credential-free backend configuration; pass short-lived credentials
   through the process environment only and redact runner output.
3. Run the selected engine's `init`, `validate`, `plan -out=plan.bin`, then
   `show -json plan.bin` in a controlled request directory. Hash `plan.bin`
   immediately and treat it as immutable and potentially sensitive.
4. Normalize plan JSON into typed `PlanChange` values; store paths/digests and
   state fingerprints, never credentials, in `LocalPlanResult`. Seal the exact
   toolchain, engine, version, platform, dependency-lock digest, backend digest,
   and rendered-artifact digest with it.

Acceptance: fake-runner tests prove exact argv/environment/redaction and that
credentials never enter graph state, backend files, logs, plan metadata, or
events. A real sandbox smoke test remains opt-in.

**Blocking policy decision before D is enabled:** both local adapters use the
reviewed S3 lockfile backend, which needs
`s3:PutObject/DeleteObject`. That is an external coordination mutation before
the human can approve the plan, while root `AGENTS.md` currently says a
mutating action requires recorded approval. Do not silently grant those writes.
Maintainers must explicitly select and document one of: (a) classify the
bounded lock lease as an allow-listed plan operation under a recorded
preauthorization, and amend the root rule; (b) initially plan with
`-lock=false` plus before/after state fingerprint checks and reject concurrent
change; or (c) add a separate pre-plan approval. The saved-plan approval cannot
itself authorize a lock required to create that same plan.

#### E. Deterministic plan policy and sealing — Slice 10

1. Map every `PlanChange` address to exactly one registered unit and allowed
   resource declaration.
2. Check action allow-lists (delete absent by default), provider target,
   account/region, public-access/OAC invariants, and unexplained resources.
3. Produce a `PolicyResult` containing stable violation codes,
   `policy_snapshot_digest`, and `allow_list_version`.
4. Create `SealedPlan` only on pass, binding revision, topology, rendered
   artifact, saved plan, policy, state fingerprint, workspace, and execution-
   identity snapshots plus `toolchain_identity_digest`. Any successor revision,
   local engine/version/platform change, or adapter-config change invalidates
   the whole bundle.

Acceptance: forbidden/delete/unmapped/cross-account plans never reach approval;
changing any bound input produces a different approval digest.

#### F. Approval pause and authorized resume — Slice 11A

1. Extend the real `ApprovalRequest` schema with sealed topology revision,
   topology digest, and rendered-artifact digest fields; keep existing field
   names used by AG-UI.
2. Implement request/decision stores and current-grant authorization before the
   checkpointed gate. Request creation is a separate idempotent node; the
   self-looping `interrupt()` node only consumes validated decisions.
3. Add `resume_approval` to the harness and the existing `POST /runs` resume
   path. Derive approver identity from the authenticated session, never input.
4. Supersede rather than edit approval requests after any topology/artifact/
   plan change.

Acceptance: requester self-approval, duplicate approval, stale/expired/
superseded digest, insufficient current grant, and cross-scope approval all
fail; a two-person quorum creates one request and two immutable records.

#### G. Exact saved-plan apply — Slice 11B

1. On resume, recompute every sealed digest/snapshot and the current-state
   fingerprint before acquiring an apply credential.
2. Acquire a fresh, scope-bound apply credential only after approval succeeds.
3. Execute exactly `<same sealed engine identity/version> apply plan.bin`;
   never re-render, re-plan, cross-engine apply, or fall back to an available
   binary in the apply node. Discard the credential immediately.
4. Record typed `ExecutionResult` fields: revision/plan digests, execution-
   identity reference, timestamps/status, changed resource addresses, outputs,
   and failure classification—never token material.

Acceptance: modified plan, drift, revoked grant, changed identity/policy,
expired approval, or failed credential acquisition prevents all provider
mutation.

#### H. Independent verification, evidence, and route activation — Slice 12

1. Invoke registered read-only verifiers against declared resources and
   immutable workspace context; do not treat OpenTofu exit zero as verification.
2. Persist one durable `ExecutionRecord` linking request, actor/scope, topology
   and template versions, all digests, approval records, execution identity,
   resource results, verification, and failure taxonomy.
3. Emit transport events from persisted run state, not ad-hoc executor output.
4. Only now switch the registered provision handler to start/resume the durable
   parent workflow. Preserve the existing preflight clarification behavior.

Acceptance: success and partial failure both leave immutable evidence; a live
route cannot apply without the exact persisted approval and cannot report
success when independent verification fails.

### Fixed parent graph after activation

```text
resolve_scope -> resolve_context -> search_and_resolve_cloud_stack
  -> extract_stack_request -> decrypt_verify_release
  -> load_topology_revision -> run_topology
  -> compose_plan -> render_iac -> dispatch_plan_by_toolchain
  -> validate_plan -> seal_plan
  -> create_approval_request -> approval_gate (interrupt/quorum)
  -> resume_revalidate -> dispatch_apply_by_toolchain
  -> verify -> persist_evidence -> report -> END
```

Only `run_topology` invokes a per-revision dynamic subgraph. Context,
credentials, policy, sealing, approval, apply, verification, evidence, and
reporting remain fixed parent nodes and are structurally absent from the unit
registry.

## Slice 1 contract

`ScopeHint` is structured transport input (`org:bu/project/workspace` in the
CLI), not text extracted by an LLM and not mutable `ActorSession` state. The
resolver checks both registry presence and a non-`none` provider-derived
execution grant. It intentionally does not expose which half failed.

The in-memory list of known `Scope` values is a testable seam, not the final
workspace registry schema. Workspace-registry resolution replaces that seam
without changing scope-resolution behavior. Slice 5's profile registry remains
the Cloud Stack compatibility adapter until Slice 16 replaces lookup behind the
same fail-closed boundary.

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
[CLOUD_STACK_CATALOG.md](CLOUD_STACK_CATALOG.md) owns reusable release lookup,
visibility, encryption, promotion, and the release-versus-execution-plan
boundary.
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md) owns plan/apply semantics and
[APPROVAL_GATE.md](APPROVAL_GATE.md) owns the checkpointed mutation gate. This
document only orders those designs into testable implementation slices.
