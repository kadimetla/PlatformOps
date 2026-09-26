# Proposal

## Why

PlatformOps chat needs to feel like one continuous product while safely
supporting separate workflows such as login, organization membership,
organization onboarding, and provisioning. A user needs to see and explicitly
change the current conversational context without a context switch becoming an
authorization or provider-routing decision.

## What Changes

- Add a user-visible active chat context and deterministic `/context` command.
- Present a safe chat-header identity, organization, and context projection so
  guests, signed-in users, and members understand their current state.
- Let intake infer likely workflow intent from natural language and propose a
  context change when it differs from the active context.
- Preserve unfinished workflow drafts as suspended, resumable runs when a user
  changes context.
- Define guest, registered-user, member, and authorized-provisioner context
  availability and messaging.
- Add a deterministic guest chat router that reaches only public login,
  registration, membership-entry, and help paths before a session exists.
- Adapt guest-router outcomes to AG-UI/A2UI chat surfaces, beginning with an
  in-chat `/login` entry point and preserving the existing magic-link session
  confirmation boundary.
- Deliver guest login incrementally after the browser AG-UI transport has
  replaced its local actor-session dependency with the validated browser
  session boundary.
- Keep the existing browser AG-UI transport change responsible for session and
  transport mechanics; this change owns conversation orchestration only.

## Capabilities

### New Capabilities

- `chat-workflow-context`: Visible, user-controlled chat workflow context with
  safe intent routing and resumable workflow drafts.

### Modified Capabilities

(none)

## Impact

- Intake routing, durable workflow-run state, A2UI context controls, and chat
  behavior will gain contracts.
- Protected workflows continue to use their own authorization boundaries and
  persisted PostgreSQL state.
- No cloud credential, provider-binding, membership, or role decision moves
  into chat context state.
