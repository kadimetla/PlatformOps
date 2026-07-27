---
last_updated: 2026-07-27
owner: platformops-agent maintainers
scope: whole repo — cross-tool foundation
reviewed_by: unreviewed (first draft on this branch)
---

This is the shared, cross-tool foundation for any AI agent working in
this repo — CLI-specific files (`CLAUDE.md`, etc.) add tool-specific
detail on top, never contradict this one.

## Overview & stack
PlatformOps uses **LangGraph** — no more Google ADK. `agents/`
(`agents/orchestrator.py`'s `Agent`/`sub_agents` model) is superseded;
new work goes through `workflows/` and `gateway/` instead. Neither
exists yet on this branch — they're what this branch builds, starting
with request intake. Python 3.11+, MCP servers for cloud reach
(`mcp_server/external_servers.py` — currently still imports
`StdioServerParameters` from `google.adk.tools.mcp_tool.mcp_toolset`;
migrating this to `langchain-mcp-adapters` is part of the switch, not
yet done), Pydantic schemas (to be added under `gateway/schemas.py` as
workflows need them), pytest.

A more advanced exploration of this same LangGraph direction exists on
`design/harness-architecture` — a rebuild that went much further
(`workflows/provision_stack/`, `workflows/inquiry/`, `workflows/intake/`,
`gateway/`, a Resource/Stack provisioning model, Kubernetes-cluster
provisioning). **That branch is not merged here.** Treat it as prior-art
reference to re-derive design from against this branch's actual,
earlier code — not something to cherry-pick wholesale. Its own document
map (`docs/HARNESS_DESIGN.md` on that branch) is the index if specific
design reasoning needs consulting.

## Architecture principles (hard rules)
- Deterministic checks (`spec/check_compliance.py`) stay deterministic
  — do not replace a code-level check with an LLM judgment call.
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
- `agents/` — the old ADK-based agents (`orchestrator.py`,
  `provisioning_agent.py`, `cdk_provisioning_agent.py`,
  `terraform_provisioning_agent.py`, `security_agent.py`).
  **Superseded — not the stack going forward.** Still on disk, not yet
  deleted; don't extend it or route new work through it.
- `workflows/` — **does not exist yet.** Will hold LangGraph
  `StateGraph` workflows, named by what they process, not by
  framework — starting with `workflows/intake/` for request
  classification.
- `gateway/` — **does not exist yet.** Will hold schemas, config
  loading, a brokered dispatcher — add only as an actual workflow needs
  it, not preemptively.
- `mcp_server/` — connection configs for third-party MCP servers (AWS
  IaC, CCAPI, Terraform). Currently ADK-native
  (`google.adk.tools.mcp_tool.mcp_toolset.StdioServerParameters`) —
  migrating to `langchain-mcp-adapters` is part of the stack switch,
  not yet done.
- `skills/` — Agent Skills (`SKILL.md` per folder). **Known bug,
  confirmed present on this branch**: `provision-infra/SKILL.md`'s
  `allowed-tools` is a YAML list; the real schema (per
  `google-adk==2.4.0`'s `SkillToolset`) requires a space-delimited
  string instead — fix before wiring any skill-loading mechanism to
  this file.
- `spec/` — the durable, version-controlled reference architecture
  (`reference_architecture.md`, Given/When/Then) and its deterministic
  checker (`check_compliance.py`). Unaffected by the stack decision.
- `infra/` — IAM policy and resource-type allow-lists for the agent's
  own credentials.
- `docs/` — **does not exist yet on this branch.** Create it, with
  `docs/HARNESS_DESIGN.md` as the entry-point document map, the first
  time a non-trivial design gets written down (see `CLAUDE.md`'s
  process).
- `tests/` — **does not exist yet on this branch either.** No pytest
  suite currently runs; add real tests as workflow code lands.

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
# Preferred — one field, added because a workflow actually needs it now
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
- No pytest suite exists on this branch yet. Add real tests as
  `workflows/`/`gateway/` code lands — same pattern proven on
  `design/harness-architecture` (scripted fake chat models for
  LangGraph node tests, no real model credentials needed).
- `spec/check_compliance.py` is independently runnable as a CLI check
  (`python spec/check_compliance.py <path>`).
- Bug fixes: reproduce with a failing test or a concrete repro command
  first, kept in the codebase, fix only the root cause.

## Commands
- Setup: `uv sync` (or `pip install -e .`)
- Compliance check: `python spec/check_compliance.py spec/example_submission.yaml`
- No LangGraph workflow exists yet to run — `agents/orchestrator.py`'s
  documented `python -m agents.orchestrator` only constructs `Agent`
  objects and exits (no `Runner`/`Session`), unverified/likely broken,
  same as it was before this branch started.

## Workflow
1. Before implementing something non-trivial, check
   `docs/HARNESS_DESIGN.md` — once it exists. It doesn't yet; the first
   non-trivial design on this branch should create it, per `CLAUDE.md`.
2. A resource-type or IAM-role addition always touches
   `infra/allowed-resource-types.json`/`infra/iam-policy.json` and the
   matching skill's checklist — never one without the other.
3. Verify third-party MCP server integration points (exact launch
   command, exact tool names, exact resource-schema support) against
   current docs before relying on them.

## Skills catalog
- `provision-infra` — provision AWS infra (S3/CloudFront today) via CDK
  or Terraform. Trigger: user asks to deploy/host/provision on AWS.
  **`allowed-tools` schema bug noted above — fix before relying on
  automatic tool-filtering from this file.**
- `security-review-checklist` — review a provisioning plan before
  execution. Trigger: any plan proposed by a provisioning sub-agent.
- `sdlc-diagram-compliance-check` — check a submitted spec against
  `spec/reference_architecture.md`. Trigger: "does this architecture
  comply?" Not currently wired to any agent.
