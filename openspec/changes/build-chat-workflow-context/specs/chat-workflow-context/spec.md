# Spec Delta

## Purpose

Provide a visible, safe conversation context that lets PlatformOps users move
between independent workflows without treating conversational intent as
authorization.

## ADDED Requirements

### Requirement: Chat exposes a user-controlled active context
The system SHALL present the active conversation context and SHALL provide an
allow-listed `/context` command to display or request a context selection. A
context selection SHALL represent workflow focus only and SHALL NOT grant
membership, roles, target access, provider binding access, approval authority,
or cloud execution authority.

#### Scenario: Authenticated user selects provisioning context
- **WHEN** an authenticated user requests `/context provision`
- **THEN** the system visibly selects provisioning as the chat context
- **AND THEN** the provision workflow independently evaluates live membership,
  grants, governance rules, and provider binding eligibility before a protected
  action

### Requirement: Guests are directed to reachable workflows
The system SHALL treat a browser visitor without a validated session as a
guest. It SHALL permit only public/reachable context choices and SHALL direct a
guest who requests a protected action to login without starting that protected
workflow.

#### Scenario: Guest requests provisioning
- **WHEN** a guest types `/provision` or otherwise requests provisioning
- **THEN** the system prompts the guest to use `/login`
- **AND THEN** no provision workflow, authorization evaluation, or provider
  lookup starts

### Requirement: Guest chat routing is public and deterministic
The system SHALL treat `Guest` as the absence of a validated browser session,
not as a durable workflow or a low-privilege PlatformOps principal. Before
login, a deterministic guest chat router SHALL reach only login, registration,
organization-membership entry, and help paths. It SHALL NOT invoke protected
workflow handlers or load protected control-plane data.

#### Scenario: Guest requests onboarding review
- **WHEN** a guest asks to review an organization-onboarding request
- **THEN** the guest router renders a login prompt or public guidance
- **AND THEN** it does not look up the review request, reviewer access,
  organization, target, provider, or binding

#### Scenario: Guest completes login
- **WHEN** a guest completes the login confirmation flow
- **THEN** the browser receives a validated session through the existing
  browser-session boundary
- **AND THEN** subsequent context availability is derived as an authenticated
  user rather than as a guest

### Requirement: Chat header shows safe identity, organization, and context state
The system SHALL show a safe chat-header projection of identity state,
authorized selected-organization state when present, and active conversation
context. A visitor without a validated session SHALL be labelled `Guest` and
offered a sign-in action. The header SHALL NOT render roles, grants, target
access, provider data, session tokens, raw identity-provider claims, or review
request details.

#### Scenario: Guest opens chat
- **WHEN** a browser visitor without a validated session opens chat
- **THEN** the header displays `Guest`, the active public context, and a
  sign-in action
- **AND THEN** it displays no organization or protected control-plane data

#### Scenario: Organization member opens chat
- **WHEN** an authenticated user has an authorized selected organization
- **THEN** the header displays safe user, organization, and active-context
  projections
- **AND THEN** it does not use a displayed role or grant as authorization

### Requirement: Natural-language intake proposes context switches safely
The system SHALL constrain natural-language intake to known candidate intents.
When a candidate differs from an active context with meaningful unfinished
work, it SHALL request explicit user confirmation before suspending that work
and changing context.

#### Scenario: User changes topic during a provision draft
- **WHEN** a user with an active provision draft asks to join an organization
- **THEN** the system presents a switch-to-join-organization confirmation
- **AND THEN** it retains the provision draft unless the user confirms the
  context switch

### Requirement: Incomplete workflow drafts are owner-scoped and resumable
The system SHALL persist an incomplete workflow run with its owner and state.
It SHALL allow only the owning authorized principal to list, resume, or cancel
that draft. Resuming a protected workflow SHALL re-evaluate its normal
authorization and lifecycle checks from persisted server state.

#### Scenario: User resumes a provision draft after organization membership changes
- **WHEN** a user resumes a suspended provision draft
- **THEN** the provision workflow reloads current membership and authorization
  rather than trusting the draft's prior context

### Requirement: Slash commands are deterministic
The system SHALL recognize only an explicit allow-list of slash commands before
model-backed intake. Unknown slash commands SHALL render guidance and SHALL NOT
select or invoke arbitrary workflows.

#### Scenario: Unknown slash command
- **WHEN** a user sends `/delete-everything`
- **THEN** the system renders command guidance
- **AND THEN** no workflow or mutating action starts
