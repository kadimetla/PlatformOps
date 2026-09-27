# Proposal

## Why

PlatformOps currently has a local file-session AG-UI chat transport and a
separate browser-session command foundation. One browser product needs one
authenticated interaction boundary for chat, A2UI surfaces, HITL, and
deterministic control-plane commands.

## What Changes

- Replace the browser-facing `/runs` file-session dependency with the existing
  HttpOnly browser-session and CSRF boundary.
- Route chat and typed control-plane actions through one AG-UI HTTP/SSE
  transport, rendering structured outcomes with A2UI.
- Migrate the onboarding administrator wizard to the same interaction surface.
- Keep WebSocket as a future transport optimization, not a second protocol.

## Capabilities

### New Capabilities

- `browser-agui-control-plane`: Browser-cookie-authenticated AG-UI/A2UI
  interaction and deterministic command routing.

### Modified Capabilities

(none)

## Impact

- `transports/http.py`, browser session composition, command routing, and the
  React client.
- Removes browser reliance on server-local actor session files.
- No cloud credential, provider binding, or authorization decision moves to
  the browser.
