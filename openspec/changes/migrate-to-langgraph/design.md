## Context

`agents/*.py` and `gateway/plan_request.py`'s execution internals are
100% ADK today — real, tested (41 passing tests), built across the
`wire-plan-request-envelope` change (complete, not yet archived). A
chat exploration compared ADK against LangGraph for this project
specifically, verifying every claim by direct package inspection
(`langgraph==1.2.9`, `langchain-mcp-adapters`, `langchain`, all
installed and introspected in an isolated scratch venv — not web
research) rather than trusting `docs/langgraph_vs_adk_inner_layer.md`'s
earlier, partly web-sourced comparison. Every ADK-side advantage that
doc found turned out to have a verified LangGraph/LangChain equivalent,
and one — Agent Skills progressive disclosure — turned out not to be an
ADK framework capability at all. This design covers *how* to execute
the migration `proposal.md` scopes; the verified facts it rests on are
new information this session produced, not re-derived here.

## Goals / Non-Goals

**Goals:**
- Replace ADK with LangGraph as the sole inner agent framework,
  preserving `plan_request()`'s external contract exactly.
- Keep the existing 41-test suite green throughout — never a window
  where neither implementation works.
- Remove the `google-adk` dependency entirely at cutover, not just stop
  using most of it.
- **Decided (2026-07-14, resolves this design's own former Open
  Question)**: close the pre-existing propose-vs-execute gap as part of
  this change, not a separate follow-on. `cdk_provisioning_agent`/
  `terraform_provisioning_agent` currently have `CCAPI_MCP_SERVER`/
  `TERRAFORM_MCP_SERVER` attached directly — a real mutating capability
  `specs/plan-request-boundary/spec.md` (in `wire-plan-request-envelope`)
  already flagged as not closed by that change. Since `propose_tool_intent`
  is already being rebuilt as a real bound tool in this migration
  (Decisions below), the provisioning nodes route every mutating call
  through it instead of calling CCAPI/Terraform tools directly.
- **Decided (2026-07-14)**: model backend is `litellm` (via
  `langchain_litellm.ChatLiteLLM`), not `init_chat_model` + per-provider
  packages — supports any provider via an API key with one dependency,
  matching the property this project had with ADK's `LiteLlm` and
  removing a cost the original design accepted unnecessarily.
- **Decided (2026-07-14), new scope**: every LLM call's input, output,
  tokens, latency, and success/failure gets captured for observability/
  evals, via `litellm`'s native callback hooks, written to a new
  `llm_call_logs` table in the same SQLite file `tool_dispatcher.py`
  already opens.

**Non-Goals:**
- Adopting `interrupt()`/`Command(resume=...)` for mid-draft human
  clarification — the capability that motivated this exploration, but
  deferred to a follow-on change (`proposal.md`'s "NOT in scope").
- Auditing or changing which LLM providers this project actually
  targets — `config/models.yaml`'s current contents aren't reviewed
  here.

## Decisions

**Parallel-build in a new `workflows/drafting/` package, not in-place
rewrite, and named by workflow, not by framework — corrected
(2026-07-14) from an earlier `langgraph_agents/` choice.** The original
name mirrored `agents/`'s flat top-level convention but named the
*implementation technology* rather than *what the folder processes* —
a real mismatch once `design.md`'s own "Beyond This Change" section and
`docs/request_intent_taxonomy_and_workflow_routing.md` established that
gateway will orchestrate several separately-lifecycled LangGraph
workflows (`drafting`, `approval`, `dispatch`, `audit`, `discovery`),
each its own graph referenced by name in a `WORKFLOW_REGISTRY`. A flat
`langgraph_agents/` folder would have become an undifferentiated home
for all of them; `workflows/<name>/` makes the module path and the
registry key the same string, and this change specifically builds only
`workflows/drafting/` — the others are future siblings, not scaffolded
here. `gateway/plan_request.py`'s ADK-based internals stay untouched
and green until a new, separately-tested `graph.stream()`-based
implementation exists and passes an equivalent suite; only then does
`plan_request()` get repointed at it, in one commit. Alternative
considered: rewrite `agents/*.py` and `plan_request.py` in place —
rejected, it accepts a window where the 41-test suite can't pass
against either implementation, which this project's own history (every
prior change here shipped incrementally, verified at each step) argues
against.

**`security_agent` becomes a separate graph node, not a sub-agent.**
`docs/langgraph_outer_adk_inner_wiring.md` already found this
specific hardening independent of this migration: splitting drafting
and security review into two graph nodes turns review-before-dispatch
into a structural edge instead of a prompt instruction the model has to
choose to obey. Since the graph is being built from scratch here
anyway, this is adopted now rather than carried forward as a second,
separate change later.

**MCP tools bind via `langchain-mcp-adapters`' `StdioConnection`,
verified compatible with zero MCP-server-side changes.** All three
servers this project already runs (`aws-iac-mcp-server`,
`ccapi-mcp-server`, `terraform-mcp-server`) launch over stdio
(`mcp_server/external_servers.py`'s `StdioServerParameters`).
`StdioConnection`'s real, installed fields (`transport: Literal["stdio"]`,
`command: str`, `args: list[str]`, `env: dict[str,str]|None`) map
directly onto the existing `command`/`args`/`env` values — this is a
re-expression of existing config, not new integration work.

**Model-agnosticism via `langchain_litellm.ChatLiteLLM`, corrected
(2026-07-14) from an earlier `init_chat_model` choice.** The original
choice accepted a real cost — a separate LangChain integration package
per provider (`langchain-openai`, `langchain-anthropic`, etc.) — as the
price of leaving ADK's `LiteLlm` wrapper behind. That cost turns out to
be unnecessary: `langchain-litellm` (verified real, `ChatLiteLLM`
confirmed to support `.bind_tools()`, so it works with the same
MCP-tool-binding nodes `init_chat_model`-backed models would have)
wraps the real `litellm` package directly — the exact same library
ADK's `LiteLlm` was always a thin wrapper around. This restores the
"one package, any provider via an API key" property this project had
before the migration, with **no added per-provider package cost**, and
without needing ADK at all. Confirmed minimal footprint: `pip show
langchain-litellm` lists only `langchain-core`, `litellm`, `httpx`,
`cryptography` as dependencies — not the full `langchain` metapackage,
which is not needed anywhere else in this migration either (`langgraph.prebuilt.create_react_agent`
only needs `langchain-core`). Both `langchain` and `langchain-google-genai`
were added then removed from `pyproject.toml` during this same
implementation session once this was confirmed.

**A real gotcha this correction avoided**: `init_chat_model`'s own
docstring warns a bare `gemini-...` model name is inferred as
`model_provider="google_vertexai"` by default — *"default changes in
next major; pass `model_provider` to lock in."* This project actually
uses Google AI Studio (`README.md`'s `GOOGLE_API_KEY`), not Vertex AI —
had `init_chat_model` shipped without an explicit, hardcoded
`model_provider="google_genai"` override, every model call would have
silently authenticated against the wrong Google Cloud surface entirely.
`ChatLiteLLM` sidesteps this: `litellm`'s own model-string convention
(`gemini/gemini-2.5-flash`) is unambiguous about provider without
needing a second parameter to get right.

**LLM call observability — new requirement, not in the original
proposal.** Every LLM call (prompt in, response out, tokens, latency,
cost, success/failure) must be captured for metrics/evals. `litellm`
has real, built-in hooks for this — confirmed present:
`litellm.success_callback`/`failure_callback`/`callbacks` — a custom
Python callback function registered once, fired on every call
regardless of which node or provider made it. **Decision: write
captured calls to a new `llm_call_logs` table in the same SQLite file
`gateway/tool_dispatcher.py` already opens**, not a new storage system
or an external observability platform (Langfuse, Helicone, etc.) —
consistent with `docs/config_storage_backend.md`'s "one storage
system, not many" principle, applied here the same way it was applied
against adopting a dedicated graph database in
`docs/infra_graph_modeling_and_db_options.md`. Named, not built,
external integrations remain a real, deliberate escalation path if a
dedicated observability platform is ever needed — `litellm`'s callback
list accepts named integrations directly, so this isn't a dead end if
outgrown.

**Checkpointing uses a persistent `SqliteSaver`-family saver from the
start, never `InMemorySaver` past local dev.** `InMemorySaver` (the
langgraph docstring's own example) doesn't survive a process restart —
same failure mode already flagged for ADK's `use_in_memory_services=True`
in the earlier CopilotKit/AG-UI exploration. `SqliteSaver` is confirmed
real and installed, but its own docstring warns it's *"meant for
lightweight, synchronous use cases... does not scale to multiple
threads"* — the actual implementation should use `AsyncSqliteSaver`
(same package, confirmed present), not the sync variant used only for
this session's introspection check.

**Vendor `list_skills_in_dir`/`load_skill_from_dir`'s ~50 lines into
this project's own code rather than keep depending on `google-adk`
just for them.** Confirmed by reading the installed source directly:
both functions are pure `pathlib`/YAML parsing with zero ADK runtime
coupling. Keeping `google-adk` installed post-cutover solely for two
small utility functions would directly undercut `proposal.md`'s own
"consolidate onto one framework" motivation. Alternative considered:
keep the `google-adk` dependency just for `google.adk.skills` — rejected
for that reason; `gateway/skill_matching.py`'s own logic already treats
these as plain data (`dict[str, Frontmatter]`), so vendoring doesn't
touch its matching logic at all, only the two import lines.

**`propose_tool_intent` harvesting keeps the two-pass shape
`plan_request()` already uses, ported to LangGraph's state model.**
Today's implementation collects raw tool-call args during the event
loop and constructs `ToolIntent` objects only after `plan_hash` is
known from the fully-assembled `plan_text` — a real sequencing bug an
earlier draft hit and fixed (stamping `plan_hash` before it existed).
The LangGraph port represents `propose_tool_intent` as a real bound
tool (`langchain_core.tools`), walks the final state's message list for
`tool_calls` named `propose_tool_intent` after `graph.stream()`
completes, and constructs `ToolIntent`s only then — same two-pass
discipline, new mechanism underneath.

**The drafting graph's topology is static (`route_toolchain` →
provisioning → `security_review` → `END`), not dynamically constructed
— matches original ADK behavior exactly, not a limitation worth
lifting yet.** Verified during this implementation: LangGraph has no
supported way to construct new graph topology at request time (a
checkpoint references specific node names from *the* compiled graph;
resuming against a differently-constructed one is undefined). What it
does support, real and verified, is dynamic *routing* among a fixed,
pre-declared node set — `Send(node_name, input)` for runtime fan-out to
an existing node (e.g., once per resource in a spec, count unknown
ahead of time) and `Command(goto=node_name)` for any node to
dynamically redirect to any other, including looping back. The packaged
version, `langgraph_supervisor.create_supervisor(agents: list[Pregel],
model, ...)`, confirmed installed and real, builds exactly this: a
supervisor LLM dynamically choosing which of a *fixed, pre-built* agent
list to hand off to per turn. None of this was adopted here because the
original `security_agent`'s own instruction is explicit about *not*
looping — *"If security_agent rejects the plan, return its reason to
the user instead of retrying silently"* — so the static graph already
matches the behavior being preserved.

**Two concrete, real future enhancements this unlocks, named for later
rather than built now:**
- **A revision loop**: `security_review` returning `Command(goto="cdk_provisioning")`
  on rejection instead of hard-terminating, letting a provisioning node
  redraft against the rejection reason — a genuine behavioral
  improvement, but out of this change's "internals swap, not a
  contract change" scope.
- **Mixed-toolchain fan-out via `Send`**: today's (and the original
  ADK's) toolchain choice is one-per-request, cdk *or* terraform, never
  both. `Send` could dispatch per-resource provisioning across both
  toolchains in one request if that requirement ever arises — not a
  parity requirement, since the system being replaced never supported
  it either.

## Risks / Trade-offs

- [Risk] `langgraph.prebuilt.create_react_agent` (used throughout
  `workflows/drafting/nodes.py`) is deprecated as of LangGraph v1.0 —
  confirmed by a real deprecation warning surfaced while writing task
  5.2's tests against the actual installed `langgraph==1.2.9`:
  *"create_react_agent has been moved to `langchain.agents`... Deprecated
  in LangGraph V1.0 to be removed in V2.0."* → [Mitigation] not migrated
  now — still fully functional on the installed 1.x version, and the
  replacement (`langchain.agents.create_agent`) lives in the full
  `langchain` package, which was deliberately removed at task 1.4 to
  keep the `ChatLiteLLM` decision's "no added per-provider or
  full-`langchain` dependency" property. Re-adding `langchain` just to
  silence a not-yet-breaking deprecation warning would undo that
  decision for no immediate benefit. Real, known cost to revisit before
  any LangGraph v2.0 upgrade — not silently deferred without a note.
- [Risk] Node functions written now, before the deferred clarification
  follow-on adds `interrupt()`, could have side effects before what
  will later become an interrupt point — `interrupt()`'s own
  documented behavior re-executes a node's logic from the top on
  resume, so a node with pre-interrupt side effects would double them
  → [Mitigation] write node functions to be side-effect-free/idempotent
  up to their tool-calling boundary now, even though `interrupt()`
  itself isn't wired in this change — cheaper than restructuring nodes
  later.
- [Risk] `PostgresSaver` was referenced in `docs/langgraph_vs_adk_inner_layer.md`
  Part E but **not independently verified this session** — only
  `SqliteSaver`/`AsyncSqliteSaver` were confirmed real by direct
  introspection → [Mitigation] `SqliteSaver`-family is sufficient for
  this migration's cutover; don't assume `PostgresSaver`'s API shape
  matches until it gets the same verification pass.
- [Risk] A parallel-build package sitting alongside `agents/` mid-migration
  could confuse a contributor about which is authoritative
  → [Mitigation] a clear module-level docstring in `workflows/drafting/`
  stating it's the not-yet-cut-over replacement; delete it immediately
  at cutover rather than leaving both around indefinitely.
- [Risk] Cutover is a single commit repointing `plan_request()` — if it
  regresses something the parallel test suite didn't catch, rollback
  needs the old `agents/*.py` + `google-adk` dependency still available
  → [Mitigation] keep `agents/*.py` and the `google-adk` dependency for
  one full release cycle after cutover before actually deleting them,
  not removed in the same commit as the swap.
- [Risk] Routing the provisioning nodes' mutating calls through
  `propose_tool_intent` instead of calling CCAPI/Terraform tools
  directly is a real behavioral change, not just a rewiring — a bug
  here could silently reopen the exact gap this decision closes
  → [Mitigation] `specs/langgraph-agent-runtime/spec.md` gets an
  explicit requirement + scenario for this (task 3.x), and
  `BrokeredToolDispatcher.evaluate_intent()`'s existing deny-by-default
  behavior is the backstop either way — an intent that never reaches it
  correctly is a drafting bug, not a security hole, since nothing
  mutates without passing that check regardless of how the intent got
  proposed.

## Migration Plan
1. Add new dependencies (`langgraph`, `langgraph-checkpoint-sqlite`,
   `langchain-mcp-adapters`, `litellm`, `langchain-litellm`) alongside
   `google-adk`, not replacing it yet.
2. Build `workflows/drafting/` — the `StateGraph`, node functions,
   `MultiServerMCPClient` MCP wiring, `ChatLiteLLM` model config —
   structurally mirroring today's `agents/*.py` graph shape (Decisions
   above cover the three intentional deviations: `security_agent` as a
   node, vendored skill-loading, and `litellm` callback-based LLM call
   observability).
3. Build a new `plan_request()` implementation against
   `workflows/drafting/`, same external signature, in a distinctly-named
   module so `gateway/plan_request.py` stays untouched.
4. Port the existing 41 tests to exercise the new implementation;
   both suites pass simultaneously.
5. Cutover: repoint `gateway/plan_request.py`'s implementation at
   `workflows/drafting/` in one commit. `agents/*.py` and the old
   `plan_request()` internals are deleted from the active path but not
   yet removed from the repo.
6. After one release cycle with no regressions, remove `agents/*.py`,
   the old test suite, and the `google-adk` dependency for real.

**Rollback**: before step 5, trivial — the new package simply isn't
wired to anything yet. After step 5, revert the single cutover commit;
step 6 not having happened yet means the old implementation is still
present and immediately restorable.

**The one-release-cycle wait between cutover and cleanup, explicitly
overridden (2026-07-15).** This plan originally called for keeping
`agents/*.py` and `google-adk` installed for a release cycle after
cutover before deleting them. Direct user instruction ("use only
langraph workflow so that we don't have many frameworks to solve")
explicitly asked for immediate full consolidation instead — steps 6
and 7 both happened in the same session. Rollback past this point is
now `git revert` across multiple commits, not "the old files are still
sitting there," a real reduction in how cheap rollback is — a
deliberate trade this project chose in exchange for not running two
agent frameworks simultaneously any longer than necessary. Two real
gaps in this Migration Plan surfaced only once execution actually
reached step 7, neither anticipated when this design was written:
`mcp_server/external_servers.py` depended on ADK's own
`StdioServerParameters` class (not named as a dependency anywhere
above) and `gateway/skill_template_agent.py`'s dead
`SkillTemplateFillAgent` class still had a live ADK import that would
have broken on `google-adk` removal — both found and fixed as part of
task 7's actual execution, documented in `tasks.md`.

## Beyond This Change: Multi-Workflow Orchestration Direction

**Scope note**: everything below is captured because it's the
architectural direction this migration is a foundation for, verified
during the same exploration — but it is **not** in this change's Goals
or `tasks.md`. `proposal.md` scopes this change to replacing
`plan_request()`'s drafting-phase internals only. Steps 6–8
(approval/dispatch/execution) stay exactly as undesigned as they are
today unless and until a follow-on change adopts what's sketched here.
Written down now so it isn't re-derived from scratch later, per this
project's "capture every non-trivial decision" discipline — not a
silent scope expansion of this change. **Extended further in
`docs/request_intent_taxonomy_and_workflow_routing.md`**: the full
read-path scenario catalog (audit, discovery, cost — flagged as a
future gap), the schedule-triggered (`on_scheduled_trigger`) entry
point for cron-driven workflows like the nightly drift sweep, and the
`audit`/`discovery` graph shapes for deterministic/judgment-required
reads (split from an earlier single "`query` graph" sketch, corrected
in that doc for the same reason `workflows/drafting/` replaced
`langgraph_agents/` above — named by what each actually reads, not a
generic catch-all) — not repeated here, that doc is the deeper capture.

### The shape: gateway as orchestrator over several separately-lifecycled workflows, not one graph spanning 01–08

Different stages of a request's life have genuinely different
lifecycles — drafting completes in seconds; an approval wait can sit
open for days. Forcing both into one LangGraph thread means that
thread's checkpointer, retention policy, and monitoring have to satisfy
both timescales at once. The better fit: separate LangGraph graphs per
stage (`drafting`, `approval`, `dispatch`, plus the four already-designed
discovery workflows from `infra-inventory-discovery`), each with its own
`thread_id` namespace, with `gateway/` holding the durable
cross-workflow ledger — the same SQLite database `tool_dispatcher.py`
already opens, not a new storage system (`docs/config_storage_backend.md`'s
"one storage system, not many" principle applied here too). This also
resolves a question `docs/harness_deep_dive.md`/`docs/langgraph_vs_adk_inner_layer.md`
circled without landing on (Temporal-outer vs. LangGraph-outer): neither
is needed as a dedicated "outer" framework if `gateway/`, in plain
Python, is itself the orchestrator, and each LangGraph graph stays
scoped to one bounded, resumable unit of work.

**Checkpoint state and audit log stay two separate things, not one.** A
checkpointer's job is resumability — LangGraph's own `interrupt()`
docstring calls resumption "best-effort," and checkpoints are allowed to
be pruned. `audit_logs` is compliance-grade and must never be silently
dropped. A workflow's terminal node should still explicitly write to
the existing `audit_logs` table as a side effect, same as today; the
checkpointer is not a substitute audit trail.

### Inbound message routing — new request vs. resume of an open wait

Every inbound message (from CopilotKit, Slack, Teams, WhatsApp, etc.)
needs one deterministic answer before anything else: is this a brand
new request, or a reply to something the system is already waiting on?

```
inbound message (channel, channel_user_id, raw_payload)
                │
                ▼
   Is there an OPEN WAIT for this (channel, channel_user_id)?
                │
        ┌───────┴───────┐
       YES              NO
        │                │
        ▼                ▼
   RESUME that      START the
   thread_id        drafting workflow
   (Command(resume=...))  (new thread_id)
```

**The mapping is gateway's own responsibility** — LangGraph's
checkpointer knows nothing about channels or users, only `thread_id`s.
A small table, `pending_waits(channel, channel_user_id, thread_id,
workflow_name, started_at)`, written when a workflow pauses and deleted
when it resumes, is the natural extension of `RequestEnvelope`'s
existing `channel`/`channel_user_id` fields into a lookup key.

**Whether it's still actually waiting is not duplicated as a second
flag — ask the checkpointer.** Confirmed by direct introspection of the
installed package: `CompiledStateGraph.get_state(config) -> StateSnapshot`,
and `StateSnapshot` has real `next` and `interrupts` fields. Gateway
calls `graph.get_state(config).interrupts` as the authoritative check
rather than trusting a potentially-stale `pending_waits` row — avoiding
a real bug class (a stale row surviving after a thread resumed through
some other path).

**Structured correlation vs. free-text inference is a genuine
per-channel capability split, not one uniform mechanism:**
- Channels with structured interactive elements (CopilotKit's
  `renderAndWaitForResponse`, Slack Block Kit buttons, Teams Adaptive
  Cards) carry the correlation ID (`thread_id`) directly in the
  action/button payload — unambiguous by construction, no lookup-table
  disambiguation needed.
- Free-text-only channels (WhatsApp, plain SMS-style) must fall back to
  "most recent open wait for this user," which breaks down the moment a
  user has two open waits at once (e.g. approving Request A while
  having just fired off new Request B in the same chat). This ambiguity
  is a real open question (see below), not silently resolved by picking
  a tie-breaker here.

### Workflow-to-workflow handoff — deliberately not the same mechanism as resume

`Command(resume=...)` only continues *one* workflow past its own pause.
A prior workflow finishing and a *new* workflow starting are two
different events, joined by gateway's own glue code (plain Python, not
another graph):

```
approval workflow's interrupt() resumes (human clicked approve)
         │
         ▼
approval workflow runs to completion; terminal node writes
ApprovalRecord to gateway's DB
         │
         ▼
gateway's glue code sees "approval workflow finished, status=approved"
and starts a BRAND NEW thread_id on the dispatch graph, seeded with the
narrow (PlanRecord, list[ToolIntent]) contract — not the approval
workflow's raw internal state
```

Conflating these — e.g. having an approval click directly trigger
dispatch, skipping "let the approval workflow actually finish and
record its own completion first" — would break the durable ledger this
whole design rests on: there'd be no recorded "approval workflow
completed" row to reconcile against if gateway crashed mid-handoff.

### Putting it together

```python
def on_inbound_message(channel, channel_user_id, raw_payload, structured_correlation_id=None):
    if structured_correlation_id:              # Slack button / CopilotKit action / Teams card
        thread_id, workflow_name = resolve_correlation(structured_correlation_id)
    else:                                        # free-text channel (WhatsApp, plain SMS)
        candidates = pending_waits.lookup(channel, channel_user_id)
        if len(candidates) > 1:
            return ask_which_request(candidates)  # real ambiguity, don't guess
        thread_id, workflow_name = candidates[0] if candidates else (None, None)

    if thread_id is None:
        start(WORKFLOW_REGISTRY["drafting"], new_thread_id(), envelope_from(raw_payload))
        return

    graph, _ = WORKFLOW_REGISTRY[workflow_name]
    snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
    if not snapshot.interrupts:                 # stale row — trust the checkpointer, not the table
        pending_waits.delete(thread_id)
        start(WORKFLOW_REGISTRY["drafting"], new_thread_id(), envelope_from(raw_payload))
        return

    resume(graph, thread_id, extract_answer(raw_payload, snapshot.interrupts))
```

### Real cost this direction reintroduces, not smoothed over

`docs/langgraph_vs_adk_inner_layer.md` Part B already found neither ADK
nor LangGraph gives automatic failure detection on its own. Gateway
becoming the cross-workflow orchestrator reintroduces that same gap one
layer up: if gateway crashes between "approval workflow finished" and
"dispatch workflow started," that handoff is lost unless gateway
durably records the intermediate state *before* attempting the next
start, with something (shaped like the already-designed nightly drift
sweep) to notice and retry stuck handoffs. This is the one place a real
durable-execution engine (Temporal) would give something this
plain-Python-orchestrator design doesn't — flagged as a conscious
trade-off, not solved here.

## Open Questions
- ~~Should this migration also close the pre-existing propose-vs-execute
  gap...~~ — **resolved (2026-07-14)**: yes, see Goals above.
- `PostgresSaver`'s real API shape — unverified this session, needed
  before any production (non-SQLite) checkpointing decision.
- Exact provider package list — depends on auditing `config/models.yaml`,
  not done in this design pass.
- ~~Final name for the parallel-build package...~~ — **resolved
  (2026-07-14): `workflows/drafting/`**, matching the existing flat
  top-level convention (`gateway/`, `agents/`, `mcp_server/`, `spec/`,
  `skills/`).
- **From the Multi-Workflow Orchestration direction above, not yet
  decided, not yet in scope for this change**: the multi-open-wait
  ambiguity on free-text-only channels (a user with two simultaneous
  open waits) — needs a real tie-breaker rule or an explicit
  disambiguation reply, not silently picked here.
- **Same section**: whether the crash-between-workflow-handoffs gap
  gets a hand-rolled reconciliation sweep (consistent with this
  project's nightly-drift-sweep pattern) or stays a known,
  unmitigated risk for now — a conscious choice to make explicitly
  when a follow-on change actually builds the approval/dispatch
  workflows, not assumed here.
