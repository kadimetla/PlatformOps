## Context
`interaction/tui.py` (terminal) and `transports/remote_tui.py`
(protocol-state only, no network) exist; nothing serves a browser.
`docs/INTERACTION_LAYER.md` designed the eventual web path (CopilotKit
React + AG-UI + A2UI) but flagged it "documented future path only." This
change builds the backend half of that path for real, narrowed to what's
genuinely buildable today: only the `compliance_check` intent resolves to
a real route (`workflows/intake/nodes.py`'s `resolve_route`); no
approval/execution workflow exists to build UI for.

Two rounds of live verification against installed npm packages (not
prose docs) corrected assumptions made earlier in the same design
session:
1. `ag_ui.core`'s real Pydantic models showed `RunFinishedEvent.result`
   sits on the event itself, not nested under `outcome` for the success
   case (`RunFinishedSuccessOutcome` carries only `type`).
2. `@a2ui/web_core`'s real Zod schemas and example fixtures showed A2UI
   messages carry a sibling `version` field with the message kind as a
   key (`{version, createSurface: {...}}`), not a `type` field; and
   components compose via `Column.children: [id, ...]` referencing
   sibling components by id, with `Button.child: <id>` for its label
   (no `text` prop on Button) and `Button.action.event.{name,context}`
   for the click-report shape (not a bare `action.{name,context}`).

Both corrections are already applied in the actual code this change
ships -- this section records why the shapes look the way they do, not a
pending TODO.

## Goals / Non-Goals

**Goals:**
- `transports/http.py` proves the backend contract a browser AG-UI
  client can drive today, using real `ag-ui-protocol` types throughout
  (`RunAgentInput`, `RunStartedEvent`, `CustomEvent`, `RunFinishedEvent`)
  rather than bare dicts at the transport boundary -- `interaction/agui.py`
  still returns plain dicts internally (its own established, deliberate
  design), but `transports/http.py` constructs real `ag_ui.core` event
  objects from them before encoding, so a malformed dict fails loudly at
  construction time, not silently over the wire.
- `interaction/a2ui.py` renders every HITL/route-resolved outcome using
  only `@a2ui/react`'s built-in `basicCatalog` components (`Column`,
  `Text`, `Button`) -- no custom catalog to register or keep in sync
  between backend and frontend.
- Session handling stays exactly as narrow as the real current auth
  surface: no browser login, no multi-user routing, just the same
  on-disk file `platformops login` already writes.

**Non-Goals:**
- No `Scope`/per-org_bu policy integration -- `IntakeRequest` still has
  no `scope` field (`build-intake-dispatcher`'s non-goal, unchanged).
- No approval-gate rendering path exercised -- `interaction/a2ui.py`'s
  `hitl_event_to_a2ui_messages` handles `HITLEventKind.APPROVAL_REQUIRED`
  generically (same responseSchema-driven logic as the clarification
  case) since `HITLEvent`'s type covers both, but nothing in the current
  system ever produces an approval-required event yet.
- No CopilotKit Node Runtime, no Next.js -- `@ag-ui/client`'s `HttpAgent`
  talks AG-UI directly to `transports/http.py`; CopilotKit's chat chrome
  can be layered on later without touching this backend at all.
- No production session/auth hardening -- single on-disk file, re-read
  every request, no cookie/header-based multi-tenancy.

## Decisions

**`transports/http.py` computes `result` before opening the SSE stream,
not inside the async generator.** An `HTTPException` raised after the
first `yield` can't change a response whose 200 status and headers are
already sent -- it just aborts the stream mid-flight instead of
producing a clean 4xx. All validation (`_extract_text`/`_extract_answer`)
and the `harness.start_run`/`resume_clarification` call (whose `ValueError`
covers session expiry races, round-cap exhaustion, malformed resume, no
pending clarification) happen in the route handler body; the async
generator that follows only shapes an already-computed `result` into SSE
frames and cannot fail in a way that needs an HTTP status code.

**One `POST /runs` endpoint, not a separate resume endpoint.** AG-UI's
own convention -- already proven by `transports/remote_tui.py`'s
`build_user_run_input`/`build_resume_run_input`, which both build the
same `{threadId, runId, messages|resume}` shape -- is a resume is
another run on the same thread, distinguished by which field is present.
A separate `/actions` endpoint would diverge from what `@ag-ui/client`'s
`HttpAgent` actually posts.

**`_build_model()` lives in `transports/http.py`, not `harness/core.py`
or `workflows/intake/graph.py`.** Both of those modules deliberately
refuse to pick an LLM provider (their own docstrings state this
explicitly) so the decision isn't made by accident. A transport is where
that decision belongs -- `transports/cli.py`'s `_handle_run` already
established the pattern of failing clearly rather than guessing; this
transport is the first to actually need a real model, so it's the first
to make the call. `ChatAnthropic()`'s construction doesn't require
`ANTHROPIC_API_KEY` eagerly (verified directly against the installed
`langchain-anthropic` package -- validation happens at the first real
`.ainvoke()` call, not construction), so the module-level
`app = create_app(model=_build_model(), ...)` line never blocks test
collection or import in an environment with no key configured.

**`interaction/a2ui.py` renders `Column` + flat sibling `Text`/`Button`
components, not a `Card`.** The verified example fixture
(`@a2ui/web_core`'s own `00_interactive-button.json`) demonstrates
`Column`/`Text`/`Button` concretely; `Card`'s exact prop schema was never
independently verified in this session. Building only what's confirmed
against real installed source, rather than a plausible-looking but
unverified shape, matches this repo's verify-before-build discipline.

**Button labels are separate `Text` components referenced via `child`,
not a `text` prop on Button.** `ButtonApi`'s real Zod schema
(`basic_components.d.ts`) has no `text` field -- only `child: string`
(a component id) and `action`. `hitl_event_to_a2ui_messages` creates a
sibling `{id: "choice-<x>-label", component: "Text", text: <x>}` for
each choice and points the Button's `child` at it.

## Risks / Trade-offs
- [Risk] `transports/http.py`'s SSE frames were verified by constructing
  real `ag_ui.core` Pydantic objects from every dict shape this change
  produces (confirmed no `ValidationError`), and by an actual running
  smoke test (uvicorn + vite dev server + curl through the proxy,
  Tier-2 zero-model path) in the session that built this change -- but
  no real browser ever rendered the A2UI surfaces, since this
  environment has no browser to drive. → [Mitigation] `npm run build`
  and `tsc -b` both pass cleanly against the real installed
  `@ag-ui/client`/`@a2ui/react`/`@a2ui/web_core` type declarations,
  which is the strongest verification available without a browser;
  flagged in `docs/WEB_CHAT_APP.md` as the one remaining manual smoke-test
  step before considering this fully proven.
- [Risk] `ChatAnthropic`'s lazy API-key validation means a misconfigured
  deployment won't fail until the first real (non-Tier-2) chat message
  arrives, not at server startup → [Mitigation] accepted; matches
  `transports/cli.py`'s existing "fail clearly at the point of use, not
  speculatively" discipline, and a startup-time check would need to make
  a real API call (cost, latency) just to validate a key.
- [Risk] Single on-disk session file re-read on every request has no
  meaningful security boundary beyond local-machine file permissions
  (already `chmod 0o600` by `gateway/auth/cli.py`'s `write_session`) →
  [Mitigation] explicitly single-user/local-dev only, stated as a
  Non-Goal; multi-user auth is a distinct, larger follow-up.

## Migration Plan
1. `interaction/agui.py`: add `platformops_event_to_run_finished` +
   test.
2. `interaction/a2ui.py` (new) + tests -- pure dict-in/dict-out, no new
   runtime deps beyond what (1) already uses.
3. `pyproject.toml`/`​.env.example`: add `fastapi`, `uvicorn`,
   `ag-ui-protocol`, `langchain-anthropic`; `ANTHROPIC_API_KEY` and
   related vars.
4. `transports/http.py` (new) + tests -- depends on (1)-(3).
5. `frontend/` (new) -- depends on the SSE frame shapes from (2)/(4)
   being real; `npm install && npm run build` verified clean in the
   session that built this change.
6. Docs: `docs/WEB_CHAT_APP.md` (new), corrections to
   `docs/INTERACTION_LAYER.md`/`docs/TRANSPORTS.md`/`docs/HARNESS_DESIGN.md`.

No cutover step -- purely additive; nothing existing changes behavior
except `interaction/agui.py` gaining one new function.

## Open Questions
- Whether `Card`'s real prop schema should be verified and adopted for a
  richer result display later, instead of a flat `Column` of `Text`
  fields -- deferred, not needed for this milestone's content.
- Whether CopilotKit's chat chrome gets layered on in a later milestone
  -- explicitly deferred, not decided against permanently (see
  docs/WEB_CHAT_APP.md's Scope Decision).

## Corrected 2026-08-07 (review pass)
A review of the first version of this change found real gaps, fixed in
place rather than left as follow-ups:

**Approval buttons removed, not completed.** The original
`hitl_event_to_a2ui_messages` rendered a `Button` for every
`responseSchema` enum choice regardless of `HITLEventKind` -- including
`APPROVAL_REQUIRED`'s `verdict` choices, whose click context
(`{"verdict": "approve"}`) never included `approval_digest`, and whose
resume path (`harness/core.py`'s `resume_approval`) doesn't exist.
Alternative considered: thread `approval_digest` through and add
`resume_approval` to the harness -- rejected, since there is no
checkpointed approval-gate workflow to resume *into* yet (the harness's
own pre-existing docstring already said this explicitly before this
change ever touched it). Building resume plumbing with nowhere real to
route to would be exactly the speculative-infrastructure-ahead-of-need
pattern this repo's other docs reject repeatedly. The correct fix at
this milestone's actual boundary is to stop presenting an affordance
that can never work: `hitl_event_to_a2ui_messages` now renders buttons
only for `CLARIFICATION_REQUIRED`.

**Resume now validates `interrupt_id` and actor identity.**
`PlatformOpsHarness._pending_intake` was `dict[str, IntakeRequest]` --
keyed only by `request_id` (AG-UI's `threadId`), so any resume naming a
known thread would succeed no matter which `interruptId` or which actor
it claimed, since neither was ever recorded to check against. Now
`_pending_intake: dict[str, _PendingClarification]`
(`request`/`interrupt_id`/`actor_id`), and `resume_clarification` takes
`interrupt_id` as a required parameter, checked -- along with
`actor.actor.user_id` -- before the pending entry is popped, so a
rejected resume attempt (wrong id, wrong actor) never invalidates a
still-valid pending clarification. This also incidentally fixed the same
latent issue for the pre-existing empty-answer check, which previously
popped the entry before validating it too.

**Frontend: one shared in-flight guard, errors surfaced, transcript
added.** `frontend/src/lib/agui.ts`'s A2UI action handler had no
in-flight guard (double-clicks could fire duplicate resumes) and
discarded `agent.runAgent`'s promise with `void` (network/server errors
vanished silently). Restructured so `createPlatformOpsClient` owns
`isSubmitting`/a result-and-error log as one small external store
(`useSyncExternalStore` on the `App.tsx` side) shared by both
`sendMessage` and the action handler -- a guard only works if one place
owns the flag both call sites check. `App.tsx` renders that log as a
transcript, closing the "no conversation history" finding in the same
pass since both fixes needed the same underlying data.

**`frontend/package.json` gained an `engines` field, `frontend/.nvmrc`,
and `frontend/README.md`.** The `volta` field alone only takes effect if
Volta itself is installed and its shims are first on `PATH`; nothing
failed loudly otherwise, which is exactly what happened in the
reviewing environment (Node 16.20.2 active, Vite needs >=20.19).
`engines` makes `npm install`/`npm run build` warn explicitly instead of
failing with an unrelated-looking Vite error; `.nvmrc` covers nvm users
without Volta.

**Also fixed while touching `frontend/package.json`**:
`@a2ui/web_core` was imported directly in `agui.ts` but never declared
as a direct dependency -- only present because `@a2ui/react` pulls it in
as a peer and npm happened to hoist it. Not part of the original review,
found during this pass; now declared explicitly.

**Not fixed, deliberately (see Non-Goals)**: real `resume_approval`
plumbing, interrupt expiration enforcement, and a server-side A2UI
catalog allow-list (already true by construction -- `interaction/a2ui.py`'s
catalog/component types are hardcoded constants the LLM never
influences).
