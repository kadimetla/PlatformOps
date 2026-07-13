# Flow Step 7: ToolIntent Dispatch

## Owning code
`gateway/tool_dispatcher.py` — `BrokeredToolDispatcher.evaluate_intent()`.
Real, tested standalone (`tests/test_gateway.py`); not yet wired to
intercept the real `cdk_provisioning_agent`/`terraform_provisioning_agent`
MCP tool calls.

## Input contract
`ToolIntent` (`gateway/schemas.py:62`) — `plan_id`, `plan_hash`,
`org_id`, `bu_id`, `resource_type`, `resource_identifier`, `operation`,
`region`, `estimated_monthly_cost`, `payload`.

## Output contract
`bool` (allow/deny) + one row written to the `audit_logs` table.

## Scenarios
Existing, real (`gateway/tool_dispatcher.py:50-105`):

## Scenario: No workspace bundle for this BU
Given a `ToolIntent` whose `(org_id, bu_id)` has no loaded `WorkspaceBundle`
When `evaluate_intent()` runs
Then it denies with reason "No workspace bundle found for {org_id}-{bu_id}"

## Scenario: Resource type not allow-listed
Given a `ToolIntent.resource_type` not in the BU's `allowed_resource_types`
When `evaluate_intent()` runs
Then it denies with reason "Resource type {type} not in allow-list for BU {bu_id}"

## Scenario: Region mismatch
Given a `ToolIntent.region` different from the BU's `WorkspaceBundle.aws_region`
When `evaluate_intent()` runs
Then it denies with the target/allowed region named in the reason

## Scenario: Plan hash mismatch — tampering suspected
Given a `ToolIntent.plan_hash` that doesn't match the recorded approval's `plan_hash`
When `evaluate_intent()` runs
Then it denies with reason "Plan hash mismatch. Tampering suspected."

## Scenario: No agent approval
Given a valid, matching approval record with `agent_approved=False`
When `evaluate_intent()` runs
Then it denies with reason "Agent approval missing."

New, designed but not yet implemented in this file
(`docs/iam_permissions_boundary_implementation.md`,
`docs/foundation_app_layering_and_iam_tiers.md` Part D):

## Scenario: IAM role creation missing its permissions boundary
Given a `ToolIntent` with `resource_type == "AWS::IAM::Role"` whose `payload.PermissionsBoundary` doesn't match the BU's `permissions_boundary_arn`
When `evaluate_intent()` runs
Then it denies — independent of AWS IAM's own enforcement, catching a malformed intent before it ever reaches AWS

## Scenario: App-layer deploy with no active foundation
Given a `ToolIntent` with `depends_on_foundation_id` set
When `evaluate_intent()` runs and the referenced `FoundationRecord.status != "active"`
Then it denies — re-checked at dispatch time, not just at plan time, since a foundation could be decommissioned in between

## Status
Core deny-by-default logic: **real, tested.** The two new IAM-boundary
and foundation-dependency checks: design only, not in
`gateway/tool_dispatcher.py` yet. This step, alongside Step 2, is the
most-built part of the whole flow.
