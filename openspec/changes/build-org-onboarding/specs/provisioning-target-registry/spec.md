## ADDED Requirements

### Requirement: Canonical provisioning target uses environment terminology
The system SHALL represent a target with `org`, `group`, `team`, `project`,
and `env`.  It SHALL derive a human-readable canonical key as
`org:group:team:project:env`.  `env` is the PlatformOps term; a
provider-specific workspace is not an alias for it.

#### Scenario: Target key is derived from all five segments
- **WHEN** a target contains `acme`, `commerce`, `payments`, `checkout`, and
  `prod`
- **THEN** its canonical key is `acme:commerce:payments:checkout:prod`

### Requirement: Provider binding is registry controlled
The system SHALL resolve an exact active target to a provider binding that
contains provider identity, cloud account/subscription/project reference,
execution-identity reference, and optional provider-specific workspace name.
The client, requester token, and model SHALL NOT provide trusted binding
values.

#### Scenario: Client-supplied account is ignored
- **WHEN** a request includes an account identifier that differs from the
  registered binding for its target
- **THEN** the resolved binding uses the registry value and the client value
  is not used for planning or execution

### Requirement: Target resolution fails closed
The system SHALL return a non-routable result when an organization is not
active, a target is absent, a target is not active, or no exact binding
exists.  It SHALL NOT fall back to a parent target, another environment, or a
provider default.

#### Scenario: Missing production target does not fall back to development
- **WHEN** `acme:commerce:payments:checkout:prod` has no active binding and
  the equivalent `dev` binding exists
- **THEN** the production request is non-routable and the development binding
  is not returned

### Requirement: Resolved context is immutable and auditable
The system SHALL create an immutable resolved context containing the canonical
target, the registry binding, and a registry version or digest before planning.
Approval and execution SHALL use that same resolved context.

#### Scenario: Registry changes after planning
- **WHEN** a binding changes after a plan has been created
- **THEN** the earlier plan cannot be approved or executed against the changed
  binding without a new resolution and plan
