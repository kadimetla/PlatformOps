## 1. Resolve open questions before implementation starts

- [x] 1.1 Decide whether this change also closes the pre-existing
      propose-vs-execute gap on `cdk_provisioning_agent`/
      `terraform_provisioning_agent` — **resolved 2026-07-14: yes**,
      closed as part of this change (design.md Goals). Task 3.9 below
      implements it.
- [x] 1.2 Confirm the parallel-build package name — **resolved
      2026-07-14: `workflows/drafting/`**, reads naturally as a Python
      package and matches the existing flat top-level convention
      (`gateway/`, `agents/`, `mcp_server/`, `spec/`, `skills/`)
- [x] 1.3 Audit `config/models.yaml` for the exact set of LLM providers
      in use — **resolved 2026-07-14: Gemini only** (`gemini-2.5-flash`
      for routing/execution/orchestration, `gemini-2.5-pro` for review),
      via Google AI Studio (`README.md:183`'s `GOOGLE_API_KEY`), not
      Vertex AI. **Superseded by the `litellm` decision below**: this no
      longer matters for package selection (one package, any provider),
      but the underlying finding stands — `litellm`'s own
      `gemini/gemini-2.5-flash` model-string convention is unambiguous
      about provider, avoiding the `init_chat_model` Vertex-vs-Studio
      inference gotcha this audit originally surfaced.
- [x] 1.4 **New, resolved 2026-07-14**: model backend is `litellm` via
      `langchain_litellm.ChatLiteLLM`, not `init_chat_model` —
      confirmed real (`ChatLiteLLM.bind_tools` present, dependencies are
      only `langchain-core`/`litellm`/`httpx`/`cryptography`, not the
      full `langchain` metapackage or any per-provider package). Also
      adds a new requirement: every LLM call logged for observability
      via `litellm`'s native `success_callback`/`failure_callback`
      hooks, to a new `llm_call_logs` table. See design.md's
      corresponding correction and new Decision.

## 2. Dependencies and scaffolding

- [x] 2.1 Add `langgraph`, `langgraph-checkpoint-sqlite`,
      `langchain-mcp-adapters`, `litellm`, `langchain-litellm` to
      `pyproject.toml`/`uv.lock` via `uv add` — additive, alongside
      `google-adk`, not replacing it yet. **Done 2026-07-14** — `uv add
      langgraph langgraph-checkpoint-sqlite langchain-mcp-adapters
      langchain langchain-google-genai` was run first (per the original
      `init_chat_model` plan), then `langchain`/`langchain-google-genai`
      removed and `litellm`/`langchain-litellm` added once task 1.4's
      correction landed. **Real issue hit and fixed**: `uv remove`
      dropped the `dev` extras group (`pytest` disappeared from the
      environment even though correctly declared in `pyproject.toml`) —
      fixed with `uv sync --extra dev`; all 41 existing tests confirmed
      green afterward.
- [x] 2.2 Scaffold the parallel-build package (name per task 1.2) with a
      module-level docstring stating it is the not-yet-cut-over
      replacement for `agents/` — **done**, `workflows/__init__.py`,
      `workflows/drafting/__init__.py`

## 3. Build the LangGraph agent runtime

- [x] 3.1 Implement the `StateGraph` structure mirroring
      `agents/orchestrator.py`'s routing shape: a routing node
      (`provisioning_agent` equivalent) and provisioning tool-calling
      nodes (`cdk_provisioning_agent`/`terraform_provisioning_agent`
      equivalents). **Done**: `workflows/drafting/state.py` (state
      schema), `workflows/drafting/nodes.py` (node functions, via
      `langgraph.prebuilt.create_react_agent` for the tool-calling
      loop), `workflows/drafting/graph.py` (wiring). Verified: graph
      compiles, all 4 real nodes + start/end present.
      **Real deviation, flagged not silently decided**: toolchain
      routing (`route_toolchain`) is deterministic (reads
      `spec["toolchain"]`, defaults `"cdk"`) rather than the original
      LLM sub-agent decision — a plain field read doesn't need an LLM
      call. Matches `PlanRecord.toolchain`'s own hardcoded `"cdk"`
      default in today's `gateway/plan_request.py`.
- [x] 3.2 Implement `security_agent`'s review as a separate graph node
      connected by a structural edge gating provisioning output from
      dispatch (design.md's "security review as a node" decision;
      matches `specs/langgraph-agent-runtime/spec.md`'s corresponding
      requirement). **Done**: `workflows/drafting/security_tools.py`
      (`record_security_decision`, mirrors `propose_tool_intent`'s
      pattern), `security_review_node` in `nodes.py`.
      **Real design note, not silently decided**: unlike ADK's
      event-stream capture (never executes `propose_tool_intent`),
      LangGraph's `ToolNode` genuinely executes bound tools — so
      provisioning nodes' proposed intents already exist in message
      history before `security_review` runs. The gate is enforced in
      `plan_request()`'s harvest step (task 4.3), which checks
      `record_security_decision(approved=True)` was called before
      including any `ToolIntent` — not by graph structure preventing
      the calls from happening in the first place. Documented in
      `security_tools.py`'s own docstring.
- [x] 3.3 Bind `aws-iac-mcp-server`, `ccapi-mcp-server`, and
      `terraform-mcp-server` via `langchain-mcp-adapters`'
      `MultiServerMCPClient`/`StdioConnection`, reusing the exact
      `command`/`args`/`env` values from `mcp_server/external_servers.py`
      unchanged. **Done**: `workflows/drafting/mcp_tools.py`. Verified
      `MultiServerMCPClient.get_tools(server_name=...)`'s real signature
      and that the client builds cleanly against the real
      `StdioConnection` conversion.
- [x] 3.4 Implement model selection via `langchain_litellm.ChatLiteLLM`,
      reading from `config/models.yaml` the same way
      `agents/model_config.py`'s `get_model()` does today, converting
      the configured bare model name (e.g. `gemini-2.5-flash`) into
      `litellm`'s `provider/model` convention (e.g.
      `gemini/gemini-2.5-flash`) for Google AI Studio specifically.
      **Done**: `workflows/drafting/model_config.py`. Verified real
      against the actual project venv (`model='gemini/gemini-2.5-flash'`
      on the instantiated `ChatLiteLLM` object).
- [x] 3.5 Implement `SkillTemplateFillAgent`'s zero-LLM drafting step as
      a plain LangGraph node function (no subclassing required).
      **Done**: `workflows/drafting/skill_fill.py` —
      `run_deterministic_skill_fill()`. Verified end-to-end against a
      synthetic Terraform skill (fill + re-parse validate + proposed
      intent args, matching `ToolIntent`'s shape exactly).
- [x] 3.6 Vendor `list_skills_in_dir`/`load_skill_from_dir`'s behavior
      as project-owned code with no `google-adk` import — confirm
      `gateway/skill_matching.py` needs no changes beyond its two import
      lines. **Done**: `workflows/drafting/skill_loading.py`. Verified
      byte-for-byte parity against the real `google.adk.skills` on this
      project's actual `skills/` directory (all 3 skills:
      `provision-infra`, `sdlc-diagram-compliance-check`,
      `security-review-checklist`) — frontmatter and full load
      (instructions + script keys) both match exactly.
- [x] 3.7 Configure checkpointing with `AsyncSqliteSaver`
      (`langgraph-checkpoint-sqlite`) — not `InMemorySaver`, not the
      synchronous `SqliteSaver`. **Done**:
      `workflows/drafting/graph.py`'s `build_checkpointed_drafting_graph()`,
      an async context manager wrapping `AsyncSqliteSaver.from_conn_string()`.
      Verified real signature (`-> AsyncIterator[AsyncSqliteSaver]`) and
      end-to-end compilation against a real temp SQLite file.
- [x] 3.8 Implement `propose_tool_intent` as a real bound tool
      (`langchain_core.tools`), called from provisioning/drafting nodes.
      **Done**: `workflows/drafting/tools.py`. Verified real —
      `@tool`-decorated, `.invoke()` confirmed working, args match
      `ToolIntent`'s field names exactly (minus `plan_id`/`plan_hash`/
      `org_id`/`bu_id`, stamped later per the two-pass discipline).
- [x] 3.9 Close the propose-vs-execute gap: route
      `cdk_provisioning_agent`/`terraform_provisioning_agent`'s
      equivalent nodes' mutating calls through `propose_tool_intent`
      (task 3.8) instead of calling `CCAPI_MCP_SERVER`/
      `TERRAFORM_MCP_SERVER`'s create/update/delete tools directly —
      those MCP servers' read-only/validation tools (cfn-lint,
      cfn-guard, etc.) may still be called directly, only the mutating
      operations route through the proposal boundary. **Done**:
      `workflows/drafting/mcp_tools.py`'s `_CCAPI_MUTATING_TOOLS`/
      `_TERRAFORM_MUTATING_TOOLS` denylists, applied before any tool
      list reaches a node's `bind_tools()` call. **Real, stated
      verification gap**: the exact mutating tool names are inferred
      from prior research, not confirmed against a live server (no
      credentials in this environment) — flagged explicitly in the
      module docstring, same category of gap
      `mcp_server/external_servers.py` already carries for the
      Terraform path. `terraform-mcp-server`'s `create_run` is excluded
      entirely (covers both safe `refresh_state` and mutating
      `plan_and_apply` via one parameter — no clean partial-allow at
      the tool-filtering level used here).
- [x] 3.10 **New**: add an `llm_call_logs` table (SQLite, same file
      `gateway/tool_dispatcher.py` opens) and a `litellm` callback
      function registered once at startup that writes every call's
      prompt, response, token counts, latency, and outcome — regardless
      of which node made the call, no per-node logging code needed.
      **Done**: `workflows/drafting/observability.py` —
      `LLMObservabilityLogger(CustomLogger)` (verified real
      `log_success_event`/`log_failure_event(self, kwargs, response_obj,
      start_time, end_time)` signature by direct introspection),
      `register_llm_observability(db_path)` sets `litellm.callbacks`.
      Verified: table creation and registration work end-to-end against
      a real SQLite file. Not yet verified against a real LLM call (no
      API key in this environment) — the `_write()` method's field
      extraction (`response_obj.usage`, `.choices[0].message.content`)
      is defensive (`getattr`/`try`/`except`) but unverified against a
      live response shape

## 4. Build the new plan_request() implementation

- [x] 4.1 Implement a new `plan_request(envelope, bundle, usage_store)
      -> (PlanRecord, list[ToolIntent])` against `workflows/drafting/`, in
      a distinctly-named module — `gateway/plan_request.py` stays
      untouched during this step. **Done**:
      `workflows/drafting/plan_request.py`. `gateway/plan_request.py`
      confirmed untouched (diff-free).
- [x] 4.2 Port compliance preflight (`run_compliance_preflight`) and
      envelope-to-spec extraction (`envelope_to_spec`) unchanged — these
      don't depend on the agent framework. **Done, but not literally
      unchanged**: `run_compliance_preflight`/`ComplianceError`/
      `is_valid_spec_shape` are *imported directly* from
      `gateway.plan_request` (genuinely zero duplication). The
      YAML-fallback half of `envelope_to_spec` needed a new
      `extract_spec_from_free_text()` using `ChatLiteLLM` instead of
      ADK's `Agent`/`Runner` — the deterministic YAML-parse-first logic
      is identical.
- [x] 4.3 Implement the two-pass `propose_tool_intent` harvesting:
      collect raw tool-call args from the final graph state's messages,
      construct `ToolIntent` objects only after `plan_hash` is computed
      from the fully-assembled `plan_text` — never before. **Done**:
      `_extract_propose_tool_intent_args()`/`_security_approved()` in
      `workflows/drafting/plan_request.py`.
- [x] 4.4 Wire `check_structured_match()`'s existing deterministic
      skill-match branch to route to the new zero-LLM node (task 3.5)
      vs. the LangGraph graph (task 3.1), mirroring today's `plan_request()`
      branch. **Done** — reuses `gateway.skill_template_agent.check_structured_match`
      directly (still ADK-backed via `gateway/skill_matching.py` until
      cutover, per that file's "unaffected" status in `proposal.md`).
      **Verified end-to-end**: `tests/test_workflows_drafting_plan_request.py`'s
      deterministic-match test passes against the real vendored skill
      loader.

## 5. Test parity

- [~] 5.1 Port the 41 existing tests to exercise the new LangGraph-based
      implementation, without modifying or removing the existing
      ADK-targeted suite. **Partially done**:
      `tests/test_workflows_drafting_plan_request.py` ports the two
      tests that don't need live LLM credentials (compliance-failure
      block, deterministic zero-LLM skill match) — the same real
      scoping limit `tests/test_plan_request_boundary.py` already
      states for the ADK suite (*"root_agent branch not exercised
      here, no model credentials"*) applies identically to the
      LangGraph-driven branch (`route_toolchain`/provisioning/
      `security_review`) — structurally wired and verified importable/
      compilable (graph.py's own checks), but not exercised against a
      real model or real MCP server subprocess in this environment.
      `tests/test_skill_matching.py`/`test_skill_usage_store.py`
      equivalents not ported separately — `gateway/skill_matching.py`
      and `skill_usage_store.py` are explicitly unmodified
      (`proposal.md` Impact), so their existing tests already cover
      this workflow's dependency on them.
- [ ] 5.2 Add tests covering `specs/langgraph-agent-runtime/spec.md`'s
      scenarios specifically: plan_hash sequencing correctness,
      security-node gating, checkpoint persistence across a simulated
      restart, `google-adk`-uninstalled skill loading, that no mutating
      MCP tool call is reachable from a provisioning node without first
      producing a `propose_tool_intent` call, and that both a successful
      and a failed LLM call produce an `llm_call_logs` row — **not yet
      done**, needs either a credentialed environment or mocked
      model/MCP responses to exercise the LLM-driven graph path
      end-to-end
- [x] 5.3 Confirm both suites (existing ADK-targeted and new
      LangGraph-targeted) pass in the same CI run before proceeding to
      cutover. **Done**: `uv run python -m pytest tests/ -q` → **43
      passed** (41 existing + 2 new), zero regressions.

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
      compatibility, `ChatLiteLLM`, portable skill-loading,
      `SqliteSaver`/`AsyncSqliteSaver`) — not a silent rewrite
- [ ] 8.2 Update `AGENTS.md`'s `agents/` bullet once cutover (task 6)
      is complete
