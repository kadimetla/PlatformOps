## Context
`build-intake-workflow` (shipped, `workflows/intake/`) built exactly
one node — `classify_workflow` — with no persona/identity awareness at
all. Separately, `provision-kubernetes-cluster` built
`gateway/scope_gate.py`'s `requester_has_stack_scope()`, tested, but
never wired to anything that runs before a real request reaches it.
This change connects the two: intake becomes the place scope gets
checked, for any workflow, not just the Kubernetes-cluster path.

**Corrected 2026-07-27 — this change's core premise was wrong, not just
its details.** Grounding both real workflow boundaries directly —
`plan_request(envelope, bundle, usage_store)`
(`workflows/provision_stack/plan_request.py:116`) and
`inquiry_request(query, bundle, store)`
(`workflows/inquiry/inquiry_request.py:20`) — both **already** take
`WorkspaceBundle` as a caller-supplied parameter, resolved at the
workflow's own boundary, never inside intake. That's the established
convention in this codebase, consistently, for both real workflows.
`resolve_scope`/`enforce_scope` therefore belong at each provisioning
(or inquiry/audit) workflow's own entry point, not as intake graph
nodes — intake should stay exactly what `build-intake-workflow`
shipped it as: verb classification only, nothing more. This change is
**superseded by
`openspec/changes/build-kubernetes-provisioning-workflow/`**, which
places bundle/scope resolution where it actually belongs, grounded in
one concrete flow instead of a hypothetical general one. Left in place
rather than deleted, per this project's "correct in place, with a
note" convention — the reasoning trail (why pre-classification
denial doesn't work, why Tier 2 isn't intent understanding) is still
correct and is carried forward into the new change, not re-derived.

**Status: design in progress, captured incrementally as the flow is
understood — not finalized.** See Open Questions for what's genuinely
still undecided; this doc will keep changing shape as more of it gets
worked out.

## Goals / Non-Goals
See `proposal.md`. Notably NOT a goal: reducing Tier 3's LLM-call cost
in general — see "Why the pre-classification ordering doesn't work"
below, which corrects this session's own earlier assumption.

## Decisions

### The graph shape
```
entry
  │
  ▼
① resolve_scope        (NEW — pure lookup, no LLM, always runs)
  bundle = config.bundles.get(f"{org_id}-{bu_id}")
  scope  = next((m.scope for m in bundle.members
                 if m.channel_user_id == request.channel_user_id), None)
  → writes {"bundle": bundle, "scope": scope} to state
  │
  ▼
② classify_workflow    (EXISTING — unchanged, Tier 2 prefix / Tier 3 LLM)
  → writes {"result": IntakeResult(workflow_hint=..., ...)} to state
  │
  ▼
③ enforce_scope        (NEW — pure comparison, no LLM, always runs)
  if result.workflow_hint == "provision_stack" and scope not in ("stack", "both"):
      overwrite result → denial
  else:
      pass result through unchanged
  │
  ▼
 END
```

### Why the pre-classification ordering doesn't work
Earlier in this session's discussion, "cheaper ordering" was taken to
mean `resolve_scope`/deny-check runs entirely *before*
`classify_workflow`, skipping the LLM call for requesters who'll be
denied anyway. That's wrong, and the reasoning matters for future
readers who might reach for the same shortcut:

- Scope requirements are **intent-dependent**. `scope="app"` is
  perfectly valid for `"inquiry"` and insufficient only for a
  Stack-tier `"provision_stack"` ask. There is no way to know which
  applies until `workflow_hint` is resolved — you cannot gate on a
  value that doesn't exist yet.
- Tier 2's prefix match (`raw_text.startswith("provision_stack:")`) is
  **not intent understanding** — it's a literal string convention for
  scripted/CLI/slash-command callers. Real chat text and voice-STT
  transcripts essentially never match it. For that traffic — which is
  most real traffic — Tier 3's LLM call is unavoidable and this design
  does not try to avoid it.
- What genuinely *is* free and safe to front-load is `resolve_scope`'s
  lookup itself (doesn't depend on intent at all) — not a denial
  decision. Hence the shape above: cheap lookup first, LLM
  classification in the middle (unchanged, paid when it's paid today),
  cheap gate last.

### `classify_workflow` is not modified
`resolve_scope` and `enforce_scope` compose *around* the existing node
rather than being spliced into its Tier 2 branch. Considered and
rejected: short-circuiting inside Tier 2 (deny immediately on an
exact-prefix match without even checking Tier 3) — real but narrow
savings (only for the scripted/prefix-typed case Tier 2 already covers,
which is not real end-user traffic per above), traded against modifying
an already-shipped, already-tested node. Not worth it for this slice.

### Identity resolution — voice doesn't change the assumption, it confirms it
`IntakeRequest`'s existing docstring: "org_id/bu_id are assumed already
resolved from the authenticated session — never parsed from raw_text."
`channel_user_id` needs the identical treatment. For chat, it's the
channel's own user identity. For a future voice channel, it's
whatever the call/session layer resolves (caller ID, SIP identity, a
voice-auth token) — never something extracted from the transcript
itself. This change doesn't build a voice channel; it just makes sure
`IntakeRequest`'s shape doesn't assume "chat" by only having org/bu and
raw text.

## Risks / Trade-offs
- [Risk] `resolve_scope` needs a `ConfigLoader`/`WorkspaceBundle` that
  `intake_request()` doesn't receive today (its signature is just
  `IntakeRequest -> IntakeResult`) → [Mitigation] not yet resolved —
  see Open Questions, this is the biggest concrete gap standing between
  this design and buildable tasks.
- [Risk] A requester with no matching `TeamMember` at all (`scope =
  None`) needs a defined denial behavior, not just the
  scope-insufficient case → not yet decided, see Open Questions.

## Open Questions
- **How does `intake_request()` get a `WorkspaceBundle`?** New required
  parameter (caller resolves it, same as `org_id`/`bu_id` today), or
  does `resolve_scope` hold its own `ConfigLoader` and look it up
  internally? Leaning toward the former (matches the existing "accepted
  as given, never resolved internally" rule for org_id/bu_id) but not
  decided.
- **What does `enforce_scope` write on denial?** Reuse
  `IntakeResult.clarifying_question` (bends its meaning — "you can't do
  this" is not "I don't understand"), or add a distinct field/status
  (e.g. `denied: bool` or a `denial_reason`) so a caller can tell the
  two apart? Not decided.
- **`scope = None`** (no matching `TeamMember` in the bundle at all) —
  does this deny unconditionally regardless of `workflow_hint`, or only
  when `workflow_hint` turns out to require a specific scope (same as
  the insufficient-scope case)? Not decided.
- Whether `resolve_scope`'s lookup failure (no bundle at all for
  `org_id`/`bu_id`) is a denial or a different error class entirely —
  not addressed yet.

## Migration Plan
Not written yet — deliberately. Per the user's request, this doc is
being captured as understanding solidifies rather than all at once;
`tasks.md`/`specs/` follow once the Open Questions above are resolved
enough to make concrete, checkable tasks.
