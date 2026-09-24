# Design

## Context

The existing provision preflight is non-mutating. The target workflow consumes
stored active user, membership, Resource Scope, governance, and Provider
Binding records; it never creates them.

## Decisions

### `/provision` is an explicit deterministic gateway route

The gateway validates a short-lived PlatformOps session, derives the principal,
and passes only a safe principal reference plus requested `scope_id` to the
graph. Current authorization state is loaded from PostgreSQL and trusted
registries for every run so revocation takes effect.

### The LangGraph workflow has no authority-bearing LLM decisions

```text
principal + scope_id
  → active membership lookup
  → scope authorization
  → governance guardrails
  → exactly-one binding resolution
  → typed preflight and plan seal
  → HITL approval when required
  → separately authorized execution
  → evidence
```

Every security edge is deterministic Python. Optional LLM assistance can only
collect typed input or explain outcomes; it cannot select a binding, bypass a
deny, approve, or execute.

### Resolved context is sealed at the plan boundary

Before planning, the workflow seals principal, membership, scope, grant,
guardrail, and binding IDs plus versions/digests. Approval and execution verify
the same context; revocation or version drift requires a fresh run.

### PostgreSQL stores authority and evidence

Control-plane records and plan/approval/execution evidence persist in
PostgreSQL. LangGraph checkpointing may store safe state but is never the
authorization source of truth.

## Non-Goals

- No login, registration, organization claim, membership onboarding, scope
  bootstrap, provider-container attachment, or provider-container creation.
- No token, credential, client provider-selection hint, or LLM authority decision.
