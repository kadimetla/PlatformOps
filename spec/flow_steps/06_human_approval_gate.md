# Flow Step 6: Human Approval Gate (Conditional)

## Owning code
Not built — no Control UI exists.
`docs/HARNESS_DESIGN.md`'s "Output surfaces" section designs this as a
web dashboard showing pending Vibe Diffs. An alternative/additional
path for this same step — approval via an external ServiceNow/Jira
change ticket instead of a Control UI click — is designed in
`docs/external_ticket_approval_integration.md`; foundation-tier
resources default to requiring that path, not just a UI click.

## Input contract
`ApprovalRecord` with agent-side fields already populated (from Step 5)
+ the review policy for this resource type/tier + the requesting
`TeamMember`.

## Output contract
`ApprovalRecord.human_approved` (bool) + `human_reviewer`
(`channel_user_id`) + `approval_timestamp`.

## Scenarios

## Scenario: An approver approves
Given a plan requiring human approval and a `TeamMember` with `role="approver"` (or `"admin"`) clicking Approve
When the approval is processed
Then `ApprovalRecord.human_approved=True` and `human_reviewer` is set to their `channel_user_id` (`docs/skills_and_workspace_design.md`'s `TeamMember` sketch)

## Scenario: A requester cannot self-approve
Given a `TeamMember` with `role="requester"` only, attempting to approve their own plan
When the approval is processed
Then it is rejected regardless of the button click — role, not intent, gates this (same `TeamMember.role` check)

## Scenario: Scope must match tier, not just role
Given a `TeamMember` with `role="admin", scope="app"` attempting to approve a foundation-tier plan
When the approval is processed
Then it is rejected — `scope` is a second, independent axis from `role`; an app-scoped admin has no foundation-tier authority regardless of role (`docs/infra_discovery_and_platform_app_split.md` Part C)

## Scenario: Low-risk plans skip this step entirely
Given a plan whose resource type is fully autonomous-eligible per policy
When review completes
Then this step is skipped — agent approval alone is sufficient, matching the sandbox-demo behavior already in `harness/tool_dispatcher.py:97-99`'s comment (a production `review_policy` would tighten this per resource-type risk tier)

## Status
Design only. No Control UI, no code path for a human to actually click
Approve/Reject anywhere in this repo.
