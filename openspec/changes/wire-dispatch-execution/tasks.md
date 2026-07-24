## 1. Live verification (blocking precondition)

- [ ] 1.1 Connect to a live `ccapi-mcp-server` via `MultiServerMCPClient.get_tools()` and record the real tool names/signatures for `create_resource`/`update_resource`/`delete_resource` (or whatever they're actually named)
- [ ] 1.2 Call `get_resource_schema_information` for `AWS::S3::Bucket` and `AWS::CloudFront::Distribution` and record the actual returned shape
- [ ] 1.3 Correct `workflows/drafting/mcp_tools.py`'s `_CCAPI_MUTATING_TOOLS` denylist and docstring if step 1.1 found any difference from what's currently inferred
- [ ] 1.4 Decide the payload-mapping fallback (schema-driven vs. explicit per-type function) based on what step 1.2 actually returned, per design.md's Risks section

## 2. Fix `evaluate_intent()`'s `human_approved` gate

- [ ] 2.1 Change `gateway/tool_dispatcher.py`'s `evaluate_intent()` to require `human_approved` in addition to `agent_approved`, removing the unused `_human_app` variable
- [ ] 2.2 Add a test to `tests/test_gateway.py`: agent-approved but not human-approved denies
- [ ] 2.3 Add a test to `tests/test_gateway.py`: both approved passes (update any existing passing-case test that only set `agent_approved`)
- [ ] 2.4 Run the full existing `tests/test_gateway.py` suite and confirm nothing else silently depended on the old (bugged) behavior

## 3. Fix `PlanRecord.toolchain`

- [ ] 3.1 Confirm `DraftingState` carries the resolved toolchain through to the graph's final state (check `workflows/drafting/state.py`, `workflows/drafting/nodes.py`)
- [ ] 3.2 Change `workflows/drafting/plan_request.py` to read the resolved toolchain from `result` instead of hardcoding `"cdk"`
- [ ] 3.3 Add a test to `tests/test_workflows_drafting_plan_request.py`: a Terraform-routed request produces `PlanRecord.toolchain == "terraform"`

## 4. `executions` table

- [ ] 4.1 Add the `executions` table (schema per design.md) to `gateway/tool_dispatcher.py`'s `_init_db()` or a shared init path, same `db_path` as `audit_logs`/`approvals`
- [ ] 4.2 Add a small `ExecutionStore` (or extend `BrokeredToolDispatcher`) with `record_execution(intent_id, plan_id, status, provider_request_id=None, error_message=None)`

## 5. `gateway/dispatch_execution.py`

- [ ] 5.1 Create `gateway/dispatch_execution.py` with `dispatch_and_execute(plan, tool_intents, human_approved, dispatcher, mcp_client) -> DispatchResult`
- [ ] 5.2 Implement `agent_approved` derivation (`bool(tool_intents)`) and the single `record_approval()` call per plan
- [ ] 5.3 Implement per-intent `evaluate_intent()` check; record `"denied"` execution outcome and skip the MCP call for denied intents
- [ ] 5.4 Implement the payload-building step against the verified schema shape from task 1.2/1.4
- [ ] 5.5 Implement the real `create_resource` MCP call for approved intents, using the tool name confirmed in task 1.1
- [ ] 5.6 Implement stop-on-first-failure ordering: on the first `"failed"` outcome, mark all remaining intents in the plan `"skipped_prior_failure"` without attempting them
- [ ] 5.7 Write one `executions` row per processed intent via `record_execution()`
- [ ] 5.8 Define `DispatchResult` (Pydantic model: per-intent outcomes, overall plan status)

## 6. Tests

- [ ] 6.1 Test: denied intent (dispatcher returns `False`) never triggers an MCP call, recorded `"denied"`
- [ ] 6.2 Test: payload schema mismatch is caught and recorded `"failed"` before any `create_resource` call (using a fake/mocked MCP client)
- [ ] 6.3 Test: multi-intent plan where the second intent fails — first stays `"succeeded"`, second `"failed"`, third `"skipped_prior_failure"`, no automatic rollback attempted
- [ ] 6.4 Test: successful execution records `provider_request_id` in the `executions` table
- [ ] 6.5 Test: `agent_approved` is derived correctly from a non-empty `tool_intents` list without a separate input
- [ ] 6.6 Run the full test suite (`pytest tests/`) and confirm no regressions in existing dispatcher/plan_request tests
