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
- [x] 5.2 Add tests covering `specs/langgraph-agent-runtime/spec.md`'s
      scenarios. **Done, via mocked model/MCP responses (no live
      credentials in this environment)**: `tests/test_workflows_
      drafting_graph.py` — real end-to-end graph execution using
      `langchain_core`'s `FakeMessagesListChatModel` (scripted tool
      calls) and stubbed MCP tool loaders. Covers: security-node
      gating (a rejected plan's `propose_tool_intent` call IS still in
      message history — LangGraph executes tools immediately, unlike
      ADK's event-stream capture — but `plan_request.py`'s
      `_security_approved()` check correctly excludes it from harvest),
      and both successful and failed LLM calls producing an
      `llm_call_logs` row (tested directly against
      `LLMObservabilityLogger`'s real callback methods, since the fake
      model bypasses `litellm` entirely and can't exercise its
      callbacks). **Not done**: `google-adk`-uninstalled skill loading
      (deferred to task 7.3, which is exactly that check) and
      checkpoint-persistence-across-a-restart (no test added; the
      mechanism itself was verified in task 3.7 against a real SQLite
      file, but not through a full drafting-graph pause/restart cycle).
      **Real finding surfaced while writing these tests**:
      `langgraph.prebuilt.create_react_agent` (used in `nodes.py`) is
      deprecated as of LangGraph v1.0, in favor of
      `langchain.agents.create_agent` — *"Deprecated in LangGraph V1.0
      to be removed in V2.0."* Still fully functional on the installed
      `langgraph==1.2.9`; not migrated now because the replacement
      lives in the full `langchain` package, which was deliberately
      removed for the `ChatLiteLLM` decision (task 1.4) — flagged as a
      real, known future migration cost in design.md's Risks, not
      silently absorbed by re-adding that dependency.
- [x] 5.3 Confirm both suites (existing ADK-targeted and new
      LangGraph-targeted) pass in the same CI run before proceeding to
      cutover. **Done**: `uv run python -m pytest tests/ -q` → **43
      passed** (41 existing + 2 new), zero regressions.

## 6. Cutover

- [x] 6.1 Repoint `gateway/plan_request.py` at the LangGraph
      implementation. **Done** — `gateway/plan_request.py` is now a
      thin re-export of `workflows/drafting/plan_request.py`.
      `ComplianceError`/`is_valid_spec_shape`/`run_compliance_preflight`/
      `REQUIRED_SPEC_KEYS` extracted to a new `gateway/compliance_preflight.py`
      (framework-independent) specifically to avoid a circular import
      between the two modules — verified clean in both import orders.
- [x] 6.2 Remove `agents/*.py` and the old `plan_request()` internals
      from the active import path, but do not delete the files yet.
      **Done, and required zero additional edits**: confirmed by
      repo-wide search that nothing outside `agents/` itself imports
      from it anymore — task 6.1's re-export was the only real
      dependency on the old implementation.
- [x] 6.3 Run the full test suite post-cutover to confirm no regression.
      **Done**: `uv run python -m pytest tests/ -q` → **43 passed**,
      zero regressions, same count as pre-cutover.

## 7. Cleanup (after one release cycle with no regressions)

- [x] 7.1 Delete `agents/*.py` and the old ADK-based test suite for
      real. **Done (2026-07-15) — release-cycle gate explicitly
      overridden by direct user instruction** ("use only langraph
      workflow so that we don't have many frameworks to solve"), not
      silently skipped — the design's Rollback plan wanted one release
      cycle first; this was a deliberate, explicit call to consolidate
      onto one framework immediately instead. `agents/*.py` (all 7
      files) and `tests/test_skill_template_agent.py` (tested the now-
      deleted ADK `SkillTemplateFillAgent` class directly) deleted via
      `git rm`.
- [x] 7.2 Remove the `google-adk` dependency from `pyproject.toml`/`uv.lock`.
      **Done**: `uv remove google-adk`. Same `uv remove` dev-extras-drop
      issue as task 2.1 (pytest disappeared again) — fixed the same way,
      `uv sync --extra dev`.
      **Real, previously-unflagged blocker found and fixed**:
      `mcp_server/external_servers.py` defined the three MCP server
      configs using ADK's own `StdioServerParameters` class — not
      named as a dependency anywhere in this change's design. Replaced
      with a local, framework-independent `@dataclass` of the same
      shape (`command`/`args`/`env`) — `workflows/drafting/mcp_tools.py`'s
      `_to_stdio_connection()` only ever duck-typed those three
      attributes, so this needed zero changes there.
- [x] 7.3 Confirm `gateway/skill_matching.py` and all tests still pass
      with `google-adk` fully uninstalled. **Done.** Required two more
      real fixes beyond the "just the two import lines" design
      estimate: `gateway/skill_matching.py`'s import swapped to
      `workflows.drafting.skill_loading` as designed, but
      `gateway/skill_template_agent.py` also needed its dead
      `SkillTemplateFillAgent(BaseAgent)` class removed entirely (ADK
      import, superseded by `workflows/drafting/skill_fill.py`,
      confirmed nothing in the cut-over path still called it) and its
      `Skill` import swapped the same way. One test renamed
      (`test_structured_match_drafts_via_skill_template_fill_agent_zero_llm`
      → `..._deterministic_zero_llm_path`) since it now tests the
      cut-over path, not the deleted class. **Verified**: zero real
      `google.adk` imports remain anywhere (repo-wide grep, comments
      only); `uv run python -c "import google.adk"` fails as expected;
      full suite — **40 passed**, zero regressions, with `google-adk`
      genuinely uninstalled.

## 8. Documentation

- [x] 8.1 Correct `docs/langgraph_vs_adk_inner_layer.md`'s comparison
      table and Part D cost argument in place, with a note pointing at
      this change and the verified findings it rests on. **Done** —
      Status line notes the doc is superseded; Part C's three rows
      (skill-loading, deterministic branch, model-agnosticism) each
      corrected inline with what was actually found; Part D's core
      "re-deriving all three" claim corrected with what the real cost
      turned out to be instead (the circular-import restructuring, the
      `create_react_agent` deprecation) — nothing silently deleted.
- [x] 8.2 Update `AGENTS.md`'s `agents/` bullet once cutover (task 6)
      is complete. **Done** — `agents/` bullet marked superseded/
      pending-deletion, new `workflows/drafting/` bullet added,
      `gateway/` bullet updated to describe the re-export, "Overview &
      stack" section's "a Google ADK agent graph" claim corrected to
      LangGraph.
