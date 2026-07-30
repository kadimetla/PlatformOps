## Why
`docs/INTAKE_HITL_ROUTING.md` designed request intake in full (scope
model, capability-based routing, HITL clarification) but nothing on
this branch is buildable yet — `workflows/`, `gateway/` don't exist.
The full design has real external dependencies (an auth layer for
`actor.execution_grants`, a policy registry, downstream workflows to
route to) that don't exist either. This change ships the smallest
slice that's genuinely buildable and testable today: the data
contracts, and intent classification alone — no routing, no grants, no
auth. It's also this repo's own proven pattern: `design/harness-
architecture`'s first intake slice was exactly this shape (one
classify node, scripted-fake-model tests, 15/15 tasks), and this
change re-derives that shape against this branch's corrected design
(`docs/INTAKE_HITL_ROUTING.md`'s C1-C6 corrections) rather than
cherry-picking that branch's code.

## What Changes
- Add `gateway/schemas.py`: `Scope`, `IntakeRequest`, `IntakeDecision`,
  `ClarificationQuestion`, the `Intent` enum (`provision` | `inquiry` |
  `compliance_check` — per C4, not the original seven-intent
  taxonomy).
- Add `workflows/intake/`: a `StateGraph` that turns `raw_text` into
  either a resolved `Intent` or a `clarifying_question` — Tier 2
  deterministic prefix match first, Tier 3 one bound-tool LLM call
  only on a miss (per A2, C3). Node count decided in design.md.
- Explicitly **out of scope for this change**: `resolve_route` /
  `POLICY` lookup, `actor.execution_grants`, the approval gate, and
  any downstream workflow dispatch. `IntakeDecision.route` stays
  `None` and `ready_to_route` stays `False` on every path this change
  produces — classification only, no routing decision yet. A follow-up
  change adds the deterministic dispatcher once there's a real route
  target to dispatch to (`compliance_check` → `spec/check_compliance.py`
  is the first candidate, per `docs/INTAKE_HITL_ROUTING.md`).

## Capabilities

### New Capabilities
- `intake-schemas`: the Pydantic data contracts every downstream
  intake/gateway piece will consume — `Scope`, `IntakeRequest`,
  `IntakeDecision`, `ClarificationQuestion`, `Intent`.
- `intake-classification`: the LangGraph workflow that classifies
  `raw_text` into an `Intent` or a clarifying question, with no
  routing/dispatch/auth attached.

### Modified Capabilities
(none — nothing existing on this branch has spec-level behavior to
change)

## Impact
- New files only: `gateway/__init__.py`, `gateway/schemas.py`,
  `workflows/__init__.py`, `workflows/intake/__init__.py`,
  `workflows/intake/state.py`, `workflows/intake/nodes.py`,
  `workflows/intake/tools.py`, `workflows/intake/graph.py`.
- New test files under `tests/` (doesn't exist yet on this branch;
  created here) — scripted fake chat model per
  `AGENTS.md`'s testing strategy, no real model credentials needed.
- One existing-file change: `pyproject.toml` gains `langgraph`,
  `langchain-core`, `pydantic` in `dependencies` — the code now
  directly imports them, and they were already implied by `AGENTS.md`'s
  stack declaration but never actually declared. No other existing
  file changes.
