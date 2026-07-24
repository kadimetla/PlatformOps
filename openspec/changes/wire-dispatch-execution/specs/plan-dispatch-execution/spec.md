## ADDED Requirements

### Requirement: `evaluate_intent()` requires both agent and human approval
The system SHALL return `True` from `BrokeredToolDispatcher.evaluate_intent()`
only when the stored approval record has both `agent_approved` and
`human_approved` set to `True`, in addition to every existing check
(resource-type allow-list, region, plan hash, validity).

#### Scenario: Agent-approved but not yet human-approved is denied
- **WHEN** an approval record has `agent_approved=True` and
  `human_approved=False`
- **THEN** `evaluate_intent()` returns `False`, and an audit log entry
  records the denial

#### Scenario: Both approvals present passes the approval check
- **WHEN** an approval record has `agent_approved=True` and
  `human_approved=True`, and every other check passes
- **THEN** `evaluate_intent()` returns `True`

### Requirement: `dispatch_and_execute()` derives `agent_approved` from `plan_request()`'s own output
The system SHALL treat a non-empty `tool_intents` list from
`plan_request()` as proof that agent-side approval already happened
(either the LLM security-review node approved, or a deterministic
skill-fill match's own trusted provenance stood in for review), and
SHALL NOT require a separate agent-approval input to `dispatch_and_execute()`.

#### Scenario: Non-empty tool_intents implies agent_approved
- **WHEN** `dispatch_and_execute()` is called with a non-empty
  `tool_intents` list
- **THEN** it records the plan's approval with `agent_approved=True`
  without requiring a separate agent-approval argument

### Requirement: Execution only proceeds for dispatcher-approved intents
The system SHALL call the real mutating MCP tool for a `ToolIntent`
only after `BrokeredToolDispatcher.evaluate_intent()` returns `True` for
that intent, and SHALL record a `"denied"` execution outcome, with no
MCP call made, for any intent the dispatcher rejects.

#### Scenario: A denied intent never reaches the MCP call
- **WHEN** `evaluate_intent()` returns `False` for a given `ToolIntent`
  (e.g. `human_approved` is still `False`)
- **THEN** `dispatch_and_execute()` does not call any mutating MCP tool
  for that intent, and records its outcome as `"denied"` in the
  `executions` table

### Requirement: The desired-state payload is built from live CCAPI schema introspection
The system SHALL call CCAPI's `get_resource_schema_information` tool for
a `ToolIntent`'s `resource_type` before building its `create_resource`
call, and SHALL NOT construct the desired-state payload from
`ToolIntent.payload` alone without validating it against that schema.

#### Scenario: Payload shape mismatch is caught before the mutating call
- **WHEN** `ToolIntent.payload` is missing a field the resource type's
  schema requires
- **THEN** `dispatch_and_execute()` records that intent's outcome as
  `"failed"` with a specific error message, and does not call
  `create_resource`

### Requirement: Execution stops on first failure within a plan, with no automatic rollback
The system SHALL execute a plan's approved `ToolIntent`s in order, and
upon the first execution failure SHALL mark every remaining intent in
that same plan as `"skipped_prior_failure"` without attempting them, and
SHALL NOT automatically delete or roll back any resource already
created earlier in the same plan.

#### Scenario: A later intent's failure stops the rest of the plan
- **WHEN** a plan has three approved `ToolIntent`s and the second one's
  `create_resource` call fails
- **THEN** the first intent's resource remains created, the second is
  recorded `"failed"`, the third is recorded `"skipped_prior_failure"`
  and never attempted, and no automatic deletion of the first resource
  occurs

### Requirement: Every execution attempt is recorded with a terminal per-intent status
The system SHALL write one row to the `executions` table per
`ToolIntent` processed by `dispatch_and_execute()`, recording at least
`intent_id`, `plan_id`, `status`, and (when execution was attempted)
`provider_request_id` or `error_message`.

#### Scenario: A successful execution is recorded with a provider request ID
- **WHEN** `create_resource` succeeds for a given `ToolIntent`
- **THEN** the `executions` table gains a row for that `intent_id` with
  `status="succeeded"` and the provider's returned request/resource
  identifier

### Requirement: `PlanRecord.toolchain` reflects the path that actually executed
The system SHALL set `PlanRecord.toolchain` from the drafting graph's
actual routing decision (`DraftingState`'s resolved toolchain), and
SHALL NOT hardcode a fixed value regardless of which path ran.

#### Scenario: A Terraform-routed request produces a Terraform-labeled plan
- **WHEN** `route_toolchain` resolves `state["toolchain"]` to
  `"terraform"` for a given request
- **THEN** the `PlanRecord` returned by `plan_request()` for that
  request has `toolchain="terraform"`, not `"cdk"`
