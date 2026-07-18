---
last_updated: 2026-07-17
owner: platformops-agent maintainers
scope: comparing this project's skill mechanism to Microsoft Agent Framework's Agent Skills, and designing skills' scripts/ as the actual IaC templates run_deterministic_skill_fill() fills — extends docs/skill_loading_and_enforcement_gap.md and docs/skills_and_workspace_design.md
reviewed_by: unreviewed (first draft)
---

# Skill Scripts as IaC Templates, and a Comparison to Microsoft Agent Framework's Agent Skills

## Status
Design + verified findings against real code. Two things happened in
one pass: (1) research into Microsoft Agent Framework's Agent Skills
(three sources, see below) to compare against this project's own skill
mechanism, and (2) tracing that comparison directly into real code,
which surfaced a concrete, previously-undocumented gap —
`docs/skill_loading_and_enforcement_gap.md` Finding 4, added alongside
this doc. Nothing in the design sections below (Part C, Part D) is
built.

## Part A: What Microsoft Agent Framework's Agent Skills actually do
- **Shape**: a folder with `SKILL.md` (frontmatter + instructions) plus
  optional `scripts/`, `references/`, `assets/` — the same shape this
  project already uses (`workflows/drafting/skill_loading.py`, vendored
  from `google.adk.skills`; both trace back to the same
  Anthropic-originated skill convention).
- **Progressive disclosure, four real stages**: advertise names+descriptions
  in the system prompt (~100 tokens) → agent calls `load_skill` (full
  instructions) → agent calls `read_skill_resource` (resources on
  demand) → agent calls `run_skill_script` (code execution, gated).
- **Runtime selection is autonomous**: no external router — the agent
  itself decides a request matches a skill and calls `load_skill`.
  Skills are exposed *as tools*, not injected as static instruction
  text.
- **Scoping is composition/filtering, not precedence**: multiple
  directories (`company-skills/`, `team-skills/`, `agent-skills/`) get
  combined into one provider, with "per-key isolation so one provider
  can serve different skill sets to different agents or tenants."
  Explicitly no override/shadowing semantics.
- **Script execution requires host approval by default** — a real,
  built-in pause-and-wait before any skill's bundled code runs,
  independent of whatever governance the surrounding app adds.

## Part B: Side by side with this project

| | MS Agent Skills | This project |
|---|---|---|
| File shape | `SKILL.md` + frontmatter + scripts/references/assets | Identical shape (`Frontmatter`/`Skill`/`Resources`/`Script`) |
| Multi-tenancy model | Composition/filtering — one provider serves a curated subset per agent/tenant | Strict precedence — bundled → org → BU, highest tier wins, stop at first match (`gateway/skill_matching.py:56-67`); no individual tier, rejected for governance reasons (`docs/skills_and_workspace_design.md` Part B) |
| Runtime selection | Always LLM-mediated — agent calls `load_skill` itself | Two deliberately separate paths (Part C below) |
| Script execution | Real, built-in host-approval gate before any skill script runs | No skill scripts are executed by an agent anywhere in this codebase today — `Resources.scripts` exists in the vendored model but is read directly by deterministic code (`skill_fill.py`), never invoked as agent-triggered execution |

## Part C: This project's two skill paths, and where each stands against MS's model

**Path 1 — deterministic, zero-LLM** (`gateway/skill_matching.py`'s
`resolve_skill_candidates()`): exact resource-type-set match plus
`lifecycle_state == "stable"`, no model call. This is a **deliberate
rejection** of the LLM-mediated model MS (and ADK) both use —
`docs/structured_match_rule_for_skills.md` Part F0 verified by direct
package inspection that ADK's `SkillRegistry.search_skills()` is an
agent-callable tool the LLM decides to invoke, "structurally
incompatible with a zero-LLM-call branch." Not similar to MS's
approach, on purpose.

**Path 2 — the LLM-driven graph** (`workflows/drafting/nodes.py`): the
path where a real comparison to MS's `load_skill` mechanism should
apply, and doesn't yet. `security_review_node` binds
`tools=[record_security_decision]` only (`workflows/drafting/nodes.py:87`)
while its prompt says *"Load the 'security-review-checklist' skill for
the exact checks to run"* (`:90`) — no `load_skill` tool exists
anywhere in this codebase for the model to actually call.
`docs/skill_loading_and_enforcement_gap.md` Finding 1 flagged this
against the pre-migration ADK agents; confirmed here, directly against
the current code, that it survived the LangGraph cutover unchanged.

## Part D: The gap that surfaced while grounding this — Path 1 has never touched real content either

Tracing "does the deterministic path actually work against a real
skill" (prompted by the idea that `scripts/` should hold the actual IaC
templates a skill fills) led to `docs/skill_loading_and_enforcement_gap.md`
Finding 4: `skills/provision-infra/SKILL.md` — the only real,
provisioning-relevant skill this project ships — has no
`metadata.resource_types` (so it can never win
`find_matching_skill_path()`'s match) and no `scripts/` directory at
all (so `_find_template_script()` returns `None` and
`run_deterministic_skill_fill()` can only fail). Every test proving
Path 1 works constructs its own synthetic fixture skill by hand
(`tests/test_plan_request_boundary.py`) — the real bundled skill has
never been exercised.

### Design: `scripts/` holds the exact IaC template(s) this skill fills
`workflows/drafting/skill_fill.py:32-38`'s `_find_template_script()`
already knows how to find and parse a `.tf` or CFN-style
`.yaml`/`.yml`/`.json` script inside `Skill.resources.scripts` — the
mechanism exists, it's just never been given real content. Closing
Finding 4 for `provision-infra` means:
1. Add `metadata.resource_types: [...]` (CFN-style, matching
   `infra/allowed-resource-types.json`'s convention) to
   `skills/provision-infra/SKILL.md`'s frontmatter.
2. Add a `scripts/` directory with the actual template(s) —
   `main.tf` and/or a CloudFormation-style `.yaml`, matching what
   `_fill_template()` expects to find and fill with `spec`/`bundle`
   values.

### A second, real bug this surfaces: `_find_template_script()` is toolchain-blind
`provision-infra`'s own frontmatter says it supports *"either AWS
CDK-native tooling or Terraform depending on the user's stated
preference"* — meaning, if Finding 4 is closed by giving it both a
`.tf` and a CFN-style template (rather than splitting into two skills),
it would need to pick the one matching the request's toolchain. But
`_find_template_script()` (`workflows/drafting/skill_fill.py:32-38`)
checks for `.tf` files first, unconditionally, and only falls back to
`.yaml`/`.yml`/`.json` if no `.tf` exists — it never reads
`spec["toolchain"]` at all. A skill shipping both templates would
**always** resolve to Terraform regardless of `route_toolchain()`'s own
choice (`workflows/drafting/nodes.py:27-32`, default `"cdk"`) —
silently contradicting the graph's own routing decision one layer
below it. Two ways to close this were named, not decided:
1. Make `_find_template_script()` toolchain-aware — take
   `spec["toolchain"]` as a parameter, look for the matching extension
   first.
2. Split `provision-infra` into two single-toolchain skills
   (`provision-infra-cdk`, `provision-infra-terraform`) — each ships
   exactly one template, no ordering ambiguity, matches
   `_find_template_script()`'s current "one template per skill"
   assumption without changing it.

**Fixed 2026-07-17, option 1.** `_find_template_script(skill, toolchain)`
now takes the toolchain explicitly, prefers the matching extension
(`terraform` → `.tf`, anything else → CFN-style `.yaml`/`.yml`/`.json`),
and falls back to whatever's bundled if no exact match exists — so a
skill shipping only one template (today's real case, per Finding 4)
still resolves correctly regardless of toolchain. Fixed in **both**
copies — `workflows/drafting/skill_fill.py` and
`gateway/skill_template_agent.py`'s duplicate (used by
`check_structured_match()`'s `missing_vars` check) — kept in lockstep
deliberately, since the two must agree on which template a request
resolves to. `run_deterministic_skill_fill()` and
`check_structured_match()` both now derive `toolchain =
spec.get("toolchain", "cdk")` once and thread it through. Covered by
`tests/test_skill_fill_toolchain_selection.py` (4 tests, including one
asserting both copies resolve identically). Option 2 (splitting the
skill) wasn't taken — option 1 fixes the shared mechanism once instead
of constraining future skill authors to one-template-per-skill.

## Real vs. designed
| Piece | Status |
|---|---|
| MS Agent Framework research (Part A) | External, verified via the three sources below |
| `run_deterministic_skill_fill()`, `_find_template_script()` | Real, built, tested |
| `provision-infra` skill having `metadata.resource_types` + real `scripts/` | **Fixed 2026-07-17** — `AWS::S3::Bucket`, `scripts/main.tf` + `scripts/template.yaml`, proven against the real skill by `tests/test_provision_infra_skill_content.py` |
| `_find_template_script()` toolchain-awareness | **Fixed 2026-07-17** — both copies, `tests/test_skill_fill_toolchain_selection.py` |
| A skill ever reaching `lifecycle_state == "stable"` in production | **Does not exist** — found while closing Finding 4; see `docs/skill_loading_and_enforcement_gap.md` Finding 5 |
| `load_skill`/`read_skill_resource` tools for the LLM-driven path | Not designed — named as the concrete missing piece, not scoped here |

## Open Questions
- ~~Toolchain-aware `_find_template_script()` vs. splitting
  `provision-infra` into two skills~~ — **resolved 2026-07-17**, option 1
  (toolchain-aware function), see Part D.
- ~~`provision-infra` itself has no `metadata.resource_types` and no real
  `scripts/`~~ — **resolved 2026-07-17**, Finding 4 fully closed. Closing
  it surfaced a new, separate gap — `docs/skill_loading_and_enforcement_gap.md`
  Finding 5: nothing in production code ever calls
  `SkillUsageStore.record_skill_usage()`, so a skill can mechanically
  match and fill correctly but can never reach `"stable"` in a real
  running system. Not fixed here — a real design decision, not a quick
  patch (see Finding 5 for the options named).
- Whether `security-review-checklist` and `sdlc-diagram-compliance-check`
  need the same `scripts/`-as-executable-reference treatment, or stay
  pure-instruction skills (the former has `allowed-tools: []` "deliberately
  none, it's a pure reasoning gate" per `docs/skill_loading_and_enforcement_gap.md`
  — likely no script content ever belongs there) — not decided.
- Whether closing Finding 1 (a real `load_skill` tool for Path 2) is
  worth building before `workflows/inquiry/`-adjacent intake work
  starts trusting skills are "real," given Path 2 is the LLM-driven
  graph specifically, not the deterministic path this doc's Part D
  focuses on — raised, not scheduled.

## Sources
- [Agent Skills for Python is now released](https://devblogs.microsoft.com/agent-framework/agent-skills-for-python-is-now-released/)
- [Give your agents domain expertise with Agent Skills in Microsoft Agent Framework](https://devblogs.microsoft.com/agent-framework/give-your-agents-domain-expertise-with-agent-skills-in-microsoft-agent-framework/)
- [What's new in Agent Skills: code skills, script execution, and approval for Python](https://devblogs.microsoft.com/agent-framework/whats-new-in-agent-skills-code-skills-script-execution-and-approval-for-python/)

## How this relates to the existing docs
- Extends `docs/skill_loading_and_enforcement_gap.md` — adds Finding 4
  there directly (deterministic path unusable against real skill
  content) and confirms Finding 1 (no `load_skill` mechanism) survived
  the LangGraph migration unchanged; this doc holds the MS comparison
  and the `scripts/`-as-IaC-template design that doc only references.
- Extends `docs/skills_and_workspace_design.md` Part B/C — doesn't
  change bundled → org → BU precedence or `SkillProposal` authoring,
  both of which still assume the bundled tier works; this doc is about
  making that assumption true for `provision-infra` specifically.
- Doesn't change `workflows/inquiry/` or `build-discovery-workflow` —
  raised as a precondition worth knowing about before an intake
  workflow starts routing requests that assume skills "just work."
