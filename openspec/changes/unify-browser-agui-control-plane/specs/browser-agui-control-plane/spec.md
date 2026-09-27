# Spec Delta

## Purpose

Provide one browser-authenticated AG-UI and A2UI interaction boundary for
PlatformOps chat, human review, and deterministic control-plane workflows.

## ADDED Requirements

### Requirement: Browser AG-UI runs require PlatformOps browser session authentication
The system SHALL validate the HttpOnly PlatformOps browser session and
same-origin CSRF proof before starting or resuming a browser AG-UI run. It
SHALL derive only the validated principal and SHALL NOT load a server-local
actor-session file for browser authorization.

#### Scenario: Missing browser session
- **WHEN** a browser starts an AG-UI run without a valid session cookie
- **THEN** the server rejects the run before a workflow or model starts

### Requirement: A2UI actions use deterministic command routing
The system SHALL route structured browser actions through the trusted command
router and server-side workflow handlers. A2UI payloads SHALL NOT select cloud
providers, bindings, credentials, reviewer identity, or authorization grants.

#### Scenario: Wizard action includes a provider field
- **WHEN** an A2UI onboarding-review action includes provider routing data
- **THEN** the server rejects it and no lifecycle state changes

### Requirement: HTTP/SSE is the initial unified transport
The system SHALL use AG-UI HTTP request input and SSE events for the initial
unified browser transport. WebSocket SHALL NOT be required for chat, A2UI, or
HITL behavior in this change.

#### Scenario: Review requires human input
- **WHEN** a workflow needs a structured reviewer action
- **THEN** it emits an AG-UI/A2UI interaction and accepts a later authenticated
  HTTP resume without opening a separate WebSocket protocol
