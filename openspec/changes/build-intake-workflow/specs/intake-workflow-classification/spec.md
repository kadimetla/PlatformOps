## ADDED Requirements

### Requirement: `intake_request()` resolves which workflow should handle raw text
The system SHALL provide `intake_request(request: IntakeRequest) ->
IntakeResult`, returning an `IntakeResult` with `workflow_hint` set to
`"drafting"` or `"inquiry"` when classification succeeds.

#### Scenario: A clear drafting request resolves to the drafting workflow
- **WHEN** `raw_text` clearly describes creating or modifying
  infrastructure
- **THEN** `intake_request()` returns `workflow_hint="drafting"`

#### Scenario: A clear inquiry request resolves to the inquiry workflow
- **WHEN** `raw_text` clearly asks whether a resource already exists
- **THEN** `intake_request()` returns `workflow_hint="inquiry"`

### Requirement: Tier 2's text-prefix convention is checked before any LLM call
The system SHALL resolve `workflow_hint` deterministically, with no
model call, when `raw_text` starts with `"drafting:"` or `"inquiry:"`.

#### Scenario: A prefixed request skips classification entirely
- **WHEN** `raw_text` is `"inquiry: does invoices-prod already exist"`
- **THEN** `intake_request()` returns `workflow_hint="inquiry"` and no
  model call is made

### Requirement: Tier 3 resolves unprefixed text via a bound, forced-choice tool call
The system SHALL fall back to one `select_workflow` bound tool call,
constrained to `"drafting"` | `"inquiry"` | a clarifying question, when
`raw_text` has no recognized prefix. The system SHALL NOT accept an
LLM-generated workflow name that isn't one of those two values.

#### Scenario: Unprefixed but unambiguous text resolves via the model
- **WHEN** `raw_text` has no `"drafting:"`/`"inquiry:"` prefix but
  clearly describes one workflow's kind of request
- **THEN** `classify_workflow` calls the model once, bound to
  `select_workflow`, and `intake_request()` returns the resolved
  `workflow_hint`

### Requirement: An unresolvable request returns a clarifying question, not a guess, with no blocking pause
The system SHALL return `IntakeResult(clarifying_question=...)`, with
`workflow_hint=None`, when neither tier resolves a workflow, and SHALL
NOT pause or wait for a reply before returning.

#### Scenario: Ambiguous text produces a clarifying question
- **WHEN** `raw_text` doesn't clearly match either workflow's kind of
  request
- **THEN** `intake_request()` returns a `clarifying_question` and
  `workflow_hint=None`, in the same response, with no separate wait step

### Requirement: `org_id`/`bu_id` are accepted as given, never parsed from text
The system SHALL treat `IntakeRequest.org_id` and `IntakeRequest.bu_id`
as already-resolved inputs and SHALL NOT attempt to extract or infer
either field from `raw_text`.

#### Scenario: Org/BU scoping comes from the request object, not text parsing
- **WHEN** `intake_request()` is called with an `IntakeRequest` whose
  `org_id`/`bu_id` were set by the caller from an authenticated session
- **THEN** no node in `workflows/intake/` inspects `raw_text` for
  org/BU identifiers
