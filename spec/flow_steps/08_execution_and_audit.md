# Flow Step 8: Execution + Audit

## Owning code
Real MCP tool calls exist (`ccapi-mcp-server`, Terraform MCP server,
and — per `docs/eks_helm_mcp_integration.md` — `kubernetes-mcp-server`
for the Helm app-layer path). `harness/tool_dispatcher.py`'s
`audit_logs` table is real and tested. Not yet connected: execution
isn't gated by Step 7 in the live agent graph, and the audit table is
missing `channel_user_id`.

## Input contract
An `ALLOW` result from Step 7, plus the `ToolIntent` that produced it.

## Output contract
A real cloud resource created/updated/deleted, plus one `audit_logs`
row recording `plan_id`, `org_id`, `bu_id`, `resource_type`,
`operation`, `decision`, `reason`, `payload`
(`harness/tool_dispatcher.py:24-35`).

## Scenarios

## Scenario: Only an ALLOW result reaches the real cloud call
Given a Step 7 dispatch result
When execution proceeds
Then the real CCAPI/Terraform/Helm call happens if and only if that result was `ALLOW` — never as a side effect of drafting or reviewing a plan

## Scenario: Every decision is audited, not just allowed ones
Given any dispatch decision, ALLOW or DENY
When `evaluate_intent()` completes
Then `_log_audit()` writes a row regardless of outcome (`harness/tool_dispatcher.py:104-105` — `ALLOW` and every `DENY` branch both call `_log_audit`)

## Scenario: The audit trail should record who, not just which BU
Given a dispatch decision made in response to a specific person's request
When the audit row is written
Then it should include `channel_user_id`, not just `org_id`/`bu_id` — **currently does not**, a known gap since individual-action accountability (e.g. who clicked Approve) needs person-level, not BU-level, granularity (`docs/ui_and_multitenancy_deep_dive.md`'s audit gap finding)

## Scenario: Skill provenance is recorded
Given execution using a plan built from a matched skill (bundled/org/BU tier)
When the audit row is written
Then it should record which tier and skill version was used, not just the outcome — **currently does not**, per `docs/end_to_end_flow_example.md` step 11

## Status
Real MCP execution tools and a real, tested audit table exist as
separate pieces. They are not yet connected to each other in a live
agent run — `docs/HARNESS_DESIGN.md`'s "enforcement gap" (mutating MCP
tools still attached directly to provisioning agents, not routed
through the dispatcher first).
