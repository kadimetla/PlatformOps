**Superseded 2026-07-27 — see design.md's correction note.** This
change assumed bundle/scope resolution belongs inside intake; grounding
`plan_request()`/`inquiry_request()` directly showed both already take
`WorkspaceBundle` at their own boundary, not intake's. Continued in
`openspec/changes/build-kubernetes-provisioning-workflow/`. Left in
place, not deleted, per this project's correction convention.

## Why
`workflows/intake/`'s one-node graph (`build-intake-workflow`, shipped)
resolves *what* a request means (`"provision_stack"` vs `"inquiry"`) but
never resolves *who* is asking. `gateway/scope_gate.py`'s
`requester_has_stack_scope()` is real, tested, and completely
orphaned — grep confirms it's called only by
`tests/test_scope_gate.py` and `scripts/manual_test_cluster_flow.py`,
never from any routing/workflow code. An app-scoped requester asking to
provision a Kubernetes cluster today reaches `classify_workflow`, pays
for an LLM classification call, and only then (in a future workflow
that doesn't exist yet) would discover they're not allowed — the deny
happens too late and in the wrong place.

## What Changes
- Add `channel_user_id` to `IntakeRequest` (currently absent — nothing
  identifies the requester today, only `org_id`/`bu_id`).
- Add a `resolve_scope` node to the intake graph, running first: a
  pure `WorkspaceBundle`/`TeamMember` lookup (same `ConfigLoader`
  convention `BrokeredToolDispatcher` already uses — `bundle_id =
  f"{org_id}-{bu_id}"`), no LLM call, writes the requester's resolved
  `scope` (or `None` if unknown) to state.
- Add an `enforce_scope` node, running last, after `classify_workflow`:
  a pure comparison (no LLM call) — denies only when the resolved
  `workflow_hint` actually requires scope the requester doesn't have.
  **Cannot run before `classify_workflow`**: scope requirements are
  intent-dependent (`scope="app"` is fine for `"inquiry"`, insufficient
  only for a Stack-tier `"provision_stack"` ask) — there is nothing to
  gate on until intent is known. (Corrected from this session's earlier,
  wrong assumption that the whole gate could be pre-classification.)
- `classify_workflow` itself is **unchanged** — no modification to its
  Tier 2/Tier 3 internals.

**Explicitly NOT a general "skip the LLM call" mechanism.** Tier 2's
prefix match (`"provision_stack: ..."`) is a literal `str.startswith`
check for scripted/CLI/slash-command callers, not intent
understanding. Real chat text and voice-transcribed text almost never
match it and always fall to Tier 3's LLM call — this change does not
reduce that cost, it only avoids paying it *again* or gating on a
value that doesn't exist yet.

**Explicitly NOT in scope**: voice/STT integration itself (only the
identity-resolution assumption it depends on — see design.md); a
`WORKFLOW_REGISTRY`; dispatch from `workflow_hint` to
`plan_request()`/`inquiry_request()` (still `build-intake-workflow`'s
stated non-goal, unchanged here).

## Capabilities

### New Capabilities
- `intake-persona-scope-routing`: resolves the requester's `scope`
  before classification completes, and denies a request whose resolved
  `workflow_hint` requires scope the requester doesn't have — before
  any skill/tool resolution or provisioning workflow runs.

### Modified Capabilities
- `intake-workflow-classification` (from `build-intake-workflow`):
  `IntakeRequest` gains `channel_user_id`; the graph gains two nodes
  around the existing `classify_workflow` node. `classify_workflow`'s
  own behavior is unchanged — only the graph shape around it changes.

## Impact
- **Changed code**: `workflows/intake/state.py` (`IntakeRequest`,
  `IntakeState`), `workflows/intake/graph.py` (two new nodes + edges),
  `workflows/intake/intake_request.py` (needs a `WorkspaceBundle` or
  `ConfigLoader` passed in — today it receives nothing but the
  request).
- **Reused, not rebuilt**: `gateway/scope_gate.py`'s
  `requester_has_stack_scope()` — this change is what finally gives it
  a real caller. `gateway/schemas.py`'s `TeamMember`/`WorkspaceBundle` —
  unchanged.
- **Not affected**: `classify_workflow`'s internals, `workflows/inquiry/`,
  `workflows/provision_stack/`.
- **Still open, deliberately not resolved here**: whether a scope
  denial reuses `IntakeResult.clarifying_question` or needs its own
  field/status distinct from "ambiguous intent" — see design.md Open
  Questions.
