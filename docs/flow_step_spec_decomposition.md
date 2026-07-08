# Flow-Step Spec Decomposition — One Spec Per Harness Stage

## Status
Design only — nothing here is built. **This is this project's own
extension, not something the course material taught.** Re-queried the
Day 1 and Day 5 decks specifically for "how do you decompose a
multi-stage pipeline into per-step specs" and got a precise negative
answer on both — see Part A. Everything from Part B onward is original
design, grounded in what this project already has (the 8-step flow
already enumerated in `docs/HARNESS_DESIGN.md`, the schemas already in
`harness/schemas.py`), not an application of taught methodology.

## Part A: What the research actually found
Re-queried both source decks with a narrow, specific question. Neither
covers it:

- **Day 5 (Spec-Driven Development)**: no guidance on decomposing a
  pipeline into per-step spec files, no spec-to-spec dependency
  declaration, no granularity checklist below whole-project/whole-
  feature. The one adjacent concept — splitting work across an ADK
  sub-agent pipeline (Search → Story → Impact → Task-breakdown → Coding
  agent, p.24-25) — decomposes *agent labor at runtime*, not *spec
  documents*. Structurally different from what this doc does.
- **Day 1 (New SDLC)**: the Factory Model diagram (Planning Agent →
  Coding Agent → Tests & Verification) is drawn once, at the whole-
  system level. "Decomposition" is named as one of three orchestrator
  skills in a single bullet, no methodology behind it. The material
  explicitly argues for "success criteria rather than step-by-step
  instructions" — the opposite direction from per-step specs.

Stated plainly so this doesn't get cited later as "the course taught
this": it didn't. What follows is this project's own design, built
because the underlying materials this project already has (an
enumerated flow, defined schemas, an established Given/When/Then
grammar) make it tractable, not because a course slide prescribed it.

## Part B: What already exists that makes this tractable
Two things, already real:
1. **The flow steps are already enumerated** —
   `docs/HARNESS_DESIGN.md`'s "How the flow works" is a clean 8-step
   canonical list.
2. **Most steps already have a defined input/output schema** —
   `harness/schemas.py`'s five classes are exactly the contracts each
   step consumes and produces.

The extension: reuse `spec/reference_architecture.md`'s Given/When/Then
grammar and `docs/spec_driven_development_scaling.md`'s
`ComplianceRule`/`ComplianceContext` registry pattern, applied one level
up — not "rules a submitted spec must satisfy" but "one spec file per
harness flow step," each declaring:
- **Step name + owning code module**
- **Input contract** (schema class, or raw payload shape if pre-schema)
- **Output contract** (schema class, or the specific failure shape)
- **Given/When/Then scenarios** for that step's behavior in isolation
- **Build status** — several steps already have real code
  (`config_engine.py`, `tool_dispatcher.py`); others are pure design —
  visible per-step now, not only in the whole-project table
  `docs/HARNESS_DESIGN.md` already has.

This is what makes it *repeatable*: build one step's spec, verify it
against the existing schema and any existing code, hand it to an agent
to implement or complete, move to the next step — instead of one
monolithic spec for the whole harness.

## Part C: The eight flow-step specs
Live at `spec/flow_steps/`, index at `spec/flow_steps/README.md`. One
file per step, numbered in pipeline order:

| # | Step | Owning code | Status |
|---|---|---|---|
| 1 | Request intake & normalization | none yet — channel adapters not built | Design only |
| 2 | Binding & context resolution | `harness/config_engine.py` | **Real, tested** |
| 3 | Deterministic preflight | `spec/check_compliance.py` | Real code, not wired as mandatory |
| 4 | Plan drafting | `agents/*.py` | Real ADK agents; `plan_request(envelope)` wrapper not built |
| 5 | Security review | `agents/security_agent.py` | Real agent, prompt-level only |
| 6 | Human approval gate (conditional) | none — no Control UI | Design only |
| 7 | `ToolIntent` dispatch | `harness/tool_dispatcher.py` | **Real, tested**; not wired to live agent calls |
| 8 | Execution + audit | MCP tool calls + `audit_logs` table | Real pieces exist; not gated by step 7 yet, `channel_user_id` audit gap open |

This table is deliberately the same shape as every other built-vs-
designed table in this project's docs — the point of this doc is to
make that granularity available *per pipeline stage*, not to invent a
new status vocabulary.

## Part D: Spec file template
```markdown
# Flow Step N: <Name>

## Owning code
<module path, or "not built yet">

## Input contract
<schema class, with the specific fields this step reads>

## Output contract
<schema class, or failure shape>

## Scenarios
## Scenario: <name>
Given <precondition>
When <this step's action>
Then <specific outcome, PASS/FAIL + reason>

(repeat per scenario)

## Status
<Real/tested | Real, not wired | Design only>, with a one-line reason.
```
Same Given/When/Then grammar as `spec/reference_architecture.md` —
deliberately, so a future `ComplianceRule`-style registry could load
both without a second parser.

## Open questions / not yet decided
- Whether step-level specs should eventually replace or merge into
  `spec/reference_architecture.md`, or stay a separate, complementary
  layer (resource-property rules vs. pipeline-stage rules) — leaning
  toward staying separate, since they check different things at
  different granularities; not decided.
- Whether a step's spec should declare which *other* steps' output it
  depends on (step 7 depends on step 4's `PlanRecord` and step 6's
  `ApprovalRecord`, for instance) as a structured field, or whether the
  ordering table above is sufficient — not decided.
- Whether these specs should drive actual code generation (per-step,
  agent-built) or serve primarily as a verification/documentation
  artifact once code exists — not decided; both are compatible with the
  format as written.

## How this relates to the existing docs
- Extends `docs/spec_driven_development_scaling.md`'s registry pattern
  to a new axis — pipeline stages, not submission-content rules.
- Reuses `docs/HARNESS_DESIGN.md`'s existing 8-step flow enumeration
  and built-vs-designed table shape rather than inventing new ones.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3)
  — step 4's spec documents what that wrapper needs to satisfy, it
  isn't a new prerequisite for it.
