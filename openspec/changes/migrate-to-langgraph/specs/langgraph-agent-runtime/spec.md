## ADDED Requirements

### Requirement: `plan_request()`'s external contract is unchanged
The system SHALL preserve `plan_request(envelope, bundle, usage_store) ->
(PlanRecord, list[ToolIntent])`'s exact signature and return shape after
migrating its internals to LangGraph — this is an internals swap, not a
contract change, per `wire-plan-request-envelope`'s already-built and
tested boundary.

#### Scenario: A caller of plan_request() needs no code changes
- **WHEN** the LangGraph-based implementation is cut over
- **THEN** any existing caller of `plan_request(envelope, bundle,
  usage_store)` continues to receive a `(PlanRecord, list[ToolIntent])`
  tuple with no change to its own code

### Requirement: Security review is a structural graph node, not a sub-agent
The system SHALL implement `security_agent`'s review as a distinct
LangGraph node connected by a graph edge that gates provisioning-node
output from reaching dispatch, rather than a prompt-level sub-agent
delegation.

#### Scenario: A drafted plan cannot reach dispatch without traversing the security node
- **WHEN** a provisioning node finishes drafting a plan
- **THEN** the graph's structure routes execution through the security
  review node before any `propose_tool_intent` call can be harvested as
  part of a final plan, not merely as an instruction the model is
  expected to follow

### Requirement: MCP tools bind via langchain-mcp-adapters with no MCP-server-side changes
The system SHALL connect to `aws-iac-mcp-server`, `ccapi-mcp-server`,
and `terraform-mcp-server` using `langchain-mcp-adapters`'
`StdioConnection`, preserving each server's existing `command`/`args`/
`env` values from `mcp_server/external_servers.py` unchanged.

#### Scenario: The same MCP server processes launch under the new binding
- **WHEN** the LangGraph runtime starts a provisioning node that needs
  `ccapi-mcp-server`
- **THEN** it launches the identical `uvx awslabs.ccapi-mcp-server@latest`
  subprocess this project already runs today, via `StdioConnection`
  instead of ADK's `StdioServerParameters`

### Requirement: Model selection is provider-agnostic via ChatLiteLLM
The system SHALL select LLM models through `langchain_litellm.ChatLiteLLM`,
preserving the ability to switch providers via configuration without
changing agent code or adding a per-provider integration package,
equivalent to the existing `LiteLlm`-based mechanism.

#### Scenario: Switching a node's model provider requires no code change
- **WHEN** `config/models.yaml` is changed to point a role at a
  different provider
- **THEN** the corresponding LangGraph node picks up the new provider
  on next run without any change to the node's own function code or
  its installed dependencies

### Requirement: Every LLM call is captured for observability
The system SHALL log every LLM call's input, output, token counts,
latency, and success/failure to an `llm_call_logs` table in the same
SQLite database `gateway/tool_dispatcher.py` already opens, via
`litellm`'s native callback hooks — regardless of which node or
provider made the call.

#### Scenario: A drafting node's LLM call is captured
- **WHEN** any LangGraph node makes an LLM call through `ChatLiteLLM`
- **THEN** an `llm_call_logs` row is written recording the prompt,
  response, token counts, latency, and outcome, without the calling
  node needing to log anything itself

#### Scenario: A failed LLM call is still captured
- **WHEN** an LLM call raises an error (rate limit, timeout, provider
  outage)
- **THEN** an `llm_call_logs` row is still written recording the
  failure, not silently dropped

### Requirement: Checkpointing uses a persistent saver, never in-memory past local dev
The system SHALL use a persistent `BaseCheckpointSaver` (a
`SqliteSaver`-family saver or better) for any deployment beyond local
development, and SHALL NOT rely on an in-memory-only checkpointer for
state that must survive a process restart.

#### Scenario: Graph state survives a process restart
- **WHEN** the process running the LangGraph runtime restarts between
  two turns of the same `thread_id`
- **THEN** the checkpointer's persisted state is still readable, unlike
  an in-memory-only saver

### Requirement: Skill loading is vendored, not dependent on the google-adk package
The system SHALL implement Agent Skills' frontmatter-only listing and
full-skill loading (equivalent to `list_skills_in_dir`/
`load_skill_from_dir`'s existing behavior) as project-owned code with no
`google-adk` import, so that `google-adk` can be fully removed at
cutover without breaking `gateway/skill_matching.py`.

#### Scenario: gateway/skill_matching.py works with google-adk uninstalled
- **WHEN** the `google-adk` package is uninstalled after cutover
- **THEN** `find_matching_skill_path()`/`resolve_skill_candidates()`
  still function correctly, sourcing frontmatter and full skill loads
  from the vendored implementation

### Requirement: propose_tool_intent harvesting preserves the two-pass sequencing
The system SHALL collect raw `propose_tool_intent` tool-call arguments
during graph execution and construct `ToolIntent` objects only after
`plan_hash` is computed from the fully-assembled `plan_text` — never
before, matching the sequencing already required by
`wire-plan-request-envelope`'s implementation and the bug it fixed.

#### Scenario: Every constructed ToolIntent carries the correct, final plan_hash
- **WHEN** a graph run proposes two or more `propose_tool_intent` calls
  before completing
- **THEN** every resulting `ToolIntent.plan_hash` equals the
  `PlanRecord.plan_hash` computed from the complete `plan_text`, not a
  partial or placeholder value

### Requirement: The existing ADK-based test suite stays green until cutover
The system SHALL keep `tests/test_gateway.py` and the other 40 existing
ADK-based tests passing, unmodified, for the entire duration the
LangGraph implementation is being built in parallel — cutover SHALL NOT
happen until an equivalent LangGraph-based suite also passes.

#### Scenario: CI is green on both implementations simultaneously, pre-cutover
- **WHEN** the LangGraph implementation exists in `workflows/drafting/`
  but `plan_request()` still points at the ADK implementation
- **THEN** both the existing 41-test suite and the new LangGraph-targeted
  suite pass in the same CI run

### Requirement: Provisioning nodes never call mutating MCP tools directly
The system SHALL route every create/update/delete operation the
provisioning nodes would otherwise send to `ccapi-mcp-server` or
`terraform-mcp-server` through a `propose_tool_intent` call instead,
closing the gap `specs/plan-request-boundary/spec.md` (in
`wire-plan-request-envelope`) flagged as not closed by that change.
Read-only/validation tools on those same MCP servers (e.g. `cfn-lint`,
`cfn-guard`) MAY still be called directly by provisioning nodes — this
requirement scopes to mutating operations only.

#### Scenario: A provisioning node cannot reach a mutating tool without proposing first
- **WHEN** a provisioning node's graph execution would previously have
  called a create/update/delete tool on `ccapi-mcp-server` or
  `terraform-mcp-server` directly
- **THEN** it instead produces a `propose_tool_intent` call, and no
  direct call to the mutating tool occurs anywhere in that node's
  execution path

#### Scenario: Read-only MCP tool calls are unaffected
- **WHEN** a provisioning node calls a read-only or validation tool
  (e.g. `cfn-lint`) on `aws-iac-mcp-server`
- **THEN** that call proceeds directly, without needing a
  `propose_tool_intent` call first

### Requirement: The propose-never-execute boundary is unaffected
The system SHALL route every mutating cloud operation through
`gateway/tool_dispatcher.py`'s `BrokeredToolDispatcher` exactly as
today — this migration SHALL NOT change `gateway/schemas.py`,
`config_engine.py`, `tool_dispatcher.py`, `skill_usage_store.py`, or
`skill_matching.py`'s matching logic.

#### Scenario: A ToolIntent from the new runtime is checked identically to one from the old
- **WHEN** a `ToolIntent` produced by the LangGraph runtime is passed to
  `BrokeredToolDispatcher.evaluate_intent()`
- **THEN** it is evaluated by the same allow-list/region/approval checks,
  unmodified by this migration, that a pre-migration `ToolIntent` would
  have received
