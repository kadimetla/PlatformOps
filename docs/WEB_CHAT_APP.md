## Status
Real, Milestone 1. `interaction/a2ui.py`, `transports/http.py`, and
`interaction/agui.py`'s `platformops_event_to_run_finished` are real code
(`openspec/changes/build-agui-a2ui-transport/`), backed by tests and a
real running smoke test (uvicorn + Vite dev server + curl through the
proxy). `frontend/` is real, `npm install`/`tsc -b`/`npm run build` all
verified clean against the actually-installed `@ag-ui/client`/
`@a2ui/react`/`@a2ui/web_core` packages -- but no browser ever rendered
it in the environment this was built in (no browser available), so
in-browser rendering is the one remaining manual verification step.

**Corrected 2026-08-07 (review pass)**: a review of the first version of
this milestone found five real gaps, all fixed in place, not left as
follow-ups: (1) A2UI rendered clickable approval verdict buttons the
backend could never actually resolve (no `resume_approval` exists) --
approval events now render message-only; (2) resume didn't validate
`interruptId` or actor identity, so any resume for a known thread would
succeed regardless of which interrupt or which actor it claimed --
`harness/core.py`'s `_pending_intake` now stores both and
`resume_clarification` verifies them before consuming the pending entry;
(3) the A2UI button-click handler had no in-flight guard and dropped
errors via `void` -- `frontend/src/lib/agui.ts` now owns a shared
`isSubmitting` guard between text-send and button actions, and surfaces
errors into a log instead of swallowing them; (4) the chat had no
conversation transcript -- `App.tsx` now renders one, built from the
same log; (6) `frontend/`'s Node requirement wasn't enforced without
Volta active -- `package.json` gained an `engines` field, a `.nvmrc`,
and a `frontend/README.md`. (5), the local-dev-only session model, was
already a documented Non-Goal, reinforced with a stronger docstring note
in `transports/http.py`. See `openspec/changes/build-agui-a2ui-transport/design.md`'s
matching correction section for the full reasoning per fix.

## Real vs. Designed
| Area | Status |
|---|---|
| `interaction/a2ui.py` (A2UI message building) | Real, tested against the real `@a2ui/web_core` wire schema |
| `interaction/agui.py`'s `platformops_event_to_run_finished` | Real, tested |
| `transports/http.py` (`GET /info`, `POST /runs`) | Real, tested; single-user/local-dev session handling only |
| `frontend/` (Vite + React + `@ag-ui/client` + `@a2ui/react`) | Real, compiles and builds clean; not yet verified in an actual browser |
| Browser-based OIDC login | Not implemented -- reuses `platformops login`'s on-disk session file |
| Approval-gate / execution UI | Not implemented -- no real workflow exists to route `provision`/`inquiry` into yet |
| CopilotKit Node Runtime / chat chrome | Not implemented, deliberately deferred (see Scope Decision below) |
| Multi-user session routing | Not implemented, deliberately deferred |

## Scope Decision: AG-UI + A2UI directly, no CopilotKit Runtime
The ask was AG-UI + A2UI with dynamic rendering from day one -- not
CopilotKit specifically. CopilotKit's chat chrome and Node Runtime sit
*on top of* AG-UI, not as part of the protocol itself. For this
milestone, `frontend/` uses `@ag-ui/client`'s `HttpAgent` directly
against `transports/http.py`, with `@a2ui/react`'s built-in
`basicCatalog` for dynamic rendering -- no CopilotKit Runtime, no
Next.js, no `selfManagedAgents` proxy layer. Reasons:
- A second unverified integration surface (CopilotKit Runtime's own
  `/info` discovery contract and SSE-proxying behavior) stacked on an
  already-new hand-verified AG-UI/A2UI backend buys nothing for M1 --
  nothing here needs CopilotKit's action system or provider abstraction.
- Avoids the Node-version problem entirely: this machine's system Node
  is v16.20.2 (too old for modern React tooling); `frontend/`'s own
  `volta pin node@22.23.1 npm@11.12.0` (in `frontend/package.json`)
  scopes a newer Node to that directory only, with no second Node
  process needed for a Runtime.
- CopilotKit's chat chrome can be layered on later without touching
  `transports/http.py` at all -- that decoupling is the point of AG-UI
  being transport-agnostic in the first place.

## Verified Wire Shapes
Two corrections were made mid-session after inspecting the actually
installed npm packages' real type declarations/Zod schemas/example
fixtures, rather than trusting prose documentation alone -- both are
already reflected in the shipped code, recorded here for the trail:

**AG-UI's `RunFinishedEvent`** (`ag_ui.core`, confirmed via the
installed package's Pydantic `model_fields`): the success outcome's
`result` payload sits on the event itself, not nested under `outcome` --
`RunFinishedSuccessOutcome` carries only `type`.
```json
{"type": "RUN_FINISHED", "threadId": "...", "runId": "...",
 "result": {"intent": "compliance_check", "route": "compliance_check"},
 "outcome": {"type": "success"}}
```
The interrupt case matches what `interaction/agui.py` already built
before this change:
```json
{"type": "RUN_FINISHED", "threadId": "...", "runId": "...",
 "outcome": {"type": "interrupt", "interrupts": [{"id": "...", "reason": "clarification.required", ...}]}}
```

**A2UI's v0.9 message envelope** (`@a2ui/web_core`, confirmed via its
installed `CreateSurfaceMessageSchema`/`UpdateComponentsMessageSchema`
Zod schemas and its own `00_interactive-button.json` example fixture):
a sibling `version` field with the message kind as a key, not a `type`
field:
```json
{"version": "v0.9", "createSurface": {"surfaceId": "...", "catalogId": "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"}}
{"version": "v0.9", "updateComponents": {"surfaceId": "...", "components": [
  {"id": "root", "component": "Column", "children": ["message", "choice-provision"]},
  {"id": "message", "component": "Text", "text": "Which workflow?"},
  {"id": "choice-provision-label", "component": "Text", "text": "provision"},
  {"id": "choice-provision", "component": "Button", "child": "choice-provision-label",
   "action": {"event": {"name": "<interrupt id>", "context": {"selected_choice": "provision"}}}}
]}}
```
Two shape details that don't match a naive reading of the spec prose:
`Button` has no `text` prop (`child` references a sibling `Text`
component's `id` instead), and `Button.action` is
`{"event": {"name", "context"}}`, not a bare `{"name", "context"}`.

**A2UI client action report** (`@a2ui/web_core`'s
`A2uiClientActionSchema`): `{"name": "...", "surfaceId": "...",
"sourceComponentId": "...", "timestamp": "...", "context": {...}}` --
`name` in `interaction/a2ui.py`'s output is always set to the surface's
own id, which is the wrapped `HITLEvent.event_id`, which is also the AG-UI
`Interrupt.id` (`interaction/agui.py`'s `hitl_event_to_interrupt` sets
`"id": event.event_id`). One id ties a Button click back to exactly the
interrupt it should resume, with no separate id-mapping table needed on
either side.

**`@ag-ui/client`'s `HttpAgent`** already implements the pending-interrupt
tracking `transports/remote_tui.py`'s `RemoteTUIState`/`observe_agui_event`
were hand-built to prove out for a future client:
`agent.pendingInterrupts: Interrupt[]` populates on a `RUN_FINISHED`
interrupt outcome and clears on the next successful run, and
`buildResumeArray(interrupts, responses)` builds a spec-correct
`resume[]` array. `frontend/src/lib/agui.ts` uses both directly --
no second hand-rolled protocol-state layer was needed in TypeScript.

## Endpoint Shape
```text
GET  /info    AG-UI/client discovery
POST /runs    one endpoint for both a new turn (messages) and a
              clarification resume (resume) -- matching AG-UI's own
              convention, already proven by transports/remote_tui.py's
              build_user_run_input/build_resume_run_input
```
`request_id` (the `PlatformOpsHarness` contract) is AG-UI's `threadId`;
`runId` only tags SSE frames and never reaches the harness.

## Session Handling
Single-user/local-dev only for this milestone: no browser-based OIDC
login exists. `platformops login` (unchanged, `transports/cli.py`)
still runs in a terminal and writes `.platformops/session.json`;
`transports/http.py` reads that same file fresh on every request via
`PLATFORMOPS_SESSION_PATH` (same env convention as `transports/cli.py`).
Missing or expired session returns 401 before `PlatformOpsHarness` is
ever called.

## Model Provider
`transports/http.py` is the first place in the repo that actually
constructs a model provider -- `workflows/intake/graph.py` and
`harness/core.py` both deliberately refuse to, by design, so a transport
that genuinely needs one is where that decision belongs.
`langchain-litellm`'s `ChatLiteLLM`, with the provider selected by the
`PLATFORMOPS_MODEL` identifier. The default is `openai/gpt-4o-mini`; LiteLLM
model prefixes select other providers, for example `anthropic/...`,
`ollama/...`, or an OpenAI-compatible local endpoint. Set
`PLATFORMOPS_LITELLM_API_BASE` when the selected provider needs a custom base
URL. The old `PLATFORMOPS_ANTHROPIC_MODEL` variable remains a compatibility
fallback and is translated to an `anthropic/...` identifier.

Provider credentials stay in the process environment (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or the provider's equivalent) and are never put into
LangGraph state, events, or generated artifacts. Model construction does not
make a provider request; the first real `.ainvoke()` does. Therefore importing
`transports.http` and running its tests do not require a live provider key.
The selected model must support the tool-calling behavior required by intake.

## Verification Performed
- `.venv/bin/python -m pytest tests/interaction/ tests/transports/ -q`
  -- passes, zero real model credentials anywhere.
- `npm install && npx tsc -b && npm run build` in `frontend/` -- clean,
  against the real installed `@ag-ui/client`/`@a2ui/react`/
  `@a2ui/web_core` packages.
- A real running smoke test: `uvicorn transports.http:app` (port 8000)
  + `npm run dev` (Vite, port 5173, proxying `/runs`/`/info` to 8000) +
  `curl` a Tier-2-prefixed message (`"compliance_check: ..."`, zero model
  calls) through the Vite proxy -- confirmed real `RUN_STARTED` ->
  `CUSTOM` (`a2ui.createSurface`/`a2ui.updateComponents`) -> `RUN_FINISHED`
  frames end to end.
- **Not performed**: an actual browser rendering `frontend/`'s UI and a
  real Tier-3 (LLM-backed) clarification round-trip with a live provider
  credential -- this environment has no browser and no key configured. Both
  remain manual acceptance steps before this milestone is considered fully
  proven end-to-end.

## Sources
- [AG-UI: Introduction](https://docs.ag-ui.com/introduction), [Events](https://docs.ag-ui.com/concepts/events), [Interrupts](https://docs.ag-ui.com/concepts/interrupts)
- [A2UI](https://a2ui.org/), [renderer ecosystem](https://a2ui.org/ecosystem/renderers/), [v0.9.1 specification](https://a2ui.org/specification/v0.9.1-a2ui/)
- [LiteLLM](https://docs.litellm.ai/), [LangChain LiteLLM integration](https://docs.langchain.com/oss/python/integrations/providers/litellm)
- [CopilotKit: AG-UI introduction](https://docs.copilotkit.ai/ag-ui/introduction), [self-managed agents](https://docs.copilotkit.ai/backend/self-managed-agents), [connecting a custom AG-UI backend](https://docs.copilotkit.ai/backend/ag-ui)
- [`ag-ui-protocol` on PyPI](https://pypi.org/project/ag-ui-protocol/), [`ag-ui-langgraph` on PyPI](https://pypi.org/project/ag-ui-langgraph/) (evaluated, not used -- see Scope Decision in `openspec/changes/build-agui-a2ui-transport/design.md`)
- Installed package inspection (this session, 2026-08-07): `ag_ui.core`'s
  Pydantic `model_fields`, `@a2ui/web_core`'s Zod schemas and
  `00_interactive-button.json` example fixture, `@ag-ui/client`'s
  `dist/index.d.ts` -- the source of truth for every wire shape in this
  doc, taking precedence over prose documentation where the two
  disagreed.

## How this relates to the existing docs
Extends [TRANSPORTS.md](TRANSPORTS.md)'s HTTP/SSE section from designed-only
to real for `transports/http.py`'s endpoints, and
[INTERACTION_LAYER.md](INTERACTION_LAYER.md)'s "documented future web
path" from designed-only to real for the AG-UI adapter half
(`interaction/agui.py`'s success-outcome function) plus the new
`interaction/a2ui.py` -- see that doc's dated correction of its earlier
"A2UI later, fixed-schema widgets first" recommendation. Consumes
`docs/INTAKE_HITL_ROUTING.md`'s `IntakeDecision`/`resolve_route` (real as
of `openspec/changes/build-intake-dispatcher/`) as the only genuinely
routable content this milestone renders. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
