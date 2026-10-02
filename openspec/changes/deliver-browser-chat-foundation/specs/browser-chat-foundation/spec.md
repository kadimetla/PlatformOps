# Browser Chat Foundation

## ADDED Requirements

### Requirement: Functional browser chat is built in dependency order

The system SHALL complete browser session transport, guest login, durable
conversations, and the V2 Chat shell before presenting Work or Settings as
functional server-backed product features. A fixture-only UI SHALL be labelled
as a design/test fixture and SHALL NOT be presented as an authorized queue or
governance interface.

#### Scenario: Work UI is under development without Work Item persistence

- **WHEN** the browser shell is being developed before Work Item projections
  exist
- **THEN** it may render fixture data only in development/test mode
- **AND THEN** it does not expose actionable Work controls in a production
  browser route

### Requirement: The first browser slice preserves existing security boundaries

The first functional browser slice SHALL use the gateway browser-session and
CSRF boundary, the deterministic guest router, owner-private conversations,
and AG-UI/A2UI transport. It SHALL NOT use a server-local CLI session file,
browser-stored JWT, browser-supplied principal, or cloud credential.

#### Scenario: Guest completes passwordless login

- **WHEN** a guest completes passwordless confirmation from chat
- **THEN** later protected chat requests use the validated browser session
- **AND THEN** the browser has no readable bearer token
