## 1. Live verification (blocking precondition)

- [ ] 1.1 Connect to a live `awslabs.eks-mcp-server` via `MultiServerMCPClient.get_tools()` and confirm `manage_eks_stacks`'s exact operations/parameters (`generate`/`deploy`/`describe`)
- [ ] 1.2 Connect to a live `gke-mcp` (self-hosted Go binary) via `get_tools()` and confirm its cluster-creation tool name and parameters
- [ ] 1.3 Connect to a live `aks-mcp` (self-hosted Go binary) via `get_tools()` and confirm its cluster-creation tool name and parameters (`az_aks_operations create` or equivalent)
- [ ] 1.4 Record the confirmed tool names/schemas for each cloud in `mcp_server/external_servers.py`'s module docstring, same convention as the existing AWS entries

## 2. `TeamMember`/`scope` and the scope gate

- [x] 2.1 Add `TeamMember` (`channel_user_id`, `display_name`, `role`, `scope`) to `gateway/schemas.py`, per `docs/skills_and_workspace_design.md`
- [x] 2.2 Add `members: list[TeamMember]` to `WorkspaceBundle`
- [x] 2.3 Add the scope-gate check function (denies before skill/tool resolution if `scope == "app"`)
- [x] 2.4 Tests: app-scoped requester denied; stack-scoped and both-scoped requesters pass

## 3. `ResourceRecord`

- [x] 3.1 Add `ResourceRecord` to `gateway/schemas.py`, including `compute_paradigm: str = "kubernetes"` per design.md
- [x] 3.2 Add the `resource_records` SQLite table, same `db_path` as `BrokeredToolDispatcher`
- [x] 3.3 Add a small store (`record_resource()`, `get_resource()`) — mirrors `SkillUsageStore`'s shape
- [x] 3.4 Tests: write and read a `ResourceRecord`, confirm `compute_paradigm`/`layer` defaults

## 4. MCP server configs

- [x] 4.1 Add `EKS_MCP_SERVER` to `mcp_server/external_servers.py` (uvx, matches existing AWS entries)
- [x] 4.2 Add `GKE_MCP_SERVER` (Go binary path, `StdioServerParameters`)
- [x] 4.3 Add `AKS_MCP_SERVER` (Go binary path, `StdioServerParameters`)
- [x] 4.4 Document the hosted-override branch as a comment/TODO per server (not implemented this change, per design.md Non-Goals) — same shape as `docs/multi_cloud_foundation_and_iam.md` Part E's sketch

## 5. `gateway/kubernetes_resource_dispatch.py`

- [x] 5.1 Create the module with `dispatch_and_execute_cluster(plan, tool_intent, human_approved, dispatcher, mcp_client, cloud_provider) -> ClusterDispatchResult`
- [x] 5.2 Implement the generate/deploy split: generation call (non-mutating, recorded) before the gated `ToolIntent` is even proposed
- [x] 5.3 Implement the approval check: single `record_approval()` + `evaluate_intent()` call, always requiring `human_approved=True`
- [x] 5.4 Implement `_execute_aws_eks()` using the tool name/schema confirmed in task 1.1 — **built against researched, not live-verified, tool name** (`manage_eks_stacks`); task 1.1 itself still open, no AWS credentials in this environment
- [x] 5.5 Implement `_execute_gcp_gke()` using the tool name/schema confirmed in task 1.2 (blocked until 1.2 done) — **built against researched, not live-verified, tool name** (`create_cluster`); task 1.2 itself still open, no GCP credentials in this environment
- [x] 5.6 Implement `_execute_azure_aks()` using the tool name/schema confirmed in task 1.3 (blocked until 1.3 done) — **built against researched, not live-verified, tool name** (`az_aks_operations`); task 1.3 itself still open, no Azure credentials in this environment
- [x] 5.7 On success, write the `ResourceRecord` (task 3.3's store)
- [x] 5.8 Define `ClusterDispatchResult` (Pydantic: status, resource_identifier, error_message, resource_id, stack_id)

## 6. Tests

- [x] 6.1 Test: denied `ToolIntent` (human_approved=False) never calls any MCP tool, no `ResourceRecord` written
- [x] 6.2 Test: AWS path — mocked `manage_eks_stacks` success writes a `ResourceRecord` with `cloud_provider="aws"`, `compute_paradigm="kubernetes"`
- [x] 6.3 Test: GCP path — same, mocked `gke-mcp` tool, `cloud_provider="gcp"`
- [x] 6.4 Test: Azure path — same, mocked `aks-mcp` tool, `cloud_provider="azure"`
- [x] 6.5 Test: generation step succeeds and is recorded even with no approval record present yet
- [x] 6.6 Test: a failed execution (mocked MCP error) does not write a `ResourceRecord`
- [x] 6.7 Run the full test suite (`pytest tests/`) and confirm no regressions — 80 passed, 0 failed (81 after task 8's rename added one more test)

## 7. Manual real-credential checklist (not automated — for whoever runs this with real cloud access)

- [ ] 7.1 AWS: run the flow end to end against a real sandbox account, confirm a real EKS cluster is created and `ResourceRecord` matches it
- [ ] 7.2 GCP: same, against a real GKE-enabled project
- [ ] 7.3 Azure: same, against a real AKS-enabled subscription
- [ ] 7.4 For each: confirm the denied-approval path is also exercised against the real dispatcher (no accidental cluster creation on a rejected plan)

## 8. Rename to Resource/Stack terminology (docs/composable_foundation_blueprints.md Parts G–M, applied same session)

- [x] 8.1 `FoundationRecord` → `ResourceRecord`; `foundation_id` → `resource_id`; add required `stack_id` field (binding mechanism still undesigned — see design.md Open Questions)
- [x] 8.2 `TeamMember.scope` values: `"foundation"` → `"stack"`
- [x] 8.3 `gateway/scope_gate.py`: `requester_has_foundation_scope()` → `requester_has_stack_scope()`
- [x] 8.4 `gateway/foundation_store.py` → `gateway/resource_store.py`; `FoundationStore` → `ResourceStore`; `record_foundation()`/`get_foundation()` → `record_resource()`/`get_resource()`
- [x] 8.5 `gateway/kubernetes_foundation_dispatch.py` → `gateway/kubernetes_resource_dispatch.py`; `ClusterDispatchResult.foundation_id` → `resource_id` + new `stack_id` field; `dispatch_and_execute_cluster()` gains optional `stack_id` parameter (auto-generates one if omitted)
- [x] 8.6 `mcp_server/external_servers.py` comments updated ("Kubernetes foundation-layer" → "Kubernetes cluster (Stack-tier)")
- [x] 8.7 All tests renamed/updated (`test_foundation_store.py` → `test_resource_store.py`, `test_kubernetes_foundation_dispatch.py` → `test_kubernetes_resource_dispatch.py`, `test_scope_gate.py` updated), plus one new test (`test_explicit_stack_id_is_reused_not_overridden`)
- [x] 8.8 `scripts/manual_test_cluster_flow.py` updated, including a new `--stack-id` flag
- [x] 8.9 Full test suite re-run: 81 passed, 0 failed
- [x] 8.10 These OpenSpec artifacts (proposal/design/tasks/specs) updated to match the renamed code
