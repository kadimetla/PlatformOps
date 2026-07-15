---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: LangGraph vs. ADK as the INNER agent layer, plus a durability correction to docs/harness_deep_dive.md §6
reviewed_by: unreviewed (first draft)
---

# LangGraph vs. ADK — Inner Agent Layer, and a Durability Correction

## Status
Research + design, grounded in current (2026) sources, cross-checked
across multiple independent comparisons rather than a single article.
**Corrects `docs/harness_deep_dive.md` §6's durability table in
place.** Reuses this project's own already-verified ADK findings
(`SkillToolset`, `BaseAgent`, `LiteLlm`) rather than re-deriving them —
those stay verified-by-package-inspection; everything LangGraph-side
here is web-sourced, not independently installed and inspected the
same way. Nothing built.

**Superseded (2026-07-14/15)**: the migration this doc only speculated
about actually happened — `openspec/changes/migrate-to-langgraph` is
built and cut over, `gateway/plan_request.py` now runs on LangGraph.
Every "cost" Part D claimed below turned out to be wrong or resolved
differently once verified by direct package inspection instead of web
research — see the corrections inline in Parts C/D rather than a
rewrite, so the reasoning trail (why this doc originally recommended
staying on ADK) stays legible.

## Part A: Two different questions, previously conflated
`docs/harness_deep_dive.md` §6 evaluates LangGraph/Temporal/CrewAI only
as candidates for the **outer** plan→review→approve workflow layer —
the durable state machine wrapping agent execution. This doc asks a
different question the existing table doesn't answer: could LangGraph
replace ADK as the **inner** agent layer — the thing that actually does
tool-calling, reasoning, and IaC drafting, currently
`agents/orchestrator.py`'s ADK graph?

## Part B: Correction — the durability claim in `harness_deep_dive.md`'s table
That table lists *"lacks native cluster durability for enterprise
scale"* as a LangGraph-specific con, implicitly favoring ADK by
omission. A dedicated, direct comparison of exactly this point (not a
general LangGraph review) shows that framing is wrong: it **groups
LangGraph and ADK together**, not apart. Both give you a checkpoint —
*"a save point... that you, the developer, are responsible for
detecting the need to use"* — not true durable execution. Concretely,
for both frameworks:
- No automatic failure detection or watchdog; a crashed process just
  stops, silently.
- The caller must detect the interruption and manually resume with the
  correct `thread_id` (LangGraph) or `invocation_id` (ADK).
- Neither guarantees exactly-once execution or prevents duplicate
  resumption if two processes resume the same run concurrently, absent
  external distributed locking.

ADK gets "slightly more credit" in that comparison for its
event-sourcing model, but the fundamental gap — *"your agent workflows
will run to completion, period"* is not a guarantee either framework
makes on its own — is identical. **Corrected**: this is not a reason to
prefer ADK for durability; neither framework solves it, which is
exactly why `docs/harness_deep_dive.md`'s own recommendation reaches
outside both to Temporal for the outer layer in the first place.

## Part C: The actual inner-layer comparison
| | ADK (verified/built against in this project) | LangGraph |
|---|---|---|
| Agent composition | Hierarchical tree, `sub_agents=[...]` — matches this project's existing `orchestrator → provisioning_agent → cdk/terraform_provisioning_agent` shape exactly, already built | Explicit graph — nodes + conditional edges, more precise control over branching, but a rewrite of the existing shape |
| Skill/reusable-capability loading | `SkillToolset`/Agent Skills spec — **verified real** by direct package inspection (`docs/plan_request_verified_implementation.md`), resolves this project's skill-loading gap natively | **Corrected (2026-07-14)**: "no equivalent" was wrong — `list_skills_in_dir`/`load_skill_from_dir` turned out to be ~50 lines of plain `pathlib`/YAML parsing with **zero ADK runtime coupling**, confirmed by reading the installed source directly. Vendored into `workflows/drafting/skill_loading.py`, verified byte-for-byte identical output against the real `google.adk.skills` on this project's actual skills. Not a LangGraph-native replacement — a discovery that the original capability was never ADK-specific at all. |
| Deterministic (non-LLM) branch | `BaseAgent` subclass, zero LLM calls — **verified real** (`docs/deterministic_plan_drafting.md`) | Confirmed correct, and built: `workflows/drafting/skill_fill.py`'s `run_deterministic_skill_fill()` is a plain function, verified end-to-end — no subclassing needed, simpler than the ADK version it replaced. |
| Model-agnosticism | `LiteLlm` wrapper — **verified real**, any litellm-supported provider incl. self-hosted (`docs/model_agnosticism_and_hermes_agent_evaluation.md`) | **Corrected (2026-07-14)**: "LangChain's own chat-model abstraction" was the wrong guess — that's `init_chat_model`, which needs a separate integration package per provider. The actual equivalent, `langchain_litellm.ChatLiteLLM`, wraps the real `litellm` package directly (the same library ADK's `LiteLlm` always wrapped) — verified real, `bind_tools()` confirmed present, keeps the "one package, any provider" property with zero added cost. Built in `workflows/drafting/model_config.py`. |
| MCP tool support | First-class, already wired in this repo (`aws-iac-mcp-server`, `ccapi-mcp-server`, `terraform-mcp-server`) | Real, actively maintained: `langchain-mcp-adapters` (v0.3.0, June 2026), `MultiServerMCPClient` for connecting multiple MCP servers, stdio + SSE transports — confirmed directly, not assumed. Not a blocker either way. |
| State/audit transparency | State threaded through `Session`/`Event` — workable, less explicit | A first-class `state` object passed node-to-node and mutated visibly at each step — a real LangGraph strength for auditability |
| Durability | Checkpoint-based, not true durable execution (Part B) | Same — checkpoint-based, not true durable execution, and explicitly single-process unless distributed locking is added separately |

## Part D: The asymmetry that actually matters for this project

**Corrected in place (2026-07-14/15) — this section's core claim was
wrong.** It argued switching to LangGraph meant "re-deriving all three"
ADK-side capabilities with no replacement for skill-loading
specifically. Once actually attempted (`openspec/changes/migrate-to-langgraph`),
verified by direct package inspection rather than web research: none of
the three needed re-deriving.
- `SkillToolset`'s actual behavior turned out to be pure `pathlib`/YAML
  parsing with zero ADK coupling — vendored directly, not rebuilt.
- `BaseAgent`'s zero-LLM pattern ported to a plain function, simpler
  than the original.
- `LiteLlm` has a direct LangChain-compatible equivalent
  (`langchain_litellm.ChatLiteLLM`) wrapping the same underlying
  `litellm` package, found only after this doc's original research
  guessed the wrong replacement (`init_chat_model`).

The real cost this doc should have surfaced instead: a genuine
circular-import restructuring at cutover time (`ComplianceError`/
`is_valid_spec_shape`/`run_compliance_preflight` extracted to a new
`gateway/compliance_preflight.py` so `gateway/plan_request.py` and
`workflows/drafting/plan_request.py` could import from each other
without a cycle), and a real, still-open deprecation
(`langgraph.prebuilt.create_react_agent` deprecated as of LangGraph
v1.0 — see `openspec/changes/migrate-to-langgraph/design.md`'s Risks).
Neither was knowable from web research alone; both only surfaced during
actual implementation.

## Part E: What this changes — a second viable outer-layer topology
Since Part B shows neither Temporal nor LangGraph gives true durability
on its own, `docs/harness_deep_dive.md`'s "Architectural Recommendation"
(Temporal outer + ADK inner) shouldn't be read as "Temporal because it's
more durable than the alternative" — durability is a wash at the
framework level either way; both need the same external work
(idempotency keys, a watchdog, distributed locking) to become genuinely
durable. What actually differs is operational cost: Temporal requires
hosting a cluster; LangGraph's checkpointer (e.g. `PostgresSaver`) is a
library plus a Postgres database this project would likely need anyway.
For a project at this stage — no dedicated infra-ops team yet, per
`docs/HARNESS_DESIGN.md`'s "What's built vs. designed" table showing the
Gateway process itself isn't built — **LangGraph outer + ADK inner** is
a legitimate, lighter-weight alternative to Temporal outer + ADK inner,
not a replacement recommendation, an added option. `LangGraph`'s
`interrupt()`/resume semantics are also a more direct fit for the
plan→review→approve pause-for-human-approval boundary this project
hasn't built yet than hand-rolling that wait state in a custom Gateway.

## Part F: The wiring mechanics — `docs/langgraph_outer_adk_inner_wiring.md`
This doc established *whether* LangGraph-outer is viable; it left *how*
it would actually connect to ADK unanswered, which read as "two agents
negotiating" rather than what it actually is. Answered in
`docs/langgraph_outer_adk_inner_wiring.md`: LangGraph is not a
competing agent brain here — its nodes are plain functions, and exactly
two of them happen to internally call ADK's `Runner.run_async()`, the
same way another node calls a database. That doc also finds splitting
drafting and security review into two separate LangGraph nodes (instead
of today's one combined ADK `sub_agents` graph) turns the review-before-
dispatch ordering into a structural graph edge instead of a prompt
instruction — a real hardening worth adopting regardless of how the
rest of the outer-layer question resolves — and maps the resulting
graph 1:1 onto `spec/flow_steps/01`–`08`.md, resolving
`docs/remaining_deep_dives.md` item 7 for this topology.

## Open questions / not yet decided
- Whether LangGraph's checkpointer should replace, or sit alongside,
  `gateway/tool_dispatcher.py`'s existing SQLite `approvals`/`audit_logs`
  tables if a LangGraph-outer topology is ever adopted — not evaluated.
- Whether running two frameworks (ADK inner + LangGraph outer) adds
  more integration complexity than it saves versus just building the
  approval-wait state machine directly in the custom Gateway design
  without adopting either external workflow framework — not evaluated,
  a real cost this doc doesn't weigh against the benefit.
- LangGraph-side findings here are web-sourced and cross-checked across
  independent articles, not independently installed and inspected the
  same way this project verified ADK's `SkillToolset`/`BaseAgent`/
  `LiteLlm` — worth a real `pip install langgraph` + introspection pass
  before this comparison is used to make an actual build decision, same
  rigor bar as the ADK-side findings it's compared against.

## How this relates to the existing docs
- **Corrects `docs/harness_deep_dive.md` §6's durability table in
  place** — LangGraph's "lacks native cluster durability" con applies
  to ADK equally, not as a differentiator favoring ADK.
- **Extends, doesn't replace, `docs/harness_deep_dive.md` §6's**
  "Architectural Recommendation" — adds LangGraph-outer + ADK-inner as
  a second viable topology alongside Temporal-outer + ADK-inner,
  differing mainly in operational cost, not durability guarantees.
- Draws directly on `docs/plan_request_verified_implementation.md`
  (`SkillToolset`), `docs/deterministic_plan_drafting.md` (`BaseAgent`),
  and `docs/model_agnosticism_and_hermes_agent_evaluation.md`
  (`LiteLlm`) for the inner-layer comparison, rather than re-verifying
  those ADK claims here.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Checkpoints Aren't Durable Execution: LangGraph, CrewAI, Google ADK — Diagrid](https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows)
- [Persistence — Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph vs ADK: A Developer's Guide — Jitendra Jaladi, Google Cloud Community, Medium](https://medium.com/google-cloud/langgraph-vs-adk-a-developers-guide-to-choosing-the-right-ai-agent-framework-b59f756bcd98)
- [Google ADK vs LangGraph 2026: I Installed Both and Compared Them Side by Side](https://jangwook.net/en/blog/en/google-adk-vs-langgraph-agent-framework-comparison-2026/)
- [Google ADK vs LangGraph: Which One Develops and Deploys AI Agents Better — ZenML](https://www.zenml.io/blog/google-adk-vs-langgraph)
- [LangGraph Multi-Agent Supervisor — LangChain Reference](https://reference.langchain.com/python/langgraph-supervisor)
- [langchain-mcp-adapters — GitHub, langchain-ai](https://github.com/langchain-ai/langchain-mcp-adapters)
- [Model Context Protocol (MCP) — Docs by LangChain](https://docs.langchain.com/oss/python/langchain/mcp)
