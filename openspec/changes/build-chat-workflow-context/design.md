# Design

## Context

The unified browser AG-UI control plane supplies authenticated chat transport.
Domain workflows already own login, registration, organization membership,
organization onboarding, and provisioning lifecycle decisions. This change
adds the conversation-level layer that selects and presents those workflows.

## Goals / Non-Goals

**Goals:**

- Make the active chat context visible and explicitly user controlled.
- Allow natural-language intake to suggest safe context switches.
- Suspend and resume incomplete user-owned workflow drafts.
- Give guests a useful path to login, registration, and membership without
  exposing protected organization or target information.

**Non-Goals:**

- This does not authenticate a user, grant membership or roles, select a cloud
  provider binding, execute a plan, or replace individual workflow state
  machines.
- This does not make an LLM an authorization decision maker.
- This does not introduce a generic policy language or WebSocket transport.

## Decisions

### Context is a user-visible workflow selection, not an intent or authority

The system calls the persisted selection `active_context`. It has a constrained
kind and an optional active workflow run reference:

```text
active_context = {
  kind: login | register_account | join_organization | register_organization |
        onboarding_review | provision | help,
  active_run_id: optional,
  selected_organization_id: optional and server-authorized only
}
```

The term *intent* is reserved for intake's constrained interpretation of a
message. Users use `/context`, rather than `/intent`, because they are choosing
what the conversation should work on. Context never carries memberships,
roles, grants, provider fields, approval state, or a browser-derived authority
claim.

### Chat header presents safe identity, organization, and context state

The browser header has three independently derived presentation fields:

```text
identity:     Guest | authenticated user's safe display projection
organization: absent | selected authorized organization safe display projection
conversation: active context safe display projection
```

A guest sees a `Guest` label and a sign-in action. An authenticated user sees
a safe display name and signed-in state. A member may additionally see the
selected authorized organization and a server-derived organization switcher.
The header does not present roles, grants, target access, provider accounts,
review request details, session tokens, or raw identity-provider claims. Those
facts remain server-side authorization inputs and are checked at each protected
workflow boundary.

### Slash commands are deterministic and session-bounded

`/context` displays the current context and allowed choices. `/context <kind>`
requests an explicit context change. `/resume` lists resumable drafts and
`/cancel` requests cancellation of the active user-owned draft. `/login` is a
public direct route to login. Command recognition happens before model-backed
intake and uses an allow-list; an unknown slash command is help text, not an
arbitrary route.

Guests may choose only `login`, `register_account`, `join_organization`, and
`help`. A protected context requires an authenticated session before its
workflow starts. The server derives available contexts from live state and
does not expose organization names, review requests, targets, or bindings to
an unauthorized guest.

### Natural-language intake proposes, rather than silently changes, context

For ordinary chat text, intake produces a constrained candidate intent and its
required missing inputs. If it differs from the current context and an active
meaningful run exists, the system emits an A2UI confirmation surface. An
explicit switch can suspend the old draft and activate the requested context.
When no meaningful draft exists, the system may switch directly and visibly.

The model may classify language or ask questions; it cannot declare a user
authorized, select a provider/account/binding, or invoke a privileged command.

### Workflow runs are independent and resumable

Each draft has a durable `run_id`, workflow kind, owner principal reference,
state (`active`, `suspended`, `completed`, `cancelled`), and safe summary.
Switching context preserves a suspendable active draft rather than merging
state between workflows. Resuming reloads the workflow's own persisted state
and repeats its normal authorization and lifecycle checks. Cancellation is
explicit, ownership-checked, and does not delete completed audit records.

### Authorization is re-evaluated at protected boundaries

An authenticated session identifies a principal only. A context change to
`provision` never grants target access. Provisioning continues to load active
membership, target grants, governance rules, and provider bindings from the
control plane when it creates or executes a protected action.

## Risks / Trade-offs

- [Risk] Context switching could conceal unfinished work. **Mitigation:** show
  the current context, preserve a safe draft summary, and provide `/resume`.
- [Risk] Intake classification may be incorrect. **Mitigation:** use constrained
  intent output and confirmation when an existing meaningful workflow would be
  suspended.
- [Risk] Context UI could leak protected data. **Mitigation:** derive choices
  and safe summaries server-side after authentication and authorization.

## Migration Plan

1. Define context/run contracts and deterministic slash-command parsing.
2. Persist owner-scoped active/suspended run metadata and add safe context
   projections.
3. Connect constrained intake results to context-switch proposals and A2UI.
4. Render safe guest, authenticated-user, and member header projections.
5. Integrate individual workflows incrementally, beginning with guest login
   and provision intake, while retaining their existing authorization checks.
