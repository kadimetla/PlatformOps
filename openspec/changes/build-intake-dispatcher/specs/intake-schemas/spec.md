## MODIFIED Requirements

### Requirement: IntakeDecision expresses classification and inert routing fields
The system SHALL define an `IntakeDecision` model with `intent:
Intent | None`, `clarification_questions: list[ClarificationQuestion]`,
`route: str | None` (default `None`), `ready_to_route: bool` (default
`False`), `mutation_requested: bool` (default `False`),
`approval_required: bool` (default `False`), `unsupported_reason: str |
None` (default `None`), and `evidence: list[str]`. `route` and
`ready_to_route` SHALL be populated with meaningful values by the
`resolve_route` node (`intake-routing` capability) for intents with a
real workflow target; `approval_required` SHALL stay inert (always
`False`) until a real mutating route exists to require approval for.

#### Scenario: Fields present and populated for a routable intent
- **WHEN** an `IntakeDecision` is produced by the full intake graph
  (`classify_workflow -> resolve_route`) for `intent ==
  Intent.compliance_check`
- **THEN** `route == "compliance_check"` and `ready_to_route is True`

#### Scenario: Fields present but at their defaults before resolve_route runs
- **WHEN** an `IntakeDecision` is constructed directly, or produced by
  `classify_workflow` alone before `resolve_route` has run
- **THEN** `route is None`, `ready_to_route is False`,
  `mutation_requested is False`, `approval_required is False`, and
  `unsupported_reason is None` — the model's own defaults
