## ADDED Requirements

### Requirement: Capability enum has exactly seven values, totally ordered
The system SHALL define a `Capability` enum with exactly these values,
in this order: `none`, `describe`, `plan`, `propose_change`,
`apply_limited`, `apply_full`, `admin`. Comparison operators (`<`,
`<=`, `>`, `>=`) and `min()`/`max()` SHALL follow this order exactly.

#### Scenario: Enum membership and order
- **WHEN** code inspects `Capability`'s members in order
- **THEN** they are exactly `none, describe, plan, propose_change,
  apply_limited, apply_full, admin`, in that order, and no others

#### Scenario: min() picks the lower capability
- **WHEN** `min(Capability.APPLY_LIMITED, Capability.DESCRIBE)` is
  evaluated
- **THEN** the result is `Capability.DESCRIBE`

#### Scenario: Comparison operators work directly
- **WHEN** `Capability.APPLY_LIMITED >= Capability.PLAN` is evaluated
- **THEN** the result is `True`

#### Scenario: String serialization stays readable
- **WHEN** `Capability.APPLY_LIMITED.value` is inspected
- **THEN** it equals the string `"apply_limited"`, not an integer

### Requirement: ExecutionGrant and ApprovalGrant nest Scope
The system SHALL define `ExecutionGrant` with `scope: Scope`,
`provider: str`, `capability: Capability`, and `ApprovalGrant` with
`scope: Scope`, `max_capability: Capability`. Neither model SHALL
duplicate `org`/`bu`/`project`/`workspace` as separate flat fields
alongside `scope`.

#### Scenario: ExecutionGrant carries a real Scope
- **WHEN** an `ExecutionGrant` is constructed with
  `scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev")`,
  `provider="aws"`, `capability=Capability.APPLY_LIMITED`
- **THEN** `grant.scope.org_bu == "aiq:it"` and
  `grant.capability == Capability.APPLY_LIMITED`

#### Scenario: ApprovalGrant carries no execution provider
- **WHEN** an `ApprovalGrant` is constructed with a `scope` and
  `max_capability`
- **THEN** construction succeeds without any `provider` argument —
  approval authority is provider-agnostic by design

### Requirement: Actor carries both grant sets and a resolution timestamp
The system SHALL define `Actor` with `user_id: str`, `email: str`,
`execution_grants: list[ExecutionGrant]`,
`approval_grants: list[ApprovalGrant]`, and `resolved_at: datetime`.

#### Scenario: Actor with both grant sets
- **WHEN** an `Actor` is constructed with one `ExecutionGrant` and one
  `ApprovalGrant` on different workspaces
- **THEN** both lists are independently populated and neither grant
  type is required to also appear in the other list
