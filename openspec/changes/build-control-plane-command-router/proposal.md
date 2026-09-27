# Proposal

## Why

PlatformOps needs one trusted boundary that maps explicit user commands to
their independent workflows. Chat may render commands or buttons, but must not
select Python handlers, invent routes, or supply authority-bearing identity.

## What Changes

- Add explicit gateway routing for `/login`, `/onboard-org`, `/join-org`, and
  `/provision`.
- Require a validated safe principal projection for protected commands.
- Dispatch only to injected trusted workflow handlers.
- Keep LLM intent classification, raw JWTs, credentials, and workflow-specific
  authorization outside the router.

## Capabilities

### New Capabilities

- `control-plane-command-routing`: deterministic command allow-list, session
  precondition, and trusted workflow-handler dispatch.
