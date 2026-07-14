## 1. Resolve open questions before implementation starts

- [x] 1.1 Decide whether this change also closes the pre-existing
      propose-vs-execute gap on `cdk_provisioning_agent`/
      `terraform_provisioning_agent` — **resolved 2026-07-14: yes**,
      closed as part of this change (design.md Goals). Task 3.9 below
      implements it.
- [x] 1.2 Confirm the parallel-build package name — **resolved
      2026-07-14: `langgraph_agents/`**, reads naturally as a Python
      package and matches the existing flat top-level convention
      (`gateway/`, `agents/`, `mcp_server/`, `spec/`, `skills/`)
- [ ] 1.3 Audit `config/models.yaml` for the exact set of LLM providers
      in use, to scope which `langchain-<provider>` integration
      packages task 2.1 actually needs (not a defensive install-everything)

## 2. Dependencies and scaffolding

- [ ] 2.1 Add `langgraph`, `langgraph-checkpoint-sqlite`,
      `langchain-mcp-adapters`, `langchain`, and the provider packages
      from task 1.3 to `pyproject.toml`/`uv.lock` — additive, alongside
      `google-adk`, not replacing it yet
- [ ] 2.2 Scaffold the parallel-build package (name per task 1.2) with a
      module-level docstring stating it is the not-yet-cut-over
      replacement for `agents/`

## 3. Build the LangGraph agent runtime

- [ ] 3.1 Implement the `StateGraph` structure mirroring
      `agents/orchestrator.py`'s routing shape: a routing node
      (`provisioning_agent` equivalent) and provisioning tool-calling
      nodes (`cdk_provisioning_agent`/`terraform_provisioning_agent`
      equivalents)
- [ ] 3.2 Implement `security_agent`'s review as a separate graph node
      connected by a structural edge gating provisioning output from
      dispatch (design.md's "security review as a node" decision;
      matches `specs/langgraph-agent-runtime/spec.md`'s corresponding
      requirement)
- [ ] 3.3 Bind `aws-iac-mcp-server`, `ccapi-mcp-server`, and
      `terraform-mcp-server` via `langchain-mcp-adapters`'
      `MultiServerMCPClient`/`StdioConnection`, reusing the exact
      `command`/`args`/`env` values from `mcp_server/external_servers.py`
      unchanged
- [ ] 3.4 Implement model selection via `init_chat_model(model,
      model_provider, ...)`, reading from `config/models.yaml` the same
      way `agents/model_config.py`'s `get_model()` does today
- [ ] 3.5 Implement `SkillTemplateFillAgent`'s zero-LLM drafting step as
      a plain LangGraph node function (no subclassing required)
- [ ] 3.6 Vendor `list_skills_in_dir`/`load_skill_from_dir`'s behavior
      as project-owned code with no `google-adk` import — confirm
      `gateway/skill_matching.py` needs no changes beyond its two import
      lines
- [ ] 3.7 Configure checkpointing with `AsyncSqliteSaver`
      (`langgraph-checkpoint-sqlite`) — not `InMemorySaver`, not the
      synchronous `SqliteSaver`
- [ ] 3.8 Implement `propose_tool_intent` as a real bound tool
      (`langchain_core.tools`), called from provisioning/drafting nodes
- [ ] 3.9 Close the propose-vs-execute gap: route
      `cdk_provisioning_agent`/`terraform_provisioning_agent`'s
      equivalent nodes' mutating calls through `propose_tool_intent`
      (task 3.8) instead of calling `CCAPI_MCP_SERVER`/
      `TERRAFORM_MCP_SERVER`'s create/update/delete tools directly —
      those MCP servers' read-only/validation tools (cfn-lint,
      cfn-guard, etc.) may still be called directly, only the mutating
      operations route through the proposal boundary

## 4. Build the new plan_request() implementation

- [ ] 4.1 Implement a new `plan_request(envelope, bundle, usage_store)
      -> (PlanRecord, list[ToolIntent])` against `langgraph_agents/`, in
      a distinctly-named module — `gateway/plan_request.py` stays
      untouched during this step
- [ ] 4.2 Port compliance preflight (`run_compliance_preflight`) and
      envelope-to-spec extraction (`envelope_to_spec`) unchanged — these
      don't depend on the agent framework
- [ ] 4.3 Implement the two-pass `propose_tool_intent` harvesting:
      collect raw tool-call args from the final graph state's messages,
      construct `ToolIntent` objects only after `plan_hash` is computed
      from the fully-assembled `plan_text` — never before
- [ ] 4.4 Wire `check_structured_match()`'s existing deterministic
      skill-match branch to route to the new zero-LLM node (task 3.5)
      vs. the LangGraph graph (task 3.1), mirroring today's `plan_request()`
      branch

## 5. Test parity

- [ ] 5.1 Port the 41 existing tests (`tests/test_gateway.py`,
      `test_plan_request*.py`, `test_skill_*.py`) to exercise the new
      LangGraph-based implementation, without modifying or removing the
      existing ADK-targeted suite
- [ ] 5.2 Add tests covering `specs/langgraph-agent-runtime/spec.md`'s
      scenarios specifically: plan_hash sequencing correctness,
      security-node gating, checkpoint persistence across a simulated
      restart, `google-adk`-uninstalled skill loading, and that no
      mutating MCP tool call is reachable from a provisioning node
      without first producing a `propose_tool_intent` call
- [ ] 5.3 Confirm both suites (existing ADK-targeted and new
      LangGraph-targeted) pass in the same CI run before proceeding to
      cutover

## 6. Cutover

- [ ] 6.1 Repoint `gateway/plan_request.py` at the LangGraph
      implementation in one commit
- [ ] 6.2 Remove `agents/*.py` and the old `plan_request()` internals
      from the active import path, but do not delete the files yet
- [ ] 6.3 Run the full test suite post-cutover to confirm no regression

## 7. Cleanup (after one release cycle with no regressions)

- [ ] 7.1 Delete `agents/*.py` and the old ADK-based test suite for real
- [ ] 7.2 Remove the `google-adk` dependency from `pyproject.toml`/`uv.lock`
- [ ] 7.3 Confirm `gateway/skill_matching.py` and all tests still pass
      with `google-adk` fully uninstalled

## 8. Documentation

- [ ] 8.1 Correct `docs/langgraph_vs_adk_inner_layer.md`'s comparison
      table and Part D cost argument in place, with a note pointing at
      this change and the verified findings it rests on (stdio MCP
      compatibility, `init_chat_model`, portable skill-loading,
      `SqliteSaver`/`AsyncSqliteSaver`) — not a silent rewrite
- [ ] 8.2 Update `AGENTS.md`'s `agents/` bullet once cutover (task 6)
      is complete
