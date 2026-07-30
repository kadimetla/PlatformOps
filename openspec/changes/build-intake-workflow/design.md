## Context
`docs/INTAKE_HITL_ROUTING.md` is the full design (grounded and
corrected 2026-07-27/28 against `design/harness-architecture`'s real,
built `workflows/intake/`). This change implements only its
classification slice — `gateway/schemas.py` and `workflows/intake/`'s
`extract_signals`/`classify_intent` behavior — deliberately excluding
`resolve_route`, `POLICY` lookup, `actor.execution_grants`, and the
approval gate, none of which have a real dependency to attach to yet
(no auth layer, no policy registry, no downstream workflow to route
into besides a future `compliance_check` wrapper). Prior art is
reference, not something to cherry-pick: this branch's earlier code
was removed (`87b2db4`), and `design/harness-architecture` is
unmerged.

## Goals / Non-Goals
**Goals:**
- `gateway/schemas.py` defines the data contracts every later intake
  piece (dispatcher, approval gate, executor) will build on, matching
  `docs/INTAKE_HITL_ROUTING.md`'s corrected shapes exactly.
- `workflows/intake/` classifies free text into `Intent | None` +
  optional `clarifying_question`, deterministic-first, LLM only as
  fallback, testable with zero real model credentials.

**Non-Goals:**
- No routing/dispatch (`resolve_route`, `POLICY[(org_bu, intent)]`) —
  follow-up change, once `compliance_check` has a real wrapper target.
- No `actor.execution_grants` / `Scope.org`/`bu` resolution from an
  auth session — no auth layer exists on this branch. `Scope` is
  defined as a schema now; nothing populates it from a real session
  yet.
- No HITL clarification loop (caller re-invoke with
  `clarification_round`) — this change produces the
  `clarifying_question` output; the re-invoke loop is caller-side and
  has no caller yet.
- No approval gate, executor, or any cloud credential — entirely out
  of scope for classification.

## Decisions

**One node, not two — `classify_workflow`, mirroring prior art exactly.**
`docs/INTAKE_HITL_ROUTING.md`'s LangGraph exploration sketched
`extract_signals -> classify_intent` as two nodes, reasoning that once
`resolve_route` exists after them, the prefix-skip becomes a real
conditional edge. That reasoning doesn't apply to *this* change:
`resolve_route` is explicitly out of scope, so there is nothing after
classification for a second node or a conditional edge to lead to —
exactly the condition prior art's own `build-intake-workflow` used to
justify one node ("nothing after classification for this graph to
do"). This change re-derives that same one-node shape:

```python
async def classify_workflow(state: IntakeState) -> dict:
    tier2 = _tier2_prefix_match(state["request"].raw_text)
    if tier2 is not None:
        return {"result": IntakeDecision(intent=tier2, ...)}
    # Tier 3: one bound-tool call, forced choice or clarifying_question
    ...
```
A second node (or `resolve_route` itself) is added in the follow-up
change once there's a real route target — at that point the reasoning
flips back to two nodes, per `docs/INTAKE_HITL_ROUTING.md`'s original
sketch, and this decision gets revisited then, not now.

**Intent enum is the corrected three, not the original seven** (C4):
`provision | inquiry | compliance_check`. `audit`/`security_review`
aren't included at all — not even as unreachable values — since
nothing routes to them yet and adding them now would be exactly the
"reserve a prefix for a workflow that doesn't exist yet" anti-pattern
prior art explicitly rejected.

**Tier 2 prefixes match `Intent` values exactly** (`"provision: ..."`,
`"inquiry: ..."`, `"compliance_check: ..."`), case-sensitive, no
reserved-but-unused prefixes — same convention prior art used for its
two-intent set, extended to three.

**Tier 3 uses one direct model call with a bound tool, not
`create_react_agent`** — single-shot classification, not a multi-turn
conversation. Mirrors prior art's `select_workflow` tool exactly:
`select_intent(intent: str | None, clarifying_question: str | None)`,
enforced by prompt instruction (candidates listed, "call exactly once"),
not an unverified forced-`tool_choice` API shape.

**`IntakeDecision.route`/`ready_to_route` exist in the schema now but
are always `None`/`False` from this change's graph** — the fields
belong in `gateway/schemas.py` because the dispatcher change will need
them on the same model, but nothing in this change's graph populates
them meaningfully. Adding the fields now and leaving them inert is
cheaper than a schema-breaking change later, and doesn't violate
"minimum code" since the fields are zero-logic.

**No `WORKFLOW_REGISTRY`** — `Intent`'s three values are a plain enum
in `gateway/schemas.py`, extended by hand as workflows land. Same "no
registry before a third thing needs it" discipline prior art already
proved out.

## Risks / Trade-offs
- [Risk] `IntakeDecision.route`/`ready_to_route` sitting inert in the
  schema could be mistaken for "routing already works" by a future
  reader → [Mitigation] docstring on both fields states plainly they're
  unpopulated until the dispatcher change lands; this design doc is
  linked from the module docstring.
- [Risk] Tier 3's `Intent` candidate list is a plain enum with nothing
  to catch a typo if `compliance_check`'s wrapper needs a slightly
  different name later → [Mitigation] accepted, same precedent prior
  art accepted for its own candidate tuple; not defended against until
  a real second/third route target proves it matters.
- [Risk] Without a caller, `classify_workflow`'s output (especially
  `clarifying_question`) has no real consumer yet → [Mitigation]
  accepted, identical precedent to prior art's own
  `discover_request()` at the point it shipped — a callable, tested
  contract is the deliverable, not a wired end-to-end path.

## Migration Plan
1. `gateway/schemas.py`: `Intent`, `Scope`, `ClarificationQuestion`,
   `IntakeRequest`, `IntakeDecision`.
2. `workflows/intake/state.py`: `IntakeState` (TypedDict).
3. `workflows/intake/tools.py`: `select_intent` bound tool + the Tier 2
   prefix table.
4. `workflows/intake/nodes.py`: `classify_workflow` (Tier 2 then
   Tier 3).
5. `workflows/intake/graph.py`: one-node graph builder +
   `intake_request()` entry function.
6. Tests: scripted fake chat model, no real credentials — covering
   Tier 2 hit, Tier 3 resolved, Tier 3 clarification, malformed tool
   call.

No cutover step — purely additive, nothing existing changes.

## Open Questions
- Where `intake_request()` gets called from first — a CLI harness for
  manual testing, or straight to the dispatcher change. Not resolved
  here; whichever the next `openspec` change picks up.
- Exact prompt wording for Tier 3's system message — implementation
  detail, not a design decision, left to the coding step.
