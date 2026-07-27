## Context
Three real, tested, disconnected pieces exist today, confirmed by grep
(zero production callers between any of them):
- `intake_request()` (`workflows/intake/`) — classifies verb only,
  `workflow_hint="provision_stack"|"inquiry"`. No persona/scope
  awareness, no `channel_user_id` field even.
- `plan_request()`/`inquiry_request()` — both take `bundle:
  WorkspaceBundle` as a caller-supplied parameter at their own entry,
  never resolved by intake. This is the established convention this
  change follows for the new workflow too.
- `dispatch_and_execute_cluster()` (`gateway/kubernetes_resource_dispatch.py`)
  — approval-gated, three real cloud adapters, writes `ResourceRecord`
  on success. Fully real and tested, but every adapter today only
  actually uses `cluster_name` (AWS additionally uses a `template`
  blob) — GCP/Azure's real required fields (`project_id`, `zone`,
  `network`, node pool sizing, `subscription_id`, `resource_group`,
  `location`, ...) aren't modeled or collected anywhere. This is the
  same open question as `provision-kubernetes-cluster/tasks.md` Task 1
  (live MCP verification), not a new one.

**Status: design in progress.** The overall shape below is settled;
the exact per-cloud field lists are explicitly not decided here
(blocked on live verification) and several mechanics are open
questions at the bottom.

## Goals / Non-Goals
See `proposal.md`.

## Decisions

### The graph shape
```
New workflow entry (mirrors plan_request()/inquiry_request()'s own
shape: caller-constructed request + WorkspaceBundle in):

  provision_kubernetes_cluster(request, bundle, resource_store, mcp_client)
      │
      ▼
① resolve_scope         (no LLM — requester_has_stack_scope(bundle,
                          request.channel_user_id); deny immediately
                          if insufficient, same as
                          scripts/manual_test_cluster_flow.py already
                          demonstrates by hand)
      │
      ▼
② resolve_cloud_provider (from request text if stated, else ask —
                           "aws"|"gcp"|"azure")
      │
      ▼
③ collect (loop)
      resolve_skill_candidates(spec, ..., cloud-specific skill set)
        → missing_vars for that cloud's declared template variables
        │ empty                    │ non-empty
        ▼                          ▼
     proceed to ④          interrupt({"ask_for": missing_vars})
                            ⋯ pause (checkpointer-backed — same
                            AsyncSqliteSaver build_checkpointed_
                            provision_stack_graph already uses) ⋯
                            resume with human's answer → merge → loop
      (no skill exists yet for this cloud+shape → LLM drafts a fresh
      template, same create_react_agent mechanism
      cdk_provisioning_node/terraform_provisioning_node already use —
      reused, not rebuilt)
      │
      ▼
④ build_cluster_tool_intent(...)   (real, unchanged,
                                     gateway/kubernetes_resource_dispatch.py:89)
      │
      ▼
⑤ dispatch_and_execute_cluster(...)  (real, unchanged, tested)
```

### Where bundle/scope resolution lives — corrected from the superseded change
`route-intake-by-persona-scope` assumed intake needed a `resolve_scope`
node ahead of `classify_workflow`. Wrong premise: `plan_request()` and
`inquiry_request()` both already take `bundle: WorkspaceBundle` as a
parameter resolved by the *caller*, at the workflow's own boundary —
not inside intake. This change follows that same convention: intake
stays exactly as shipped (verb classification only); this workflow's
own entry point resolves scope, the same place `bundle` already
arrives. Whatever eventually bridges `intake_request()`'s
`workflow_hint="provision_stack"` output to calling this workflow is a
separate, later concern (same explicit non-goal
`build-intake-workflow`'s design.md already stated for dispatch).

### Skills as procedural memory, collect loop as the missing wiring
`docs/session_memory_design.md`'s taxonomy (design-only, but the
mapping is sound): a skill's declared template variables *are*
procedural memory — "for GCP GKE we use these fields" is exactly
`parse_declared_variables()` reading a GKE skill's template. What's
missing structurally is step ③'s loop itself: `check_structured_match()`
already computes `missing_vars`
(`gateway/skill_template_agent.py:118-122`) and discards it into a
bool — this change is what finally turns that signal into a real
`interrupt()`-based ask.

**Explicitly deferred, not fixed here**: the generic `provision_stack`
path has two real bugs that would break this same mechanism if reused
as-is — `extract_spec_from_free_text()`'s produced spec shape never
matches what `check_structured_match()` checks against (confirmed
against `tests/test_provision_infra_skill_content.py`'s fixture, which
hand-adds a redundant key the real extraction path never produces),
and `SkillUsageStore.record_skill_usage()` has zero production callers
so no skill can ever reach `"stable"` in a real running system. The
new EKS/GKE/AKS skills and their matching path in this change need to
be built correctly from the start rather than inheriting either bug —
not by fixing the generic path (separate change), but by not repeating
its mistakes here.

## Risks / Trade-offs
- [Risk] Per-cloud field lists aren't known yet → [Mitigation] this
  design proceeds with the *shape* (skill → declared vars → missing_vars
  → collect loop) fully specified; the actual GKE/AKS/EKS field lists
  get filled in once live `get_tools()` verification runs, not guessed.
- [Risk] `interrupt()` has never been used anywhere in this codebase —
  first real usage carries integration risk (exact resume-payload
  shape, how a caller outside a test harness would actually deliver
  the human's answer) → not yet mitigated, see Open Questions.

## Open Questions
- Exact resume mechanics: what does the *caller* of this workflow do
  with an `interrupt()` payload — is there a real channel adapter to
  show it to a human and call back with `Command(resume=...)`, or does
  this change only prove the mechanism against a test harness (same
  precedent `build-intake-workflow`/`build-discovery-workflow` accepted
  for their own "no real caller yet" gap)?
- Does `resolve_cloud_provider` (step ②) itself need a collect/ask step
  (interrupt) if the cloud isn't stated, or is it assumed given for
  this change's first slice?
- Whether the new EKS/GKE/AKS skills live under `skills/` alongside
  `provision-infra` (same directory, same `list_skills_in_dir()`
  mechanism) or need their own matching path entirely, given the
  deferred bugs above — leaning toward same directory, new/parallel
  matching function, not decided.
- Whether `resolve_scope`'s denial and `resolve_cloud_provider`'s
  ambiguity should share one result shape or two distinct ones (mirrors
  the same open question `route-intake-by-persona-scope` left
  unresolved for intake — carried forward, not re-litigated).

## Migration Plan
Not written yet, deliberately — per this session's "capture as we
understand it" approach. `tasks.md` follows once the Open Questions
above narrow enough to produce concrete, checkable steps; the live
verification blocker (Task 1 in `provision-kubernetes-cluster`) likely
needs addressing first since it gates the skill-authoring work this
design depends on.
