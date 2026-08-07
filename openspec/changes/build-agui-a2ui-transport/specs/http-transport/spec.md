## ADDED Requirements

### Requirement: A single POST /runs endpoint handles both new turns and resumes
The system SHALL expose exactly one `POST /runs` endpoint that accepts
an AG-UI `RunAgentInput` body and branches on which field is present:
`messages` (a new turn, calling `PlatformOpsHarness.start_run`) or
`resume` (answering a pending interrupt, calling
`PlatformOpsHarness.resume_clarification`). It SHALL NOT expose a
separate endpoint for resumes.

#### Scenario: A message-only body starts a new run
- **WHEN** `POST /runs` is called with `messages` set and `resume` unset
- **THEN** the handler calls `harness.start_run`

#### Scenario: A resume-only body resumes clarification
- **WHEN** `POST /runs` is called with `resume` set
- **THEN** the handler calls `harness.resume_clarification` with the
  `interrupt_id` and answer extracted from the single resume entry

### Requirement: A resume must name the exact pending interrupt and actor
**Added 2026-08-07 (review pass)** -- originally `resume_clarification`
took only `request_id`/`answer`, so any resume naming a known thread
would succeed regardless of which interrupt or which actor it claimed to
address. The system SHALL reject a resume whose `interruptId` does not
match the interrupt id the pending clarification was created with, and
SHALL reject a resume submitted by an actor other than the one who
started the run, both as HTTP 400 -- before the pending clarification is
consumed, so a rejected attempt does not invalidate a still-resumable
pending clarification.

#### Scenario: Wrong interruptId for a real pending thread is rejected
- **WHEN** `POST /runs` resumes a thread with a real pending
  clarification, but `resume[0].interruptId` does not match the
  interrupt id that clarification was issued with
- **THEN** the response status is 400, and a subsequent resume with the
  correct `interruptId` still succeeds

#### Scenario: A different actor's resume is rejected
- **WHEN** the resuming session's actor differs from the actor who
  started the run that produced the pending interrupt
- **THEN** `harness.resume_clarification` raises `ValueError`, which the
  handler translates to HTTP 400

### Requirement: request_id is the AG-UI threadId; runId only tags frames
The system SHALL pass `RunAgentInput.thread_id` as the `request_id`
argument to `PlatformOpsHarness.start_run`/`resume_clarification` --
stable across a clarification round-trip, matching what
`PlatformOpsHarness._pending_intake` is keyed by. `RunAgentInput.run_id`
SHALL be used only to tag the SSE frames of that one call and SHALL NOT
be passed into the harness.

#### Scenario: Same threadId resumes the same pending clarification
- **WHEN** a resume call carries the same `threadId` as the run that
  produced the pending interrupt
- **THEN** `harness.resume_clarification` finds and resolves that
  pending clarification

### Requirement: All failure handling completes before the SSE stream opens
The system SHALL compute the harness result and validate the request
body entirely within the route handler, before constructing the
`StreamingResponse`. A `ValueError` from the harness (expired session
race, empty answer, round-cap exhaustion, no pending clarification, or
similar) SHALL be translated to an HTTP 400 response. The system SHALL
NOT raise an HTTP-status-bearing exception from inside the SSE
generator after the first frame has been yielded, since the response's
status and headers are already committed by that point.

#### Scenario: Malformed resume returns a clean 400, not a broken stream
- **WHEN** `POST /runs` resumes an interrupt id that has no pending
  clarification
- **THEN** the response status is 400 and no SSE frames are sent

#### Scenario: Round-cap exhaustion returns a clean 400
- **WHEN** a resume would exceed `PlatformOpsHarness`'s clarification
  round cap
- **THEN** the response status is 400

### Requirement: Missing or expired session returns 401 before the harness runs
The system SHALL read the `ActorSession` from the configured
`session_path` on every request (not cached), and SHALL return HTTP 401
if the file does not exist or the session `is_expired`, without ever
calling into `PlatformOpsHarness`.

#### Scenario: No session file yields 401
- **WHEN** `POST /runs` is called and `session_path` does not exist
- **THEN** the response status is 401 and the harness is never invoked

#### Scenario: Expired session yields 401
- **WHEN** `POST /runs` is called and the session at `session_path` has
  `is_expired == True`
- **THEN** the response status is 401

### Requirement: The model provider is constructed lazily, never blocking import
The system SHALL construct its `ChatAnthropic` model instance in a way
that does not require `ANTHROPIC_API_KEY` to be set at module-import
time -- API key validation happens on first real model invocation, not
construction. `create_app` SHALL accept `model` as an explicit parameter
so tests can inject a fake model without constructing a real one.

#### Scenario: Module import succeeds without ANTHROPIC_API_KEY set
- **WHEN** `transports.http` is imported in an environment with no
  `ANTHROPIC_API_KEY`
- **THEN** import succeeds without raising

#### Scenario: Tests never construct a real model
- **WHEN** a test calls `create_app(model=<fake>, session_path=<tmp path>)`
- **THEN** no real network call or API credential is required anywhere
  in the test run

### Requirement: SSE frames use real ag_ui.core event types, encoded via EventEncoder
The system SHALL construct `ag_ui.core.RunStartedEvent`,
`ag_ui.core.CustomEvent`, and `ag_ui.core.RunFinishedEvent` instances
(not bare dicts) for each SSE frame, and SHALL encode them with
`ag_ui.encoder.EventEncoder` rather than hand-formatting SSE `data:`
lines.

#### Scenario: A malformed frame dict fails at construction, not silently over the wire
- **WHEN** an internal dict produced by `interaction/agui.py` or
  `interaction/a2ui.py` does not match `ag_ui.core`'s real Pydantic
  schema for the corresponding event type
- **THEN** constructing the `ag_ui.core` event object raises a validation
  error before any bytes are sent
