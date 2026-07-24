## Context
`plan_request()` (`workflows/drafting/plan_request.py`) and
`BrokeredToolDispatcher` (`gateway/tool_dispatcher.py`) are both real,
independently tested, and never called together anywhere outside a test.
A code review that read the actual files (not assumed) found three things
that change the shape of "just wire them up":

1. `evaluate_intent()` reads `human_approved` from the `approvals` table
   into an unused variable (`_human_app`, `gateway/tool_dispatcher.py:88`)
   and never checks it — only `agent_approved` gates today
   (lines 97-102).
2. Mutating MCP tools are structurally unreachable from the drafting
   workflow by design — `workflows/drafting/mcp_tools.py` filters
   `create_resource`/`update_resource`/`delete_resource` (CCAPI) and
   `create_run` (Terraform) out of every tool list bound to an LLM, so
   drafting can only ever call `propose_tool_intent`. There is no code
   anywhere that calls a mutating tool. This is the intended shape
   (agents propose, never execute) — but it means the execution step
   doesn't just need wiring, it needs building.
3. The exact mutating tool names are **inferred, not live-verified**
   (`workflows/drafting/mcp_tools.py:13-22`, explicitly flagged in that
   module's own docstring) — no AWS/TFE credentials have been available
   in this environment to confirm them against a running server.

## Goals / Non-Goals

**Goals:**
- Fix `evaluate_intent()` to actually enforce `human_approved`.
- Build the missing execution step for the CDK/CCAPI path specifically:
  approved `ToolIntent` → real `create_resource` call → resource exists.
- Define a payload contract from `ToolIntent` to CCAPI's expected
  desired-state shape, using CCAPI's own read-only introspection tool
  (`get_resource_schema_information`) rather than guessing the shape.
- Add execution-outcome tracking (succeeded/failed/skipped, per intent)
  to the audit trail.
- Decide and implement partial-failure behavior across a multi-intent
  plan.
- Fix `PlanRecord.toolchain`'s hardcoded `"cdk"` so the field reflects
  which path actually ran.

**Non-Goals:**
- **Terraform execution.** `terraform-mcp-server`'s `create_run` mixes
  `plan_and_apply` (mutating) and `refresh_state` (read-only) behind one
  tool via a `run_type` parameter — `mcp_tools.py`'s own comment already
  flags there's no clean way to allow one and deny the other at
  tool-name-filtering granularity. Building a safe Terraform executor is
  a second, separable problem (scoping `create_run` to `run_type=plan_and_apply`
  only, never letting a caller smuggle a different run type through) —
  deferred to its own change rather than solved as a side effect of this
  one. `PlanRecord.toolchain` still gets fixed to be *accurate*
  (reflecting which path actually ran), independent of whether a
  Terraform executor exists yet to consume it.
- Live-verifying the mutating tool names against a real running MCP
  server is a **precondition** for implementation (Migration Plan step
  0), not something this design does — no AWS credentials are available
  in this planning environment either.
- Any Control UI, `TeamMember`/`scope`, foundation/Kubernetes work — all
  explicitly out of scope per the proposal.
- Automatic rollback of partially-created resources on failure (see
  Risks below — surfaced, not automated).

## Decisions

**`agent_approved` is derived, not a new input.** `plan_request()`
already only ever returns non-empty `tool_intents` when the agent side
has already approved: the LLM-graph path only harvests
`propose_tool_intent` calls `if _security_approved(messages)`
(`workflows/drafting/plan_request.py:150`), and the deterministic
skill-fill path's own existing comment states "a stable skill's
provenance IS its review." So: `agent_approved = bool(tool_intents)` —
a fact already established by the time `plan_request()` returns, not a
new judgment call this change introduces.

**`human_approved` is required for every intent at this MVP's scope.**
No autonomous-approval tier is designed anywhere yet (`review_policy`'s
`"automated"` mode, `docs/personas_and_tool_blueprints.md` Part C, is
sandbox-only and doesn't exist in code) — so the fixed policy for this
change is simply: `evaluate_intent()` returns `True` only if both
`agent_approved` **and** `human_approved` are `True`. Revisit once a
real autonomous-tier policy exists; don't invent one here.

**New module: `gateway/dispatch_execution.py`, not inside
`workflows/drafting/`.** Mirrors the propose/execute split this project
already draws structurally (mutating tools filtered out of the drafting
graph entirely) — execution operates on plain `PlanRecord`/`ToolIntent`
Pydantic objects, has no LangGraph dependency, and belongs next to
`gateway/tool_dispatcher.py` it calls directly, not inside the
framework-specific drafting package.

```python
async def dispatch_and_execute(
    plan: PlanRecord,
    tool_intents: list[ToolIntent],
    human_approved: bool,
    dispatcher: BrokeredToolDispatcher,
    mcp_client: MultiServerMCPClient,
) -> DispatchResult:
    ...
```
`human_approved` stays a plain boolean parameter — the minimal stand-in
named in the proposal, supplied by a CLI prompt or test today, by a real
Control UI decision later, with no interface change required at that
point.

**Payload contract built from live schema introspection, not a
hardcoded mapping.** `ToolIntent.payload` today carries the raw spec
dict (`type`/`name` fields from `skill_fill.py`). Rather than guess
CCAPI's exact desired-state shape (unverified, per Context item 3), the
executor calls CCAPI's existing read-only `get_resource_schema_information(resource_type)`
tool first, and builds `create_resource`'s desired-state payload against
the returned schema. This also means the payload-mapping code degrades
safely if CCAPI's actual schema differs from what today's `payload` dict
assumes — a schema mismatch surfaces as a clear pre-execution error, not
a malformed live API call.

**Partial-failure policy: stop on first failure, never auto-rollback,
surface exactly what succeeded.** Intents execute sequentially (plan
order). On the first execution failure, remaining intents in the same
plan are skipped (recorded as `skipped_prior_failure`, not attempted).
Already-created resources from earlier intents in the same plan are
**not** automatically torn down — matches this project's existing bias
against automated destructive recovery (e.g. `FoundationRecord`
decommissioning requires an explicit request elsewhere in this project's
design, never an automatic cascade). `DispatchResult` reports per-intent
terminal status so a human can decide manual cleanup.

**New `executions` table, same SQLite file `BrokeredToolDispatcher`
already opens.** Matches this project's established storage convention
(`docs/config_storage_backend.md`: one database, not a new storage
system per concept):
```sql
CREATE TABLE IF NOT EXISTS executions (
    intent_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_identifier TEXT NOT NULL,
    status TEXT NOT NULL,  -- "succeeded" | "failed" | "denied" | "skipped_prior_failure"
    provider_request_id TEXT,
    error_message TEXT,
    executed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
```

**`PlanRecord.toolchain` set from which path actually executed, not a
hardcoded literal.** `workflows/drafting/plan_request.py:171` sets
`toolchain="cdk"` unconditionally, even on the LLM-graph path where
`route_toolchain` (`workflows/drafting/nodes.py:27`) may have chosen
`"terraform"`. Fix: read `result["toolchain"]` off the graph's final
state (already present, `DraftingState`) instead of hardcoding — a
one-line correctness fix, independent of whether a Terraform executor
exists yet to act on the corrected value.

## Risks / Trade-offs
- [Risk] The inferred CCAPI/Terraform mutating tool names
  (`workflows/drafting/mcp_tools.py:13-22`) could be wrong, causing the
  executor to call a tool that doesn't exist or has a different
  signature than assumed → [Mitigation] Migration Plan step 0 (below)
  is a hard blocker: live-verify via `MultiServerMCPClient.get_tools()`
  against a running `ccapi-mcp-server` before writing the executor
  against these names, not after.
- [Risk] Stop-on-first-failure with no auto-rollback can leave real,
  partially-created AWS resources billing/running with no automated
  cleanup → [Mitigation] deliberate — matches this project's standing
  bias against automated destructive actions; `DispatchResult` and the
  `executions` table make the partial state fully visible for manual
  handling, cost ceiling (`WorkspaceBundle.cost_ceiling_usd`) still
  applies per-resource going forward.
- [Risk] `human_approved` as a bare boolean parameter is a real security
  surface if a future caller passes `True` without an actual human
  decision behind it → [Mitigation] accepted for this MVP slice (same
  precedent as `plan_request()` itself, which had no real caller before
  this change either) — flagged explicitly so it isn't silently trusted
  once a real caller exists; a Control UI's `ApprovalRecord.human_reviewer`
  (`docs/control_ui_approval_queue_design.md`) is the eventual real
  source of this boolean, not designed here.
- [Risk] `get_resource_schema_information` might not return a shape this
  executor can mechanically turn into a `create_resource` payload
  (e.g., it could be documentation-shaped, not JSON-Schema-shaped) →
  [Mitigation] unverified until Migration Plan step 0's live check;
  if it isn't mechanically usable, fall back to a small explicit
  per-resource-type payload-building function for exactly the two
  in-scope types (`AWS::S3::Bucket`, `AWS::CloudFront::Distribution`)
  instead of a generic schema-driven mapper.

## Migration Plan
0. **Blocking precondition**: connect to a live `ccapi-mcp-server` (and
   `terraform-mcp-server`, for completeness even though execution is
   deferred) via `MultiServerMCPClient.get_tools()`, diff the real tool
   names/signatures against `workflows/drafting/mcp_tools.py`'s inferred
   denylist, and confirm `get_resource_schema_information`'s actual
   return shape. Correct `mcp_tools.py`'s docstring/denylist if anything
   differs from what's currently inferred.
1. Fix `evaluate_intent()`'s `human_approved` check
   (`gateway/tool_dispatcher.py`) — small, isolated, testable alone
   against the existing `tests/test_gateway.py` pattern first.
2. Fix `PlanRecord.toolchain` (`workflows/drafting/plan_request.py`) —
   independent one-line fix, testable alone.
3. Add the `executions` table and `gateway/dispatch_execution.py`'s
   `dispatch_and_execute()`, built against the verified tool names/schema
   from step 0.
4. Tests: fixed `human_approved` gate, payload-mapping against a fake
   `get_resource_schema_information` response, stop-on-first-failure
   ordering, `executions` table writes — mirrors
   `tests/test_gateway.py`'s dispatcher-test structure.

No cutover step — additive to existing, real, tested code; nothing
currently working changes behavior except the two named bug fixes
(`human_approved`, `toolchain`).

## Open Questions
- Whether `dispatch_and_execute()` becomes a `gateway/`-level public
  entry point later (a `dispatch_plan(plan, tool_intents, human_approved)`
  re-export, matching `plan_request()`'s own boundary shape) — same
  open-question pattern already left for `intake_request()`/
  `inquiry_request()`; not resolved here either.
- Exact fallback shape if `get_resource_schema_information` turns out
  not to be mechanically usable (Risk above) — decide once Migration
  Plan step 0's live check actually runs, not speculatively here.
- Whether a Terraform executor (deferred, Non-Goals) should reuse
  `dispatch_and_execute()`'s shape once `create_run`'s `run_type`
  scoping problem is solved, or need its own function entirely — not
  designed, flagged for whichever change takes that on next.
