# Harness & Model Architecture — Design

## Status
This is a design document, not a build log. It describes where this project
is headed once it grows beyond the hackathon MVP: a **harness** (the
runtime that wraps agents with channels, sessions, and human review) and a
**model layer** (how agents pick which LLM backs them) that any team can
adopt and configure for their own org, not just run our specific demo.

Only the model-layer config described below has real code behind it today.
The Gateway/harness described below is design only — see "What's built vs.
designed" at the bottom for the exact line.

## Why a harness, and why OpenClaw's pattern

Right now, `agents/orchestrator.py` is invoked directly — one process, one
session, one requester, no persistent identity across requests. That's fine
for a hackathon demo and wrong for a real platform-ops tool: real usage
means multiple teams, multiple concurrent requests, requests arriving from
wherever people already work (Slack, a ticket, a CLI), and a human
sometimes needing to see and approve a pending action before it runs.

[OpenClaw](https://docs.openclaw.ai/) solves a structurally similar problem
for coding agents: a **single Gateway process** as the source of truth for
sessions, routing, and channel connections, sitting between many input
surfaces (Discord, Slack, Telegram, WhatsApp, Signal, iMessage) and
whichever agent backend does the actual work, with per-sender/per-workspace
session isolation and multiple output surfaces (control UI, CLI, mobile).
We're borrowing that shape, not its code — our Gateway talks to our own
ADK agent tree instead of a coding agent, and adds a review-queue concept
OpenClaw doesn't need (approving cloud-infra changes, not approving code
edits). See "Deep dive: mapping onto OpenClaw's actual primitives" below for
exactly how that borrowing works once you look past the marketing diagram
and into OpenClaw's real data model.

## Model layer design

### Design goals
1. No agent's model choice should be a hardcoded string buried in Python —
   an adopting org should be able to point any agent at a different model
   without touching agent logic.
2. Different agent roles have different stakes and different ideal
   cost/capability tradeoffs — routing decisions are cheap and frequent;
   security review is rare and high-stakes. One model for everything is
   the wrong default, not a simplification.
3. Deterministic checks (`spec/check_compliance.py`) stay deterministic —
   the model layer governs *agents*, not the parts of the system that
   shouldn't be probabilistic in the first place.

### Role-based model tiers (recommended defaults)
| Role | Example agents | Tier rationale |
|---|---|---|
| Routing | `provisioning_agent` (router) | High volume, low ambiguity — cheapest capable model |
| Execution | `cdk_provisioning_agent`, `terraform_provisioning_agent` | Needs tool-use reliability; mid tier |
| Review | `security_agent` | Low volume, high stakes, worth the most capable available model |

### Config-driven model selection (implemented)
`config/models.yaml` maps agent role → model identifier. Agents load their
model from this file via `agents/model_config.py` instead of hardcoding a
model string. This is real, working code as of this design — see that file
for the current mapping. Swapping a model for an org's preferred one is a
one-line config edit, not a code change.

### Path to true model-agnosticism (designed, not built)
The current config still assumes Gemini-family model identifiers. ADK
supports non-Gemini models via a LiteLLM-style adapter in newer releases —
**verify this against the installed google-adk version's docs before
relying on it**. The next step is making `model_config.py` return a model
*handle* constructed through whatever adapter the configured identifier
implies (a `gemini-*` string vs. an `openai:*` / `anthropic:*` prefix, for
instance), so an adopting org isn't locked into Gemini just because we
started there.

## Harness layer design (not built — this section is the design to build toward)

```
                     ┌─────────────────────────────────────────┐
                     │              Gateway (new)                │
                     │  single process: source of truth for      │
                     │  sessions, routing, channel connections    │
                     └─────────────────────────────────────────┘
   Input channels             │                    Output surfaces
 ─────────────────►           │           ◄─────────────────────
  Slack / Teams               │            Chat reply (same channel)
  CLI                         │            Control UI (approval queue)
  Webhook (CI/CD trigger)     │            Audit log / observability
  (future: Jira/ServiceNow)   │
                              ▼
                  ┌───────────────────────────┐
                  │   Session & Routing layer   │
                  │  binding: channel account →   │
                  │  agentId (= one Business Unit) │
                  │  org registry: org → [BU→agentId] │
                  └───────────────────────────┘
                              │
                              ▼
                  ┌───────────────────────────┐
                  │     Agent layer (built)      │
                  │  orchestrator → compliance    │
                  │  skill, provisioning router →  │
                  │  {cdk, terraform} agents,       │
                  │  security_agent                  │
                  └───────────────────────────┘
```

### Input layer (channels)
Each channel is a thin adapter that normalizes an inbound message into a
common request shape (requester identity, workspace, text, attachments)
and hands it to the Session & Routing layer. Slack first (most platform-ops
teams already live there), then a generic webhook adapter for CI/CD
triggers (a PR that changes an infra spec), then other chat platforms.

### Session & routing layer
Modeled directly on OpenClaw's binding/`agentId` primitives (see the deep
dive below for the exact mechanics): a channel account binds to an
`agentId`, and each `agentId` **is** one business unit's fully isolated
scope — workspace, auth, sessions. An org registry sits above this mapping
`org_id` to its set of BUs/`agentId`s. This layer is also where **per-BU
configuration** lives: which cloud account/credentials, which
`infra/allowed-resource-types.json`, which cost ceiling, which model tier
overrides apply. This is the single biggest thing that turns this from
"our demo" into "a tool other orgs configure for themselves" — see
Adoption story below.

### Agent layer
Unchanged from what's built — the Gateway is agnostic to what's behind it,
the same way OpenClaw is agnostic to which coding agent it routes to. A
different org could in principle swap in a different agent graph entirely
as long as it accepts the Gateway's request shape.

### Output surfaces
- **Chat reply**: the agent's response returns via the same channel the
  request arrived on.
- **Control UI (new concept, not in the current build)**: a web dashboard
  showing pending Vibe Diffs awaiting human review. Today,
  `security_agent` autonomously approves or rejects against static
  policy files. A production-grade harness should make that
  **configurable per resource-type risk tier**: low-risk resource types
  (e.g., an S3 bucket matching all naming/region/cost rules) can stay
  fully autonomous; higher-risk types, or anything the agent itself flags
  as borderline, route to a human reviewer in the Control UI instead of
  an auto-reject. This turns `security_agent` from a gate into a
  recommendation-plus-human-approval workflow where the operator wants it.
- **Audit log**: every approve/reject decision (already logged per the
  security-review-checklist skill's existing requirement) surfaces here,
  not just in application logs.

### Multi-tenancy: Org → Business Unit → isolation unit
A single Gateway deployment must serve multiple **orgs**, each with
multiple **business units**, without any mixing across either boundary —
not just "multiple teams" as a flat list. Concretely (see the deep dive
below for why this shape, not some other one):

- **Org** = a customer/tenant. Exists only in *our* config layer — OpenClaw
  has no native concept of it.
- **Business unit** = the actual isolation unit, mapped 1:1 onto an OpenClaw
  `agentId` (its workspace, auth profiles, and session store). This is
  non-negotiable: OpenClaw's isolation guarantee only exists at the
  `agentId` level, so a BU that shares an `agentId` with another BU is not
  actually isolated, regardless of what our own config layer claims.
- **Workspace config bundle** (credentials, `infra/allowed-resource-types.json`
  equivalent, cost ceiling, model tier overrides) attaches per BU
  (per-`agentId`), not per org — an org with three BUs on three clouds needs
  three bundles, not one.
- **Org registry** (new, not yet built): a config store mapping
  `org_id → [{bu_id, agentId, workspace_bundle_ref}]`, so onboarding a new
  org means minting one fresh `agentId` per BU and registering it here —
  never reusing an existing `agentId`, which is an OpenClaw hard rule (see
  deep dive).

## What's built vs. designed
| Piece | Status |
|---|---|
| Agent layer (orchestrator, routing, CDK/Terraform sub-agents, security agent) | Built |
| Model config file + loader | Built |
| True model-agnosticism (non-Gemini models) | Designed, not built |
| Gateway process, channel adapters, session/routing layer | Designed, not built |
| Control UI / human-in-the-loop approval queue | Designed, not built |
| Org → Business Unit → agentId multi-tenancy model | Designed, not built |
| Org registry + onboarding automation | Designed, not built |
| OpenClaw plugin-harness integration (running our ADK tree as a registered runtime) | Design direction chosen (plugin-harness over CLI-backend); contract not yet spiked |

## Adoption story
A new org onboards by: registering itself in the org registry, minting one
fresh `agentId` (never reused) per business unit, binding each BU's
channel(s) to its `agentId`, and attaching a workspace config bundle per BU
— cloud credentials, `infra/allowed-resource-types.json`, cost ceiling,
optional model tier overrides. If a BU wants a new cloud or tool, that's
one new provisioning sub-agent following the existing pattern (a skill + an
MCP server routing table entry) — none of this touches the Gateway,
routing/binding layer, org registry, or Security Agent's review logic.

## Deep dive: mapping onto OpenClaw's actual primitives

The "borrow the shape" framing above undersells how specific OpenClaw's
actual data model is. This section is the result of reading its real docs
(`agent-runtime-architecture`, `plugins/sdk-overview`, `concepts/multi-agent`)
rather than inferring from the marketing page, and it changes some earlier
assumptions.

### The isolation unit is `agentId`, and it's flat
Per OpenClaw's own docs: *"An agent is the full per-persona scope: workspace
files, auth profiles, model registry, and session store."* Concretely, each
`agentId` owns:
- `~/.openclaw/workspace-<agentId>` — files, `SOUL.md`, `AGENTS.md`, `USER.md`
- `~/.openclaw/agents/<agentId>/agent` — auth profiles, model registry
- `~/.openclaw/agents/<agentId>/sessions` — chat history

This is **not hierarchical** — there's no built-in concept of an org
containing business units. That's why our Org/BU model above treats
`agentId` as the BU-level primitive and layers "org" entirely in our own
registry on top. **Hard rule from the docs, worth repeating verbatim**:
*"Never reuse `agentDir` across agents (it causes auth/session
collisions)."* Our org-onboarding process must always mint a new `agentId`
— reusing one to save setup steps is exactly the mistake OpenClaw warns
against, and would silently break tenant isolation.

### Routing is binding-based, most-specific-wins
*"A binding maps a channel account (e.g. a Slack workspace or a WhatsApp
number) to one of those agents."* Precedence, most to least specific:
exact peer (DM/group ID) → thread inheritance (`parentPeer`) → Discord
role+guild → guild/team ID → account ID fallback → channel-level wildcard
→ default agent. For our use case: **one Slack workspace per org is the
simplest binding**, with per-BU routing inside that workspace handled via
channel- or thread-level bindings mapped to each BU's `agentId`.

**Real risk this surfaces, not hypothetical**: *"Direct chats collapse to
the agent's main session key, so true isolation requires one agent per
person."* If two people from different BUs DM the bot without a binding
specific enough to separate them, they land on the same session. Our
Gateway design must enforce that BU-level bindings are always
channel/thread-scoped, never "whoever DMs this bot" — a config validation
rule to build, not just a recommendation to document.

### Two paths to plug our ADK agent tree in as the backend
1. **CLI Backend Plugin** (`api.registerCliBackend(...)`) — the documented
   extension point, but it's built for *existing CLI tools*: it configures
   argument translation (`resolveExecutionArgs`) and config merging for a
   CLI that already exists, not a full execution layer. To use this path,
   our ADK agent tree would need its own CLI entry point that accepts
   whatever arguments the plugin resolves — an adapter shim, not a native
   fit.
2. **Plugin harness registering a new runtime ID** — *"Plugin harnesses can
   register additional runtime ids. `auto` selects a supporting plugin
   harness when one exists and otherwise uses the built-in OpenClaw
   runtime."* This is the deeper integration: implement the
   `openclaw/plugin-sdk/*` runtime contract directly, so our ADK agents run
   as a first-class runtime rather than being shelled out to via a CLI
   wrapper. More upfront work (implementing an undocumented-in-what-we-
   reviewed contract, without importing `src/**` internals directly), but
   avoids CLI-argument-marshaling overhead and gives us structured
   session/tool-call fidelity end to end.

**Recommendation**: build toward the plugin-harness path, not the CLI
backend path. The CLI path is faster to prototype but would mean losing
structured tool-call/session data at the CLI boundary — exactly the
fidelity our security review and audit logging depend on. This needs a
prototype spike against OpenClaw's actual plugin-sdk source (the packages
under `openclaw/plugin-sdk/*`) before committing further design detail;
the docs describe the shape but not a full worked example for a
non-coding-agent backend.

## Open questions / risks
- Where does workspace config (and now, the org registry) actually live (a
  database, config files per workspace, a secrets manager)? Not decided —
  depends on target deployment (self-hosted vs. managed).
- How does the Control UI's human-approval path affect latency/UX for
  low-risk requests that would otherwise be instant? Needs the risk-tier
  threshold to be genuinely useful, not a rubber stamp.
- The plugin-harness runtime contract needs a real spike, not just doc
  reading — we don't yet know its exact interface shape, only that it
  exists and that `auto` runtime selection can dispatch to it.
- Org-onboarding automation (minting a fresh `agentId` per BU, registering
  it in our org registry, wiring its workspace config bundle) doesn't exist
  yet — right now this would all be manual steps, which is fine for one
  org and wrong the moment there's a second.
