# SkillProposal: Execution-Confirmation Gate and Templating

## Status
Design only. Closes two gaps in `docs/skills_and_workspace_design.md`
Part C's `SkillProposal` design: (1) a proposal can currently be
created before the plan has even executed, so "successful" never
actually meant "confirmed to work"; (2) the stored `draft_iac_snippet`
is a literal transcript of one request's specific values, not a
reusable template. Nothing here is built.

## Part A: Existing flow, recapped
1. `resolve_skill()` finds nothing for a request.
2. The provisioning agent drafts fresh IaC — the literal generated
   script (CFN template or Terraform HCL), made concrete in
   `docs/foundation_discovery_and_creation_chat_walkthrough.md`.
3. The draft can optionally become a `SkillProposal` — `draft_skill_md`
   + `draft_iac_snippet`, scoped to the originating BU only.
4. A human reviewer (`TeamMember` with `role="approver"`/`"admin"`)
   reviews it before it's trusted.
5. On approval, materialized as a real `SKILL.md` at
   `workspaces/<agent_id>/skills/<name>/SKILL.md`.

## Part B: Gap 1 — "successful" must mean execution succeeded, not just drafted
As designed, step 3 happens at **drafting time** — before the plan has
gone through the dispatcher, let alone actually executed against real
cloud resources. A plan can pass compliance and security review and
still fail at execution: a quota limit, a naming conflict, a transient
API error. Storing a pattern that looked right on paper but never ran
successfully is worse than an unreviewed draft — it's a
*confirmed-looking* failure, and it would poison the skill library with
false confidence.

**Fix**: `SkillProposal.status` gains a step between drafting and human
review:
```python
class SkillProposal(BaseModel):
    ...  # existing fields (docs/skills_and_workspace_design.md Part C)
    status: str = "pending_execution_confirmation"
    # "pending_execution_confirmation" | "pending_review" | "approved" | "rejected"
    confirmed_execution_plan_id: Optional[str] = None
    # the PlanRecord whose execution (spec/flow_steps/08) actually
    # succeeded — CORRECTED in docs/post_apply_smoke_testing.md: must be
    # a passing SmokeTestResult (does it work), not just a
    # get_resource/list_resources existence check (does it exist) —
    # the weaker claim was never sufficient to trust a pattern
```
The human review step (Part A step 4) should only ever see proposals
already in `"pending_review"` — i.e., ones where real execution already
confirmed the pattern works. `spec/flow_steps/08_execution_and_audit.md`
gains the transition: on confirmed successful execution, any
`SkillProposal` tied to that plan moves from
`"pending_execution_confirmation"` to `"pending_review"`.

## Part C: Gap 2 — the stored script needs to be a template, not a transcript
`draft_iac_snippet` today is exactly what was drafted for *this
specific request* — a script that creates bucket `acme-orders-logs-1234`
in `us-east-1` isn't directly reusable for a future request to create
`acme-fulfillment-logs-5678` in `us-west-2` without this step. This
templating step has never been designed, despite
`docs/skills_and_workspace_design.md`'s promotion criteria already
gesturing at it ("a review specifically for over-fitting to BU-specific
assumptions") without specifying what actually produces a template.

**Design**: after execution confirmation (Part B) and before human
review, a templating pass identifies request-specific literals in
`draft_iac_snippet` (resource names, regions, sizes — the same fields
`RequestEnvelope`/`PlanRecord` already carried as this request's
specific parameters) and replaces them with named variables, producing
`draft_iac_template` alongside the original:
```python
class SkillProposal(BaseModel):
    ...
    draft_iac_snippet: str    # unchanged — the literal, as-executed script
    draft_iac_template: str   # NEW — the same script with request-specific
                               # values replaced by named variables
```
The human reviewer (Part A step 4) reviews `draft_iac_template`, not
`draft_iac_snippet` — approving the *reusable* version, not the
one-off transcript. `draft_iac_snippet` stays attached for provenance
(traceable back to the exact plan that proved it works), same
traceability reasoning `plan_hash` already serves elsewhere.

## Part D: Storage shape — scripts live as files, not inline text
Once parameterized and confirmed-successful, this maps directly onto
the canonical Skill format from `docs/course_concepts_and_project_structure.md`
(Day 3 course material): the generated IaC becomes the `scripts/` or
`assets/` subdirectory of a real skill folder —
`workspaces/<agent_id>/skills/<name>/scripts/main.tf` (or `.yaml` for
CFN) — not inline text embedded in `SKILL.md` itself. `SKILL.md`'s body
references the file; the script is separate and independently
versionable.

## Open questions / not yet decided
- **Corrected in `docs/foundation_blueprint_authoring_coding_agent.md`**:
  Part C's templating mechanism isn't a bespoke extraction pass at all —
  it's Terraform's own standard convention (*"avoid hardcoded values in
  modules, pass them as input variables instead"*). A properly authored
  module already declares request-specific values as `variables.tf`
  inputs from the start, so `draft_iac_template` is what a correctly
  authored module looks like natively, and `draft_iac_snippet` (the
  literal, as-executed artifact) is *derived* from it — the module plus
  this request's variable values — rather than the reverse as originally
  framed here. This resolves the "agent-performed vs. human-marked"
  question below for the Terraform toolchain specifically: neither is
  needed if the agent follows Terraform's own convention when drafting.
  Whether an equivalent native convention exists for the CDK/
  CloudFormation path (where this open question still applies as
  originally framed) isn't resolved.
- **Answered in `docs/skill_promotion_thresholds.md`**: `confirmed_execution_plan_id`
  stays at a single success for *materialization* specifically (a human
  reviews after 1 success — the human is the gate, not a count), but a
  new `"provisional"` lifecycle stage after materialization requires 3
  consecutive successes before a BU skill is treated as fully trusted,
  and BU→org promotion's "successfully used N times" is now a sourced,
  concrete threshold rather than an open blank.
- Exact diffing/extraction mechanism for Part C's templating pass — not
  designed, only the schema shape and where it sits in the flow.

## How this relates to the existing docs
- Extends `docs/skills_and_workspace_design.md` Part C's `SkillProposal`
  schema and lifecycle with the two gates it was missing.
- Ties `spec/flow_steps/08_execution_and_audit.md` to `SkillProposal`
  state transitions — that spec didn't previously mention skill
  proposals at all.
- Reuses the canonical Skill file format from
  `docs/course_concepts_and_project_structure.md` for where the
  templated script actually lives on disk.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
