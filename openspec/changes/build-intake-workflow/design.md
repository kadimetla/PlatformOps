## Context
`workflows/inquiry/` (real, built, `build-discovery-workflow`) proved
the pattern this change reuses again: a minimal `StateGraph` slice,
deterministic-first classification with an LLM fallback bound to a
forced tool response, tests using a scripted fake chat model, no real
model credentials needed. `docs/intent_routing_and_staged_confirmation.md`
Part A designed Stage 1 in detail before this document was written —
that analysis is incorporated directly below, not re-derived.

## Goals / Non-Goals
See `proposal.md`'s What Changes / NOT in scope sections — not
repeated here.

## Decisions

**One node, `classify_workflow`, not two.** Unlike
`workflows/inquiry/`'s `classify_resource_type` → `existence_check`
sequence (two genuinely different operations — classify, then look
up), Stage 1 is a single operation with a deterministic-first internal
branch: check Tier 2's text-prefix convention first (no LLM call), fall
back to Tier 3's `select_workflow` bound-tool call only if no prefix
matched. This mirrors `classify_resource_type`'s own internal
skip-if-already-known shape, just without a second node after it —
there's nothing after classification for this graph to do.

**Tier 2 prefixes match `workflow_hint`'s own values exactly** —
`"drafting: ..."` / `"inquiry: ..."` — not a separate vocabulary
(`docs/intent_routing_and_staged_confirmation.md` Part A used
`"discovery: ..."` as an example before the `workflows/discovery/` →
`workflows/inquiry/` rename; this change uses the current names
directly rather than introduce a third naming layer between the prefix
convention and the workflow package name).

**`workflow_hint`'s candidate set is exactly the two real workflow
package names**, `"drafting"` and `"inquiry"` — resolves
`docs/intent_routing_and_staged_confirmation.md`'s open question
("assumed yes [equals] the `WORKFLOW_REGISTRY` keys, not confirmed").
There is no `WORKFLOW_REGISTRY` built anywhere; the candidate list is a
plain tuple in `workflows/intake/tools.py`, extended by hand as new
workflows are built — matching this project's "don't build the
registry before a third workflow exists to need one" discipline
(the same reasoning `workflows/inquiry/design.md` used to defer a
router until a second real branch existed).

**`IntakeRequest`/`IntakeResult` as new, explicit Pydantic models**, not
reusing `RequestEnvelope`/`InquiryQuery` directly — an intake request
needs raw text plus already-resolved identity, an intake result needs
either a resolved hint or a clarifying question, neither of which any
existing model shape represents:

```python
class IntakeRequest(BaseModel):
    org_id: str
    bu_id: str
    raw_text: str

class IntakeResult(BaseModel):
    workflow_hint: Optional[str] = None       # "drafting" | "inquiry"
    clarifying_question: Optional[str] = None
```

`org_id`/`bu_id` are accepted as given, never parsed from `raw_text` —
same hard rule `docs/intent_routing_and_staged_confirmation.md` Part A
states for every stage in this pipeline, and the same constraint
`workflows/inquiry/`'s `InquiryQuery` already enforces.

**Tier 3 uses one direct `ChatLiteLLM` call, not `create_react_agent`**
— identical reasoning to `workflows/inquiry/`'s `classify_resource_type`:
a single-shot classification, not a multi-turn tool-calling
conversation. Enforcement is prompt-based (candidates listed in the
system message, "call exactly once" instruction), matching
`select_resource_type`'s own convention rather than relying on an
unverified forced-`tool_choice` API shape.

**No pause/resume mechanism for the ambiguous case.** An unresolved
classification returns `IntakeResult(clarifying_question=...)` as plain
data — the caller decides what to do with it (today: a test asserts on
it; eventually: a channel adapter shows it and re-invokes
`intake_request()` with the clarification appended to `raw_text`).
This is deliberately the same "show, don't block" shape
`workflows/inquiry/` already uses for its own unresolvable case, applied
one level upstream — not a new pattern.

## Risks / Trade-offs
- [Risk] Tier 2's prefix convention is a hard product decision (exact
  strings, case sensitivity, whether other prefixes like "audit:" get
  reserved now for a workflow that doesn't exist yet) →
  [Mitigation] scoped to exactly `"drafting:"` / `"inquiry:"`,
  case-sensitive, no reservation of unused prefixes — extend when a
  third workflow is real, not before.
- [Risk] Tier 3's candidate list is a plain tuple, not derived from
  anything that would catch a typo if a third workflow is added later
  without updating it → [Mitigation] accepted for this slice; a real
  `WORKFLOW_REGISTRY` is the natural fix once a third workflow exists,
  not designed defensively against that now.
- [Risk] Without dispatch or a channel adapter, `intake_request()` has
  no real caller yet, same as `discover_request()` at the point
  `build-discovery-workflow` shipped it → [Mitigation] accepted,
  identical precedent; a callable, tested contract is the deliverable,
  not a wired end-to-end path.

## Migration Plan
1. Add `IntakeRequest`/`IntakeResult`/`IntakeState` to
   `workflows/intake/state.py`.
2. Add `select_workflow` bound tool to `workflows/intake/tools.py`.
3. Implement `classify_workflow` node (Tier 2 then Tier 3) in
   `workflows/intake/nodes.py`.
4. Build the one-node graph + entry function.
5. Tests, no real model credentials needed.

No cutover step — additive, new functionality, nothing existing
changes.

## Open Questions
- Whether `intake_request()` becomes a `gateway/`-level re-export later
  — same open question `workflows/inquiry/design.md` left unresolved
  for `inquiry_request()`, not resolved here either.
- Where dispatch (workflow_hint → actual `plan_request()`/`inquiry_request()`
  call) ends up living — `gateway/`, a new thin module, or inside
  whatever channel adapter gets built first. Not designed here,
  deliberately — `proposal.md`'s explicit non-goal.
- Whether Tier 2's prefix convention should be case-insensitive or
  allow whitespace variants (`"Drafting:"`, `"  drafting: "`) — not
  decided; scoped to exact-match for this slice.
