## Why
`workflows/drafting/plan_request.py`'s `plan_request()` is real and tested,
returning `(PlanRecord, list[ToolIntent])`. `gateway/tool_dispatcher.py`'s
`BrokeredToolDispatcher.evaluate_intent()` is real and tested standalone.
Verified directly (grep, not assumed): zero non-test code anywhere in this
repo calls `plan_request()` and feeds its `ToolIntent`s into the dispatcher,
and nothing executes an approved `ToolIntent` against a real MCP server.
`README.md`'s entire MVP pitch — structured spec in, compliant plan drafted,
human approval required, real AWS infra provisioned out — has never actually
run end to end. Every piece is correct and tested in isolation; nothing
connects them.

A code review (read the actual files, not assumed) also found the "just
wire it up" framing undersold the work: `evaluate_intent()` reads
`human_approved` from the `approvals` table into an unused variable
(`_human_app`, `gateway/tool_dispatcher.py:88`) and never checks it — only
`agent_approved` gates today. There is also no execution step of any kind:
mutating MCP tools are explicitly filtered out before the drafting agents
ever see them (`workflows/drafting/mcp_tools.py:86-98`, by design — drafting
only proposes, never executes), so "approved" today means nothing actually
happens next.

## What Changes
- Fix `BrokeredToolDispatcher.evaluate_intent()` to actually check
  `human_approved`, not silently ignore it — decide and implement the real
  policy (required for every intent at this MVP's scope, since both
  in-scope resource types are app-tier with no autonomous-approval
  mechanism designed yet).
- Verify the mutating CCAPI/Terraform MCP tool names live, against a running
  server, before building an executor on them — `workflows/drafting/mcp_tools.py:13`
  currently states these names are inferred, not confirmed.
- Define an explicit payload contract mapping `ToolIntent.payload` (today:
  the raw resource spec dict from `skill_fill.py`, e.g. `type`/`name`) to
  the actual desired-state shape CCAPI's `create_resource` or Terraform's
  `create_run` expects.
- Add the missing execution step: a new function that, for each
  dispatcher-approved `ToolIntent`, calls the real mutating MCP tool to
  create the resource.
- Add execution-outcome tracking to the audit trail — today's `audit_logs`
  table records only gate decisions (`decision`, `reason`, `payload`), not
  execution attempts, provider request IDs, or per-intent terminal status;
  decide and implement partial-failure behavior across a multi-`ToolIntent`
  plan (some resources created, one fails).
- Fix `PlanRecord.toolchain` being hardcoded to `"cdk"`
  (`workflows/drafting/plan_request.py:171`) even though `skill_fill.py`
  can route to Terraform via `spec["toolchain"]` — otherwise Terraform
  dispatch is ambiguous or silently wrong.
- Add a minimal human-approval entry point (a function parameter or CLI
  confirmation) — **not** a Control UI; `docs/control_ui_approval_queue_design.md`
  is design-only and out of scope here.

**Explicitly NOT in scope**: `TeamMember`/`scope`, any Kubernetes or
foundation-layer work, any multi-cloud work, any change to
`infra/allowed-resource-types.json` (stays `AWS::S3::Bucket` +
`AWS::CloudFront::Distribution`, exactly as today).

## Capabilities

### New Capabilities
- `plan-dispatch-execution`: the end-to-end path from a drafted
  `PlanRecord`/`ToolIntent` list, through human approval and the
  dispatcher's deny-by-default gate (now actually honoring
  `human_approved`), to real resource creation via the verified mutating
  MCP tool, to an execution-outcome audit record — including
  partial-failure behavior across multiple intents in one plan.

### Modified Capabilities
<!-- None -- BrokeredToolDispatcher.evaluate_intent()'s human_approved fix
and PlanRecord.toolchain's fix are both bug fixes to existing, already-shipped
behavior (an ignored field, a hardcoded default), not a change to any
previously-specified requirement -- no prior spec exists for either to
diff against (openspec/specs/ is currently empty; nothing has been
archived into it yet). -->

## Impact
- **Modified**: `gateway/tool_dispatcher.py` (`evaluate_intent()`'s
  approval check), `workflows/drafting/plan_request.py`
  (`PlanRecord.toolchain` routing).
- **New code**: an execution module (exact location TBD in design.md) that
  maps an approved `ToolIntent` to a live mutating MCP tool call, plus
  whatever audit-schema addition partial-failure tracking needs.
- **Verification required before implementation**: live `get_tools()` call
  against the running CCAPI/Terraform MCP servers to confirm the exact
  mutating tool names `workflows/drafting/mcp_tools.py` currently only
  infers.
- **Not affected**: `infra/allowed-resource-types.json`, `TeamMember`/scope
  (doesn't exist), any foundation/Kubernetes design work from
  `docs/composable_foundation_blueprints.md` and related docs.
- **Tests**: new suite covering the fixed `human_approved` gate, the
  payload-mapping contract, execution success/failure per intent, and
  partial-failure across a multi-intent plan — mirrors
  `tests/test_gateway.py`'s existing dispatcher-test pattern.
