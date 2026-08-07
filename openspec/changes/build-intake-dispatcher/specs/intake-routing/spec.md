## ADDED Requirements

### Requirement: resolve_route deterministically routes a resolved intent
The system SHALL provide a `resolve_route` graph node that runs after
`classify_workflow` and makes no model call. Given an `IntakeDecision`
with a resolved `intent`, it SHALL look up a static, intent-keyed table
(not scope-keyed) to decide `route` and `ready_to_route`. The table SHALL
contain an entry only for intents with a real, existing workflow target.

#### Scenario: compliance_check resolves to its real wrapper target
- **WHEN** `classify_workflow` resolves `intent == Intent.compliance_check`
- **THEN** `resolve_route` sets `route == "compliance_check"` and
  `ready_to_route == True`

#### Scenario: No model call is made
- **WHEN** `resolve_route` runs, regardless of outcome
- **THEN** no model/LLM call occurs — the routing table lookup is the
  only operation

### Requirement: Intents with no real workflow fail closed to unsupported
The system SHALL set `unsupported_reason` (non-`None`) and leave
`route == None`, `ready_to_route == False` for any resolved `intent` that
has no entry in the routing table, rather than leaving those fields
silently blank.

#### Scenario: provision has no route yet
- **WHEN** `classify_workflow` resolves `intent == Intent.provision`
- **THEN** `route is None`, `ready_to_route is False`, and
  `unsupported_reason is not None`

#### Scenario: inquiry has no route yet
- **WHEN** `classify_workflow` resolves `intent == Intent.inquiry`
- **THEN** `route is None`, `ready_to_route is False`, and
  `unsupported_reason is not None`

### Requirement: mutation_requested reflects provision intent
The system SHALL set `IntakeDecision.mutation_requested` to `True` when
the resolved `intent == Intent.provision`, and `False` for every other
intent (including intents with no resolved route), since `provision`
inherently implies mutation regardless of routability.

#### Scenario: provision implies mutation even though unsupported
- **WHEN** `classify_workflow` resolves `intent == Intent.provision`
- **THEN** `mutation_requested is True`, even though `route is None`

#### Scenario: compliance_check does not imply mutation
- **WHEN** `classify_workflow` resolves `intent == Intent.compliance_check`
- **THEN** `mutation_requested is False`

### Requirement: A pending clarification is not marked unsupported
The system SHALL leave `route`, `ready_to_route`, `mutation_requested`,
and `unsupported_reason` at their default (unset) values when
`classify_workflow` did not resolve an `intent` (i.e.
`clarification_questions` is non-empty) — an unclassified request is not
the same outcome as a classified-but-unroutable one.

#### Scenario: Clarification pending has no unsupported_reason
- **WHEN** `classify_workflow` cannot resolve an intent and emits a
  clarifying question
- **THEN** `resolve_route` does not alter `route`, `ready_to_route`,
  `mutation_requested`, or `unsupported_reason` — they stay at their
  `IntakeDecision` defaults

### Requirement: approval_required stays inert
The system SHALL leave `IntakeDecision.approval_required` at `False` for
every outcome of this change's graph — no route this change resolves
requires approval (`compliance_check` is non-mutating; `provision` is not
routable), so there is nothing real to set it from yet.

#### Scenario: approval_required is always False
- **WHEN** `resolve_route` runs, for any intent
- **THEN** `approval_required is False`

### Requirement: resolve_route never invokes the target workflow
The system SHALL NOT call, import, or otherwise execute
`spec/check_compliance.py` (or any other workflow) from `resolve_route`.
It SHALL only decide the routing fields — intake produces a decision, it
does not act on it.

#### Scenario: compliance_check resolution does not execute the check
- **WHEN** `resolve_route` sets `route == "compliance_check"`
- **THEN** `check_compliance()` is not called and no compliance result
  appears anywhere in `IntakeDecision`
