## ADDED Requirements

### Requirement: Tier 2 deterministic prefix match runs before any model call
The system SHALL check `raw_text` for an exact, case-sensitive prefix
match against `"provision: "`, `"inquiry: "`, `"compliance_check: "`
before invoking any language model. On a match, the system SHALL
return the corresponding `Intent` with no model call made.

#### Scenario: Prefix match resolves intent with zero model calls
- **WHEN** `raw_text` is `"provision: deploy invoices to dev"`
- **THEN** `IntakeDecision.intent == Intent.provision` and no model
  call occurred

#### Scenario: Case-sensitive, no partial match
- **WHEN** `raw_text` is `"Provision: deploy invoices to dev"` (wrong
  case) or `"provisioning something"` (not the exact prefix)
- **THEN** Tier 2 does not match and classification falls through to
  Tier 3

### Requirement: Tier 3 uses exactly one bound-tool model call on a Tier 2 miss
When Tier 2 does not match, the system SHALL make exactly one model
call with a bound tool (`select_intent`) whose schema accepts either
`intent: Intent` (one of the three enum values) or
`clarifying_question: str`, never both, never neither meaningfully.
The system SHALL NOT accept a model-emitted intent value outside the
`Intent` enum.

#### Scenario: Tool call resolves a valid intent
- **WHEN** the model's tool call sets `intent="inquiry"`
- **THEN** `IntakeDecision.intent == Intent.inquiry` and
  `clarification_questions` is empty

#### Scenario: Tool call emits a clarifying question instead
- **WHEN** the model's tool call sets `clarifying_question="..."`
  instead of an intent
- **THEN** `IntakeDecision.intent is None` and
  `IntakeDecision.clarification_questions` contains one
  `ClarificationQuestion` whose `choices` are the three `Intent` values

#### Scenario: Malformed or missing tool call never guesses
- **WHEN** the model's response contains no tool call, or a tool call
  with neither `intent` nor `clarifying_question` set, or an `intent`
  value outside the enum
- **THEN** the system SHALL treat this as an unresolved classification
  (a clarifying question), never invent or guess an intent

### Requirement: This change's graph never produces a routable decision
Regardless of Tier 2 or Tier 3 outcome, `IntakeDecision.route` SHALL be
`None` and `ready_to_route` SHALL be `False` on every output of this
change's graph — routing is explicitly out of scope (see design.md).

#### Scenario: Resolved intent still has no route
- **WHEN** classification resolves to any `Intent` value via either
  tier
- **THEN** `IntakeDecision.route is None` and
  `IntakeDecision.ready_to_route is False`

### Requirement: Graph is testable without real model credentials
The system SHALL support running `classify_workflow` against a
scripted fake chat model that returns canned tool-call responses, with
no network call and no real API credentials required, for both the
Tier 2 and Tier 3 paths.

#### Scenario: Fake model drives Tier 3 in tests
- **WHEN** a test invokes the graph with a `raw_text` that misses Tier
  2, using a fake model configured to return a specific tool call
- **THEN** the graph's output matches the fake model's scripted
  response deterministically, with no real credentials configured
  anywhere in the test environment
