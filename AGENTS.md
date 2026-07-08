---
last_updated: 2026-07-08
owner: platformops-agent maintainers
scope: whole repo — cross-tool foundation
reviewed_by: unreviewed (first draft)
---

This is the shared, cross-tool foundation for any AI agent working in
this repo — CLI-specific files (`CLAUDE.md`, etc.) add tool-specific
detail on top, never contradict this one. See
`docs/repo_layout_references.md` for every source behind why this file
is shaped this way.

## Overview & stack
PlatformOps: a Google ADK agent graph that provisions AWS infra (S3/
CloudFront today) via CDK or Terraform, gated by a security-review
agent. Python 3.11+, MCP servers for cloud reach
(`mcp_server/external_servers.py`), Pydantic schemas
(`harness/schemas.py`), pytest.

## Architecture principles (hard rules)
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

## Conventions
- `agents/` — ADK agent definitions, one file per agent, `tools=` lists
  real MCP toolsets.
- `harness/` — the Gateway-layer spike: schemas, config loading, the
  brokered dispatcher. Real, tested code — see `tests/test_harness.py`.
- `skills/` — Agent Skills (`SKILL.md` per folder). Bundled/global tier
  only today; see the catalog below.
- `spec/` — the durable, version-controlled reference architecture
  (`reference_architecture.md`, Given/When/Then) and its deterministic
  checker (`check_compliance.py`), plus `spec/flow_steps/` — one spec
  per harness pipeline stage. This is the spec-driven layer — the spec
  is checked *against*, submissions are checked *against it*, never
  the reverse.
- `docs/` — design docs. `docs/HARNESS_DESIGN.md` is the entry point and
  document map; every other doc states its own built-vs-designed status
  up top. Read that map before assuming something is or isn't real.
- `config/` — per-BU workspace bundles and channel/BU bindings.
- `infra/` — IAM policy and resource-type allow-lists for the agent's
  own credentials.

## Anti-patterns to avoid (Preferred vs. Avoid)
**Deny by default, not a denylist:**
```python
# Preferred
if resource_type not in bundle.allowed_resource_types:
    return False

# Avoid
if resource_type in KNOWN_DANGEROUS_TYPES:
    return False  # implicitly allows everything else
```

**Minimum code, not a speculative config surface:**
```python
# Preferred — one field, added because a BU actually needs it now
permissions_boundary_arn: Optional[str] = None

# Avoid — a generic bag "in case we need more later"
policy_overrides: Dict[str, Any] = Field(default_factory=dict)
```

**State uncertainty about third-party integrations, don't assert it:**
```
Preferred: "Confirmed for CloudFormation's AWS::IAM::Role; not
confirmed for Cloud Control API specifically — verify before relying
on it."

Avoid: "CCAPI supports PermissionsBoundary." (stated as fact, unchecked)
```

**Surgical edits, not drive-by cleanup:**
Don't reformat, rename, or refactor adjacent code while fixing an
unrelated bug — even if it's tempting and even if it's clearly better.
Flag it separately instead.

## Testing strategy
- Deterministic harness code (`config_engine.py`, `tool_dispatcher.py`)
  gets real `pytest` tests — see `tests/test_harness.py` for the
  pattern to follow.
- `spec/check_compliance.py` is independently runnable as a CLI check
  (`python spec/check_compliance.py <path>`), not yet wrapped in a
  pytest suite.
- Bug fixes: reproduce with a failing test or a concrete repro command
  first, kept in the codebase, fix only the root cause — don't fix
  from a symptom description alone.
- **Known gap**: no evaluation suite exists for the LLM-driven agents
  themselves (`security_agent`'s review quality, provisioning agents'
  drafting quality) — only the deterministic harness code is tested
  today.

## Commands
- Setup: `uv sync` (or `pip install -e .`)
- Tests: `pytest tests/`
- Compliance check: `python spec/check_compliance.py spec/example_submission.yaml`
- Run the agent graph: **`README.md`'s documented command
  (`python -m agents.orchestrator`) is known broken** — it only
  constructs `Agent` objects and exits, no `Runner`/`Session`
  anywhere (`NEXT_STEPS.md`). The likely correct command is ADK's own
  CLI (`adk web agents/` or `adk run agents/`) — unverified against the
  installed `google-adk` version; check before relying on it.

## Workflow
1. Before implementing something non-trivial, check `docs/HARNESS_DESIGN.md`'s
   document map — this project has a strong habit of designing in
   `docs/` before writing code; don't duplicate existing design.
2. A resource-type or IAM-role addition always touches
   `infra/allowed-resource-types.json`/`infra/iam-policy.json` and the
   matching skill's checklist — never one without the other.
3. Verify third-party MCP server integration points (exact launch
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
