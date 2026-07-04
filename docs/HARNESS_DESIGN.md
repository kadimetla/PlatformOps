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
edits).

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
                  │  per-sender / per-workspace  │
                  │  isolation; maps identity →   │
                  │  which config applies below   │
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
Per-sender and per-workspace session isolation, directly modeled on
OpenClaw's pattern — Team A's pending approvals, cost ceilings, and
allow-lists must never leak into Team B's session. This layer is also
where **per-workspace configuration** lives: which AWS account/credentials,
which `infra/allowed-resource-types.json`, which cost ceiling, which model
tier overrides apply to this requester. This is the single biggest thing
that turns this from "our demo" into "a tool other teams configure for
themselves" — see Adoption story below.

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

### Multi-tenancy
A single Gateway deployment should be able to serve multiple teams/orgs by
mapping session identity to a config bundle (credentials, allow-lists, cost
ceiling, model tier overrides) rather than requiring a code fork per
adopter. This is the concrete mechanism behind "anyone can adopt this for
their needs" — adoption becomes a config change, not a fork.

## What's built vs. designed
| Piece | Status |
|---|---|
| Agent layer (orchestrator, routing, CDK/Terraform sub-agents, security agent) | Built |
| Model config file + loader | Built |
| True model-agnosticism (non-Gemini models) | Designed, not built |
| Gateway process, channel adapters, session/routing layer | Designed, not built |
| Control UI / human-in-the-loop approval queue | Designed, not built |
| Multi-tenant config-per-workspace | Designed, not built |

## Adoption story
A team wanting to use this for their own AWS/GCP/Azure setup would, in the
end-state design: point the Gateway at their chat platform, drop in their
own `infra/iam-policy.json` / `allowed-resource-types.json` / cost ceiling
as a workspace config bundle, optionally override which model backs which
agent role, and — if they want a new cloud or tool — add one new
provisioning sub-agent following the existing pattern (a skill + an MCP
server routing table entry), without touching the Gateway, session layer,
or Security Agent's review logic at all.

## Open questions / risks
- Where does workspace config actually live (a database, config files per
  workspace, a secrets manager)? Not decided — depends on target deployment
  (self-hosted vs. managed).
- How does the Control UI's human-approval path affect latency/UX for
  low-risk requests that would otherwise be instant? Needs the risk-tier
  threshold to be genuinely useful, not a rubber stamp.
- OpenClaw itself is MIT-licensed and self-hostable — worth revisiting
  whether to build our Gateway from scratch or fork/extend OpenClaw
  directly once its custom-agent extension points (not yet documented in
  what we reviewed) are better understood.
