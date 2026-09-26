# Design

## Context

The current browser chat transport reads a local server-file actor session.
Browser-session JWT/cookie validation and the deterministic command router
already exist separately. See proposal.md for why they must converge.

## Goals / Non-Goals

**Goals:** one FastAPI origin, browser-cookie authentication, AG-UI POST/SSE,
and A2UI for chat and control-plane surfaces.

**Non-Goals:** WebSocket implementation, cloud execution, client-side
authorization, or use of the legacy actor-session file for browser requests.

## Decisions

### Keep AG-UI HTTP/SSE; do not introduce a custom WebSocket client

The installed client uses `HttpAgent`. HTTP POST plus SSE supports run start,
streaming, and authenticated resume now. A future WebSocket adapter may retain
the same AG-UI event schema, but is not needed to unify the product.

### Authenticate transport before routing

The FastAPI dependency extracts the session cookie and CSRF header, invokes
the existing browser-session authenticator, and produces a validated principal.
The transport then invokes trusted router/workflow handlers; it never reads a
local actor-session file for this path.

### Chat and command outcomes share A2UI rendering

Chat remains an AG-UI run. Typed actions such as onboarding review become
trusted command invocations whose safe results are rendered as A2UI events.
The browser provides presentation and structured input only.

## Risks / Trade-offs

- [Risk] Legacy frontend still assumes `/runs` file sessions → Mitigation:
  migrate its client composition and remove the file-session browser path only
  after replacement tests pass.
- [Risk] CSRF proof is unavailable after confirmation → Mitigation: retain it
  only in browser memory, never a cookie or persistent frontend store.

## Migration Plan

1. Add browser session/CSRF dependency and tests to the transport.
2. Adapt `/runs` composition to principal-based chat and trusted command paths.
3. Render onboarding review through A2UI and remove file-session browser use.
