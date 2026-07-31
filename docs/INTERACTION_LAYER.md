## Status
Designed and partially real as of 2026-07-31 — `interaction/events.py`
(`PlatformOpsEvent`/`HITLEvent`/`HITLResponse`) is real code; no TUI or
web UI exists, and nothing yet emits or consumes the event envelope.
First design in this project to touch the human-interaction
layer at all — every prior doc designs backend workflow/access/
execution behavior, none address how a human actually talks to
PlatformOps. AG-UI and A2UI claims verified against their own current
docs 2026-07-30 (see Sources); the TUI library choice and the
device-code login pairing are this project's own decisions, not
external claims. AG-UI's concrete event taxonomy and CopilotKit
Runtime's proxy architecture verified 2026-07-31 — deeper than the
2026-07-30 pass, which only verified AG-UI's top-level framing, not
its actual event vocabulary. **Corrected again, same day**: the first
2026-07-31 pass checked only `/concepts/events` and concluded AG-UI
has no native HITL mechanism. Checking `/concepts/interrupts` directly
shows that's wrong — see the dedicated section below. Also introduces
`HITLEvent`, the concretization of this doc's previously-unnamed
"future `EventEnvelope[T]`," now with a real target wire shape (AG-UI's
interrupt mechanism). **Corrected once more**: `HITLEvent`'s home moved
from `gateway/events.py` to `interaction/events.py` — `gateway/` is the
request/auth/policy boundary (`AUTH_BOUNDARY.md`), not a UI-rendering
concern; a third top-level package (`interaction/`) keeps that boundary
intact instead of overloading `gateway/`.

## Real vs. Designed
| Area | Status |
|---|---|
| Event envelope (any) | Real, added 2026-07-31 — `interaction/events.py`, `PlatformOpsEvent`/`HITLEvent`/`HITLResponse`; nothing emits or consumes these yet |
| TUI (any renderer) | Not implemented — no `rich`/`textual`/`prompt_toolkit` installed |
| Login entry point | Not implemented — was undecided in `build-login-schemas`, resolved here to device-code |
| AG-UI/CopilotKit web path | Not implemented, not started — documented future path only; event taxonomy, Runtime proxy pattern, and interrupt-based HITL mapping verified 2026-07-31, no code |
| `HITLEvent` / `interaction/events.py` | Real, implemented 2026-07-31 in `interaction/` (relocated out of `gateway/` same day, before code landed) — concretizes this doc's "future `EventEnvelope[T]`"; also required adding `gateway/approval.py` (`ApprovalRequest`/`ApprovalRecord`) and `ActorRef` (`gateway/auth/schemas.py`), neither of which existed as code before this |
| A2UI rich widgets | Not implemented, not started — documented future path only |

## Core Decision: TUI First, Web UI Later — Same Event Stream, Two Renderers
```
NOW:    workflow emits typed events -> TUI renders them to a terminal
LATER:  the SAME typed events -> AG-UI transport -> CopilotKit renders
        them to a browser; A2UI adds declarative rich widgets
        (approval cards, plan-diff viewers) on top
```
One event schema, defined once, transport-agnostic. Building the TUI
does not mean rebuilding the interaction layer when a web UI is
eventually wanted — it means adding a second renderer and a transport
adapter, not redesigning what gets emitted.

### Why TUI first, concretely
- No web server exists anywhere on this branch. Building one just to
  unblock login would be new infrastructure this project doesn't
  otherwise need yet.
- Pairs naturally with **device-code login** (`platformops login` →
  "go to this URL, enter this code" → poll — the same shape as `gh
  auth login`/`aws sso login`), which needs no callback URL, no
  redirect handling, no server at all.
- Fits the approval-gate interaction shape well: mostly linear
  progress, occasionally pausing for a structured choice
  (clarification options, approve/reject) — exactly what a CLI prompt
  does naturally.
- Matches this repo's actual current shape: CLI-first, no frontend
  anywhere yet.

**This resolves `build-login-schemas`'s open question.** That
change's `design.md` left "redirect vs. device-code" undecided;
corrected here, in place: **device-code**, for the reasons above.

## The Event Envelope Is a Thin Layer Over Models That Already Exist
Not new design — a serialization wrapper around what's already been
designed across the rest of this doc set:

| Event | Wraps |
|---|---|
| `intake.started` | (marks the start of an `intake_request()` call) |
| `clarification.required` | `ClarificationQuestion` (`INTAKE_HITL_ROUTING.md`) |
| `route.resolved` | `IntakeDecision` (`INTAKE_HITL_ROUTING.md`) |
| `plan.started` / `plan.summary` | `build_plan`'s output, `vibe_diff` (`PROVISION_WORKFLOW.md`) |
| `approval.required` | `ApprovalRequest` — already carries `request_id`/`scope`/`plan_digest`/`approval_digest`/`vibe_diff`/`approvals_so_far`/`required_approvals` (`EXECUTION_CREDENTIALS.md`) |
| `execution.started` / `execution.progress` | the executor sub-graph's `poll_status`/`terminal_check` (`EXECUTION_CREDENTIALS.md`) |
| `execution.completed` | `ExecutionRecord` (`EXECUTION_CREDENTIALS.md`) |

A future `EventEnvelope[T]` (kind, payload, request_id, timestamp)
wrapping these existing Pydantic models is implementation work, not a
new design decision — the payload shapes are already spec'd.

## TUI Library: Rich First, Not Textual
Neither installed yet. The interaction shape here — stream progress,
occasionally pause for a structured choice — fits **Rich**
(progress bars, live-updating text, simple prompts) better than
**Textual** (a full application framework: panes, widgets, a
persistent event loop) for a first slice. Textual becomes worth it if
a persistent "watch multiple runs at once" dashboard is actually
needed later — not designed preemptively, matching the discipline used
for every other slice in this project so far (don't build the
registry/adapter/tier before something real needs it).

## The Future Web Path — Documented, Not Built
Recommended shape, once a browser UI is actually wanted:
```
Frontend:  CopilotKit React chat
Runtime:   CopilotKit runtime or a thin AG-UI-compatible server
Backend:   the same LangGraph workflows, unchanged
Protocol:  AG-UI (transport-agnostic; SSE is PlatformOps's own choice,
           not an AG-UI requirement — see Sources)
Rich UI:   A2UI later, fixed-schema widgets first (not dynamic/
           freeform schema) — approvals and provisioning need
           predictable, reviewable UI contracts, and A2UI's
           declarative-not-executable design is a structural fit for
           that: an agent can never ship code to run, only data
           describing a UI
```
Endpoint shape, for whenever this gets built:
```
POST /runs                 starts/resumes a workflow
GET  /runs/{id}/events     AG-UI event stream (SSE)
POST /runs/{id}/actions    clarification answer / approve / reject / cancel
```
SSE over WebSocket reasoning (a PlatformOps choice, not an AG-UI
mandate): most of this interaction is one-way backend→frontend
streaming (progress, clarification requests, approval requests,
execution status) with occasional frontend→backend POSTs (send
message, answer, approve/reject, cancel) — not true bidirectional
low-latency traffic. WebSockets become worth it later for live
collaborative editing, high-frequency shared state, or multiple users
watching one run simultaneously — none of which this project needs
yet.

**AG-UI is a notably strong fit, not an arbitrary pick**: it
originated from CopilotKit's partnership with LangGraph and CrewAI —
this project's actual stack (`AGENTS.md`: "LangGraph... no more ADK")
is one of AG-UI's founding integration targets.

## AG-UI's Concrete Event Taxonomy — Verified, Not Just the Framing
The 2026-07-30 pass verified AG-UI's top-level pitch (transport-
agnostic, LangGraph-originated). It did not enumerate the protocol's
actual event types, which matters for the event-envelope mapping table
above. Verified 2026-07-31 against `docs.ag-ui.com/concepts/events`:

| AG-UI category | Concrete events | Maps to this doc's table |
|---|---|---|
| Lifecycle | `RunStarted`/`RunFinished`/`RunError`, `StepStarted`/`StepFinished` | `intake.started`, `execution.completed` |
| Text message | `TextMessageStart`/`Content`/`End` | not used yet — PlatformOps has no freeform chat surface |
| Tool call | `ToolCallStart`/`Args`/`End`/`Result` | `plan.started`/`plan.summary` (a plan is structurally a tool call) |
| State | `StateSnapshot`, `StateDelta` (JSON Patch), `MessagesSnapshot` | `execution.progress` |
| Reasoning | `ReasoningStart`/`ReasoningMessage*`/`ReasoningEnd` | not used yet |
| Special | `Raw`, `Custom` | telemetry-shaped events without a closer native fit (`plan.summary`, `execution.progress` if not modeled as `StateDelta`, `evidence.recorded`, `policy.warning`) |

**Corrected below — do not use this row for HITL.** An earlier pass of
this doc mapped `clarification.required`/`approval.required` to
`Custom` here. That was based on `/concepts/events` alone and missed a
dedicated mechanism; see "AG-UI Interrupts" immediately below for the
corrected mapping.

## AG-UI Interrupts — the Real HITL Mechanism (Corrects the Row Above)
Verified 2026-07-31 against `docs.ag-ui.com/concepts/interrupts`,
which `/concepts/events` doesn't surface — that page only lists
event *categories*, and files the interrupt-carrying extension under a
"Draft Events" heading without linking the dedicated page. AG-UI has a
**structured, first-class pause/resume primitive**, not just `Custom`:

```typescript
// RunFinished.outcome, a discriminated union
type RunFinishedOutcome =
  | { type: "success" }
  | { type: "interrupt"; interrupts: Interrupt[] }

type Interrupt = {
  id: string
  reason: string
  message?: string
  toolCallId?: string
  responseSchema?: JsonSchema
  expiresAt?: string
  metadata?: Record<string, any>
}
```
Resuming is a new run: `RunAgentInput.resume: Array<{ interruptId,
status: "resolved" | "cancelled", payload?: any }>` — every open
interrupt must be addressed, partial resumes aren't supported.

**`HITLEvent` → `Interrupt` mapping:**

| `HITLEvent` field | `Interrupt` field |
|---|---|
| `event_id` | `id` |
| `kind` (`approval.required`/`clarification.required`) | `reason` |
| `payload` (`ApprovalRequest`/`IntakeDecision`) | `metadata`, optionally schema-validated via `responseSchema` |
| `expires_at` (echoes `ApprovalRequest.approval_expires_at`) | `expiresAt` |
| `HITLResponse` (verdict/value/selected_choice) | `resume[].payload`, keyed by `resume[].interruptId` |

Example, approval:
```json
{
  "id": "hitl-approval-123",
  "reason": "approval.required",
  "message": "Approval required for invoices/dev apply.",
  "responseSchema": {
    "type": "object",
    "properties": {
      "verdict": { "enum": ["approve", "reject"] },
      "approval_digest": { "type": "string" }
    },
    "required": ["verdict", "approval_digest"]
  },
  "metadata": {
    "request_id": "req-123",
    "scope": { "org": "aiq", "bu": "it", "project": "invoices", "workspace": "dev" },
    "vibe_diff": "Create S3 bucket and CloudFront distribution",
    "required_approvals": 1,
    "approvals_so_far": []
  }
}
```
Resume: `{"resume": [{"interruptId": "hitl-approval-123", "status": "resolved", "payload": {"verdict": "approve", "approval_digest": "sha256:..."}}]}`

Example, clarification:
```json
{
  "id": "hitl-clarify-456",
  "reason": "clarification.required",
  "message": "Which workflow should handle this?",
  "responseSchema": {
    "type": "object",
    "properties": { "selected_choice": { "enum": ["provision", "inquiry", "compliance_check"] } },
    "required": ["selected_choice"]
  },
  "metadata": { "request_id": "req-456", "field": "intent", "clarification_round": 1 }
}
```
Resume: `{"resume": [{"interruptId": "hitl-clarify-456", "status": "resolved", "payload": {"selected_choice": "provision"}}]}`

**`resume_mode` (`reinvoke`/`checkpoint_resume`) stays internal to
PlatformOps.** AG-UI never sees it — externally, clarification and
approval look identical ("run finished with an interrupt" / "new run
resumes it"). The adapter alone decides whether a resume re-invokes
intake or resumes a LangGraph checkpoint; the protocol doesn't need to
know which.

**Stability caveat, not papered over**: `/concepts/events` files this
under "Draft Events"; `/concepts/interrupts` itself carries no
draft/stable marker either way — the source docs disagree with
themselves on maturity. Re-verify before building the adapter against
this; it's the right shape today, not a guaranteed-stable one.

**Given that caveat, insulate PlatformOps from AG-UI's choice, not just
its instability.** `HITLEvent` is what workflows emit and what the TUI
renders directly — neither knows or cares that AG-UI exists. Only the
future web adapter translates `HITLEvent` outward, and it alone decides
whether a given `kind` becomes a native `Interrupt` or falls back to a
`Custom` event. If AG-UI's interrupt mechanism changes, is dropped, or
never stabilizes, that decision changes inside the adapter — no
workflow, no `HITLEvent` field, and no TUI code moves. This is the same
reason `HITLEvent` wraps `IntakeDecision`/`ApprovalRequest` instead of
redeclaring their fields: one seam absorbs external churn instead of
every consumer depending on the external shape directly.

## `HITLEvent` — the Concretization of the Envelope Above
**Corrected — home is `interaction/events.py`, not `gateway/events.py`.**
`gateway/` is the request/auth/policy boundary — `AUTH_BOUNDARY.md:2-8`
draws it as `gateway/auth/` vs. `gateway/schemas.py` vs. `workflows/`,
none of which is a UI concern. `HITLEvent` doesn't fit any of those
three: it's consumed by the TUI renderer and (later) the AG-UI web
adapter, neither of which is "who is asking" or "what request entered
the system." Putting it in `gateway/` would mean gateway either grows a
UI-rendering dependency or forces the TUI/web adapter to import from a
package named for something else entirely. A third top-level package
makes the boundary explicit instead of overloading `gateway/`:

```text
gateway/            # who is asking? what request/policy applies?
  schemas.py
  dispatcher.py
  policy/            # package, not policy.py — see correction below
  auth/

workflows/           # what should happen? plan/result/evidence
  intake/
  inquiry/
  provision/
  bootstrap/

interaction/         # how do humans see/respond to workflow events?
  events.py          # PlatformOpsEvent, HITLEvent, HITLResponse, ActorRef
  tui/               # created only once the TUI is actually built
  web/               # created only once the web adapter is actually built
```
`tui/` and `web/` aren't created empty — same discipline this doc
already applies to Textual and the web path itself (don't build the
registry/adapter/tier before something real needs it). Start with
`interaction/events.py` alone.

**`PlatformOpsEvent` is the generic envelope; `HITLEvent` is a sibling,
not something nested inside it.** Progress/telemetry events
(`execution.progress`, `plan.summary`, `evidence.recorded`) are shaped
fine by a generic `kind` + `payload: dict` envelope. HITL pauses need
real typing — `payload: IntakeDecision | ApprovalRequest`, not `dict`
— so `HITLEvent` stays its own model rather than being squeezed through
`PlatformOpsEvent`'s generic shape.

`HITLEvent` wraps existing models rather than redeclaring their
fields, per this doc's "thin layer" rule above:

```python
class HITLEvent(BaseModel):
    event_id: str
    request_id: str
    kind: HITLEventKind          # CLARIFICATION_REQUIRED | APPROVAL_REQUIRED
    status: HITLStatus           # PENDING/ANSWERED/APPROVED/REJECTED/EXPIRED/CANCELLED
    actor: ActorRef | None = None
    payload: IntakeDecision | ApprovalRequest   # the real models, not a re-declared shape
    resume_mode: Literal["reinvoke", "checkpoint_resume"]
    created_at: datetime
    expires_at: datetime | None = None           # mirrors ApprovalRequest.approval_expires_at when set
```
Deliberate departures from an earlier draft of this shape:
- `payload` is `IntakeDecision | ApprovalRequest` directly — no
  separate `ClarificationPayload`/`ApprovalPayload` redeclaring fields
  those models already have (`gateway/schemas.py:58-67`,
  `docs/EXECUTION_CREDENTIALS.md:423-446`).
- `clarification_round` isn't a field here — it already lives on
  `IntakeRequest` (`gateway/schemas.py:55`, cap of 2 per
  `docs/INTAKE_HITL_ROUTING.md:17,86,260`); `HITLEvent` reads it off
  the wrapped `IntakeDecision`, doesn't own a second copy.
- `ActorRef` is a **new, minimal type** (`user_id`, `email`) — not the
  existing `Actor` (`gateway/auth/schemas.py:93-103`), which carries
  `execution_grants`/`approval_grants` and has no business being
  serialized into a wire event.
- Duplicate-approval/self-approval/digest-match checks are **not**
  this model's job — those are already enforced in-graph
  (`docs/EXECUTION_CREDENTIALS.md:393-398,782`). `HITLEvent` surfaces
  the resulting `status`; it doesn't re-implement the checks.

Supporting types:
```python
class HITLEventKind(str, Enum):
    CLARIFICATION_REQUIRED = "clarification.required"
    APPROVAL_REQUIRED = "approval.required"

class HITLStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class ActorRef(BaseModel):
    user_id: str
    email: str

class HITLResponse(BaseModel):
    event_id: str
    request_id: str
    responder: ActorRef
    verdict: HITLVerdict         # ANSWER/APPROVE/REJECT/CANCEL
    value: str | None = None
    selected_choice: str | None = None
    approval_digest: str | None = None
    responded_at: datetime

class HITLVerdict(str, Enum):
    ANSWER = "answer"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
```

## CopilotKit Runtime — the Proxy Layer, Verified
Verified 2026-07-31 against `docs.copilotkit.ai/backend/copilot-runtime`.
The Runtime is a server-side intermediary — auth, AG-UI middleware
(logging/guardrails), and routing across registered agents — sitting
between the React frontend and whatever backend actually runs the
agent. It can proxy to an external AG-UI-compatible agent via
`HttpAgent({ url: ... })`, which matches this doc's "thin AG-UI-
compatible server" framing above.

**One caveat not previously captured**: CopilotKit's own docs mark
direct `HttpAgent` connections as "intended for development and
prototyping," **not recommended for production** — the documented
production path is `selfManagedAgents` configuration instead. Doesn't
change this doc's recommendation (nothing here is being built yet, and
the distinction is a Runtime-side detail two build-outs away — TUI,
then a first pass at a web adapter), but the future web-path work
should target `selfManagedAgents`, not the `HttpAgent` example, once
it's actually built.

## Sources
- [AG-UI: Introduction](https://docs.ag-ui.com/introduction) — bidirectional, transport-agnostic ("builds on HTTP, WebSockets"), origin via CopilotKit's LangGraph/CrewAI partnership
- [AG-UI: Events concept](https://docs.ag-ui.com/concepts/events) — full event taxonomy (lifecycle/text-message/tool-call/state/reasoning/special); files interrupt-carrying extensions under "Draft Events," easy to miss — see the dedicated interrupts source below, which corrects the "no native HITL event" reading of this page alone
- [AG-UI: Interrupts concept](https://docs.ag-ui.com/concepts/interrupts) — the actual native HITL mechanism (`RunFinished` interrupt outcome, `resume` array); no draft/stable marker on the page itself, contradicting the "Draft Events" label on the events-overview page
- [A2UI](https://a2ui.org/) — declarative, not executable; created by Google with CopilotKit contributions
- [A2UI on GitHub](https://github.com/a2ui-project/a2ui) — Apache 2.0, active development
- [CopilotKit: AG-UI introduction](https://docs.copilotkit.ai/ag-ui/introduction) — AG-UI vs. MCP layering (agent-to-UI vs. agent-to-tools)
- [CopilotKit: Copilot Runtime](https://docs.copilotkit.ai/backend/copilot-runtime) — Runtime's auth/middleware/routing role; `HttpAgent` proxy pattern; dev-only vs. `selfManagedAgents` for production

## How this relates to the existing docs
First doc to address the interaction layer — every other doc in this
set designs backend behavior only. Consumes
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s `IntakeDecision`/
`ClarificationQuestion`, [PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md)'s
plan/`vibe_diff`, and
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s
`ApprovalRequest`/`ExecutionRecord` as event payloads without changing
any of them. Corrects `openspec/changes/build-login-schemas`'s open
"redirect vs. device-code" question in place — device-code, per this
doc's TUI-first decision. `HITLEvent` wraps `IntakeDecision`
(`INTAKE_HITL_ROUTING.md`) and `ApprovalRequest`
(`EXECUTION_CREDENTIALS.md`) directly rather than redeclaring their
fields, and its `ActorRef` is a new minimal type distinct from
`AUTH_BOUNDARY.md`/`gateway/auth/schemas.py`'s `Actor` (which carries
grants and shouldn't be serialized into a wire event). Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
