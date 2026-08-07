## MODIFIED Requirements

### Requirement: This change's graph never produces a routable decision
Regardless of Tier 2 or Tier 3 outcome, `classify_workflow` itself SHALL
NOT set `IntakeDecision.route` or `ready_to_route` — route resolution is
delegated entirely to the downstream `resolve_route` node (see the
`intake-routing` capability), never computed inline during
classification. This **supersedes** the requirement's original text
("this change's graph never produces a routable decision"), which held
only while no downstream node existed to compute a route at all — the
full intake graph now does produce a routable decision for
`compliance_check`; classification's own contribution to that decision
remains exactly what it always was.

#### Scenario: classify_workflow's own return value never sets a route
- **WHEN** `classify_workflow` resolves an intent (Tier 2 or Tier 3) or
  emits a clarifying question
- **THEN** the `IntakeDecision` it returns has `route is None` and
  `ready_to_route is False` — `resolve_route` runs next in the graph and
  may change this before the graph ends
