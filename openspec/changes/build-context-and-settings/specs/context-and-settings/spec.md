# Context and Settings

## ADDED Requirements

### Requirement: Personal preferences are separate from governance

The system SHALL store and project personal preferences separately from
governed settings. A personal preference SHALL NOT grant membership, role,
target access, provider access, approval authority, or alter an inherited
governance rule.

#### Scenario: User selects a preferred context

- **WHEN** a user saves a preferred authorized context
- **THEN** the system may use it as a presentation default after login
- **AND THEN** each protected workflow still evaluates current authorization

#### Scenario: Assistant suggests a saved preference

- **WHEN** an assistant uses a safe saved preference to suggest a context or
  non-sensitive draft default
- **THEN** the suggestion is not an authorization or policy decision
- **AND THEN** the target workflow validates current state before using it

### Requirement: Context navigation is server-authorized and non-authoritative

The system SHALL present only server-authorized Organization, Business Unit,
Team, PlatformOps Project, and Environment context records. Selecting a
context SHALL NOT grant access, select a provider binding, or make a policy
decision.

#### Scenario: User selects a visible project context

- **WHEN** an authorized user selects a PlatformOps Project context
- **THEN** the UI updates its safe context projection
- **AND THEN** a later provision request independently evaluates membership,
  grants, effective governance, and provider-binding eligibility

#### Scenario: Project context exists before environment selection

- **WHEN** a user has selected an authorized PlatformOps Project but a
  provision workflow still requires an environment
- **THEN** the context projection identifies the project without claiming an
  environment is selected
- **AND THEN** the environment is displayed only after server-authorized
  workflow resolution

### Requirement: Governed settings preserve inherited guardrails

The system SHALL compute governed settings from scope inheritance and show an
authorized reader the effective value and source scope. A lower scope SHALL be
allowed to tighten a parent guardrail only where its setting contract permits;
it SHALL NOT weaken an inherited deny, mandatory approval, provider
restriction, region prohibition, or evidence requirement.

#### Scenario: BU attempts to relax an organization provider deny

- **WHEN** a BU administrator requests a provider configuration that conflicts
  with an organization-level deny
- **THEN** the settings workflow rejects the request
- **AND THEN** it records no effective-policy relaxation

### Requirement: Governed setting mutations use workflow-owned authorization

The system SHALL submit governed setting changes through an explicit
server-owned workflow. Before a revision is written, that workflow SHALL
re-evaluate actor eligibility, scope lifecycle, parent guardrails, revision
staleness, and required approval policy.

#### Scenario: Administrator eligibility is revoked after settings display

- **WHEN** an actor submits a displayed setting change after their
  administrative eligibility is revoked
- **THEN** the workflow denies the change
- **AND THEN** no setting revision is written

### Requirement: Settings projections omit sensitive control-plane data

The system SHALL return only allow-listed context and setting projections. It
SHALL NOT return credentials, tokens, provider execution identities, raw
grants, raw IdP claims, or internal policy evaluator traces.

#### Scenario: Unauthorized user requests a governed setting

- **WHEN** a user requests a setting outside their readable scope
- **THEN** the system returns the same outcome as for an absent setting
