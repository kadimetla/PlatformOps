# Skill Loading & Enforcement — What's Real vs. Assumed

## Status
Analysis, not a design doc in the usual sense — this doesn't propose
something new, it establishes a fact about the *existing, bundled*
skill tier that every other skill-related doc in this project has
silently assumed: **no code loads a `SKILL.md`'s content, and no code
enforces its `allowed-tools` list.** Every other doc in this set
(`docs/skills_and_workspace_design.md`, `docs/skill_submission_flow.md`,
`docs/session_memory_design.md`'s procedural-memory mapping) treats
"the bundled skill tier" as a working foundation to layer precedence and
authoring on top of. This doc is the evidence that foundation doesn't
exist yet, and needs to be built before any of the layers on top of it
mean anything at runtime.

**Largely resolved by `docs/plan_request_verified_implementation.md`**:
ADK's real `SkillToolset`/`SkillRegistry`/`load_skill_from_dir` provide
a genuine, verified native loading mechanism — this project doesn't
need to hand-build `load_skill()`. That doc also found the concrete
reason it wouldn't work yet anyway: this project's own `SKILL.md` files
use an invalid `allowed-tools` format (a YAML list; ADK requires a
space-delimited string) — confirmed by trying to actually load one and
watching it fail. The bundled-tier loading gap goes from "nothing
built" to "a real mechanism exists, blocked by one small, fixable
frontmatter bug," which is a meaningfully different, much closer-to-done
status than this doc originally found.

## What a skill physically is today
Three bundled skills exist, each a `SKILL.md` — YAML frontmatter
(`name`, `description` as the trigger phrase, `version`,
`allowed-tools`) plus a markdown procedure body:

| Skill | Triggers on | `allowed-tools` | Used by |
|---|---|---|---|
| `provision-infra` | "deploy/host/provision infrastructure on AWS" | 10 MCP tool names spanning the CDK and Terraform paths | `provisioning_agent` (routing), `cdk_provisioning_agent` (Path A), `terraform_provisioning_agent` (Path B) |
| `security-review-checklist` | any provisioning plan submitted for approval | `[]` — deliberately none, it's a pure reasoning gate | `security_agent` |
| `sdlc-diagram-compliance-check` | "does this architecture comply?" | `check_compliance` | **not wired to any agent** — see below |

The files themselves (`skills/provision-infra/SKILL.md`,
`skills/security-review-checklist/SKILL.md`,
`skills/sdlc-diagram-compliance-check/SKILL.md`) are well-formed and
well-written procedures. The gap isn't in the files — it's in what
connects them to a running agent.

## Finding 1: nothing loads a `SKILL.md`'s content
A repo-wide search confirms it directly:
```
grep -rn "SKILL\|skills/" --include="*.py" .   →   no results
```
Every reference to a skill in the actual agent code is a plain-English
sentence inside an ADK `Agent`'s `instruction=` string, trusting the
underlying model to honor it:
- `agents/security_agent.py:12` — *"Load the 'security-review-checklist'
  skill for the exact checks to run."*
- `agents/cdk_provisioning_agent.py:14` — *"Follow the 'provision-infra'
  skill's Path A (cdk)."*
- `agents/terraform_provisioning_agent.py:14` — *"Follow the
  'provision-infra' skill's Path B (terraform)."*

None of these are backed by a function call, a file read, or a
configured ADK skill-discovery mechanism. There is no code path that
guarantees a `SKILL.md`'s actual content ever reaches the model's
context — the "loading" is a naming convention the LLM is trusted to
resolve on its own. This is categorically different from the gaps
documented elsewhere in this project (which are *designed-but-not-wired*
mechanisms with real code sitting next to them, e.g.
`gateway/tool_dispatcher.py`); here there's no code to wire up at all
yet.

**Confirmed still real, post-migration (2026-07-17)**: `agents/*.py` no
longer exists (`migrate-to-langgraph` deleted it), but the identical gap
was carried into its replacement verbatim, not fixed at cutover.
`workflows/drafting/nodes.py:87-90`'s `security_review_node` binds
`tools=[record_security_decision]` only — no `load_skill` tool — while
its prompt still says *"Load the 'security-review-checklist' skill for
the exact checks to run."* Same pattern at `workflows/drafting/nodes.py:50`
and `:70` for `provision-infra`. See
`docs/skill_scripts_as_iac_templates_and_ms_agent_skills_comparison.md`
for a comparison against Microsoft Agent Framework's Agent Skills, which
*does* ship a real `load_skill` tool the agent calls — naming precisely
the mechanism missing here.

## Finding 2: `allowed-tools` is not enforced
A second, related consequence: each `SKILL.md`'s `allowed-tools`
frontmatter is documentation of intent, not a runtime allow-list.
`agents/cdk_provisioning_agent.py:21-24` attaches the *entire*
`AWS_IAC_MCP_SERVER` and `CCAPI_MCP_SERVER` toolsets:
```python
tools=[
    MCPToolset(connection_params=AWS_IAC_MCP_SERVER),
    MCPToolset(connection_params=CCAPI_MCP_SERVER),
]
```
Nothing filters this down to the specific tool names
`provision-infra/SKILL.md`'s frontmatter lists. This is the same
"guidance, not enforcement" limitation already named for `TOOLS.md` in
`docs/skills_and_workspace_design.md` — but that doc was talking about
a *workspace*-level file describing tool *preference*. This is a
different instance of the identical pattern showing up one level down,
in the skill file itself, which nobody had connected before.

## Finding 3: one bundled skill isn't wired to any agent at all
`sdlc-diagram-compliance-check` is arguably the strongest of the three
skills, because its one tool — `check_compliance` — maps to real,
deterministic code (`spec/check_compliance.py`), not an LLM-followed
procedure. But no agent in `agents/` has it in a `tools=[]` list or
references it in an `instruction=` string. There is currently no path
from a user's "does this architecture comply?" question to this skill
executing at all.

## Finding 4 (2026-07-17, added post-migration): the deterministic path is also unusable against the real bundled skill — for a different reason
Findings 1–3 are about the LLM-mediated path. The zero-LLM deterministic
path (`workflows/drafting/skill_fill.py`'s `run_deterministic_skill_fill()`,
built and tested this session) has its own, separate gap: it has never
been exercised against real, shipped skill content — only against a
synthetic fixture `tests/test_plan_request_boundary.py` constructs by
hand (`os.makedirs(..., "scripts")`, writes `main.tf` itself).

Checked directly against `skills/provision-infra/SKILL.md` — the only
real skill this project ships that's meant for provisioning:
- **No `metadata.resource_types` field.** `gateway/skill_matching.py:61`'s
  match is `set(fm.metadata.get("resource_types", [])) == normalized` —
  an empty set can never equal a non-empty one, so this skill can never
  win `find_matching_skill_path()`'s match regardless of what a request
  asks for.
- **No `scripts/` directory at all** (`find skills/provision-infra -type
  f` returns only `SKILL.md`). `workflows/drafting/skill_fill.py:32-38`'s
  `_find_template_script()` would return `None`, and
  `run_deterministic_skill_fill()` would exhaust `MAX_LAYER1_RETRIES`
  and raise `SkillFillError` — never a silent fallback (by design), but
  also never a successful draft.

So the deterministic path is real, tested, and correct in isolation, but
has zero real content to operate on today — every test proving it works
constructs its own throwaway skill. See
`docs/skill_scripts_as_iac_templates_and_ms_agent_skills_comparison.md`
for the proposed fix (skills' `scripts/` should hold the actual IaC
templates `_find_template_script()` already knows how to parse) and a
second bug that surfaced while designing it (`_find_template_script()`'s
hardcoded `.tf`-before-`.yaml` preference ignores `route_toolchain()`'s
own toolchain choice entirely).

## What this means for the layers built on top
Everything else designed about skills in this project — precedence
(`docs/skills_and_workspace_design.md` Part B), authoring/`SkillProposal`
(Part C), the procedural-memory framing
(`docs/session_memory_design.md`) — implicitly assumes "the bundled
skill tier works" as its foundation, and designs *additional* tiers and
governance on top of that assumption. None of it is wrong, but all of
it is layered on a foundation that itself doesn't exist yet:

- `resolve_skill()`'s bundled-tier fallback (`docs/skills_and_workspace_design.md`
  Part B) assumes a bundled skill, once matched, actually gets loaded.
  Today, matching would still just be a naming convention.
- A materialized `SkillProposal` (Part C) would face the identical gap
  the moment it's approved — writing a new `SKILL.md` to
  `workspaces/<agent_id>/skills/` doesn't help if nothing loads BU-level
  `SKILL.md`s either.
- The "skill = procedural memory" framing
  (`docs/session_memory_design.md`) is conceptually sound, but a
  procedure that never reaches the executor's working context isn't
  procedural memory yet — it's an unread manual sitting next to the
  agent.

So there are two separate builds hiding under "skills," not one:
1. **Foundational** (not previously identified as a gap anywhere): a
   real `load_skill(name) -> str` that reads a matched `SKILL.md`'s body
   into the agent's context, plus tool-filtering that actually restricts
   an agent's `tools=[]` to what `allowed-tools` lists, plus wiring
   `sdlc-diagram-compliance-check` to an agent.
2. **Layered on top** (already designed in prior docs): bundled → org →
   BU precedence, and the `SkillProposal` authoring/promotion gate.

(1) has to exist before (2) does anything real at runtime, even though
(2) is what all the design effort so far has gone into.

## What's real vs. designed, restated
| Piece | Status |
|---|---|
| `SKILL.md` files exist, well-written, correct frontmatter/procedure | Real |
| Code that loads a `SKILL.md`'s content into an agent's context | **Does not exist** (confirmed still true in `workflows/drafting/nodes.py`, post-migration) |
| `allowed-tools` enforced as a runtime allow-list | **Does not exist** |
| `sdlc-diagram-compliance-check` wired to any agent | **Does not exist** |
| `run_deterministic_skill_fill()` itself | Real, built, tested (`workflows/drafting/skill_fill.py`) |
| The real `provision-infra` skill usable by that function | **Does not exist** — no `metadata.resource_types`, no `scripts/` (Finding 4) |
| Bundled → org → BU precedence, `resolve_skill()` | Design only (`docs/skills_and_workspace_design.md`) |
| `SkillProposal` authoring/promotion gate | Design only (`docs/skills_and_workspace_design.md`) |

## Open questions / not yet decided
- Should `load_skill()` inject the full `SKILL.md` body into the
  instruction string at agent-construction time (static, simple, but
  means restarting the process to pick up a changed skill), or be a
  callable tool the agent invokes mid-run (dynamic, matches how
  `resolve_skill()` is sketched as a per-request lookup, closer to how
  real skill precedence would need to work)? Leaning toward the latter
  since precedence resolution is inherently per-request (depends on
  `bu_id`/`org_id`), but not decided.
- Tool-filtering mechanism: does it live in the Gateway/dispatcher layer
  (consistent with `gateway/tool_dispatcher.py` already being the
  brokered-enforcement point for mutating calls), or as a thinner
  per-agent wrapper around `MCPToolset`? Not decided.

## How this relates to the existing docs
- Doesn't change anything in `docs/skills_and_workspace_design.md`'s
  precedence or authoring design — establishes that both depend on a
  foundation (this doc's Finding 1–3) that needs building first.
- Sharpens `docs/session_memory_design.md`'s "skills = procedural
  memory" mapping with the caveat that a skill isn't functioning as
  memory yet if nothing loads it.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3),
  but is arguably a *sibling* required step, not purely "layered on
  top" the way the rest of the skill docs are — `load_skill()` and
  tool-filtering are foundational gaps in the currently-bundled tier,
  independent of the Gateway/session wiring Phase 3 covers.
