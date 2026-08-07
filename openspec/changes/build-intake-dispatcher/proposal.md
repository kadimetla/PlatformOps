## Why
`openspec/changes/build-intake-workflow/design.md` deliberately deferred
`resolve_route` as "a follow-up change, once `compliance_check` has a real
wrapper target." That target (`spec/check_compliance.py`, a pure
`check_compliance(spec: dict) -> list[str]` function) already exists and
has since before the classify-only change landed — this is that follow-up.

Grounding against the actual current code (not `docs/INTAKE_HITL_ROUTING.md`'s
full design, which assumes prerequisites this branch doesn't have yet)
found the doc's per-org_bu-policy dispatcher isn't buildable today:
`IntakeRequest` has no `scope` field at all, `gateway/auth/grants.py`
deliberately never mints `ExecutionGrant`s (`GroupGrantMapping`'s validator
raises if `grant_type != "approval"` — provider discovery doesn't exist to
mint them for real), and no `org_bu_policy.yaml`/routing-POLICY YAML data
exists anywhere in the repo. This change ships the same kind of narrow,
genuinely-buildable slice `build-intake-workflow` shipped for
classification: real routing for the one real target, everything
scope/policy/grant-dependent pushed to a further follow-up.

## What Changes
- Add `workflows/intake/nodes.py`'s `resolve_route`: a second graph node,
  deterministic, no model call. A static `Intent -> route` table (not
  scope-keyed — no scope exists to key on) resolves `compliance_check` to
  `route="compliance_check"`, `ready_to_route=True`; `provision`/`inquiry`
  resolve to `unsupported_reason` set, `ready_to_route=False`, since
  neither has a real workflow to route to yet.
- Wire `workflows/intake/graph.py`: `classify_workflow -> resolve_route ->
  END` (two nodes, matching `docs/INTAKE_HITL_ROUTING.md`'s original
  two-node sketch — the reasoning that kept `build-intake-workflow` at one
  node no longer applies now that there's something for a second node to
  do).
- Extend `gateway/schemas.py`'s `IntakeDecision`: `mutation_requested: bool`
  (default `False`), `approval_required: bool` (default `False`, stays
  inert in this change — no real mutating route exists yet to require
  approval for), `unsupported_reason: str | None` (default `None`).
- Surface the new fields through `harness/core.py`'s `PlatformOpsEvent`
  payload — previously `{"intent": ...}` only.
- Explicitly **out of scope for this change**: `Scope` on `IntakeRequest`,
  `POLICY[(org_bu, intent)]` lookup, a `gateway/dispatcher.py` module,
  `actor.execution_grants` gating, and actually invoking
  `spec/check_compliance.py` — `resolve_route` only decides the route;
  intake must not execute the request (per
  `docs/INTAKE_HITL_ROUTING.md`'s "Intake must not execute the request").
  A further follow-up adds real per-scope routing once `IntakeRequest`
  carries scope and a routing-POLICY registry exists.

## Capabilities

### New Capabilities
- `intake-routing`: the deterministic `resolve_route` node — static
  intent-keyed routing, no scope/policy dimension, `compliance_check` the
  only intent that resolves to a real route.

### Modified Capabilities
- `intake-classification` (defined in
  `openspec/changes/build-intake-workflow/specs/intake-classification/spec.md`
  — not yet archived into `openspec/specs/`, so this delta targets that
  change's spec directly as the current baseline): the requirement "This
  change's graph never produces a routable decision" no longer holds
  unconditionally — superseded by `intake-routing`'s requirements for the
  `compliance_check` case.
- `intake-schemas` (same baseline note as above,
  `openspec/changes/build-intake-workflow/specs/intake-schemas/spec.md`):
  `IntakeDecision` gains three fields.

## Impact
- Modified files: `gateway/schemas.py`, `workflows/intake/nodes.py`,
  `workflows/intake/graph.py`, `harness/core.py`.
- Modified tests: `tests/workflows/intake/test_classify_workflow.py`
  (replaces the now-false `test_route_and_ready_to_route_always_inert`
  with per-branch coverage), `tests/harness/test_core.py` (updates two
  hardcoded `event.payload` assertions).
- No new dependencies — reuses `langgraph`/`pydantic`, already declared in
  `pyproject.toml`.
- No changes to `gateway/policy/`, `gateway/auth/`, or any auth/session
  code — this change reads no `ActorSession`/`Scope` data.
