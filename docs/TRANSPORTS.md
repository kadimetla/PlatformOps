## Status
Designed and partially real as of 2026-07-31. `transports/cli.py` is
the local CLI transport. `transports/remote_tui.py` is a tested
protocol-state slice for a future remote TUI, not a real WebSocket
client. No HTTP server, SSE endpoint, WebSocket endpoint, Teams
adapter, or Google Chat adapter exists yet.

## Real vs. Designed
| Item | Status |
|---|---|
| `transports/cli.py` (`platformops login`/`whoami`/`session show`/`run`) | Real — moved here from `interaction/cli.py` before that path was ever committed |
| `transports/remote_tui.py` (`RemoteTUIState`, `build_user_run_input`, `observe_agui_event`, `build_resume_run_input`) | Real — no-network protocol-state helper; proves the pending-interrupt/all-open-interrupts-in-one-resume/thread-ownership rules before any WebSocket code exists. Known gap: validates `threadId`, not `runId` — a stale/duplicate `RUN_FINISHED` for an earlier run on the same thread could still be accepted; harmless with no live transport, needs fixing before a real WebSocket client is built |
| `transports/http.py` (REST/SSE) | Not implemented, not started |
| `transports/websocket.py` | Not implemented, not started — `remote_tui.py` is the protocol logic this would eventually carry over a real socket |
| `transports/teams.py`, `transports/google_chat.py` | Not implemented, not started |

## Transport Boundary
A transport moves bytes between a user-facing surface and the same
gateway/workflow contract. It must not classify intent, compute grants,
approve policy, or execute workflow-specific behavior. It calls into
that contract through one object, not `gateway/`/`workflows/`
directly — see [PLATFORMOPS_HARNESS.md](PLATFORMOPS_HARNESS.md).

```text
transport            normalize/render channel-specific messages
interaction/         render/adapt PlatformOpsEvent and HITLEvent
harness/              PlatformOpsHarness -- the one call-in point every transport shares
gateway/             auth, sessions, policy, request contracts
workflows/           intake, provision, inquiry, approval, execution
```

That gives PlatformOps one backend behavior with multiple surfaces:

```text
local CLI/TUI
HTTP/SSE web app
WebSocket remote TUI
Teams
Google Chat
```

## Local CLI/TUI
The local CLI is the first transport because it needs no server:

```text
platformops login
platformops whoami
platformops session show
platformops run "<request>"   # shaped, but model provider not chosen
```

It can call local Python functions and render with `interaction/tui.py`.
It does not use AG-UI, HTTP, SSE, or WebSocket.

## Remote TUI Over AG-UI
The remote TUI shape is:

```text
terminal client
  -> AG-UI run input over WebSocket later
  -> gateway
  -> workflow emits PlatformOpsEvent/HITLEvent
  -> gateway emits AG-UI events
  -> terminal client renders and resumes
```

The implemented slice in `transports/remote_tui.py` deliberately stops
before networking. It tests the protocol rules a real WebSocket client
must obey:

- build a fresh AG-UI user run input with `threadId`, `runId`, and
  `messages`
- observe `RUN_FINISHED` interrupt outcomes from the gateway
- block new user input while interrupts are pending
- build AG-UI `resume[]` messages from `HITLResponse`
- require every pending interrupt to be addressed in one resume
- reject events for another thread

This captures the design issue that matters most before WebSocket code:
the TUI is not a chat socket that can always send another message. Once
the gateway has emitted an interrupt for a thread, the next input on
that thread must be a resume for all open interrupts.

## Why No WebSocket Yet
There is no gateway web server in this repo. Adding a WebSocket
dependency now would test a framework choice, not PlatformOps's own
protocol. The current testable slice keeps the useful contract and
defers transport plumbing until a server exists.

When a server is added, the remote TUI should reuse the same helpers:

```text
send build_user_run_input(...)
receive AG-UI events
call observe_agui_event(...)
render with interaction/tui.py
send build_resume_run_input(...)
```

## HTTP/SSE Before WebSocket
HTTP/SSE is still the lower-friction first server transport:

```text
POST /runs
GET  /runs/{thread_id}/events
POST /runs/{thread_id}/resume
```

WebSocket becomes useful when the terminal needs one persistent
bidirectional session, reconnect handling, or low-latency multi-user
watching. Until then, the remote TUI protocol state can be tested
without choosing the network transport.

## How this relates to the existing docs
Sibling to [INTERACTION_LAYER.md](INTERACTION_LAYER.md), not a
replacement — that doc owns `interaction/events.py`/`tui.py`/`agui.py`
(the event contracts and per-medium rendering), this doc owns what
moves those events/responses across a process or network boundary.
`transports/cli.py` was originally sketched as `interaction/cli.py` in
`INTERACTION_LAYER.md`; relocated here before that path was ever
committed, so that doc was corrected in place rather than needing a
note. `transports/remote_tui.py` builds directly on
[INTERACTION_LAYER.md](INTERACTION_LAYER.md)'s AG-UI interrupt mapping
and `interaction/agui.py`'s `hitl_response_to_resume_entry` without
changing either. Consumes [AUTH_BOUNDARY.md](AUTH_BOUNDARY.md)'s
`gateway/auth/` boundary and
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s approval gate as
the enforcement points every transport defers to — transports
normalize and render, they never enforce. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
