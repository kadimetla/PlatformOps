## Context
`workflows/intake/graph.py` is currently one node,
`classify_workflow -> END`. `build-intake-workflow/design.md` scoped
`resolve_route` out on purpose, naming two blockers: no real route target,
and no auth/policy layer. The first blocker is gone —
`spec/check_compliance.py` is real. The second is only partly gone: an
agent-verified grounding pass against the actual current files (not
`docs/INTAKE_HITL_ROUTING.md`'s assumed end-state) found:

| `docs/INTAKE_HITL_ROUTING.md`'s design | Actual current state |
|---|---|
| `resolve_route` looks up `POLICY[(scope.org_bu, intent)]` | `IntakeRequest` (`gateway/schemas.py`) has no `scope` field at all — not unpopulated, not present |
| `effective_access = min(actor.execution_grants, ceiling)` gates routing | `gateway/auth/grants.py`'s `GroupGrantMapping` validator raises if `grant_type != "approval"` — real sessions always have `execution_grants == []` by design (provider discovery, the intended source, doesn't exist) |
| `gateway/policy/org_bu_policy.yaml` / `project_registry.yaml` back the POLICY table | No such YAML files exist anywhere in the repo; `gateway/policy/ceiling.py`'s loader exists but nothing calls it with real data, and its `CeilingEntry(scope, intent, ceiling)` shape is a capability ceiling, not the doc's richer routing-POLICY shape (`route`/`cloud`/`execution_identity`/`allowed_resource_types`) |
| `provision`/`inquiry` route to real workflows | `workflows/provision/` and `workflows/inquiry/` don't exist |

So this design builds the same kind of deliberately-narrow slice
`build-intake-workflow` built for classification: real routing for the one
real target, everything scope/policy/grant-dependent left an explicit
non-goal until its own prerequisites are real.

## Goals / Non-Goals

**Goals:**
- `resolve_route` turns a resolved `Intent` into a route decision using
  only information the graph already has (no external state) —
  deterministic, zero model calls, testable with the same
  `FakeMessagesListChatModel` pattern already in use.
- `compliance_check` becomes genuinely routable: `route="compliance_check"`,
  `ready_to_route=True`.
- `provision`/`inquiry` fail closed to `unsupported_reason` rather than
  silently staying inert — the inert-forever behavior from
  `build-intake-workflow` was correct only because nothing resolved
  routing at all; now that something does, "no route exists" needs to be
  a stated fact, not a blank field indistinguishable from "not yet
  computed."
- `IntakeDecision`'s new fields are usable by a downstream consumer
  (`harness/core.py`) without a second schema-breaking change later.

**Non-Goals:**
- No `Scope` field on `IntakeRequest`. Nothing real would consume it yet —
  see the grounding table above. Adding an unused field ahead of a real
  consumer repeats the exact anti-pattern `build-intake-workflow/design.md`
  already reasoned through and avoided for `WORKFLOW_REGISTRY`.
- No `POLICY[(org_bu, intent)]` lookup, no `gateway/dispatcher.py` module.
  `_ROUTE_TABLE` stays a plain intent-keyed dict inside
  `workflows/intake/nodes.py` — a separate module for one real entry would
  be structure with nothing to justify it yet.
- No `actor.execution_grants` / `effective_access` integration.
- No invocation of `spec/check_compliance.py`. `resolve_route` decides the
  route; a wrapper that calls `check_compliance()` and returns evidence is
  a further follow-up, matching `docs/INTAKE_HITL_ROUTING.md`'s "Intake
  must not execute the request."
- No changes to `gateway/policy/ceiling.py` — a different, already-real
  concept (capability ceiling) from the routing POLICY this change defers.

## Decisions

**Two nodes, not one — reversing `build-intake-workflow`'s decision on
its own stated terms.** That change picked one node because "`resolve_route`
is explicitly out of scope, so there is nothing after classification for a
second node ... to lead to" — and named the flip condition explicitly:
"once `resolve_route` exists ... the reasoning flips back to two nodes."
That condition is met. Alternative considered: fold routing into
`classify_workflow` itself as extra logic at the end of the same function —
rejected, since it would blur "did the LLM decide this" (classification)
from "did deterministic code decide this" (routing), the exact separation
`docs/INTAKE_HITL_ROUTING.md`'s `IntakeDecision` field table exists to
preserve ("This separation prevents a classifier result from becoming
permission to mutate infrastructure").

**`_ROUTE_TABLE` as a plain dict in `nodes.py`, not a new `gateway/`
module.** `docs/INTAKE_HITL_ROUTING.md` sketches `gateway/dispatcher.py`
as part of a `gateway/` layout alongside `policy/`, but that sketch is
for the full per-org_bu POLICY dispatcher, not this one-entry deterministic
table. Alternative considered: create `gateway/dispatcher.py` now so the
eventual richer version has a home already — rejected as the same
"reserve a slot for something that doesn't fully exist yet" anti-pattern
`build-intake-workflow` rejected for `WORKFLOW_REGISTRY` and for
`audit`/`security_review`. The table's comment states plainly where it
moves once a real POLICY registry exists.

**`provision`/`inquiry` get `unsupported_reason`, not silence.** Before
this change, `route`/`ready_to_route` were inert for every intent — no
information was lost by that, since nothing computed them. After this
change, `compliance_check` gets a real answer; leaving `provision`/`inquiry`
at the same blank `route=None` they always had would make "not yet
computed" and "computed, and there's no route" indistinguishable. Setting
`unsupported_reason` makes the fail-closed behavior a stated fact, per
`docs/INTAKE_HITL_ROUTING.md`'s routing table: "anything else, or no
POLICY entry ... -> unsupported, fail closed."

**`mutation_requested = (intent == PROVISION)`, not a separate
deterministic-signal pass.** `docs/INTAKE_HITL_ROUTING.md`'s original
design derived `mutation_requested` from local text signals ("deploy",
"provision", "create", ...) extracted in a dedicated step —
`build-intake-workflow` cut that step entirely (Tier 2 prefix + Tier 3
tool call only). Re-deriving mutation intent from `intent` alone is the
only signal this branch's real code has; a second signal-extraction layer
is exactly the kind of speculative infrastructure this project's process
avoids building ahead of a real need. Alternative considered: leave
`mutation_requested` unset/always `False` — rejected, since `provision`
inherently implies mutation regardless of whether it's routable yet, and
a downstream approval-gate design will need this signal before it needs
per-word text analysis.

**`approval_required` stays hardcoded `False`.** No route in this change
requires approval (`compliance_check` is read-only; `provision` isn't
routable). Setting it meaningfully requires a real mutating route with a
real approval policy — out of scope here, same reasoning as
`route`/`ready_to_route` were left inert in `build-intake-workflow` until
something could compute them for real.

## Risks / Trade-offs
- [Risk] `unsupported_reason`'s string content
  (`"no workflow implemented for intent 'provision' yet"`) could get
  hardcoded against in a caller/transport, making it a de facto API that's
  awkward to change later → [Mitigation] it's documentation-grade text for
  a HITL/audit surface, not a machine-matched error code; if a caller ever
  needs to branch on the reason, that's a signal to add a structured
  reason enum then, not preemptively now.
- [Risk] `_ROUTE_TABLE` living in `workflows/intake/nodes.py` instead of a
  `gateway/` module could be read as "routing is workflow-owned," at odds
  with `docs/INTAKE_HITL_ROUTING.md`'s security-boundary framing (route
  selection as deterministic gateway code, not workflow logic) →
  [Mitigation] the table's own comment states it moves to
  `gateway/dispatcher.py` once real routing policy exists; this is a
  placement-of-convenience for one static entry, not a boundary decision.
- [Risk] `harness/core.py`'s `PlatformOpsEvent.payload` growing five keys
  (`intent`, `route`, `ready_to_route`, `mutation_requested`,
  `approval_required`, `unsupported_reason` — six, not five) as a bare
  `dict` rather than a typed model could drift silently if a field is
  renamed later → [Mitigation] accepted; `PlatformOpsEvent.payload`'s
  `dict` shape predates this change (`interaction/events.py`) and
  restructuring it is out of scope here.

## Migration Plan
1. `gateway/schemas.py`: add `mutation_requested`, `approval_required`,
   `unsupported_reason` to `IntakeDecision`.
2. `workflows/intake/nodes.py`: add `_ROUTE_TABLE` and `resolve_route`.
3. `workflows/intake/graph.py`: wire `classify_workflow -> resolve_route
   -> END`.
4. `harness/core.py`: extend the `PlatformOpsEvent` payload; correct the
   module docstring's now-inaccurate "nothing downstream acts on it yet"
   framing.
5. Tests: replace `test_route_and_ready_to_route_always_inert` with
   per-branch coverage (`compliance_check` routes, `provision`/`inquiry`
   unsupported, clarification-pending stays inert); update
   `tests/harness/test_core.py`'s two hardcoded payload assertions.
6. Docs: correct `docs/INTAKE_HITL_ROUTING.md`'s Status line and Real vs.
   Designed table, `docs/HARNESS_DESIGN.md`'s document-map rows for
   `INTAKE_HITL_ROUTING.md`/`WORKFLOW_LIFECYCLE_PATTERN.md`/
   `PLATFORMOPS_HARNESS.md` — all previously said no dispatcher/one-node
   graph, now false.

No cutover step — purely additive to the schema and graph, nothing
existing breaks except the two test assertions this change updates
directly.

## Open Questions
- Whether `unsupported_reason` should eventually become a structured
  enum instead of free text, once a second caller needs to branch on it.
  Not resolved here — no second caller exists yet.
- Where a `compliance_check` wrapper that actually calls
  `check_compliance()` lives (`workflows/compliance_check/` mirroring
  `workflows/intake/`'s shape, or a thinner adapter directly in
  `harness/core.py`). Left to whichever change picks up "intake decisions
  actually get executed" next.
