This is the shared, cross-tool foundation for any AI agent working in
this repo — CLI-specific files (`CLAUDE.md`, etc.) add tool-specific
detail on top, never contradict this one.

## Stack
Python 3.11+, Google ADK agent graph (`agents/`), MCP servers for cloud
reach (`mcp_server/external_servers.py` — AWS Labs' `aws-iac-mcp-server`/
`ccapi-mcp-server`, HashiCorp's Terraform MCP Server), Pydantic schemas
(`harness/schemas.py`), pytest.

## Conventions
- `agents/` — ADK agent definitions, one file per agent, `tools=` lists
  real MCP toolsets.
- `harness/` — the Gateway-layer spike: schemas, config loading, the
  brokered dispatcher. Real, tested code — see `tests/test_harness.py`.
- `skills/` — Agent Skills (`SKILL.md` per folder). Bundled/global tier
  only today; see the catalog below.
- `spec/` — the durable, version-controlled reference architecture
  (`reference_architecture.md`, Given/When/Then) and its deterministic
  checker (`check_compliance.py`). This is the spec-driven layer — the
  spec is checked *against*, submissions are checked *against it*, never
  the reverse.
- `docs/` — design docs. `docs/HARNESS_DESIGN.md` is the entry point and
  document map; every other doc states its own built-vs-designed status
  up top. Read that map before assuming something is or isn't real.
- `config/` — per-BU workspace bundles and channel/BU bindings.
- `infra/` — IAM policy and resource-type allow-lists for the agent's
  own credentials.

## Hard rules
- Deterministic checks (`spec/check_compliance.py`,
  `harness/tool_dispatcher.py`) stay deterministic — do not replace a
  code-level check with an LLM judgment call.
- Deny by default. A mutating action is allowed only if it matches an
  explicit allow-list entry and a recorded approval — never "probably
  fine."
- Write the absolute minimum code required for the immediate task.
  No speculative abstractions, no unrequested config surfaces.
- When editing existing code, make surgical changes — touch only the
  lines the task requires.
- State assumptions and surface tradeoffs before writing code when a
  request is ambiguous; don't guess silently.
- Never hardcode credentials. Never attach a broadly-privileged AWS
  profile — see `infra/README.md`.
- Add a rule to this file every time an agent does something here it
  should not repeat.

## Workflow
1. Before implementing something non-trivial, check `docs/HARNESS_DESIGN.md`'s
   document map — this project has a strong habit of designing in
   `docs/` before writing code; don't duplicate existing design.
2. Deterministic behavior (compliance checks, dispatcher gates) gets
   real tests. See `tests/test_harness.py` for the pattern.
3. A resource-type or IAM-role addition always touches
   `infra/allowed-resource-types.json`/`infra/iam-policy.json` and the
   matching skill's checklist — never one without the other.
4. Verify third-party MCP server integration points (exact launch
   command, exact tool names, exact resource-schema support) against
   current docs before relying on them — this codebase has been wrong
   about unverified integrations before; don't repeat that.

## Skills catalog
- `provision-infra` — provision AWS infra (S3/CloudFront today) via CDK
  or Terraform. Trigger: user asks to deploy/host/provision on AWS.
- `security-review-checklist` — review a provisioning plan before
  execution. Trigger: any plan proposed by a provisioning sub-agent.
- `sdlc-diagram-compliance-check` — check a submitted spec against
  `spec/reference_architecture.md`. Trigger: "does this architecture
  comply?" **Known gap**: not currently wired to any agent — see
  `docs/skill_loading_and_enforcement_gap.md`.

See `docs/course_concepts_and_project_structure.md` for why this file
is shaped the way it is, and what's still open before the skills layer
above is real.
