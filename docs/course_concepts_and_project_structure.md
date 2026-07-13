# Course Concepts → `AGENTS.md`/`CLAUDE.md` — Mapping and Gap Analysis

## Status
Reference doc, not a design doc in the usual sense — records where
`AGENTS.md`, `CLAUDE.md`, and this project's process conventions came
from, so they're traceable and revisable rather than opaque. See
`docs/repo_layout_references.md` for the consolidated index covering
this doc's PDF sources *and* the later web-research passes (industry
validation of spec-driven development, the ADR-vs-`AGENTS.md`
correction) that this doc predates. Source material: five course decks
at
`/opt/wecan/aiml_learning_gang_ws/vibecoding_ws/learning_guides/*.pdf`
(Google, May 2026) — read in full via subagents, ~241 pages total.
Nothing here is built; it's the record behind two files that now are
(`AGENTS.md`, `CLAUDE.md`).

## Part A: Source material
| Day | File | Core topic |
|---|---|---|
| 1 | `New_SDLC_Day_1.pdf` (51pp) | Agent = Model + Harness; the Vibe Coding → Agentic Engineering spectrum; AGENTS.md as the named convention |
| 2 | `AgentTools_n_Interoperability_Day_2.pdf` (49pp) | MCP/A2A/A2UI; tool onboarding checklist; the NxM problem; monolithic-agent anti-pattern |
| 3 | `AgentSkills_Day_3.pdf` (62pp) | Canonical `SKILL.md` format; progressive disclosure; ADK's `SkillToolset` |
| 4 | `VibeCodingAgentSecurity_and_Evaluation_Day_4.pdf` (41pp) | 7-pillar security model; Vibe Diff; evaluation methodology |
| 5 | `SpecDriven_Day_5.pdf` (38pp) | Spec-as-source-of-truth; BDD/Gherkin; the AGENTS.md/GEMINI.md hierarchy |

## Part B: What went into `AGENTS.md`, and why
- **"Ten lines: stack, conventions, hard rules, workflow"** (Day 1, p.43)
  is `AGENTS.md`'s literal section structure — not a metaphor, the
  actual four headings used.
- **"Keep AGENTS.md tight... use it also as a router into the Skills
  library, with a short catalog at the bottom"** (Day 3, p.52-53,
  citing Vercel's 100%-vs-53% pass-rate data for a passive index) is
  why the skills catalog is a short trigger-only list, not a repeat of
  each `SKILL.md`'s full content.
- The four explicit content directives from Day 2 p.9 (think before
  code, minimal code, surgical edits, goal-driven execution with a
  reproducing test first) are folded into "Hard rules" and "Workflow"
  nearly verbatim.
- **"Instructions and Rule Files... must be treated as highly sensitive,
  cryptographically attested artifacts"** (Day 4) — the reason this
  project's own habit of PR-reviewing/versioning design docs (already
  established before this doc existed) extends naturally to `AGENTS.md`
  itself, not a new practice invented here.
- **"Passing an entire 100,000-token repository into every prompt is
  financially unviable at scale"** (Day 1) — the reason `AGENTS.md`
  points to `docs/HARNESS_DESIGN.md`'s document map instead of
  inlining every design decision.

## Part C: What went into `CLAUDE.md`, and why
Day 5's system-prompt hierarchy (p.31-33) — Global Profile → `AGENTS.md`
(shared cross-tool foundation) → project/tool-specific file, **local
wins** — is why `CLAUDE.md` exists as a separate, higher-priority layer
rather than folding everything into `AGENTS.md`. The deck names
`GEMINI.md` for that top tier since it's Gemini-CLI-centric;
`CLAUDE.md` plays the identical role for this tool.

The "repeatable process" section in `CLAUDE.md` **is not from the course
material** — it's a description of the process this repo's design
sessions already converged on independently (analyze → doc → cross-link
→ commit-on-request → push-on-request), written down now because the
user asked for the process itself to be captured, not just its outputs.

## Part D: The ADK `SkillToolset` finding — verify before building
Day 3 material (p. mid-deck, Figure 9) describes a **Programmatic Route**
for custom frameworks: *"e.g., Google ADK: you register the folder path
via a `SkillToolset` class, which auto-generates the necessary
`load_skill` routing tool for the model under the hood."* If accurate,
this may resolve `docs/skill_loading_and_enforcement_gap.md`'s core
finding (nothing loads a `SKILL.md`'s content) without hand-building a
loader.

**Not independently verified.** `google-adk` is not installed in this
environment (`pip show google-adk` and `import google.adk` both fail),
so this claim comes from a course slide description, not a checked API
surface — exactly the situation `mcp_server/external_servers.py`'s own
header comment warns about for every third-party integration in this
project. **Action item before building `load_skill()` by hand**: install
`google-adk`, check for a `SkillToolset` class, and read its actual
signature/behavior. If it exists and does what the slide describes, the
right move is registering `skills/` through it, not writing a parallel
mechanism. If it doesn't exist or behaves differently, the original
hand-built plan from `docs/skill_loading_and_enforcement_gap.md` stands.

## Part E: Existing `SKILL.md` files vs. the canonical format — gap analysis
Day 3's canonical frontmatter: `name`, `description` (what + when + when
NOT), `version`, `license`, `allowed-tools`, `metadata.author`. Canonical
body sections: `# Skill Name`, `## When to use`, `## When NOT to use`,
`## Workflow`, `## Examples` (Input → Output), `## Output format`,
`## Anti-patterns to avoid`.

| Skill | Has | Missing |
|---|---|---|
| `provision-infra` | `name`, `description` (what+trigger, no anti-trigger), `version`, `allowed-tools`, "When to use" section | `license`, `metadata.author`, explicit "When NOT to use", "Examples" (Input→Output), "Output format", "Anti-patterns to avoid" (partially covered by an unlabeled "Notes" section) |
| `security-review-checklist` | Same core fields, `allowed-tools: []` (correctly empty — reasoning-only skill) | Same five missing pieces |
| `sdlc-diagram-compliance-check` | Same core fields | Same five missing pieces (though step 1 informally covers part of "When NOT to use," and step 3 informally covers part of "Output format") |

**Naming convention** (Day 3: kebab-case, gerund form preferred, e.g.
`processing-pdfs` not `pdf-processor`): none of the three current names
are gerund form (`provision-infra`, not `provisioning-infra`). Lower
priority than the missing sections — cosmetic, not functional.

**Not a blocker for Part D's `load_skill()` work** — these are content
gaps in already-real files, addressable independently of whether a
hand-built or ADK-native loading mechanism gets used.

## Part F: Terminology this project should reuse verbatim going forward
Some of this project's own docs already independently arrived at
matching terms before this material was read — worth noting as a
validating cross-check, not a coincidence to ignore:
- **"Vibe Diff"** — already used throughout this project's docs
  (`skills/provision-infra/SKILL.md`, `docs/HARNESS_DESIGN.md`,
  `docs/end_to_end_flow_example.md`) exactly matching Day 4's usage
  (a plain-English summary of a proposed change, shown before a
  high-stakes tool call executes).
- **"Agent = Model + Harness"** (Day 1/2) — this project's own
  `docs/HARNESS_DESIGN.md` is built around exactly this split, though
  it never used the phrase explicitly until now.
- New terms worth adopting: **static vs. dynamic context** (Day 1 — for
  distinguishing `AGENTS.md`/`CLAUDE.md` from on-demand skill loading);
  **progressive disclosure** (Day 3 — the skill-loading mechanism
  itself); **Zero Ambient Authority** (Day 4 — precisely describes what
  `gateway/tool_dispatcher.py`'s deny-by-default design is already
  doing, without this project having named it that).

## Open questions / not yet decided
- Whether to bring the existing `skills/*/SKILL.md` files into full
  Day 3 compliance now, or only when `load_skill()`/`SkillToolset` work
  actually begins — not decided.
- Whether `spec/` should be renamed `specs/` to match Day 5's exact
  convention, or left as-is since it's already an established,
  functioning path in this repo — leaning toward leaving it, cosmetic
  rename risk outweighs benefit, not decided.
- Whether Day 4's Evaluator Quorum / trajectory-eval concepts warrant
  their own design doc — this project currently has no eval suite at
  all, which is a real gap Day 4 speaks directly to; not scoped yet.

## How this relates to the existing docs
- Directly resolves the open action item this conversation created for
  itself: capture course concepts into `AGENTS.md`/`CLAUDE.md` before
  building the skills-loading mechanism.
- **Changes the plan** in `docs/skill_loading_and_enforcement_gap.md` —
  that doc's implicit assumption (hand-build a loader) now has a
  verify-first step ahead of it (Part D above).
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
