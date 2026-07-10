# `plan_request(envelope)` — Verified Implementation

## Status
**Verified by direct package inspection, not web research.**
`pip install google-adk` (2.4.0) into an isolated scratchpad directory,
then introspected the real `Runner`, `Event`, `SkillToolset`, and
`Skill`/`Frontmatter` classes directly via Python — not docs, not
training-data recall. This closes the single most-repeated "verify
before implementing" flag in the whole project
(`docs/planned_implementation.md` Phase 3, `NEXT_STEPS.md`,
`CLAUDE.md`'s `SkillToolset` action item) and, as a side effect,
resolves `docs/skill_loading_and_enforcement_gap.md`'s core finding and
surfaces a real, concrete bug in this project's own `SKILL.md` files.
Nothing is actually wired into `agents/orchestrator.py` yet — this is
the verified design, not the commit.

## Part A: `Runner`/`Session` — real signatures, real code
```python
Runner.__init__(self, *, app=None, app_name=None, agent=None,
                 session_service: 'BaseSessionService', memory_service=None,
                 credential_service=None, auto_create_session: bool = False, ...)

Runner.run_async(self, *, user_id: str, session_id: str,
                  new_message: Optional[types.Content] = None,
                  ...) -> AsyncGenerator[Event, None]

InMemorySessionService.create_session(self, *, app_name: str, user_id: str,
                                       state: Optional[dict] = None,
                                       session_id: Optional[str] = None) -> Session
```
`Event` has built-in extraction helpers — confirmed present, no manual
`event.content.parts` parsing needed: `get_function_calls()`,
`get_function_responses()`, `is_final_response()`.

Concrete implementation of `docs/planned_implementation.md` Phase 3,
step 3:
```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
import hashlib

async def plan_request(envelope: RequestEnvelope) -> PlanRecord:
    failures = check_compliance(envelope_to_spec(envelope))  # mandatory preflight
    if failures:
        raise ComplianceError(failures)

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="platformops",
        user_id=envelope.channel_user_id,
        session_id=envelope.request_id,
    )
    runner = Runner(
        agent=root_agent, app_name="platformops", session_service=session_service
    )

    tool_intents: list[ToolIntent] = []
    vibe_diff_parts: list[str] = []
    async for event in runner.run_async(
        user_id=envelope.channel_user_id,
        session_id=envelope.request_id,
        new_message=types.Content(role="user", parts=[types.Part(text=envelope.raw_payload)]),
    ):
        for call in event.get_function_calls():
            if call.name == "propose_tool_intent":
                tool_intents.append(ToolIntent(**call.args))
        if event.is_final_response():
            vibe_diff_parts.append(event.content.parts[0].text)

    plan_text = "\n".join(vibe_diff_parts)
    return PlanRecord(
        plan_id=str(uuid.uuid4()),
        request_id=envelope.request_id,
        toolchain="cdk",  # or resolved from the matched skill
        plan_text=plan_text,
        plan_hash=hashlib.sha256(plan_text.encode()).hexdigest(),
        vibe_diff=plan_text,
    )
    # tool_intents captured above feed step 4 (BrokeredToolDispatcher),
    # not executed here — no cloud call has happened, by construction
```
Matches `docs/planned_implementation.md` Phase 3's design exactly — the
`propose_tool_intent(...)` non-executing function tool captures intent
via ADK's real `FunctionTool` auto-wrapping (a plain Python function
with type-hinted params + docstring, added directly to an agent's
`tools=[...]` list — also confirmed against real ADK docs, not assumed).

## Part B: `SkillToolset` is real — resolves `docs/skill_loading_and_enforcement_gap.md`
Confirmed via `python3 -c "import google.adk.tools.skill_toolset"` —
not speculative. The module ships:
- `ListSkillsTool`, `SearchSkillsTool` — discovery
- `LoadSkillTool` — loads a matched skill's `SKILL.md` body into context
- `LoadSkillResourceTool` — loads bundled `scripts/`/`references/`/`assets/` on demand
- `RunSkillScriptTool` — executes a skill's script

This is the exact progressive-disclosure mechanism the Day 3 course
material described (`docs/course_concepts_and_project_structure.md`) —
not a thin wrapper, a full implementation. It references
`https://agentskills.io/specification` directly in its docstring,
confirming ADK implements the same open Agent Skills spec the course
taught, not a Google-proprietary format.

**`SkillRegistry.search_skills()`/`.get_skill()` is essentially
`resolve_skill()` already implemented**
(`docs/skills_and_workspace_design.md` Part B's bundled→org→BU
precedence sketch). The three-tier directory search (`workspaces/<agent_id>/skills/`
→ `orgs/<org_id>/skills/` → `skills/`) still needs to be layered on top
— `SkillRegistry` searches *within* a given set of skills, it doesn't
know about this project's tier precedence — but the underlying
match-and-load primitive no longer needs to be hand-built.

```python
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.skills import load_skill_from_dir, list_skills_in_dir

def resolve_skill(request_text: str, bu_id: str, org_id: str):
    for tier_dir in [f"workspaces/{bu_id}/skills", f"orgs/{org_id}/skills", "skills"]:
        for skill_path in list_skills_in_dir(tier_dir):
            skill = load_skill_from_dir(skill_path)
            if matches(request_text, skill.frontmatter.description):  # still needed —
                return skill                                          # tier precedence
    return None                                                       # is this project's

# Then, per matched tier:
cdk_provisioning_agent = Agent(
    ...,
    tools=[SkillToolset(skills=[matched_skill]), propose_tool_intent, ...],
)
```

## Part C: A real, concrete bug this found in this project's own files
Attempted `load_skill_from_dir("skills/provision-infra")` against this
project's actual file — **it fails**:
```
ValidationError: allowed-tools
  Input should be a valid string [type=string_type, input_value=['mcp__aws_iac__...'], input_type=list]
```
ADK's real `Frontmatter.allowed_tools` (confirmed from its source,
`google/adk/skills/models.py`):
```python
allowed_tools: Optional[str] = Field(
    default=None, alias="allowed-tools", serialization_alias="allowed-tools",
)
"""A space-delimited list of tools that are pre-approved to run
(optional, experimental). ... e.g. allowed_tools: Read Bash Write"""
```
A **space-delimited string**, not a YAML list. All three of this
project's `SKILL.md` files (`provision-infra`, `security-review-checklist`,
`sdlc-diagram-compliance-check`) use YAML list syntax:
```yaml
allowed-tools:
  - mcp__aws_iac__read_iac_documentation_page
  - mcp__aws_iac__validate_cloudformation_template
  ...
```
which is invalid against ADK's real schema. **Fix, mechanical, not a
design decision**:
```yaml
allowed-tools: mcp__aws_iac__read_iac_documentation_page mcp__aws_iac__validate_cloudformation_template ...
```
`security-review-checklist/SKILL.md`'s `allowed-tools: []` is also
invalid the same way — should be `allowed-tools:` (omitted/empty
string) or omitted entirely, since `Optional[str]` defaults to `None`.
`Frontmatter`'s `model_config = ConfigDict(extra="allow")` means the
existing `version:` field these files also carry won't cause a failure
— it's tolerated as an extra field, just not part of ADK's validated
schema.

## Open questions / not yet decided
- Whether to fix the three `SKILL.md` files now (a mechanical,
  verified fix) or as a separate, explicitly-requested change — not
  applied in this doc, flagged for a decision.
- Whether `SkillRegistry` itself should be subclassed/wrapped to encode
  the bundled→org→BU tier search directly, or whether `resolve_skill()`
  stays a thin wrapper calling `SkillRegistry` per tier as sketched in
  Part B — leaning toward the wrapper (simpler, doesn't require
  understanding `SkillRegistry`'s internals deeply), not decided.
- Whether `metadata.adk_inject_state: true` (confirmed real — enables
  `{var}` interpolation in a `SKILL.md` body from session state) is
  useful for this project's skills (e.g., injecting `bu_id`/`region`
  into a skill's instructions) — not explored, flagged as a real
  capability worth a future look.
- `Agent.__init__` in this ADK version takes `**data: Any` (Pydantic-
  style, not a fixed keyword signature) — the exact set of accepted
  fields (`tools`, `sub_agents`, `instruction`, etc.) wasn't
  individually re-verified field-by-field, only confirmed the class
  accepts arbitrary data kwargs; the existing `agents/*.py` files'
  usage pattern should still be spot-checked against this version
  before relying on it working unchanged.

## How this relates to the existing docs
- **Resolves** `docs/planned_implementation.md` Phase 3's "verify
  before implementing" flag — the Runner/session API is now confirmed,
  not assumed.
- **Resolves** `docs/skill_loading_and_enforcement_gap.md`'s core
  finding — a native loading mechanism exists (`SkillToolset`), the
  gap was "nothing loads a `SKILL.md`," not "nothing *can*."
- **Resolves** `CLAUDE.md`'s explicit action item ("verify whether
  ADK's `SkillToolset` class already provides this natively... before
  extending `harness/` to hand-build a `load_skill()` mechanism") —
  verified, and it does.
- **Surfaces a new, concrete, fixable bug** in
  `skills/provision-infra/SKILL.md`,
  `skills/security-review-checklist/SKILL.md`, and
  `skills/sdlc-diagram-compliance-check/SKILL.md`'s `allowed-tools`
  frontmatter — not previously known, since nothing had tried loading
  them through the real library before.
- Still doesn't wire any of this into `agents/orchestrator.py` — the
  design is verified, the code isn't written.

## Sources
Direct package inspection — `pip install google-adk` (version 2.4.0
resolved), Python introspection of `google.adk.runners.Runner`,
`google.adk.events.Event`, `google.adk.tools.skill_toolset`,
`google.adk.skills.models`, and a live `load_skill_from_dir()` call
against this repo's actual `skills/provision-infra/SKILL.md`. No
external URLs — this is more authoritative than any doc page for a
fast-moving library, per this project's own "verify against the
installed version" convention.
