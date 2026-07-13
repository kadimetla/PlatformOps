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

**Corrected during implementation**: `plan_request` returns
`(PlanRecord, list[ToolIntent])`, not `PlanRecord` alone as originally
specified here. `PlanRecord` (`gateway/schemas.py`) has no field to
carry the captured intents, and `ToolIntent.plan_hash` must equal the
final `PlanRecord.plan_hash` — a value that doesn't exist until the full
event stream has been assembled, so intents are constructed in a second
pass after the loop completes, using the now-known `plan_id`/`plan_hash`.
An earlier draft of this implementation tried to stamp intents with a
placeholder hash inside the loop and fill it in later; that was a real
sequencing bug, not a viable design, caught before it shipped.

#### Scenario: A successful draft produces a complete PlanRecord
- **WHEN** compliance preflight passes and the agent graph completes
- **THEN** `plan_request` returns a `PlanRecord` with a non-empty
  `plan_text`, a `plan_hash` equal to the SHA256 of `plan_text`, and
  `request_id` matching the input envelope's `request_id`, alongside a
  `list[ToolIntent]` whose entries all carry that same `plan_id`/`plan_hash`

### Requirement: `propose_tool_intent` calls are captured, never executed by `plan_request` itself
The system SHALL capture every `propose_tool_intent` function call
emitted during the agent run into a `ToolIntent`, and `plan_request`
itself SHALL NOT make any real mutating cloud API call.

**Known, pre-existing gap this requirement does not close**: as of this
change, `cdk_provisioning_agent`/`terraform_provisioning_agent` still
have `CCAPI_MCP_SERVER`/`TERRAFORM_MCP_SERVER` (mutating tools) attached
directly — there is no `propose_tool_intent` function tool anywhere in
this codebase yet, so this guarantee is **structural only for
`SkillTemplateFillAgent`** (never given any MCP tools at all, by
construction). For the `root_agent` (LLM-drafted) branch, `plan_request`
itself never executes anything, but the underlying agent's own tool call
still could. This is `docs/HARNESS_DESIGN.md`'s already-documented
runtime-boundary gap #5 (swap the mutating toolset for a non-executing
`propose_tool_intent` tool) — out of scope for this change, not
regressed by it: the same risk exists identically today, with or without
`plan_request` wired.

#### Scenario: Drafting a plan via SkillTemplateFillAgent never touches real cloud resources
- **WHEN** `SkillTemplateFillAgent` drafts a plan (the structured-match
  branch)
- **THEN** no MCP tool of any kind is available to it, mutating or
  otherwise — the guarantee holds by construction, not by convention

#### Scenario: propose_tool_intent calls from root_agent are captured, when that tool exists
- **WHEN** the agent graph emits one or more `propose_tool_intent` calls
  while drafting (once that tool is wired — tracked separately, not by
  this change)
- **THEN** each call is captured as a `ToolIntent` in memory by
  `plan_request`, which makes no mutating call of its own either way

### Requirement: No skill match falls through to the existing LLM-drafted graph
The system SHALL route to `root_agent` (the existing `LlmAgent` graph)
whenever no deterministic skill match is available, preserving current
agent behavior unchanged.

#### Scenario: A request with no matching skill still produces a plan
- **WHEN** `resolve_skill_candidates()` returns no candidates for the
  request's resource types
- **THEN** `plan_request` invokes `root_agent` and returns a
  `(PlanRecord, list[ToolIntent])` pair from its drafted output, exactly
  as agent behavior does today
