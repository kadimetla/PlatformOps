## ADDED Requirements

### Requirement: Commands use an explicit allow-list
The gateway SHALL route only registered explicit commands to injected trusted
workflow handlers. Unknown commands SHALL not select a handler.

#### Scenario: Unknown command
- **WHEN** a caller submits an unregistered command
- **THEN** no workflow starts

### Requirement: Protected commands require a validated principal
The gateway SHALL validate the PlatformOps session before dispatching
`/onboard-org`, `/join-org`, or `/provision`. The resulting principal SHALL
contain issuer and subject derived by the gateway, not caller payload.

#### Scenario: Unauthenticated organization onboarding
- **WHEN** a caller invokes `/onboard-org` without a valid session
- **THEN** no onboarding workflow starts

### Requirement: Router does not grant authority
The router SHALL not infer membership, grant Resource Scope access, resolve a
Provider Binding, or accept a client-supplied principal, provider, credential,
or execution identity.

#### Scenario: Caller supplies a subject hint
- **WHEN** payload includes a subject different from the validated session
- **THEN** the handler receives the gateway-derived principal only
