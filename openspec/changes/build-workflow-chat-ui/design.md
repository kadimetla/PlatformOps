# Design

## Workspace shape

```text
┌─────────────┬────────────────────────────────────────────┬──────────────┐
│ navigation  │             conversation workspace          │ context pane │
│             │ header: identity · organization · context   │ optional     │
│ new chat    │                                              │ workflow     │
│ conversations│ messages / typed workflow cards            │ progress     │
│ work        │                                              │ safe details │
│ · my requests│                                             │              │
│ · needs review│                                            │              │
│ · needs action│                                            │              │
│ architecture │                                              │              │
│ review      │                                              │              │
│             │              fixed prompt composer           │              │
└─────────────┴────────────────────────────────────────────┴──────────────┘
```

The conversation column is centered and constrained for readable output. The
left rail is navigation only; the right pane is absent on small screens and
opens only for a selected workflow card or safe context details. `Work` is the
durable operational view; chat is the place to begin, discuss, and resume
workflow work.

## Workflow surface contract

The frontend renders only allow-listed server event types:

| Surface | Used by | User action |
|---|---|---|
| message/status | all workflows | none |
| short form | login, registration, onboarding | submit typed fields |
| selector | context, organization, Resource Scope | submit server-provided ID only |
| review card | onboarding/provision | resume the underlying workflow |
| findings card | architecture review | acknowledge/request change |
| Work row | Work navigation | open a workflow-owned task |

Each action contains an event ID plus typed response data. The backend checks
session, ownership, CSRF, workflow state, and live authorization; UI state is
never authority.

## Work navigation

`Work` is a single entry point with server-derived queue filters:

| Queue | Intended contents |
|---|---|
| My requests | Work the current principal initiated or owns |
| Needs my review | Pending review work for which the principal is currently eligible |
| Needs my action | Workflow steps the current principal must complete, excluding review decisions |
| Architecture reviews | Submitted design/diagram review findings and acknowledgement work |
| Completed | Recently completed, rejected, expired, or cancelled work visible to the principal |

The navigation may show safe aggregate counts. Counts and rows are hints only:
opening a row and submitting an action always reach the underlying workflow,
which re-evaluates live authorization and integrity. Queue membership is never
encoded in the browser or inferred from a chat transcript.

The UI change consumes the safe projection defined by `build-work-items`. It
does not define persistence, assignment rules, or approval state transitions.
The existing `build-reviewer-inbox` change remains the source of requirements
for the review queue until it is explicitly reconciled by that work-item
change.

## Context and identity

The header shows safe server projections only: `Guest` or signed-in display,
selected authorized organization when present, and active workflow context.
`/context` and the context selector make a requested switch visible. Natural
language may suggest a switch but requires confirmation. A context switch does
not change membership, grant access, or select a provider binding.

A partial project context is distinct from a resolved provisioning target. For
example, `Acme / Commerce / Payments / Checkout` may be shown while the
workflow asks the user to choose an environment. The environment segment is
shown only after the server resolves and authorizes it. The UI SHALL NOT show
an environment as selected while an environment selector remains a blocking
workflow step.

## Responsive behavior

Desktop shows rail + centered workspace; the context pane is collapsible.
Tablet collapses the rail to icons. Mobile uses a drawer and full-width cards;
the composer stays visible above the keyboard. Keyboard navigation, focus
return after submit, semantic labels, and status announcements are required.

On a narrow viewport the context crumb is hidden from the top bar to preserve
the conversation title and account action. The compact workflow bar shows a
short safe status such as `Checkout · environment needed`; it does not repeat
or invent a resolved target.

The wireframe uses an authenticated member state for Work and protected context
examples. A separate guest state shows `Guest`, a sign-in action, and public
workflow choices only; it shows neither Work queues nor an authorized context.

## Delivery order

1. Shell, navigation, conversation list, centered transcript, composer.
2. Header/context projection and typed status/form/selector surfaces.
3. Guest/login return-to-conversation and authenticated session refresh.
4. Workflow run panels and role-aware Work navigation.
5. Architecture-review findings and cited operations-knowledge guidance.
