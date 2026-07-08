# Flow Step 5: Security Review

## Owning code
`agents/security_agent.py` — real ADK agent, `tools=[]` (deliberately
no mutating capability). Loads `security-review-checklist` by
instruction-string reference only — see
`docs/skill_loading_and_enforcement_gap.md` for why that's currently a
naming convention, not a guaranteed content load.

## Input contract
`PlanRecord` + skill provenance (which tier the plan's pattern came
from: bundled / org / BU / freshly-drafted).

## Output contract
`ApprovalRecord.agent_approved` (bool) + `agent_reasoning` (str) —
`human_approved`/`human_reviewer` are Step 6's fields, not this step's.

## Scenarios

## Scenario: Provenance informs scrutiny
Given a plan built on a previously-approved BU skill
When `security_agent` reviews it
Then it is treated as lower-risk, since the pattern has already been vetted (`docs/end_to_end_flow_example.md` step 6)

## Scenario: A never-before-seen pattern gets more scrutiny
Given a plan drafted fresh with no matching skill at any tier
When `security_agent` reviews it
Then it is flagged as more likely to require mandatory human approval rather than agent-only sign-off — provenance-informed, not a flat rule

## Scenario: Foundation-tier resources always route to human review
Given a plan containing a foundation-tier resource type (e.g. `AWS::EKS::Cluster`)
When `security_agent` reviews it
Then human approval is always required, regardless of cost or naming compliance — no autonomous-approval exception exists for this tier (`docs/foundation_app_layering_and_iam_tiers.md` Part A)

## Scenario: Never approve silently, never reject without a reason
Given any plan
When `security_agent` reaches a decision
Then it returns a specific, actionable reason either way — silence is not a valid outcome (`skills/security-review-checklist/SKILL.md:28-29`, `agents/security_agent.py:14-15`)

## Status
Real agent, prompt-level reasoning only — the checks it runs
(cost ceiling, region, naming, destructive scope, IAM allow-list,
resource-type allow-list) are enforced by the model following
instructions, not by code that gates its output
(`docs/current_architecture.md`'s defense-in-depth analysis).
