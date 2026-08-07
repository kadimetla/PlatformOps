## 1. AG-UI wire-format completion

- [x] 1.1 `interaction/agui.py`: add `platformops_event_to_run_finished`
      (success-outcome counterpart to `hitl_event_to_run_finished`;
      `result` on the event itself, not nested under `outcome` -- verified
      against the real `ag_ui.core.RunFinishedEvent`/`RunFinishedSuccessOutcome`
      Pydantic models)
- [x] 1.2 `tests/interaction/test_agui.py`: add
      `test_platformops_event_maps_to_run_finished_success_outcome`

## 2. A2UI dynamic rendering

- [x] 2.1 `interaction/a2ui.py`: `hitl_event_to_a2ui_messages` --
      `createSurface` + `updateComponents` pair, `Column` root with a
      `Text` message and one `Button`/label-`Text` pair per choice,
      built on `hitl_event_to_interrupt`'s output
- [x] 2.2 `interaction/a2ui.py`: `platformops_event_to_a2ui_messages` --
      `createSurface` + `updateComponents` pair, `Column` of `Text`
      fields from `PlatformOpsEvent.payload`, `None` fields omitted
- [x] 2.3 Wire shape verified directly against installed
      `@a2ui/web_core`'s Zod schemas and example fixtures (not assumed):
      `{version, createSurface|updateComponents: {...}}` envelope,
      `Column.children: [id,...]`, `Button.child: <id>`,
      `Button.action.event.{name,context}`
- [x] 2.4 `tests/interaction/test_a2ui.py`: clarification/approval
      button rendering, route-resolved/unsupported field rendering

## 3. HTTP/SSE transport

- [x] 3.1 `pyproject.toml`: add `fastapi`, `uvicorn`, `ag-ui-protocol`,
      `langchain-anthropic`; `uv sync --extra dev`
- [x] 3.2 `.env.example`: add `ANTHROPIC_API_KEY`,
      `PLATFORMOPS_ANTHROPIC_MODEL`, and the previously-undocumented
      `PLATFORMOPS_OIDC_*`/`PLATFORMOPS_SESSION_PATH` vars
- [x] 3.3 `transports/http.py`: `create_app(*, model, session_path)`,
      `GET /info`, `POST /runs` (branches on `messages` vs `resume`,
      matching AG-UI's one-endpoint convention already proven by
      `transports/remote_tui.py`)
- [x] 3.4 Session dependency reads `gateway.auth.sessions.read_session`
      fresh every request; missing/expired -> 401 before the harness is
      ever called
- [x] 3.5 `_build_model()`: `ChatAnthropic` + `.bind_tools([select_intent])`,
      `claude-haiku-4-5` default, `PLATFORMOPS_ANTHROPIC_MODEL` override;
      construction verified not to require `ANTHROPIC_API_KEY` eagerly
- [x] 3.6 `tests/transports/test_http.py`: Tier-2 zero-model path,
      clarification interrupt + resume round-trip, missing/expired
      session -> 401, malformed resume -> 400, `/info` endpoint

## 4. Frontend scaffold

- [x] 4.1 `frontend/`: Vite + React + TypeScript, `volta pin node@22.23.1
      npm@11.12.0` scoped to this directory only (system Node untouched)
- [x] 4.2 `@ag-ui/client` (`HttpAgent`, `buildResumeArray`), `@a2ui/react`
      + `@a2ui/web_core` (`MessageProcessor`, `basicCatalog`, `A2uiSurface`)
- [x] 4.3 `src/lib/agui.ts`: thin client wrapper -- `HttpAgent` +
      `MessageProcessor` wiring, action-to-resume mapping via
      `agent.pendingInterrupts`
- [x] 4.4 `src/App.tsx`: chat input + surface rendering, following
      `@a2ui/react`'s own documented `onSurfaceCreated`/`onSurfaceDeleted`
      pattern
- [x] 4.5 `npm install`, `tsc -b`, `npm run build` all verified clean
      against the real installed packages

## 5. End-to-end verification

- [x] 5.1 `.venv/bin/python -m pytest tests/interaction/ tests/transports/ -q`
      -- all pass, zero real model credentials
- [x] 5.2 Real running smoke test: uvicorn backend + vite dev server +
      curl through the proxy, Tier-2 `compliance_check:` message,
      confirmed real SSE frames end to end (no browser available in this
      environment -- browser rendering itself remains an open manual
      verification step, see design.md's Risks section)
- [x] 5.3 `openspec validate build-agui-a2ui-transport --strict` passes

## 6. Docs

- [x] 6.1 `docs/WEB_CHAT_APP.md` (new)
- [x] 6.2 `docs/INTERACTION_LAYER.md`: correct "A2UI later" line in
      place, dated note
- [x] 6.3 `docs/TRANSPORTS.md`: `transports/http.py` row
- [x] 6.4 `docs/HARNESS_DESIGN.md`: document-map entry

## 7. Review-pass fixes (2026-08-07)

- [x] 7.1 `interaction/a2ui.py`: approval events render message-only, no
      Button components (no `resume_approval` path exists to honor a
      click)
- [x] 7.2 `interaction/a2ui.py`: explicit `_ROUTE_RESULT_FIELDS`
      allow-list replaces `event.payload.items()` iteration
- [x] 7.3 `harness/core.py`: `_PendingClarification` record
      (`request`/`interrupt_id`/`actor_id`); `resume_clarification`
      takes `interrupt_id`, validates it and actor identity before
      consuming the pending entry
- [x] 7.4 `transports/http.py`: `_extract_answer` returns
      `(interrupt_id, answer)`, threaded into
      `harness.resume_clarification`; docstring notes in-memory pending
      state is lost on restart/multi-worker
- [x] 7.5 `frontend/src/lib/agui.ts`: `createPlatformOpsClient` owns a
      shared `isSubmitting` guard + result/error log as one external
      store; `handleAction` and `sendMessage` both check it; errors
      caught and logged instead of `void`-dropped
- [x] 7.6 `frontend/src/App.tsx`: renders the log as a transcript via
      `useSyncExternalStore`
- [x] 7.7 `frontend/package.json`: `engines` field, `@a2ui/web_core`
      added as an explicit direct dependency (was transitive-only
      despite being imported directly); `frontend/.nvmrc`,
      `frontend/README.md` (new)
- [x] 7.8 Tests updated/added:
      `tests/interaction/test_a2ui.py` (approval message-only,
      unlisted-field-never-renders), `tests/harness/test_core.py`
      (wrong-interrupt-id, wrong-actor, all `resume_clarification` call
      sites updated), `tests/transports/test_http.py`
      (wrong-interrupt-id-for-a-real-thread -> 400)
- [x] 7.9 `openspec/changes/build-agui-a2ui-transport/specs/`: dated
      corrections to `a2ui-rendering` (approval buttons, explicit field
      list) and `http-transport` (new interrupt/actor validation
      requirement)
- [x] 7.10 `openspec validate build-agui-a2ui-transport --strict` passes
      (re-verify after spec edits)
