# Repo Layout — Full Reference List

## Status
Reference doc, not a design doc — consolidates every source (course
material + web research) that shaped `AGENTS.md`, `CLAUDE.md`, `spec/`,
`spec/flow_steps/`, and this project's documentation conventions, in
one place instead of scattered across individual docs' `## Sources`
sections. No new decisions here — see the linked docs for reasoning.

## Part A: Course learning guides (primary source)
Five decks at
`/opt/wecan/aiml_learning_gang_ws/vibecoding_ws/learning_guides/*.pdf`
(Google, May 2026), read in full via subagents.

| Day | File | What it contributed | Landed in |
|---|---|---|---|
| 1 | `New_SDLC_Day_1.pdf` (51pp) | "Ten lines: stack, conventions, hard rules, workflow"; Agent = Model + Harness; static vs. dynamic context | `AGENTS.md`'s section structure |
| 2 | `AgentTools_n_Interoperability_Day_2.pdf` (49pp) | The four explicit AGENTS.md content directives (think first, minimal code, surgical edits, goal-driven with tests-first); MCP onboarding checklist | `AGENTS.md`'s Hard rules/Workflow sections |
| 3 | `AgentSkills_Day_3.pdf` (62pp) | Canonical `SKILL.md` format; progressive disclosure; "keep AGENTS.md tight, route into skills"; the `SkillToolset` claim | `AGENTS.md`'s skills catalog; `docs/course_concepts_and_project_structure.md` Part D/E |
| 4 | `VibeCodingAgentSecurity_and_Evaluation_Day_4.pdf` (41pp) | "Vibe Diff" terminology (already independently used in this project); Zero Ambient Authority; "Instructions and Rule Files... cryptographically attested artifacts" | `docs/course_concepts_and_project_structure.md` Part F |
| 5 | `SpecDriven_Day_5.pdf` (38pp) | Spec-as-source-of-truth; BDD/Gherkin grammar (matches `spec/reference_architecture.md`'s existing format); three-tier system-prompt hierarchy (Global → `AGENTS.md` → tool-specific, local wins) | `CLAUDE.md`'s layering rationale |

## Part B: Explicitly checked and found absent in the course material
Re-queried Day 1 and Day 5 specifically, twice, rather than assuming —
recorded here so nobody re-derives these expecting the source material
to cover them:

- **HLD vs. LLD terminology**: neither deck uses "High-Level Design,"
  "Low-Level Design," "HLD," or "LLD" anywhere. Day 1's only
  design-related content is a single undifferentiated "Design and
  architecture" phase (p.21-22); Day 5's "spec" concept collapses
  architecture and implementation detail into one artifact.
- **Per-flow-step spec decomposition**: neither deck describes
  decomposing a multi-stage pipeline into separate, per-step specs.
  Day 5 stays at whole-project/whole-feature granularity; Day 1's
  Factory Model diagram is drawn once, at the whole-system level, and
  explicitly favors "success criteria... rather than step-by-step
  instructions." `spec/flow_steps/` and
  `docs/flow_step_spec_decomposition.md` are this project's own
  extension, not applied course content — stated there and restated
  here.

## Part C: Web research — industry validation and correction
Two separate research passes, both changing (not just adding to) prior
conclusions in this conversation.

### Pass 1: HLD/LLD/ADR — general software-engineering practice
| Finding | Source |
|---|---|
| HLD = system-wide blueprint, one doc; LLD = per-component detail, one doc each; different audiences | [Difference between HLD and LLD — GeeksforGeeks](https://www.geeksforgeeks.org/system-design/difference-between-high-level-design-and-low-level-design/), [High-level design — Wikipedia](https://en.wikipedia.org/wiki/High-level_design) |
| ADRs: single decision, single page, numbered, **never edited once accepted — superseded instead** | [Architectural decision record process — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html), [Architecture decision records overview — Google Cloud docs](https://docs.cloud.google.com/architecture/architecture-decision-records), [bliki: Architecture Decision Record — Martin Fowler](https://martinfowler.com/bliki/ArchitectureDecisionRecord.html), [ADR GitHub org](https://adr.github.io/) |
| RFC = pre-decision consensus process; ADR = post-decision record | Same ADR sources above |

**This pass's conclusion was itself later corrected — see Pass 2.**
Initial recommendation (retrofit this project's docs into classical
numbered, immutable ADRs) treated general software-engineering practice
as if it were the AI-specific answer. It isn't, precisely — Pass 2
below is why.

### Pass 2: What industry actually does for AI-agent-driven implementation specifically
| Finding | Source |
|---|---|
| Spec-driven development is "rapidly becoming the industry norm" for AI-agent implementation — not a niche/course-specific concept | [GitHub Spec Kit](https://github.com/github/spec-kit) (93,000+ stars, 30+ AI agents incl. Claude Code), [Understanding Spec-Driven Development: Kiro, spec-kit, and Tessl — Martin Fowler](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html) |
| Amazon Kiro's native workflow — Requirements → Design → Tasks, no code before all three — closely resembles this project's `spec/` → `docs/` → implementation shape | [Kiro](https://kiro.dev/) |
| Classical ADRs (historical, "why we chose X") and `AGENTS.md`-style files (forward-looking, enforceable constraints) are **different, complementary artifacts in 2026 practice, not one superseding the other** | [AGENTS.md vs Architecture Decision Records — AI Advances](https://ai.gopubby.com/agents-md-is-the-ew-architecture-decision-record-adr-3cfb6bdd6f2c?gi=9142039fe97d) |
| ADRs are increasingly made machine-readable to "enforce module boundaries... as architectural constraints for AI agents" — the classical/agent-facing line is blurrier than Pass 1 suggested | [awesome-ai-architect — Architecture Decision Records](https://github.com/Alexey-Popov/awesome-ai-architect/blob/main/solution-architecture/architecture-decision-records.md) |
| Concrete `CLAUDE.md`/context-file best practices: metadata header (`last_updated`/`owner`/`scope`/`reviewed_by`), Preferred/Avoid code-block pairs, a structure of overview→principles→conventions→testing→commands→anti-patterns — **applied**, both files now follow this shape | [Context Engineering Best Practices for AI-Powered Dev Teams (2026) — Packmind](https://packmind.com/context-engineering-ai-coding/context-engineering-best-practices/) |

**Correction this pass produced**: don't retrofit into classical
immutable ADRs (Pass 1's recommendation). Keep `AGENTS.md`/`CLAUDE.md`
as the living, enforceable-constraint layer (already the right
instinct), keep `spec/` as the Requirements/Design layer (already
resembles Kiro's own phase model), and add a lightweight dated
decisions index rather than rewriting 16 docs into single-page records
— not yet built, offered, not started.

## Part D: Repo artifact → source map
| Artifact | Primarily informed by |
|---|---|
| `AGENTS.md` | Day 1 (section structure, "ten lines"), Day 2 (four content directives), Day 3 ("keep it tight, route into skills") |
| `CLAUDE.md` | Day 5 (system-prompt hierarchy) + this repo's own already-converged-on process, written down rather than sourced externally |
| `spec/` (existing) + `spec/flow_steps/` (new) | Day 5 (BDD/Gherkin grammar, spec-as-source-of-truth) for the former; this project's own extension, explicitly not course-sourced, for the latter (Part B above) — validated post-hoc by Kiro's Requirements/Design/Tasks model (Pass 2) |
| `docs/*.md` as the "why" layer, not yet ADR-formatted | Pass 1 named the gap (not single-decision, not numbered); Pass 2 explained why full ADR conversion isn't the right fix |
| Decision to NOT do a classical ADR retrofit | Pass 2, specifically the `AGENTS.md`-vs-ADR finding |

## How this relates to the existing docs
- Consolidates, doesn't replace, the `## Sources` sections already in
  `docs/eks_helm_mcp_integration.md`, `docs/multi_cloud_foundation_and_iam.md`,
  `docs/iam_permissions_boundary_implementation.md`, and
  `docs/course_concepts_and_project_structure.md` — those stay as the
  per-topic citation trail; this is the single cross-topic index for
  "why is the repo laid out this way" specifically.
- Extends `docs/course_concepts_and_project_structure.md` (PDF-only)
  with the two later web-research passes it doesn't cover.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
