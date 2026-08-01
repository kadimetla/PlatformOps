## Status
Designed and partially real as of 2026-07-31. `harness/core.py`'s
`PlatformOpsHarness` is real, tested code (`start_run`/
`resume_clarification` only). Multi-session/multi-actor invocation
(`ThreadState`/`RunState`/`EventRecord`) is designed only, added same
day — no persistence, no approval flow, no concurrency control exists
yet. **Naming note**: this is unrelated to `docs/HARNESS_DESIGN.md`
(this repo's doc-map file, named per `AGENTS.md`'s convention, itself
referencing a differently-scoped `design/harness-architecture`
exploration branch) — same word, two unrelated things. Not renamed to
avoid the collision because `PlatformOpsHarness` was the name decided
in the design conversation that produced it; flagged here instead so
it isn't confused later. **Second naming note, verified 2026-07-31
against OpenClaw's own docs** (see Sources): "borrow OpenClaw's
harness pattern" was the stated motivation for this design, but
OpenClaw's own "harness" is a different concept than what got built
here — see the correction below before treating OpenClaw's harness
contract as precedent for anything in this file.

## Real vs. Designed
| Item | Status |
|---|---|
| `PlatformOpsHarness.start_run()` | Real — session validation + intake classification, wrapped as `HITLEvent`/`PlatformOpsEvent` |
| `PlatformOpsHarness.resume_clarification()` | Real — reinvokes intake with combined text, enforces the 2-round cap before asking a third question |
| Routing past classification (`route.resolved` → an actual provision/inquiry/bootstrap workflow) | Not implemented — no dispatcher, no downstream workflow exists to route to |
| Approval resume (`resume_mode="checkpoint_resume"`) | Not implemented — no `resume_approval()` method exists; would need a real LangGraph checkpointer behind a provision/inquiry workflow, neither of which exists |
| Any transport actually calling the harness | Not implemented — `transports/cli.py`'s `run` command still fails clearly on "no model provider configured" rather than constructing a harness; wiring it in doesn't unblock that decision, it just moves where the same failure would happen |
| `ThreadState`/`RunState`/`EventRecord` (multi-session/multi-actor invocation) | Designed only, added 2026-07-31 — no persistence, no approver-vs-requester authorization, no concurrency control; `harness/core.py` has no concept of a thread today, only a per-`request_id` clarification dict |
| Approver-resumes-requester's-thread authorization | Designed only — depends on both the approval flow (`resume_approval`, not built) and `ThreadState`, neither of which exists |

## Why This, Why Now
The question that prompted this: without a running web API, how does
"local CLI/TUI directly" actually work? Answer: it doesn't need a web
API — the harness is what sits below every transport (`docs/TRANSPORTS.md`),
and a local transport can call it as a plain Python object with no
network involved at all. A future HTTP/WebSocket/Teams/Google Chat
transport becomes a thin shell around the same harness — `POST /runs`
calls `start_run()`, `POST /runs/{id}/resume` calls
`resume_clarification()` (and later `resume_approval()`) — not a
second implementation of what a request means or how it's answered.

```
CLI/TUI local, HTTP API, WebSocket remote TUI, Teams, Google Chat
                          |
                          v
                 PlatformOpsHarness
                          |
                          v
                 gateway + workflows
```

## What `PlatformOpsHarness` Actually Does
```python
class PlatformOpsHarness:
    def __init__(self, model): ...

    async def start_run(self, actor: ActorSession, request_id: str, text: str) -> HITLEvent | PlatformOpsEvent: ...
    async def resume_clarification(self, actor: ActorSession, request_id: str, answer: str) -> HITLEvent | PlatformOpsEvent: ...
```
- **Requires a caller-provided `model`**, exactly like `workflows.intake.graph.intake_request` already does. This project still hasn't chosen an LLM provider — the harness doesn't invent one either; the same undecided dependency just moved up one layer.
- **`start_run`** rejects an expired `ActorSession`, then calls `intake_request`. A clarification result is wrapped as a `HITLEvent` (`resume_mode="reinvoke"`); a resolved intent is wrapped as a `PlatformOpsEvent(kind=EventKind.ROUTE_RESOLVED, payload={"intent": ...})` — deliberately not called "routed," since nothing consumes that intent yet.
- **`resume_clarification`** looks up the original `IntakeRequest` from an in-memory `dict[str, IntakeRequest]` keyed by `request_id` (the harness owns this — `HITLEvent`/`IntakeDecision` don't carry the original request text, so something has to remember it across the pause), appends the answer, increments `clarification_round`, and reinvokes. Enforces `docs/INTAKE_HITL_ROUTING.md`'s cap of 2 clarification rounds itself, before a third model call, not after.
- **No `resume_approval`.** Would need to resume a real LangGraph checkpoint from a provision/inquiry workflow. Neither exists. Adding a method that can't actually do anything would be exactly the "declare a decision by accident" failure mode this doc set keeps calling out — left absent instead.

## OpenClaw Comparison — Verified, Naming Is Inverted
Verified 2026-07-31 directly against OpenClaw's own docs (see
Sources), not accepted secondhand. The spirit of "borrow the
runtime/harness split" holds up: OpenClaw's runtime core really does
resolve provider/model, auth, workspace, tool policy, and streaming
callbacks *before* invoking anything harness-shaped, and a harness
really doesn't own those. But the two systems' "harness" doesn't mean
the same thing:

| | OpenClaw | This doc |
|---|---|---|
| **"Harness"** | Narrow, swappable single-turn executor. `supports(ctx)` checks provider/model-route compatibility; `runAttempt(params)` runs one turn with everything already resolved. Doesn't own session/thread lifecycle, provider selection, or channel delivery. | `PlatformOpsHarness` — owns session validation, request/thread bookkeeping, calling the workflow, wrapping results as events, the resume lifecycle |
| **What plays OpenClaw's actual "runtime core" role** | `src/agents/runtime/`, `src/agents/embedded-agent-runner/` — session persistence, provider/model selection, workspace/tool policy resolution | `PlatformOpsHarness`, i.e. **this is architecturally OpenClaw's core, not OpenClaw's harness** |
| **What would be PlatformOps's actual analog to OpenClaw's harness** | — | Not built. Closest fit: `PROVISION_WORKFLOW.md`'s toolchain selection (`ccapi`/`hcp_terraform`/`opentofu_local`, picked by what's compatible/available for a target) — a swappable single-step executor, selected by compatibility, exactly OpenClaw's harness shape |

Doesn't invalidate anything above — `PlatformOpsHarness` is real, tested, and doing a coherent job regardless of what OpenClaw calls the equivalent piece. Corrected here so a future doc doesn't cite OpenClaw's harness contract (`supports`/`runAttempt`) as precedent for something that's actually playing OpenClaw's core's role, which would be citing the wrong page.

## Multi-Session Invocation — Designed, Not Built
Three distinct cases, all requiring state `harness/core.py` doesn't
have today (it has only an in-memory `dict[str, IntakeRequest]` keyed
by `request_id` — no thread concept, no approval flow to authorize
against):

**1. Same actor, multiple sessions** (e.g. Alice logged in via TUI and
browser). Both may view Alice's own threads if policy allows. The
harness must still enforce same `actor_id`, same tenant/org scope, and
an unexpired session on whichever one resumes.

**2. Different actors on the same thread — approval.** The case that
actually matters: Alice starts a provision run, Bob approves it.
```
Alice session: start_run() -> thread enters approval.required
Bob session:   resume_run(thread_id, approval_response)
```
A thread is not owned solely by its requester. Access rules, not yet
enforced anywhere because `resume_approval` doesn't exist:
- the requester may view/respond to *clarification* on their own thread
- an authorized approver (has `approval_grant` for the target scope,
  is not the requester, `approval_digest` still matches, approval is
  still pending) may approve/reject an *approval* gate
- admins/auditors may view evidence per policy, separately from either

**3. Many concurrent runs.** Threads are independent; each carries its
own requester, status, events, pending interrupts, checkpoint id, and
policy snapshot id. Concurrency rule: **one active run per thread,
many threads per actor, many actors per system** — this is what
prevents two resumes racing on the same approval gate, and is a
structural constraint on any future persistence layer, not an
optimization.

Minimal shape for what this would need:
```python
class ThreadState(BaseModel):
    thread_id: str
    requester: ActorRef
    status: str
    pending_interrupt_ids: list[str]
    checkpoint_id: str | None
    policy_snapshot_id: str
    created_at: datetime
    updated_at: datetime

class RunState(BaseModel):
    run_id: str
    thread_id: str
    request_id: str
    status: str
    started_at: datetime
    finished_at: datetime | None

class EventRecord(BaseModel):
    event_id: str
    thread_id: str
    run_id: str
    request_id: str
    event: PlatformOpsEvent | HITLEvent
    created_at: datetime
```
**Not built, and deliberately not designed further than this shape
right now**: where this state lives is the same open question raised
earlier for policy config (YAML now, Postgres later, never written to
a doc — chat-only so far) — in-memory matches `harness/core.py`'s
current pattern and this project's MVP discipline, but `ThreadState`
is exactly the kind of session/approval/execution-record state that
discussion anticipated moving to Postgres once this becomes a
real, always-on service. Picking one is a separate decision, not
assumed here.

## What This Doesn't Solve
- **The model-provider decision.** `transports/cli.py`'s `run` command is unchanged — it still prints "no model provider configured" and exits. Wiring it to construct a `PlatformOpsHarness` would just move that same failure one level deeper (the harness's `model` argument would still need a real value from somewhere). Not done here; a separate decision.
- **Routing.** `EventKind.ROUTE_RESOLVED`'s payload is just the classified intent — `gateway/dispatcher.py` (sketched in `docs/INTAKE_HITL_ROUTING.md`'s layout diagram, never built) would be what actually turns that into a call to a provision/inquiry/bootstrap workflow. None of those exist yet either (`docs/WORKFLOW_LIFECYCLE_PATTERN.md`).
- **Multi-transport session lookup.** `start_run`/`resume_clarification` take an already-loaded `ActorSession`, not a session ID or file path — the harness doesn't decide how a transport finds one. `transports/cli.py` already has `gateway/auth/sessions.py:read_session` for the file-based local case; an HTTP transport would resolve a session differently (e.g. a bearer token), and that's the transport's job, not the harness's.

## Sources
- [OpenClaw: agent runtime architecture](https://docs.openclaw.ai/agent-runtime-architecture) — runtime core vs. harness layering, what each owns
- [OpenClaw: agent harness SDK contract](https://docs.openclaw.ai/plugins/sdk-agent-harness) — `supports()`/`runAttempt()`, the "prepared attempt" concept, explicit list of what a harness does and doesn't own

## How this relates to the existing docs
Sits directly below [TRANSPORTS.md](TRANSPORTS.md)'s transport
boundary — transports call the harness, never `workflows/` or
`gateway/` directly, and never reimplement classification/routing/
approval logic themselves. Calls
[workflows/intake](INTAKE_HITL_ROUTING.md) exactly as designed there
(no changes), and wraps its output using
[INTERACTION_LAYER.md](INTERACTION_LAYER.md)'s `HITLEvent`/
`PlatformOpsEvent` contracts, also unchanged. The clarification-round
cap enforced here is the same one
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) already specifies as
caller-side policy — this is that caller. The multi-session design
above depends on an approval flow that
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) already designed
(self-approval/duplicate-approval rules, `approval_digest` binding) but
this repo hasn't built — `ThreadState`'s access rules assume that
doc's rules, don't restate them. `ThreadState`/`RunState`/`EventRecord`
above are the working/episodic memory shapes in
[MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)'s six-type taxonomy —
that doc covers the other five types and doesn't restate the OpenClaw
harness-naming correction made here. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
