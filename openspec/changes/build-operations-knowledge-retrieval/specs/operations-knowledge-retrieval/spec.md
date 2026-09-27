# Operations knowledge retrieval

## ADDED Requirements

### Requirement: Retrieval is advisory only

The system SHALL treat retrieved material as advisory context and SHALL NOT
use it as authorization, approval, provider-routing, or execution authority.

#### Scenario: Guidance cannot authorize provisioning

- **WHEN** a retrieved document recommends an AWS deployment
- **THEN** the provision request still requires active membership, scope
  authorization, governance checks, a registry binding, and approval

### Requirement: Results are current, filtered, and cited

The system SHALL filter sources by lifecycle, classification, and trusted
applicability context before ranking. Each returned result SHALL include a
source reference and review date.

#### Scenario: Expired runbook is excluded

- **WHEN** a runbook has passed its expiry date
- **THEN** it is not returned to chat or architecture review

### Requirement: Architecture review is non-mutating

The system SHALL produce review findings for diagrams/specifications without
calling cloud providers, storing credentials, approving plans, or executing
work.

#### Scenario: Diagram violates a deterministic rule

- **WHEN** a submitted diagram omits a required approval boundary
- **THEN** the review reports a cited finding and does not change any workflow
  or provider state
