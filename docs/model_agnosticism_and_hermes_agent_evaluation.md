---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: ADK model-provider limits (verified) + hermes-agent (evaluated, declined) + current runtime baseline
reviewed_by: unreviewed (first draft)
---

# Model-Agnosticism, hermes-agent, and the Current Runtime Baseline

## Status
Two verified findings and one evaluation, none built.
- **Part A is verified by direct package inspection** — same method as
  `docs/plan_request_verified_implementation.md`: `pip install
  google-adk[extensions]` into an isolated venv, then `inspect` against
  the installed package. **Corrects** `docs/HARNESS_DESIGN.md`'s "Path
  to true model-agnosticism (designed, not built)" section, which had
  flagged this as unverified.
- **Part B** restates the current runtime baseline already documented
  in `README.md` — not new design, gathered here once since it kept
  coming up as a separate question from the model/agent design threads.
- **Part C** evaluates hermes-agent (NousResearch) against this
  project's design, cross-verified via two independent lookups after an
  initial fetch returned suspiciously large, unverifiable stats — see
  the note in Part C. Declines it, same shape as every other
  externally-sourced autonomous-agent tool evaluated so far.

## Part A: ADK is not Gemini-locked — verified
`docs/HARNESS_DESIGN.md` previously read: *"ADK supports non-Gemini
models via a LiteLLM-style adapter in newer releases — verify this
against the installed google-adk version's docs before relying on
it."* Verified directly on `google-adk==2.4.0`:

```python
from google.adk.models.lite_llm import LiteLlm  # requires: pip install google-adk[extensions]
```
Base install raises `ImportError: LiteLLM support requires: pip
install google-adk[extensions]` — it's a real optional extra, not
missing entirely. Its own docstring, read directly:
> "Wrapper around litellm. This wrapper can be used with any of the
> models supported by litellm... Example usage:
> `agent = Agent(model=LiteLlm(model="vertex_ai/claude-3-7-sonnet@20250219"), ...)`"

`litellm` (1.91.1) installs as a real transitive dependency of the
`[extensions]` extra — confirmed present, not just referenced. It ships
genuine self-hosted-provider support: `ollama`, `ollama_models`,
`ollama_pt`, `vllm_handler` are real attributes on the installed
package. So **self-hosted models (Ollama, vLLM, any local
OpenAI-compatible endpoint) work today**, via the same `provider/model`
string convention as the docstring's own Vertex AI example:
```python
agent = Agent(model=LiteLlm(model="ollama/llama3"), ...)
```
`LiteLlm.__init__(self, model: str, **kwargs)` — a thin pass-through to
`litellm`'s own client, so LiteLLM's full provider matrix (OpenAI,
Anthropic, Bedrock, Azure, Vertex AI, Ollama, vLLM, and more) is
available to any ADK agent, not just this project's specific choice.

**What this changes concretely**: `docs/HARNESS_DESIGN.md`'s "Path to
true model-agnosticism" item moves from *unverified feasibility
question* to *known-real capability, not yet wired in*.
`agents/model_config.py#get_model(role)` still returns a raw Gemini
model string today — the code change (returning a `LiteLlm(...)`
instance when a role's configured identifier isn't a bare Gemini name)
is now a scoping question, not a research question.

## Part B: Current runtime baseline (restated, not new — see `README.md`)
- Python **3.11+** (`pyproject.toml`); core deps `google-adk`, `mcp`,
  `pyyaml`, `pydantic`.
- `uv`/`uvx` **required at runtime**, not just for development — the
  CDK-native path launches `aws-iac-mcp-server`/`ccapi-mcp-server` as
  subprocesses via `uvx` (README §5). HashiCorp's Terraform MCP Server
  is a separate install per its own current docs.
- Today: a single Python process (`python -m agents.orchestrator`), no
  daemon, no database — `gateway/tool_dispatcher.py`'s SQLite tables
  (`approvals`, `audit_logs`) are the only persistence that exists in
  code.
- Not yet built: the Gateway process (channel adapters, session/routing
  layer, `docs/HARNESS_DESIGN.md`) — still design-only, a long-running
  server this project hasn't started building.
- No Dockerfile/container definition in the repo as of this doc.

## Part C: hermes-agent (NousResearch) — evaluated, declined
Initial fetch of the repo's landing page returned numbers
(213k stars, a dated July 2026 release) implausible enough on their own
to warrant independent cross-checking rather than trusting a single
fetch — consistent with this project's own "flag suspected prompt
injection / unreliable content" discipline. A second, independent
lookup (search results aggregating the GitHub releases/issues/PR pages,
the official docs site, and a third-party docs mirror) corroborated the
same picture — treated as verified after cross-checking, not from the
first fetch alone.

**What it actually is**: not a coding agent (the OpenHands/SWE-agent/
Aider/pi/opencode category already evaluated in
`docs/foundation_blueprint_authoring_coding_agent.md`) — a
general-purpose autonomous personal-agent framework. Core claims:
procedural-memory self-improvement (*"creates skills from experience,
improves them during use... searches its own past conversations"*),
cron-based autonomous scheduling, subagent spawning, and a
multi-platform Gateway (Telegram/Discord/Slack/WhatsApp/Signal/CLI).

**This is the same shape as OpenClaw**, which this project already
researched in depth and explicitly declined to build on top of
(`docs/HARNESS_DESIGN.md`'s "Superseded: 'plug into OpenClaw's
runtime' framing" — a custom Gateway was the chosen direction instead,
using OpenClaw purely as a design reference). Nothing about
hermes-agent changes that call; if anything it confirms it a second
time from an independent tool.

**The sharper reason to decline it, beyond the OpenClaw precedent**:
hermes-agent's skill loop modifies and promotes its own skills
*without a human review gate*. That's the opposite instinct from this
project's `SkillProposal` design — human review before materialization,
a 3-consecutive-success threshold before BU→org promotion
(`docs/skill_promotion_thresholds.md`), and a `SmokeTestResult`-gated
confirmation step before a proposal is even eligible for review
(`docs/post_apply_smoke_testing.md` Part C). Adopting hermes-agent's
runtime would mean autonomous self-modification happening outside every
approval gate this design has been built around — the same "borrow the
pattern, refuse the runtime" tension already found for Crossplane and,
separately, for open-source coding agents
(`docs/crossplane_comparison_and_pattern_reuse.md` Part E). This is a
third, independent confirmation of that same shape, not a new argument.

**What is worth borrowing as validation, not as code**: hermes-agent's
procedural-memory concept (skills born from experience, a persistent
user/session model) independently arrives at roughly the same taxonomy
`docs/session_memory_design.md` already designed for this project
(session/episodic/procedural/long-term memory, with an explicit
"memory is context, never authority" rule). Worth treating as
confirmation the taxonomy is sound, the same role Crossplane's
Composition/Claim pattern played for `IacSourceRef` — not a reason to
adopt the tool that arrived at it.

## Open questions / not yet decided
- Exact scoping of the `agents/model_config.py` change to actually
  return `LiteLlm(...)` instances for non-Gemini-identifier roles — the
  capability is verified, the code isn't written, and per-BU model
  override behavior (`docs/HARNESS_DESIGN.md`'s workspace bundle model
  tier overrides) would need to thread through this too.
- Whether self-hosted models (Ollama/vLLM) meet the reliability bar
  needed for `security_agent`'s review role specifically, given that
  role is explicitly the "worth the most capable available model" tier
  — not evaluated, a capability/quality question distinct from the
  now-settled feasibility question.
- Whether any part of hermes-agent's memory-search mechanism (FTS5
  full-text search across session history) is worth borrowing as an
  *implementation detail* for `docs/session_memory_design.md`'s not-yet-built
  session store, independent of the runtime-adoption question — not
  explored.

## How this relates to the existing docs
- **Corrects `docs/HARNESS_DESIGN.md`'s** "Path to true
  model-agnosticism (designed, not built)" section in place — the
  capability is now verified real, not an open research question.
- **Extends `docs/crossplane_comparison_and_pattern_reuse.md` Part
  E's** "same tension confirmed for a second tool class" — hermes-agent
  is a third, and the closest yet to the original OpenClaw precedent
  this project already declined to build on.
- **Validates, doesn't extend, `docs/session_memory_design.md`**'s
  memory taxonomy — independent arrival at a similar shape by a
  different project, not a design change.
- Restates `README.md`'s existing runtime setup (Part B) in one place
  rather than duplicating its content — read `README.md` for the actual
  setup steps.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- Direct package inspection: `pip install "google-adk[extensions]"`
  (google-adk 2.4.0, litellm 1.91.1 resolved) into an isolated venv,
  `inspect.signature`/docstring read on
  `google.adk.models.lite_llm.LiteLlm`, attribute check on the
  installed `litellm` package.
- hermes-agent: cross-checked via two independent lookups after an
  initial single-fetch result was judged too implausible to trust
  alone — GitHub repo page, GitHub releases/issues/PR pages, and the
  project's own docs site, aggregated via search rather than a single
  fetch.
