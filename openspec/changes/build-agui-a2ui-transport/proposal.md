## Why
`docs/TRANSPORTS.md` documents a web path (HTTP/SSE, `POST /runs` /
`GET /runs/{id}/events` / `POST /runs/{id}/resume`) but nothing serves a
browser yet -- no HTTP server exists on this branch. `docs/INTERACTION_LAYER.md`
recommended "A2UI later, fixed-schema widgets first" -- the user
explicitly wants A2UI dynamic rendering from day one instead, which
corrects that recommendation in place (see docs/WEB_CHAT_APP.md and the
dated note in docs/INTERACTION_LAYER.md).

This change ships the smallest genuinely-buildable slice: the backend
half of a browser chat app, wired to `PlatformOpsHarness` (unchanged) and
tested against the real `ag-ui-protocol` package's Pydantic types, not a
hand-assumed shape. A2UI's own wire schema (message envelope, component
composition, action-report format) was verified directly against the
installed `@a2ui/web_core`/`@a2ui/react` npm packages' Zod schemas and
example fixtures 2026-08-07 -- not assumed from prose docs alone, since
an earlier pass in this same session got the shape wrong before
inspecting the real package source.

## What Changes
- Add `interaction/agui.py`'s `platformops_event_to_run_finished` -- the
  success-outcome counterpart to the existing `hitl_event_to_run_finished`,
  keeping that module's "only place that knows AG-UI's wire shape"
  invariant intact.
- Add `interaction/a2ui.py`: `hitl_event_to_a2ui_messages` and
  `platformops_event_to_a2ui_messages`, each producing a verified
  `createSurface` + `updateComponents` A2UI v0.9 message pair, built on
  `interaction/agui.py`'s existing `hitl_event_to_interrupt` output
  rather than re-deriving message text/choices from `IntakeDecision` a
  second time. Renders using `@a2ui/react`'s built-in `basicCatalog`
  only (`Column`, `Text`, `Button`) -- no custom catalog registered on
  the frontend.
- Add `transports/http.py`: a FastAPI app exposing `GET /info` and
  `POST /runs` (one endpoint for both a fresh turn and a clarification
  resume, matching AG-UI's own convention already proven by
  `transports/remote_tui.py`'s `build_user_run_input`/
  `build_resume_run_input`). Calls `harness.start_run`/
  `resume_clarification` unchanged; streams `RUN_STARTED` -> A2UI
  `CUSTOM` events -> `RUN_FINISHED` via `ag_ui.encoder.EventEncoder`.
  Reads the on-disk session (`PLATFORMOPS_SESSION_PATH`, same convention
  as `transports/cli.py`) fresh on every request -- no browser login
  flow. First place in the repo to actually pick a model provider
  (`ChatAnthropic`, `claude-haiku-4-5` default) -- every other module has
  deliberately refused to, by design (see `workflows/intake/graph.py`'s
  docstring).
- Explicitly **out of scope for this change**: browser-based OIDC login,
  approval-gate/execution UI (no real workflow exists to route
  `provision`/`inquiry` into yet), CopilotKit's Node Runtime (the user's
  ask was AG-UI + A2UI, not CopilotKit specifically -- see
  docs/WEB_CHAT_APP.md's Scope Decision), multi-user session routing.

## Capabilities

### New Capabilities
- `a2ui-rendering`: `interaction/a2ui.py`'s two message-building
  functions plus `interaction/agui.py`'s new success-outcome function --
  together, the complete event-to-wire-format mapping the transport
  needs.
- `http-transport`: `transports/http.py`'s `GET /info` and `POST /runs`
  endpoints -- the FastAPI/SSE transport itself, session handling, and
  the model-provider construction.

### Modified Capabilities
(none -- `interaction/agui.py`/`interaction/events.py` were not built via
an openspec change originally, so there is no prior spec baseline to
delta against; the new function is spec'd as an ADDED requirement in
`a2ui-rendering` instead)

## Impact
- New files: `interaction/a2ui.py`, `transports/http.py`,
  `tests/interaction/test_a2ui.py`, `tests/transports/test_http.py`.
- Modified files: `interaction/agui.py` (+1 function),
  `tests/interaction/test_agui.py` (+1 test), `pyproject.toml` (+5
  dependencies: `fastapi`, `uvicorn`, `ag-ui-protocol`,
  `langchain-anthropic`), `.env.example` (+`ANTHROPIC_API_KEY` and
  related vars).
- New `frontend/` directory (Vite + React + TypeScript, Node pinned via
  Volta to `frontend/` only) -- implementation detail documented in
  `docs/WEB_CHAT_APP.md`, not spec'd here (no prior precedent in this
  repo for spec'ing frontend rendering behavior via openspec).
