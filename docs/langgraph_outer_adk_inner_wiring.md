---
last_updated: 2026-07-10
owner: platformops-agent maintainers
scope: the concrete wiring mechanics for LangGraph-outer + ADK-inner — extends docs/langgraph_vs_adk_inner_layer.md
reviewed_by: unreviewed (first draft)
---

# LangGraph Outer + ADK Inner — How the Wiring Actually Works

## Status
Design, grounded in current LangGraph docs for the `interrupt()`/
`Command(resume=...)` mechanics specifically (web-sourced, not
independently installed and inspected the way this project's ADK
claims are — same caveat `docs/langgraph_vs_adk_inner_layer.md` already
flagged for LangGraph-side findings generally). Extends that doc, which
established *whether* LangGraph is a viable outer layer but not *how*
it would actually wire to ADK. Also resolves
`docs/remaining_deep_dives.md` item 7. Nothing built.

## Part A: There's only one agent — LangGraph is not a competing brain
"LangGraph outer + ADK inner" reads like two agents negotiating. They
don't. A `StateGraph`'s nodes are plain functions
(`async def node(state) -> dict`); edges control which node runs next.
Most nodes in this topology are pure deterministic code. Exactly two
happen to internally call ADK's `Runner.run_async()` to do their work —
the same way another node might call a database. There is no protocol
between the two frameworks, no message-passing:
```python
async def draft_plan_node(state: PlatformOpsGraphState) -> dict:
    plan_record = await plan_request(state["envelope"])   # the ADK Runner call
    return {"plan": plan_record}                            # merged into graph state
```
From LangGraph's side, this node is indistinguishable from one that
calls a REST API — it doesn't know or care that an `LlmAgent` tool-use
loop runs inside it. **LangGraph is the skeleton; ADK is the only
brain.** LangGraph's own agent/tool-calling node patterns (real,
confirmed in `docs/langgraph_vs_adk_inner_layer.md`'s research) are
deliberately unused here — every LLM-reasoning step routes through ADK
specifically because that doc found no LangGraph-native equivalent to
`SkillToolset`.

This is the same shape `docs/harness_deep_dive.md` already designed for
Temporal: *"Keep the Google ADK agent graph encapsulated inside a
single, stateless Temporal Activity."* LangGraph-outer swaps Temporal's
Activity for a LangGraph node — same principle, different engine.

## Part B: The concrete graph, mapped onto flow steps that already exist as specs
`spec/flow_steps/01`–`08`.md already describes this exact sequence as
Given/When/Then markdown, with no executable backbone —
`docs/remaining_deep_dives.md` item 7 left open whether a flow-step spec
should ever programmatically drive behavior or stay documentation-only.
A LangGraph node per flow step makes that connection real:

| LangGraph node | Flow step (`spec/flow_steps/`) | Calls ADK? |
|---|---|---|
| `normalize_and_bind` | 01–02 | No — deterministic binding lookup |
| `deterministic_preflight` | 03 | No — `check_compliance(envelope_to_spec(envelope))` (`docs/structured_match_rule_for_skills.md`) |
| `draft_plan` | 04 | **Yes** — `plan_request(envelope)`, either branch (`SkillTemplateFillAgent` or `root_agent`, `docs/deterministic_plan_drafting.md`) |
| `security_review` | 05 | **Yes** — a *separate* Runner call against `security_agent` specifically (see Part C) |
| `wait_for_approval` | 06 | No — pure LangGraph: `interrupt()` (Part D) |
| `dispatch_tool_intents` | 07 | No — `BrokeredToolDispatcher.evaluate_intent()` per intent |
| `verify_and_audit` | 08 | No — `SmokeTestResult` + audit write |

## Part C: Splitting drafting and review hardens a prompt instruction into a graph edge
Today, `agents/orchestrator.py` runs drafting and review inside **one**
ADK graph (`sub_agents=[provisioning_agent, security_agent]`), with
sequencing enforced only by the orchestrator's system prompt —
*"delegate to provisioning_agent... then require security_agent's
explicit approval."* That's the same category of gap
`docs/HARNESS_DESIGN.md` already flags elsewhere: *"the approval rule
is a prompt instruction, not yet a runtime guard."*

**Recommendation**: in the LangGraph-outer topology, `draft_plan` and
`security_review` should be two separate nodes (two separate `Runner`
calls, `provisioning_agent`-only and `security_agent`-only
respectively), not one combined ADK graph. This turns the drafting→
review ordering into a structural guarantee — the graph literally
cannot reach `dispatch_tool_intents` without traversing
`security_review` first, an edge the graph compiler enforces, not an
instruction an LLM could fail to follow. This is a genuine hardening
this topology adds beyond today's single-ADK-graph MVP, not just an
outer durability/persistence wrapper — worth adopting even if the rest
of the LangGraph-outer question stays undecided.

## Part D: The approval-wait mechanic, verified against current LangGraph docs
`interrupt()`, called inside `wait_for_approval`, pauses the graph and
persists full state via the checkpointer — **a checkpointer is required
for `interrupt()` to work at all**, it's not optional plumbing.
Resumption, once a human acts in the Control UI:
```python
graph.invoke(
    Command(resume=approval_decision),
    config={"configurable": {"thread_id": envelope.request_id}},
)
```
This is the literal call that un-pauses execution exactly where it left
off — potentially minutes or days later, in a different process
entirely, since state lived in the checkpointer's database (e.g.
`PostgresSaver`), not in memory. `Command(goto=...)` can route
conditionally on the resume value: `Command(goto="dispatch_tool_intents"
if approval_decision.approved else "denied_end")`. This is the concrete
implementation of `docs/harness_deep_dive.md`'s "block execution for
approval token" step and `docs/control_ui_approval_queue_design.md`'s
pending-approval state — `thread_id=envelope.request_id` is the natural
key tying LangGraph's own persistence to this project's existing
`request_id`, no new identifier needed.

## Part E: Resolves `docs/remaining_deep_dives.md` item 7
That item asked whether `spec/flow_steps/*.md` should ever
programmatically drive behavior. Answer, conditional on adopting
LangGraph-outer at all: **yes, directly** — Part B's table isn't an
analogy, it's a 1:1 node-per-spec-file mapping. Each flow step's
Given/When/Then scenarios become assertions checkable against the real
graph's node behavior, not just documentation describing intended
behavior separately from what runs. This doesn't retroactively make the
specs "drive code generation" in a codegen sense — it makes them the
actual shape of the executable graph, which is a stronger connection
than codegen would have been.

## Open questions / not yet decided
- Whether `security_review`'s ADK call should still be a full
  `sub_agents`-composed graph internally (in case `security_agent` ever
  needs its own sub-agents) or a bare single-agent `Runner` call — not
  decided, doesn't block the design above either way.
- Whether `wait_for_approval` needs to distinguish `approval_mode`
  values (`"any"`/`"unanimous"`/`"automated"`,
  `docs/personas_and_tool_blueprints.md` Part C) as different interrupt
  shapes, or one `interrupt()` call with the mode-specific logic living
  in how the Control UI constructs `approval_decision` — leaning toward
  the latter (keep the graph node simple), not decided.
- LangGraph-side mechanics here (`interrupt()`, `Command(resume=...)`,
  `PostgresSaver` requirement) are web-sourced and cross-checked across
  the official docs and reference pages, not independently installed
  and inspected the way this project verified ADK's `SkillToolset`/
  `BaseAgent`/`LiteLlm` — worth a real `pip install langgraph` +
  introspection pass before this is used to make an actual build
  decision, same rigor bar `docs/langgraph_vs_adk_inner_layer.md`
  already flagged for its own findings.

## How this relates to the existing docs
- Extends `docs/langgraph_vs_adk_inner_layer.md` — that doc established
  LangGraph-outer as viable; this doc designs the actual wiring.
- Resolves `docs/remaining_deep_dives.md` item 7 — conditional on
  adopting this topology, `spec/flow_steps/*.md` becomes the literal
  node structure of the graph, not just a documentation artifact.
- Extends `docs/harness_deep_dive.md`'s Temporal-outer recommendation
  with the LangGraph-specific equivalent of "ADK encapsulated inside a
  single, stateless Activity" — same principle, `interrupt()`/
  `Command(resume=...)` instead of Temporal's signal/activity model.
- Reuses `docs/deterministic_plan_drafting.md`'s two-branch
  `plan_request()` and `docs/structured_match_rule_for_skills.md`'s
  `envelope_to_spec`/`check_structured_match` unchanged inside the
  `draft_plan` node — this doc doesn't alter either.
- Connects to `docs/control_ui_approval_queue_design.md`'s
  pending-approval state machine — `thread_id=envelope.request_id` is
  the concrete key tying LangGraph's checkpointer to that design.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Interrupts — Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [interrupt — langgraph, LangChain Reference](https://reference.langchain.com/python/langgraph/types/interrupt)
- [Interrupts and Commands in LangGraph: Building Human-in-the-Loop Workflows — DEV Community](https://dev.to/jamesbmour/interrupts-and-commands-in-langgraph-building-human-in-the-loop-workflows-4ngl)
