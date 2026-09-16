## Why
`openspec/changes/build-intake-dispatcher/` shipped `resolve_route` with
`approval_required` hardcoded `False` for every outcome, since at the time
no route in the graph required approval (`compliance_check` is read-only;
`provision` wasn't routable yet). That second condition no longer holds:
this branch's provisioning slices since registered a real `provision`
route (`gateway/dispatcher.py`'s `ROUTE_REGISTRY`, dispatching to
`workflows.provision.graph.prepare_provision_request`) without ever
revisiting `approval_required` — so `IntakeDecision.approval_required` and
every `ROUTE_RESOLVED` event `harness/core.py` emits for `provision`
report `False` for a route that mutates infra, identical to how
`compliance_check` (read-only) is reported. That's the same
"blank field indistinguishable from a real answer" problem
`build-intake-dispatcher/design.md` already named for `unsupported_reason`
— except here the wrong value is a positive claim ("no approval needed")
rather than an absent one.

## What Changes
- `workflows/intake/nodes.py`'s `resolve_route`: when a route resolves,
  set `approval_required = (intent == Intent.PROVISION)` instead of the
  hardcoded `False` — the same derivation already used for
  `mutation_requested`, keyed off the one real signal this node has.
  `compliance_check` keeps `approval_required = False` (still read-only).
- `harness/core.py`'s `_dispatch_provision`: both `ROUTE_RESOLVED` event
  payloads it builds (the `unavailable_reason` branch and the success
  branch) hardcoded `"approval_required": False`; both now report `True`,
  matching `resolve_route`'s value for `provision` (`_route_resolved_event`
  already read `decision.approval_required` dynamically and needed no
  change).
- Docs: `gateway/schemas.py`'s `IntakeDecision` docstring and
  `docs/INTAKE_HITL_ROUTING.md`'s Status line and "Dispatcher"/"Mutation
  approval" rows corrected — they described the dispatcher as
  `compliance_check`-only and mutation approval as wholly unimplemented,
  both stale since this branch's provisioning slices landed.

## Explicitly out of scope
- No approve-or-execute step. `approval_required = True` is a reported
  fact, not an enforced gate — there is still no `resume_approval`,
  checkpointer, or plan/apply node anywhere in `workflows/provision/` or
  `harness/core.py`. A request this change marks `approval_required=True`
  is dispatched and reported exactly as before; nothing new blocks it, and
  nothing new can un-block it either, since neither mechanism exists.
  Building that gate is a further follow-up once a real approval
  resume-mode exists (`harness/core.py`'s own docstring already flags
  this: "approval resume ... needs a real LangGraph checkpointer behind
  the provision workflow's plan/apply nodes, which don't exist yet").
- No changes to `gateway/dispatcher.py`'s `ROUTE_REGISTRY`,
  `check_tenant_policy`, or `KNOWN_WORKSPACES` — those are this branch's
  existing provisioning-dispatch fixtures, untouched here.
- No changes to `inquiry`'s behavior — it has no route table entry and
  stays `unsupported_reason`-marked exactly as before.

## Capabilities

### Modified Capabilities
- `intake-routing` (`openspec/changes/build-intake-dispatcher/specs/intake-routing/spec.md`):
  the requirement "approval_required stays inert" is replaced —
  `approval_required` now reflects whether the resolved route mutates
  infra (`True` for `provision`, `False` for `compliance_check`).

## Impact
- Modified files: `workflows/intake/nodes.py`, `harness/core.py`,
  `gateway/schemas.py` (docstring only).
- Modified tests: `tests/workflows/intake/test_classify_workflow.py`
  (`test_provision_resolves_a_route_at_the_intake_graph_level` renamed to
  `test_provision_resolves_a_real_route_gated_by_approval` with an
  `approval_required is True` assertion added; `approval_required is
  False` assertion added to the `inquiry` unsupported test for explicit
  regression coverage), `tests/harness/test_core.py` (four
  `approval_required` payload assertions updated for `provision`;
  `compliance_check`'s stays `False`, unchanged).
- Docs: `docs/INTAKE_HITL_ROUTING.md`.
- No new dependencies, no schema shape changes (`approval_required`
  already existed on `IntakeDecision`; only its computed value changes).
