## ADDED Requirements

### Requirement: Intent enum has exactly three values
The system SHALL define an `Intent` enum with exactly the values
`provision`, `inquiry`, and `compliance_check`. No other value SHALL
be defined, including `audit` or `security_review`, until a real
workflow exists for it.

#### Scenario: Enum membership
- **WHEN** code inspects `Intent`'s members
- **THEN** exactly `provision`, `inquiry`, `compliance_check` are
  present and no others

### Requirement: Scope identifies org/bu/project/workspace without asserting authority
The system SHALL define a `Scope` model with `org: str`, `bu: str`
(default `"root"`), `project: str | None`, `workspace: str | None`,
and a computed `org_bu` property returning `f"{org}:{bu}"`. `Scope`
SHALL NOT itself validate that the org/bu is real or that the
requester has any access to it — that is a later dispatcher's
responsibility, not this schema's.

#### Scenario: org_bu composite
- **WHEN** a `Scope` is constructed with `org="aiq"`, `bu="it"`
- **THEN** `scope.org_bu == "aiq:it"`

#### Scenario: bu defaults to root
- **WHEN** a `Scope` is constructed with only `org="aiq"`
- **THEN** `scope.bu == "root"` and `scope.org_bu == "aiq:root"`

### Requirement: IntakeRequest carries raw text and an optional clarification round
The system SHALL define an `IntakeRequest` model with `raw_text: str`
and `clarification_round: int` (default `0`). It SHALL NOT define any
identity field (`org`/`bu`/actor) that could be populated by parsing
`raw_text` — those come from an authenticated session in later
changes, not from request text, ever.

#### Scenario: Minimal construction
- **WHEN** an `IntakeRequest` is constructed with only `raw_text`
- **THEN** `clarification_round == 0` and construction succeeds
  without any org/bu/actor argument

### Requirement: IntakeDecision expresses classification and inert routing fields
The system SHALL define an `IntakeDecision` model with `intent:
Intent | None`, `clarification_questions: list[ClarificationQuestion]`,
`route: str | None` (default `None`), `ready_to_route: bool` (default
`False`), and `evidence: list[str]`. `route` and `ready_to_route`
SHALL exist on the model for forward compatibility with the dispatcher
change but SHALL NOT be populated with meaningful values by anything
in this change.

#### Scenario: Fields present but inert
- **WHEN** an `IntakeDecision` is constructed by this change's
  classification graph
- **THEN** `route is None` and `ready_to_route is False` on every
  output, regardless of `intent`

### Requirement: ClarificationQuestion is structured, not free text
The system SHALL define a `ClarificationQuestion` model with `field:
str`, `question: str`, and `choices: list[str]`. When choices are the
`Intent` enum's values, a caller re-invoking with a chosen answer
SHALL be able to match it via the Tier 2 prefix convention (see
`intake-classification`) without a second LLM call.

#### Scenario: Choices match Intent values
- **WHEN** a `ClarificationQuestion` is built for an unresolved intent
- **THEN** its `choices` list contains only valid `Intent` enum values
