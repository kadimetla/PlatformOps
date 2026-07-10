---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: plan_request(envelope) internals — a non-LLM BaseAgent branch for skill-matched requests
reviewed_by: unreviewed (first draft)
---

# Deterministic Plan Drafting — A Non-LLM `BaseAgent` for Skill-Matched Requests

## Status
Design, grounded by direct package verification — same method as
`docs/plan_request_verified_implementation.md` (`pip install google-adk`
into an isolated venv, then `inspect` against the installed package, not
assumed from docs or training data). Extends that doc's
`plan_request(envelope)` implementation with a second branch. Nothing
here is built.

## Part A: The gap — every request pays for an LLM, even matched ones
`skills/provision-infra/SKILL.md`, read directly: it's a *procedure* the
LLM agent follows ("determine the tool preference," "draft the
template"), not a template that bypasses agent reasoning. Confirmed by
reading the file, not assumed. `docs/skill_proposal_execution_and_templating.md`
Part C designs how a `draft_iac_template` gets *produced* (the
templating pass after execution confirmation), but never designs the
*reuse* side: once that template exists, does applying it to a new
request still require an LLM generation pass, or is it pure
lookup-and-substitute? As implemented in
`docs/plan_request_verified_implementation.md`, `plan_request(envelope)`
always calls `Runner.run_async()` against `root_agent` (an `LlmAgent`)
— there is no branch that skips generation even when the match is
exact. This spends LLM tokens and adds LLM latency/nondeterminism on
work that, once a template exists, is deterministic string
substitution and static validation.

## Part B: Verified — `BaseAgent` is real, generic, and ADK already uses it non-LLM
Installed `google-adk` fresh (resolved 2.4.0, matching the version in
`docs/plan_request_verified_implementation.md`) into an isolated venv
and introspected directly:

```python
>>> from google.adk.agents import BaseAgent, Agent, LlmAgent
>>> Agent is LlmAgent
True
```

`Agent` — the class every agent in this project's codebase currently
uses (`agents/orchestrator.py`, `provisioning_agent.py`,
`security_agent.py`) — is not a distinct concept. It's a bare alias for
`LlmAgent`. `BaseAgent` is the actual root class, and ADK ships three
other subclasses that don't inherently make their own LLM call:
`SequentialAgent`, `ParallelAgent`, `LoopAgent` — pure control-flow
composition. The method any subclass overrides:

```python
>>> import inspect
>>> print(inspect.getsource(BaseAgent._run_async_impl))
  async def _run_async_impl(
      self, ctx: InvocationContext
  ) -> AsyncGenerator[Event, None]:
    """Core logic to run this agent via text-based conversation.
    ...
    """
    raise NotImplementedError(
        f'_run_async_impl for {type(self)} is not implemented.'
    )
    yield
```

ADK's own default raises `NotImplementedError` — it's a hook meant for
arbitrary subclassing, not an LLM-specific contract. A subclass that
overrides it with pure Python (no model call at all) is exactly as
legitimate a `BaseAgent` as `LlmAgent` is.

## Part C: `SkillTemplateFillAgent` — the deterministic subclass
```python
class SkillTemplateFillAgent(BaseAgent):
    """Zero-LLM-call agent: fills a matched skill's draft_iac_template
    with this request's structured parameters, validates it locally,
    and yields the same propose_tool_intent-shaped Event plan_request()
    already knows how to parse."""

    def __init__(self, matched_skill: SkillProposal, params: dict):
        super().__init__(name="skill_template_fill")
        self._skill = matched_skill
        self._params = params

    async def _run_async_impl(self, ctx: InvocationContext):
        filled = substitute_template_vars(
            self._skill.draft_iac_template, self._params
        )
        # Layer 1 (docs/three_layer_validation_model.md) reused here,
        # not reimplemented — same static-validate/fix/re-validate loop,
        # just running inside a deterministic agent instead of an LLM one.
        validated = run_static_validation_with_retry(filled, max_retries=3)
        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(
                    function_call=types.FunctionCall(
                        name="propose_tool_intent",
                        args=tool_intent_from_template(validated),
                    )
                )],
            ),
        )
```

## Part D: `plan_request(envelope)` gains a branch, not a rewrite
```python
async def plan_request(envelope: RequestEnvelope) -> PlanRecord:
    failures = check_compliance(envelope_to_spec(envelope))
    if failures:
        raise ComplianceError(failures)

    matched_skill, params = resolve_skill(envelope)  # deterministic lookup — NOT an LLM call
    agent = (
        SkillTemplateFillAgent(matched_skill, params)
        if matched_skill and matched_skill.has_structured_match
        else root_agent  # today's LlmAgent graph — unchanged
    )

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="platformops",
        user_id=envelope.channel_user_id,
        session_id=envelope.request_id,
    )
    runner = Runner(
        agent=agent, app_name="platformops", session_service=session_service
    )
    # everything below this line is IDENTICAL to
    # docs/plan_request_verified_implementation.md — same event loop,
    # same propose_tool_intent capture, same PlanRecord construction.
    ...
```
Only which `agent=` gets constructed changes. The `Runner`/`Session`/
`Event` plumbing, the `propose_tool_intent` capture loop, and the
`PlanRecord` shape are all untouched — this is a branch inside an
already-verified implementation, not a new pipeline.

## Part E: What doesn't change
- `BrokeredToolDispatcher.evaluate_intent()`, `ApprovalRecord`, the
  audit trail — completely unaffected. This only changes how
  `PlanRecord.plan_text` gets produced; everything downstream treats
  both branches' output identically.
- The no-skill-match / authoring path — unaffected. Still `root_agent`
  (the `LlmAgent` graph) today, or a constrained coding-agent tool for
  the rare foundation-module-authoring case specifically
  (`docs/foundation_blueprint_authoring_coding_agent.md`).
- Gateway channel adapters (Slack/CLI/webhook/ticket,
  `docs/HARNESS_DESIGN.md`) — unaffected. This branch point sits inside
  `plan_request()`, after request normalization, not per-protocol —
  the same request could reach either branch regardless of which
  channel it arrived on.

## Open questions / not yet decided
- What exactly makes a skill match "structured enough to skip the LLM"
  (`has_structured_match` above is a placeholder, not a designed rule).
  `resolve_skill()` as designed elsewhere
  (`docs/skills_and_workspace_design.md`) is something the *agent*
  calls via `SkillToolset` — an LLM decision by construction. This doc
  proposes the harness call a deterministic variant of it directly,
  before ever constructing a `Runner`, but the matching logic itself
  (exact resource-type/parameter match vs. fuzzy natural-language
  intent) isn't designed.
- Whether free-text chat input needs a cheap routing-tier LLM call to
  extract structured parameters *before* the deterministic branch can
  even be attempted, versus requiring structured input (a Control UI
  form, CLI flags, a webhook's typed payload) to reach the deterministic
  path at all — leaning toward requiring structured input for the
  fully-deterministic case and falling back to `root_agent` for
  anything arriving as free text, not decided as a hard rule.
- Whether `SequentialAgent`/`ParallelAgent` could compose the
  deterministic template-fill step and `security_agent`'s review into
  one `Runner` graph instead of two separate invocations — not
  explored; flagged as a possible efficiency worth checking against
  those classes' actual constructor signatures with the same
  install-and-inspect rigor used here.

## How this relates to the existing docs
- Extends `docs/plan_request_verified_implementation.md`'s
  `plan_request(envelope)` with a second branch — the verified
  `Runner`/`Session`/`Event` machinery in that doc is unchanged, only
  which `agent=` is constructed.
- Answers a question `docs/skill_proposal_execution_and_templating.md`
  never posed: once `draft_iac_template` exists, does reusing it need
  an LLM at all? No — `SkillTemplateFillAgent` is the deterministic
  reuse mechanism that doc's templating design was missing.
- Connects to `docs/foundation_blueprint_authoring_coding_agent.md`'s
  instantiation-vs-authoring split: this doc is the concrete mechanism
  for the instantiation side specifically (and shows it doesn't need
  `LlmAgent` at all, only `docs/three_layer_validation_model.md`'s
  Layer 1 retry loop, now running inside a deterministic agent); that
  doc's coding-agent discussion is about the authoring side only.
- Reuses `docs/three_layer_validation_model.md`'s Layer 1 (static
  validate/retry) inside `SkillTemplateFillAgent._run_async_impl`, not
  as a separate mechanism.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3)
  — it changes that step's internal design before it's built, not
  after.

## Sources
No web sources. Grounded entirely by direct package installation and
introspection: `pip install google-adk` into an isolated venv (resolved
version 2.4.0, same version confirmed in
`docs/plan_request_verified_implementation.md`), then `inspect.getsource`/
`inspect.signature` against the installed package — the same
higher-rigor verification method used for every other ADK claim in this
project, not web documentation or training-data recall.
