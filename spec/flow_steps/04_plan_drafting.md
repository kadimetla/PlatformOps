# Flow Step 4: Plan Drafting

## Owning code
`agents/provisioning_agent.py`, `agents/cdk_provisioning_agent.py`,
`agents/terraform_provisioning_agent.py` — real ADK agents. The
`plan_request(envelope) -> PlanRecord` wrapper that would formalize this
step's boundary is `docs/planned_implementation.md` Phase 3, the one
required next step across this whole project.

## Input contract
`RequestEnvelope` + the matched skill (bundled/org/BU tier, or none —
see `docs/skills_and_workspace_design.md` Part B) + the resolved
`WorkspaceBundle`.

## Output contract
`PlanRecord` (`harness/schemas.py:39`) — `plan_id`, `request_id`,
`toolchain`, `plan_text`, `plan_hash`, `vibe_diff`,
`estimated_monthly_cost`.

## Scenarios

## Scenario: A BU-level skill match reuses a reviewed pattern
Given `resolve_skill()` matched a skill at `workspaces/<agent_id>/skills/`
When the provisioning agent drafts a plan
Then it starts from that skill's already-reviewed IaC pattern, filling in request-specific parameters rather than drafting from nothing (`docs/end_to_end_flow_example.md` step 4)

## Scenario: No skill match — fresh draft, optional SkillProposal
Given `resolve_skill()` returned nothing at any tier
When the provisioning agent drafts a plan
Then a genuinely new template is drafted, and the draft may optionally become a `SkillProposal` scoped to the originating BU (`docs/skills_and_workspace_design.md` Part C)

## Scenario: plan_hash is tamper-evident
Given a drafted `plan_text`
When `plan_hash` is computed
Then it is the SHA256 of `plan_text`, checked again at dispatch time against the value recorded at approval time — a mismatch means "tampering suspected" (`harness/tool_dispatcher.py:89-91`)

## Scenario: cdk vs. terraform toolchain selection
Given a user request with no stated tool preference
When `provisioning_agent` follows the `provision-infra` skill's Step 0
Then it defaults to `cdk` — one fewer external dependency than the Terraform path (`skills/provision-infra/SKILL.md:37`)

## Status
Real ADK agents draft plans today, but not through a formal
`plan_request(envelope)` boundary — there's no `Runner`/`Session`
construction anywhere in `agents/orchestrator.py`
(`NEXT_STEPS.md:26-27`), so this step exists as agent behavior, not as
a callable function with the contract above yet.
