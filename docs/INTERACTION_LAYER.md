## Status
Designed only. No TUI, event envelope, or web UI code exists on this
branch. First design in this project to touch the human-interaction
layer at all — every prior doc designs backend workflow/access/
execution behavior, none address how a human actually talks to
PlatformOps. AG-UI and A2UI claims verified against their own current
docs 2026-07-30 (see Sources); the TUI library choice and the
device-code login pairing are this project's own decisions, not
external claims. AG-UI's concrete event taxonomy and CopilotKit
Runtime's proxy architecture verified 2026-07-31 — deeper than the
2026-07-30 pass, which only verified AG-UI's top-level framing, not
its actual event vocabulary.

## Real vs. Designed
| Area | Status |
|---|---|
| Event envelope (any) | Not implemented |
| TUI (any renderer) | Not implemented — no `rich`/`textual`/`prompt_toolkit` installed |
| Login entry point | Not implemented — was undecided in `build-login-schemas`, resolved here to device-code |
| AG-UI/CopilotKit web path | Not implemented, not started — documented future path only; event taxonomy and Runtime proxy pattern verified 2026-07-31, no code |
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
| Special | `Raw`, `Custom` | `clarification.required`, `approval.required` |

**The one finding that actually changes something**: AG-UI has **no
native event type for human-in-the-loop approval or clarification**.
There is no `ApprovalRequired` or `InputRequested` event in the
protocol — every HITL pause this project's design already relies on
(`ClarificationQuestion`, `ApprovalRequest`) would have to ride on
AG-UI's `Custom` event, not a first-class one. This doesn't block
anything (`Custom` is explicitly designed as the extension point), but
it means the web-adapter layer (`PlatformOpsEvent` → AG-UI, described
above) carries real translation weight for exactly the two event kinds
this project's HITL design depends on most — worth knowing before
that adapter gets built, not after.

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
- [AG-UI: Events concept](https://docs.ag-ui.com/concepts/events) — full event taxonomy (lifecycle/text-message/tool-call/state/reasoning/special); confirms no native approval/HITL event type
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
doc's TUI-first decision. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
