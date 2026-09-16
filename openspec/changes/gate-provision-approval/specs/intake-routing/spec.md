## MODIFIED Requirements

### Requirement: approval_required reflects whether the resolved route mutates infra
The system SHALL set `IntakeDecision.approval_required` to `True` when
`resolve_route` resolves a route for `intent == Intent.PROVISION`, and to
`False` for every other resolved route (including `compliance_check`) and
for any outcome where no route resolves. This replaces
`openspec/changes/build-intake-dispatcher/specs/intake-routing/spec.md`'s
"approval_required stays inert" requirement, which held only because no
mutating route existed yet to require approval for -- `provision` now has
one (`gateway/dispatcher.py`'s `ROUTE_REGISTRY`).

Setting `approval_required = True` is a reported fact only. It does not
by itself block dispatch or provide any way to satisfy the requirement --
no approve-or-execute mechanism exists yet (see Non-Goals in this
change's design.md).

#### Scenario: provision requires approval
- **WHEN** `classify_workflow` resolves `intent == Intent.provision` and
  `resolve_route` resolves it to the real `"provision"` route
- **THEN** `approval_required is True`

#### Scenario: compliance_check does not require approval
- **WHEN** `classify_workflow` resolves `intent == Intent.compliance_check`
- **THEN** `approval_required is False`

#### Scenario: An unrouted intent does not require approval
- **WHEN** `resolve_route` cannot resolve a route for the given intent
  (e.g. `inquiry`), or no intent has been classified yet
- **THEN** `approval_required is False`

#### Scenario: harness/core.py reports the same value it was given
- **WHEN** `harness/core.py`'s `_dispatch_provision` builds a
  `ROUTE_RESOLVED` event for a dispatched `provision` request, in either
  its `unavailable_reason` branch or its success branch
- **THEN** the event's `approval_required` payload field is `True`,
  matching what `resolve_route` set on the `IntakeDecision` that reached
  it
