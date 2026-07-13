# Session Memory — Design, and the Full Memory-Concept Mapping

## Status
Design only — nothing here is built. Part A is analysis (grounded in a
repo-wide search — see the exact evidence below), Part B is new design
for the one gap that analysis surfaces: session/working memory, the
only one of the four classic agent-memory concepts with no existing
analog anywhere in this project.

## Part A: How the classic memory taxonomy maps onto what already exists
`episodic`, `procedural`, `long-term`/`long_term`, and `short-term`/
`working memory` appear **zero times** anywhere in this repo before this
doc — that taxonomy has never been used as an organizing frame here. But
three of the four concepts already have real, unlabeled analogs:

| Concept | What it means | Existing analog | Where | Fit |
|---|---|---|---|---|
| **Procedural memory** | "How to do X" — a learned, reusable procedure | **Skills** — `SKILL.md`, `resolve_skill()`, `SkillProposal` authoring/promotion | `skills/*/SKILL.md`, `docs/skills_and_workspace_design.md` | Clean 1:1. A skill *is* procedural memory: learned once through the authoring gate, reused without re-deriving it each time. |
| **Episodic memory** | A dated record of a specific past event | **`memory/YYYY-MM-DD.md`** — the append-only daily log, `MemoryEntry.created_at` + `source_plan_id` | `docs/harness_memory_design.md` | Clean fit by construction — it's an episode log, just not labeled "episodic" when designed. |
| **Semantic / long-term memory** | Consolidated, stable facts, decoupled from any one event | **`MEMORY.md`** — the curated index of currently-valid entries | `docs/harness_memory_design.md` | Reasonable fit, **with one caveat worth stating precisely**: it overlaps with `WorkspaceBundle`/`AGENTS.md` (static, human-authored config), which is *also* long-lived but is declared configuration, not memory that was learned/inferred from interactions. Keep these conceptually separate even though both are "long-term" — conflating them would blur the "memory is context, never authority" rule, since config genuinely *is* authoritative and memory genuinely isn't. |
| **Session / working memory** | Continuity within (or across) one conversation — "what did we just discuss" | **Nothing.** `RequestEnvelope` has no `session_id`/`conversation_id` field (`gateway/schemas.py:14-22`); `NEXT_STEPS.md:26-27` confirms no `Runner`/`Session` construction exists anywhere in the actual ADK code either. Every occurrence of "session" in the docs (30+ hits) means the *isolation/routing scope* — one session store per `agent_id` — never conversational continuity. | — | **Real gap, not a naming gap.** Nothing today carries state within a multi-turn interaction. Designed below. |

## Part B: Session memory design

### What problem this solves
Continuity *within* one interaction — Alice says "set up an S3 bucket
for logs," the agent asks "which region?", she replies "us-east-1"; or
two turns later, "now put CloudFront in front of it" needs to resolve
"it" to the bucket just discussed. None of this works today — each
`RequestEnvelope` is independent, with nothing linking it to a prior one
from the same conversation.

### Two different layers, easy to conflate
- **ADK's own Session/Runner** (framework-provided, not yet wired at
  all — this is exactly the gap `NEXT_STEPS.md` flags: no
  `Runner`/`Session` construction anywhere in this codebase). Once
  `plan_request(envelope)` wires a Runner, this gives raw turn-by-turn
  message history and context-window management *for free*, per session
  key — verify the exact API against the installed `google-adk` version
  when building this, per that file's existing caution.
- **Gateway-owned `SessionState`** (new design, this doc) — everything
  ADK's Session doesn't and can't know: which `org_id`/`bu_id`/workspace
  bundle this conversation belongs to, whether the session key is
  specific enough to be safe, when it expires, and enforcing the safety
  rule below. The Gateway resolves a session the same way it resolves an
  org/BU — deterministically, from the binding — and hands ADK's Runner
  a session key to run within, not the other way around.

### The safety rule: session state is continuity, never authority
Same shape as `docs/harness_memory_design.md`'s "memory is context,
never authority," restated for sessions: **an approval recorded in turn
N of a session never silently covers a *different* `ToolIntent` in turn
N+1.** Every mutating action still requires its own `PlanRecord` /
`ApprovalRecord` / `ToolIntent` lookup through
`BrokeredToolDispatcher.evaluate_intent()`, regardless of what happened
earlier in the same conversation. Session state may supply *reference
resolution* ("that bucket" → which `plan_id`) — it may never supply
*authorization*. Without this rule stated explicitly, session memory is
exactly the kind of thing that quietly turns into "we already approved
something in this session, so wave the next thing through" — the same
category of risk this project has already refused twice, for skills and
for memory.

### `SessionState` schema sketch (not yet implemented — matches `gateway/schemas.py`'s style)
```python
class SessionState(BaseModel):
    session_id: str
    org_id: str
    bu_id: str
    agent_id: str
    channel: str
    channel_thread_key: str   # exact channel/thread/DM id the binding
                              # resolved from — see specificity rule below
    participants: list[str] = Field(default_factory=list)  # channel_user_ids seen this session
    last_plan_id: Optional[str] = None  # reference resolution only — never a substitute for a plan_hash match
    turn_count: int = 0
    created_at: datetime.datetime
    last_active_at: datetime.datetime
    expires_at: Optional[datetime.datetime] = None
```

`RequestEnvelope` gains one new optional field: `session_id:
Optional[str]`. Optional because one-shot channels (a webhook/CI
trigger) legitimately have no multi-turn conversation and no session at
all — this mirrors how `tfe_workspace` is optional on `WorkspaceBundle`
for BUs that don't use Terraform.

### `session_id` assignment must reuse the existing binding-specificity rule
`docs/HARNESS_DESIGN.md` already establishes, for org/BU routing: *"BU-
level bindings are always channel/thread-scoped, never 'whoever DMs this
bot'"* — because *"direct chats collapse to the agent's main session
key, so true isolation requires one agent per person."* That exact risk
reappears one level down, at session granularity, if `session_id` is
assigned too coarsely: two different people DMing the bot without a
thread-specific key would collapse onto the same `SessionState`, leaking
one person's in-progress conversation context into another's. The fix is
the same fix, reapplied: `session_id` must derive from the same
channel/thread-specific key the binding resolver already requires, never
a bare account/DM fallback. This isn't a new validation rule to invent —
it's the existing one, applied to a second concept that turns out to
need it.

### Lifecycle: expiry, not indefinite accumulation
`expires_at` — an inactivity timeout (exact value TBD, plausibly a
`WorkspaceBundle`-level override like `cost_ceiling_usd` already is).
Once expired, the next message on the same channel/thread starts a
*fresh* `session_id`, forcing clean context resolution instead of
silently reusing stale state. This is the actual defining property that
separates "working memory" from "long-term memory" in the taxonomy —
not where each is stored, but that one is deliberately short-lived and
the other deliberately durable until explicitly invalidated.

### Storage
Same convergence point already reached three times in
`docs/config_storage_backend.md` and `docs/harness_memory_design.md` —
reuse whichever store the managed-deployment decision lands on, rather
than a fifth storage system. Unlike config, approvals, or `MemoryEntry`,
losing `SessionState` on restart is low-severity, not a
correctness/security issue — worst case, a follow-up like "approve that"
needs re-stating. So an in-memory store with expiry is plausibly
sufficient for self-hosted/single-instance deployments even where config
and memory use a real database — this is the one piece of state in the
whole harness design where "just keep it in memory" is a legitimate
answer, precisely because it's ephemeral by design.

### How this ties to the one required next step
`plan_request(envelope)` (`docs/planned_implementation.md` Phase 3) is
exactly where an ADK Runner needs a session key to run within. This
design doesn't add a new prerequisite to that step — it specifies what
shape session resolution has to take *when* that wiring happens, the
same relationship every other doc in this set already has to Phase 3.

## Open questions / not yet decided
- Exact inactivity timeout for session expiry — likely
  workspace-bundle-configurable, not decided.
- Whether `last_plan_id` should be a single field or a short bounded
  history (last N plans) for richer "which one do you mean" resolution
  — start with a single field, not decided beyond that.
- Whether session start/expiry itself needs an audit-log entry, or
  whether that's noise on top of the existing plan/approval/dispatch
  audit trail — leaning toward no, not decided.

## How this relates to the existing docs
- Fills the fourth slot left open when `docs/skills_and_workspace_design.md`
  (procedural) and `docs/harness_memory_design.md` (episodic, semantic)
  are compared against the classic session/episodic/procedural/long-term
  memory taxonomy — an analysis frame applied after the fact, not a new
  architectural layer beyond what those two docs already describe.
- Reuses `docs/HARNESS_DESIGN.md`'s binding-specificity rule (channel/
  thread-scoped, never a bare DM fallback), applied one level down from
  BU routing to session routing.
- Reuses `docs/harness_memory_design.md`'s "context, never authority"
  principle, restated as "continuity, never authority" for sessions.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  same relationship every doc above already has to it.
