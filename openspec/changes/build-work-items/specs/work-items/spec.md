# Work Items

## ADDED Requirements

### Requirement: Work Items are server-owned workflow references

The system SHALL persist a Work Item independently of chat messages for each
supported actionable workflow state. A Work Item SHALL reference an originating
workflow run and lifecycle state. It MAY reference a conversation for
navigation, but that reference SHALL NOT confer access or authority.

#### Scenario: A workflow creates reviewer work

- **WHEN** a workflow reaches a pending reviewer decision state
- **THEN** it creates or updates a server-owned Work Item referencing that run
- **AND THEN** no approval occurs merely from Work Item creation

### Requirement: Work queues use live server authorization

The system SHALL compute Work queue visibility and counts from the
authenticated principal's current membership and workflow eligibility. It SHALL
NOT accept browser-supplied roles, queue labels, or identity-group identifiers
as authority.

#### Scenario: Eligibility is revoked after a queue is displayed

- **WHEN** a previously eligible actor opens or acts on a visible Work Item
- **THEN** the originating workflow re-evaluates current eligibility
- **AND THEN** it denies the action when eligibility is absent

### Requirement: Work Item projections are safe and non-enumerating

The system SHALL expose only allow-listed summaries, status, urgency,
timestamps, and authorized navigation references. It SHALL omit credentials,
tokens, provider account details, grants, approval digests, raw identity
claims, and workflow checkpoints. An unauthorized item lookup SHALL not reveal
whether the item exists.

#### Scenario: Actor requests another organization's item

- **WHEN** an actor requests a Work Item outside current visibility
- **THEN** the system returns the same outcome as for an absent Work Item

### Requirement: Work registry does not mutate workflow authority

The Work registry SHALL NOT approve, reject, execute, activate, or otherwise
transition an originating workflow. It SHALL delegate action handling to the
workflow-owned boundary.

#### Scenario: Actor selects approve from a Work surface

- **WHEN** the actor submits a decision from a Work Item surface
- **THEN** the action is handled by the originating workflow
- **AND THEN** that workflow validates state, authorization, and integrity
  before any transition

### Requirement: Daily operational work is workflow-derived

The system SHALL create daily operational Work Items only from a named
workflow or deterministic server-owned operational rule. A daily item SHALL
carry an owning workflow reference, eligible principal or identity-group
references, and a due time when applicable. It SHALL NOT be created from a
chat message, local browser state, or an unrestricted user-maintained task
list.

#### Scenario: Due operational follow-up appears in Work

- **WHEN** a server-owned workflow creates a follow-up with a due time
- **THEN** the Work projection may present it in Needs my action ordered by
  urgency or due time
- **AND THEN** opening it delegates resolution to the owning workflow

### Requirement: Security-review visibility and decisions use live policy

The system SHALL expose a security-review Work Item only to principals
currently eligible under the owning workflow's security-review policy. The
Work registry SHALL NOT infer security-review authority from a UI queue or a
browser role claim.

#### Scenario: Security reviewer membership is revoked

- **WHEN** an actor opens a previously visible security-review Work Item after
  their eligibility is revoked
- **THEN** the owning workflow denies the decision
- **AND THEN** no security-review state changes
