## ADDED Requirements

### Requirement: `plan_request` runs mandatory compliance preflight before any agent reasoning
The system SHALL run `check_compliance()` against the request's
structured spec before constructing an ADK `Runner` or invoking any
agent. A failing preflight SHALL raise `ComplianceError` and SHALL NOT
invoke the agent graph at all.

#### Scenario: Compliance failure blocks drafting entirely
- **WHEN** `envelope_to_spec(envelope)` produces a spec that fails
  `check_compliance()`
- **THEN** `plan_request` raises `ComplianceError` with the failure
  reasons, and no `Runner` is ever constructed

### Requirement: `plan_request` produces a `PlanRecord` via ADK's real `Runner`/`Session` API
The system SHALL wrap agent execution in `google.adk.runners.Runner`
with `InMemorySessionService`, using `session_id=envelope.request_id`
and `user_id=envelope.channel_user_id`, and SHALL construct the returned
`PlanRecord` from the captured event stream — `plan_text` from the final
response, `plan_hash` as its SHA256, `vibe_diff` mirroring `plan_text`.

#### Scenario: A successful draft produces a complete PlanRecord
- **WHEN** compliance preflight passes and the agent graph completes
- **THEN** `plan_request` returns a `PlanRecord` with a non-empty
  `plan_text`, a `plan_hash` equal to the SHA256 of `plan_text`, and
  `request_id` matching the input envelope's `request_id`

### Requirement: `propose_tool_intent` calls are captured, never executed
The system SHALL capture every `propose_tool_intent` function call
emitted during the agent run into a `ToolIntent`, and SHALL NOT make any
real mutating cloud API call during `plan_request`'s execution.

#### Scenario: Drafting a plan never touches real cloud resources
- **WHEN** the agent graph emits one or more `propose_tool_intent` calls
  while drafting
- **THEN** each call is captured as a `ToolIntent` in memory, and no
  `ccapi-mcp-server`/`terraform-mcp-server` mutating call occurs before
  `plan_request` returns

### Requirement: No skill match falls through to the existing LLM-drafted graph
The system SHALL route to `root_agent` (the existing `LlmAgent` graph)
whenever no deterministic skill match is available, preserving current
agent behavior unchanged.

#### Scenario: A request with no matching skill still produces a plan
- **WHEN** `resolve_skill_candidates()` returns no candidates for the
  request's resource types
- **THEN** `plan_request` invokes `root_agent` and returns a `PlanRecord`
  from its drafted output, exactly as agent behavior does today
