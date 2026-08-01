## Status
Designed only, no code changed by this doc. Captures a full design
conversation translating OpenClaw's memory/identity/behavior/session
concepts into PlatformOps terms — explicitly *not* copying OpenClaw's
personal-assistant model, per the governing distinction below. OpenClaw
claims verified 2026-07-31 against its own docs (see Sources), not
accepted secondhand. The memory taxonomy and the skills-as-procedural-
memory mapping are grounded against this repo's actual code; the
identity/behavior sections are grounded against already-enforced rules,
not proposed as new config surfaces (see "Identity & Behavior" below).

## The Governing Distinction
```
OpenClaw:    personal assistant continuity
PlatformOps: governed operations continuity
```
OpenClaw's own docs make this distinction sharper than expected —
*"Memory can preserve approval context, but it does not enforce
policy"* (`concepts/memory`). PlatformOps's version of that rule is
absolute, not just a design preference:

**Policy memory is authoritative. Every other memory type is context
only.**
```
episodic memory: "Alice approved prod last week"
policy memory:   "Alice currently holds an approval grant for prod"
```
Only the second sentence may ever gate an action. This isn't new — it's
already true in real code (`ActorSession.approval_grants`,
`gateway/policy/ceiling.py`'s `effective_access`) — this doc exists so
the six-type taxonomy below can't blur that line once episodic/semantic
memory actually get built.

## Real vs. Designed
| Item | Status |
|---|---|
| Working memory | Real, narrow — `harness/core.py`'s `dict[str, IntakeRequest]` keyed by `request_id`. No thread/run persistence (`docs/PLATFORMOPS_HARNESS.md`'s `ThreadState`/`RunState` are designed only) |
| Policy memory | Real — `gateway/policy/ceiling.py`'s `effective_access = min(grant, ceiling)`, `gateway/auth/schemas.py`'s `ExecutionGrant`/`ApprovalGrant` |
| Procedural memory | Real, as `skills/{provision-infra,security-review-checklist,sdlc-diagram-compliance-check}/SKILL.md` — see below |
| Semantic memory | Designed only — `gateway/policy/*.yaml` (`org_bu_policy.yaml`/`project_registry.yaml`) per `ACCESS_POLICY_AND_IAM_DISCOVERY.md`, no data file exists |
| Episodic memory | Not designed — no event/run history store exists or is speced beyond `docs/PLATFORMOPS_HARNESS.md`'s `EventRecord` shape |
| Evidence memory | Partially designed — `ExecutionRecord`/`InquiryRecord`/`ApprovalRecord` schemas exist (`EXECUTION_CREDENTIALS.md`, `INQUIRY_WORKFLOW.md`, `gateway/approval.py`), no append-only store implemented |
| `PlatformOpsIdentity`/`behavior/` YAML (as new config) | Not designed, not recommended — see "Identity & Behavior" below |

## The Six Memory Types
| Type | Answers | PlatformOps home (real or planned) |
|---|---|---|
| **Working** | What's happening in this run right now? | `harness/core.py` today (in-memory); LangGraph checkpointer once a checkpointed workflow exists |
| **Episodic** | What happened in previous runs? | Not built. Would answer "did this fail before?", "who approved the last prod change?" — queryable, not prompt-only |
| **Semantic** | What are the stable facts about this org/project/workspace? | `gateway/policy/*.yaml` (designed, no data yet) — toolchain, account id, execution identity per workspace |
| **Procedural** | How does PlatformOps do a known kind of task safely? | `skills/*/SKILL.md` — see below |
| **Policy** | Who is allowed to do what, where, right now? | `gateway/policy/ceiling.py`, `gateway/auth/schemas.py` — real, authoritative |
| **Evidence** | What immutably happened, for audit? | Schemas designed (`ExecutionRecord`/`InquiryRecord`/`ApprovalRecord`), no store built |

Working memory is per-run and disappears (or archives) when the run
ends. Episodic, semantic, and evidence memory are durable and
queryable, not injected wholesale into a prompt — same principle
OpenClaw's own docs state for daily notes (`memory/YYYY-MM-DD.md`
stays outside bootstrap injection, retrieved on demand via
`memory_search`, not blanket-loaded every turn).

### Where Each Type Is Used
Mapped onto [WORKFLOW_LIFECYCLE_PATTERN.md](WORKFLOW_LIFECYCLE_PATTERN.md)'s
seven steps — restated with memory types added, not a new sequence:

| Step | Memory types involved |
|---|---|
| intake | working, semantic, policy |
| context | semantic, episodic |
| plan | working, semantic, procedural, policy |
| approval | working, policy, evidence |
| executor | semantic, procedural, policy, evidence |
| evidence | evidence |
| reporting | episodic, evidence |

## Skills Are Procedural Memory
Grounded, not a stretch: every `SKILL.md` in this repo already
self-describes as a procedure —
`skills/provision-infra/SKILL.md`: *"Procedure for provisioning AWS
infrastructure..."*; `skills/security-review-checklist/SKILL.md`:
*"Procedure for reviewing a provisioning plan..."*;
`skills/sdlc-diagram-compliance-check/SKILL.md`: *"Procedure for
checking a submitted infrastructure spec..."*. The mapping is
descriptive, not aspirational.

**The boundary that matters**: a skill can say *how* — "to provision a
static site, create S3 + CloudFront, use the approved template, run
the security review checklist" — it cannot say *whether* — "Alice may
apply this in prod." That's policy memory's job alone, enforced the
same way regardless of which skill produced the plan:
```
skill says how       (procedural memory)
policy says whether  (policy memory — actor grants, org/BU ceilings, approval grants)
executor does it     (short-lived credentials, allow-list checked)
evidence records it  (append-only)
```
A skill that could also authorize its own execution would collapse
this boundary — "unchecked execution authority," not a procedure.

**Existing, already-tracked gap, not new**:
`skills/provision-infra/SKILL.md`'s free-form-drafting shape was
already flagged as needing correction toward template-first IaC, no
unreviewed generated IaC in the hot path, deterministic allow-list
checks, and the `opentofu_local` runner path — see
`docs/PROVISION_WORKFLOW.md`'s doc-map entry in
`HARNESS_DESIGN.md`, corrected there in place, not yet applied to the
skill file itself. This doc doesn't add a new task, just confirms the
procedural-memory framing agrees with a correction already on record.

## Identity & Behavior — Already Enforced, Not a New Config Surface
OpenClaw's `IDENTITY.md`/`SOUL.md` shape who the agent is and how it
behaves, injected every session. The proposal to borrow this as a
`PlatformOpsIdentity` profile and a `behavior/` policy YAML
(`interaction_policy.max_clarification_rounds`,
`execution_policy.require_approval_for_mutation`, etc.) is worth
having as a **single human-readable reference**, but not as new code
to build: every boundary it would state is already enforced somewhere
real, and a parallel YAML config would just be a second copy that can
drift from the code that actually enforces it.

| Proposed boundary | Already enforced at |
|---|---|
| Never mutate without approval | `EXECUTION_CREDENTIALS.md`'s approval gate (designed); `gateway/policy/ceiling.py` deny-by-default |
| Deny by default | `gateway/policy/ceiling.py`: no matching grant/ceiling → `Capability.NONE`, always |
| `max_clarification_rounds: 2` | `harness/core.py`'s `_MAX_CLARIFICATION_ROUNDS`, enforced before a third model call |
| Never use user cloud credentials | `AUTH_BOUNDARY.md`: execution identities are PlatformOps-owned, never a requester's own credentials |

If this becomes a doc, it should read as an index into these
enforcement points, not a spec for a new `behavior/*.yaml` loader —
the code is the source of truth, this would just be the map to it.

## What Not to Build Yet
`memory/{working,episodic,semantic,procedural,policy,evidence}.py` as
a uniform package, `context/project_memory.py`,
`context/evidence_store.py`, `executors/` — all real translations of
the taxonomy above, all speculative today. None has a second
workflow, dispatcher, or executor yet to actually serve — building
them now would be exactly the "registry/adapter/tier before something
real needs it" this project has avoided everywhere else
(`docs/INTERACTION_LAYER.md`'s Textual/web-adapter deferrals,
`docs/TRANSPORTS.md`'s HTTP/WebSocket/Teams/Google Chat deferrals).
Semantic memory (`gateway/policy/*.yaml`) and evidence memory
(`ExecutionRecord`'s persistence) are the two most likely to be needed
next, once a provision workflow exists to write to either — not
before.

## Sources
- [OpenClaw: memory model](https://docs.openclaw.ai/concepts/memory) — four-layer file model, "the model only remembers what gets saved to disk," "memory can preserve approval context, but it does not enforce policy"
- [OpenClaw: agent workspace / bootstrap files](https://docs.openclaw.ai/concepts/agent-workspace) — `AGENTS.md`/`SOUL.md`/`IDENTITY.md`/`USER.md`/`MEMORY.md` injection, per-file and total truncation budgets
- [OpenClaw: system prompt assembly](https://docs.openclaw.ai/concepts/system-prompt) — cache-boundary strategy, on-demand `memory_search` for daily notes vs. blanket bootstrap injection
- [OpenClaw: agent runtime architecture](https://docs.openclaw.ai/agent-runtime-architecture) and [OpenClaw: agent harness SDK contract](https://docs.openclaw.ai/plugins/sdk-agent-harness) — see `docs/PLATFORMOPS_HARNESS.md` for the harness-specific correction (OpenClaw's harness ≠ `PlatformOpsHarness`; not restated here)

## How this relates to the existing docs
Extends [PLATFORMOPS_HARNESS.md](PLATFORMOPS_HARNESS.md)'s OpenClaw
comparison — that doc corrects the harness-naming mapping and sketches
`ThreadState`/`RunState`/`EventRecord` (working/episodic memory
shapes); this doc covers the other five memory types and where skills
fit, without restating the harness correction. Cross-cutting like
[WORKFLOW_LIFECYCLE_PATTERN.md](WORKFLOW_LIFECYCLE_PATTERN.md), which
it reuses directly (the "Where Each Type Is Used" table adds a column
to that doc's steps, doesn't redefine them). Policy memory here is the
same `effective_access` invariant
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)
already owns — not a second definition. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
