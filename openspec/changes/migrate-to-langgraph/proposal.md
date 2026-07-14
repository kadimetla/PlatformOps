## Why
This project's inner agent layer (`agents/*.py`) and `gateway/plan_request.py`'s
execution engine are 100% ADK today. A chat exploration (verified by
direct package inspection, not web-sourced assumption — `langgraph==1.2.9`,
`langchain-mcp-adapters`, `langchain` installed and introspected in an
isolated scratch venv) found that ADK's real advantages over LangGraph —
model-agnosticism, MCP tool support, deterministic zero-LLM nodes — all
have direct, verified LangGraph/LangChain equivalents (`init_chat_model`,
`langchain-mcp-adapters`'s `StdioConnection`, and a plain Python function,
respectively), and that Agent Skills progressive disclosure — previously
thought to have "no LangGraph-native replacement" — turns out not to be
an ADK framework capability at all: `list_skills_in_dir`/`load_skill_from_dir`
are ~50 lines of plain `pathlib`/YAML parsing with zero ADK runtime
coupling, confirmed by reading the installed source directly. Consolidating
onto one agent framework removes a real cost this project has paid since
`docs/langgraph_vs_adk_inner_layer.md` first split "inner" and "outer"
into two separate framework questions.

## What Changes
- Replace `agents/orchestrator.py`'s ADK `sub_agents=[...]` tree with a
  LangGraph `StateGraph`: a routing node, provisioning tool-calling
  nodes, and — a structural improvement over today's prompt-level
  delegation — `security_agent` becomes its own graph node, turning
  review-before-dispatch into a graph edge instead of an instruction
  the model has to obey.
- Replace `SkillTemplateFillAgent(BaseAgent)`'s zero-LLM deterministic
  drafting step with a plain LangGraph node function — no subclassing
  needed, this is a simplification.
- Replace `cdk_provisioning_agent`/`terraform_provisioning_agent`'s
  `MCPToolset(StdioServerParameters(...))` wiring with
  `langchain-mcp-adapters`' `MultiServerMCPClient`, using the
  `StdioConnection` TypedDict — verified compatible with this project's
  existing stdio-launched MCP servers (`aws-iac-mcp-server`,
  `ccapi-mcp-server`, `terraform-mcp-server`), no MCP-server-side changes.
- Replace `LiteLlm`-based model-agnosticism (`agents/model_config.py`)
  with `init_chat_model(model, model_provider, ...)` — same
  "swap providers without changing code" property, with one added cost:
  a separate integration package per provider (`langchain-openai`,
  `langchain-anthropic`, etc.) instead of `LiteLlm`'s single package.
- Rewrite `gateway/plan_request.py`'s execution internals (`Runner`/
  `InMemorySessionService`/event-loop harvesting of `propose_tool_intent`
  calls) against `graph.stream()` and a `BaseCheckpointSaver`
  (`SqliteSaver`, confirmed real and installed). **`plan_request()`'s
  external signature does not change**:
  `plan_request(envelope, bundle, usage_store) -> (PlanRecord, list[ToolIntent])`
  stays exactly as `wire-plan-request-envelope` built and tested it —
  this is an internals swap, not a contract change.
- **Build in parallel, cut over once, not rip-and-replace.** The new
  LangGraph runtime is built and tested alongside the existing ADK code
  (separate module path) until it passes an equivalent test suite; only
  then does `plan_request()` swap internals in one commit and the old
  `agents/*.py`/ADK dependency get removed. Chosen over a direct
  rewrite-in-place because it keeps the 41 currently-passing tests green
  throughout instead of accepting a window where nothing works.
- **NOT in scope**: adopting LangGraph's `interrupt()`/`Command(resume=...)`
  for mid-draft human clarification. That was the original motivating
  problem for this exploration and this migration is a direct
  enabler of it, but it's a separable capability — deferred to a
  follow-on change once the base LangGraph runtime exists, same
  reasoning `infra-inventory-discovery/design.md` already used to defer
  its own "surface candidates, confirm" interaction.
- **Unaffected, explicitly**: `gateway/schemas.py`, `config_engine.py`,
  `tool_dispatcher.py`, `skill_usage_store.py`, and — most notably —
  `gateway/skill_matching.py`, whose progressive-disclosure logic was
  confirmed framework-independent this session and needs zero changes.

## Capabilities

### New Capabilities
- `langgraph-agent-runtime`: the LangGraph `StateGraph` replacing
  `agents/*.py` and `gateway/plan_request.py`'s ADK-specific execution
  internals — routing, provisioning tool-calling nodes, security review
  as a structural graph node, MCP tool binding via
  `langchain-mcp-adapters`, model-agnosticism via `init_chat_model`, and
  checkpointing via a persistent `SqliteSaver` — all while preserving
  `plan_request()`'s existing external contract and the
  propose-never-execute boundary `BrokeredToolDispatcher` enforces
  downstream.

### Modified Capabilities
<!-- openspec/specs/ is currently empty -- wire-plan-request-envelope
is complete but not yet archived, so there is no archived baseline
spec to diff against. This change's relationship to that work is
described in Why/Impact instead: it replaces plan_request()'s
internals while preserving the external contract
wire-plan-request-envelope's (not-yet-archived) plan-request-boundary
spec already established. -->

## Impact
- **Affected code**: `agents/orchestrator.py`, `provisioning_agent.py`,
  `cdk_provisioning_agent.py`, `terraform_provisioning_agent.py`,
  `security_agent.py`, `model_config.py` (all rewritten, initially under
  a parallel module path); `gateway/plan_request.py` (internals rewritten,
  signature unchanged); `mcp_server/external_servers.py` (connection
  configs re-expressed as `StdioConnection` TypedDicts).
- **New dependencies**: `langgraph`, `langgraph-checkpoint-sqlite`,
  `langchain-mcp-adapters`, `langchain` plus per-provider packages for
  whichever model providers this project actually uses.
- **Dependency removed, at final cutover only**: `google-adk` — not
  removed until the parallel build passes an equivalent test suite and
  `plan_request()` is swapped over; both frameworks coexist until then.
- **Tests**: a new suite mirroring the existing 41 ADK-based tests
  (`tests/test_gateway.py`, `test_plan_request*.py`, `test_skill_*.py`)
  against the LangGraph runtime; the existing suite stays green
  throughout, per the parallel-build decision above.
- **Docs**: `docs/langgraph_vs_adk_inner_layer.md`'s comparison table
  and Part D cost argument get corrected in place — several rows are
  now stale in LangGraph's favor per this session's verified findings —
  with a note, not a silent rewrite.
- **Not affected**: `gateway/`'s deterministic, already-framework-
  independent modules (`schemas.py`, `config_engine.py`,
  `tool_dispatcher.py`, `skill_usage_store.py`, `skill_matching.py`),
  and `spec/check_compliance.py`.
