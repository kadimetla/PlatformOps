## Status
Designed and partially real. The module boundary described here
(`gateway/auth/` vs. `gateway/schemas.py`, vs. `workflows/`) exists on
disk today for the pieces `build-login-schemas` built
(`gateway/auth/schemas.py`, `gateway/auth/claims.py`,
`gateway/auth/grants.py`, `gateway/auth/sessions.py`, and
`gateway/auth/login.py`); provider discovery adapters under
`gateway/auth/providers/` do not exist yet. **Updated 2026-07-31**:
`gateway/policy/` (the `effective_access` evaluator) and
`gateway/approval.py` (`ApprovalRequest`/`ApprovalRecord`) now exist
too, plus `interaction/` — a third top-level package, sibling to
`gateway/` and `workflows/`, for TUI/web-facing event schemas
(`docs/INTERACTION_LAYER.md`). Neither `gateway/` nor `workflows/` may
import from `interaction/`.

## Real vs. Designed
| Area | Status |
|---|---|
| `gateway/auth/schemas.py` (`Capability`, `ExecutionGrant`, `ApprovalGrant`, `Actor`, `ActorRef`) | Real, moved here from `gateway/schemas.py` in a post-implementation restructuring; `ActorRef` added 2026-07-31 |
| `gateway/policy/ceiling.py` (`effective_access = min(grant, ceiling)`) | Real — `CeilingEntry`/`OrgBuPolicyConfig`, most-specific-scope-wins matching (stated assumption, not pinned down elsewhere); no live `org_bu_policy.yaml` data exists, only the schema/evaluator |
| `gateway/approval.py` (`ApprovalRequest`, `ApprovalRecord`) | Real — schema only, matches `EXECUTION_CREDENTIALS.md`'s Payload section field-for-field; the approval gate node itself doesn't exist |
| `interaction/events.py` (`PlatformOpsEvent`, `HITLEvent`, `HITLResponse`) | Real — see `docs/INTERACTION_LAYER.md`; no TUI/web adapter consumes it yet |
| `gateway/auth/claims.py` (`OIDCClaims`, `parse_id_token`) | Real, moved here from `gateway/oidc.py` |
| `gateway/auth/grants.py` | Real — exact IdP-group to `ApprovalGrant` mapping, deterministic and offline-testable; never mints `ExecutionGrant` |
| `gateway/auth/sessions.py` | Real — `ActorSession` construction plus an in-memory dev/test session store; stores no OIDC tokens or provider credentials |
| `gateway/auth/login.py` | Real — Authentik/OIDC device-code primitives with injected HTTP callables; no live IdP dependency in tests |
| `gateway.auth.cli` | Real — CLI smoke entry point over `gateway/auth/login.py`; talks to a real Authentik issuer when configured |
| `gateway/auth/providers/{aws,azure,gcp}.py` (`CloudAccessAdapter` implementations) | Not implemented — no empty stubs created either, per this project's discipline against speculative scaffolding |

## The Core Rule: Auth Is a Security Boundary, Not Agent Workflow Behavior
Authentication and grant resolution answer fundamentally different
questions from what LangGraph workflows answer:

```
AUTH asks (deterministic, must complete before any workflow):
  Who is this user? Is the token valid? What grants do they have?
  What session should exist?

WORKFLOWS ask (can involve LLMs, interrupts, long-running orchestration):
  What does the user want? What plan should be built? Does this need
  clarification? What step comes next?
```

Auth must never answer workflow questions, and workflows must never
answer auth questions — in particular, **no workflow decides whether a
request is authenticated**; that's decided before the workflow is ever
invoked:

```
NOT THIS:
  request -> workflow (LangGraph) decides if the user is authenticated

THIS:
  request -> authenticate (plain code) -> build ActorSession
          -> THEN call workflow
```

## Why This Boundary, Concretely
- **Auth must be deterministic.** Token validation, signature checks,
  group mapping, and grant normalization are plain code with tests —
  no LLM, no dynamic routing. Already true of everything built:
  `parse_id_token()` has zero non-deterministic paths.
- **Auth must be reusable by every workflow** — intake, provision,
  inquiry, approval, bootstrap all need the same `Actor`. If auth
  lived inside one workflow, every other workflow would either call
  into it or duplicate it.
- **Auth is a cross-cutting control**, not a business-logic decision —
  the gateway rejects unauthenticated requests before they reach any
  workflow, the same way a reverse proxy rejects requests before an
  application ever sees them.
- **Auth state and workflow state are different shapes.** Auth session
  state is token/expiry/refresh/grants; workflow state is
  request/plan/approval/execution evidence/checkpoint. Mixing them
  makes both harder to reason about, and would mean auth data ends up
  inside a LangGraph checkpoint store for no reason — directly at odds
  with `EXECUTION_CREDENTIALS.md`'s "nothing secret in graph state"
  rule, since session/grant data is exactly the kind of thing that
  rule is protecting.

## Grant Resolution: A Pipeline, Not a Workflow — Resolved, Not Hedged
Worth stating plainly rather than leaving open: grant resolution
(`resolve_principal → fetch_assignments → normalize_grants`) is
**not** LangGraph-shaped, full stop. LangGraph's entire value is
checkpointing, HITL interrupts, and LLM-driven conditional routing —
none of which apply to a fixed-order pipeline with no branch that
isn't already known at compile time. Using `StateGraph` here would be
framework overhead with no payoff; plain function composition is
simpler to read, test, and reason about. Same instinct as
`AGENTS.md`'s hard rule ("do not replace a code-level check with an
LLM judgment call"), extended one step further: don't reach for
LangGraph's machinery where a function call already suffices.

## Module Layout
```
gateway/
  schemas.py           # Intent, Scope, ClarificationQuestion,
                       # IntakeRequest, IntakeDecision -- intake-general/
                       # shared. Scope lives here (not gateway/auth/)
                       # because both intake and auth consume it.
  auth/
    schemas.py         # Capability, ExecutionGrant, ApprovalGrant, Actor
    claims.py          # OIDCClaims, parse_id_token()
    grants.py          # exact IdP group names -> approval grants only
    sessions.py         # build/store ActorSession; no token persistence
    login.py            # Authentik/OIDC device-code primitives

CLI:
  python -m gateway.auth.cli
                        # first smoke entry point; validates ID token
                        # and writes token-free ActorSession JSON
    providers/
      aws.py             # (future) AwsAccessAdapter
      azure.py            # (future) AzureAccessAdapter
      gcp.py               # (future) GcpAccessAdapter

workflows/
  intake/               # LangGraph -- receives an already-authenticated
  provision/            # ActorSession, never authenticates itself
  inquiry/
  bootstrap/
```
Workflows receive an `ActorSession` (or equivalent) as part of their
request envelope — they consume it, they never construct one.

## Sources
No external claims in this doc beyond LangGraph's own documented
purpose (checkpointing, HITL, LLM orchestration), already established
via this project's own use of it elsewhere — nothing new to verify.

## How this relates to the existing docs
Names explicitly a principle that was already implicit in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s
`CloudAccessAdapter` (a plain `Protocol`, never a graph) and
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
login flow (always described as a linear function sequence). Describes
the module boundary `openspec/changes/build-login-schemas` built
against, corrected there in place with a pointer to this doc rather
than rewritten. Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
