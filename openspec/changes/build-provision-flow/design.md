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

### Plan and approval digests bind reviewed inputs, policy, and context

The non-mutating planner emits typed request inputs. A deterministic seal then
hashes canonical JSON containing those inputs, the selected trusted profile
policy ID/version, and the resolved context digest. The plan stores the input
snapshot and its plan digest; its approval digest is derived from the plan,
policy, and context digests. A later approval check uses constant-time digest
comparison for both values. It cannot accept an approval for a different plan,
policy version, or Resource Scope/binding context.

This task deliberately creates no approval record, HITL checkpoint, executor,
or cloud call. Those remain tasks 3.3 and 3.4.

### User corrections create immutable request revisions

Before a plan is sealed, a clarification or confirmed typed correction may
update the active draft through a workflow event. Once a plan exists, the
system never patches that plan, its input snapshot, or its approval in place.
A user correction creates a new monotonically increasing provision-request
revision with a typed before/after patch, actor, timestamp, reason or source,
and a `supersedes` reference to the prior revision. The new revision repeats
resolved-context and governance evaluation, produces a fresh plan digest, and
requires fresh approval when approval policy applies. Earlier revisions and
their plan/approval records remain immutable evidence.

The correction interface may be chat or a typed UI control. Natural language
can be interpreted as a *candidate* patch only; the workflow validates and,
where needed, asks the user to confirm the typed change. A correction to
governance itself (for example, requesting a different approval policy) is a
separate governed-setting or workflow-change request, never a hidden change to
the active provision revision. An execution that has started cannot be edited;
later desired-state changes use a separate controlled change or rollback path.

### LLM context is non-authoritative and bounded

An optional LLM may receive a minimum safe working view—active workflow,
unsealed draft inputs, allowed next input types, and safe explanation text—to
help collect or explain a correction. It does not receive credentials, raw
grants, provider bindings, policy evaluator traces, cross-user history, or
unrestricted preference data. Confirmed corrections, plans, approvals, and
execution outcomes are PostgreSQL-backed workflow/evidence records, not LLM
memory. The LLM is never asked to remember a prior provision decision as an
authority source.

### Checkpointed approval receives reviewer identity only from the gateway

The approval graph pauses with LangGraph `interrupt` and a plan/approval digest
payload. A later gateway-authenticated resume injects the reviewer principal
into graph state; the browser resume body supplies only the verdict and those
digests. The graph rechecks reviewer/requester separation, `provision_approve`
scope access, and both digests before marking the plan approved. This graph
stops at approval: execution and durable approval evidence remain later work.

### Execution is an injected worker boundary, not a graph privilege

An execution gate accepts only a sealed plan, matching approval digest, and
fresh registry records. It rechecks scope/binding versions before calling an
injected executor, which is the only component allowed to hold a provider
execution capability. The gate returns terminal reference-only evidence; this
initial slice supplies a fake executor for tests and no cloud adapter.

### PostgreSQL stores authority and evidence

Control-plane records and plan/approval/execution evidence persist in
PostgreSQL. LangGraph checkpointing may store safe state but is never the
authorization source of truth.

## Non-Goals

- No login, registration, organization claim, membership onboarding, scope
  bootstrap, provider-container attachment, or provider-container creation.
- No token, credential, client provider-selection hint, or LLM authority decision.
