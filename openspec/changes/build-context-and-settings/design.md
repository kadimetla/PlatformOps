# Design

## Two different settings domains

Personal preferences belong to an individual user and never alter authorization
or governance. Examples are theme, notification delivery preferences, default
landing view, and a preferred authorized organization/context.

An LLM may receive a minimum safe preference projection to phrase a suggestion,
but preferences remain explicit PostgreSQL records and convenience only. The
model does not retain preferences as an authority source, and a recalled
preference never selects a provider binding, bypasses governance, or grants
access.

Governed settings belong to an administrative scope and affect PlatformOps
behavior. They are editable only through server-authorized administrative
workflows and auditable control-plane records.

```text
Organization
  -> Business Unit
    -> Team
      -> PlatformOps Project
        -> Environment
```

Governance values may inherit downward. A lower scope may add a stricter rule,
but it cannot weaken an inherited deny, mandatory approval, provider
restriction, region prohibition, or evidence requirement. The server computes
the effective result before a protected workflow uses it.

## Settings ownership

| Area | Owner | Examples |
|---|---|---|
| Personal preferences | individual user | theme, notification channel, default view, preferred authorized context |
| Organization governance | tenant admin | approved providers, global denies, mandatory evidence, production approval baseline |
| BU governance | authorized BU administrator | tighter budgets/regions, allowed project types |
| Team governance | authorized team administrator | team templates, quotas, allowed identity groups/roles |
| Project governance | authorized project administrator | app profiles, lifecycle rules, approved environments |
| Environment governance | authorized environment/scope administrator | production approval, permitted resource classes, eligible provider bindings |

The initial role names and their exact permissions remain owned by the
target-bootstrap/access-policy design. Settings does not invent a browser role
or assume a displayed role grants mutation authority.

## UI shape

The shell displays a compact, server-projected context crumb when an
authorized context is selected. It may end at the PlatformOps Project while a
provision workflow has not yet selected an Environment:

```text
Context: Acme / Commerce / Payments / Checkout
```

Selecting it opens only contexts the user is already authorized to view.
Changing it updates presentation and requested workflow focus; it does not
change membership, grant a role, select a provider binding, or authorize a
provisioning request. Chat's `active_context` and resumable-run behavior stay
under `build-chat-workflow-context`. An Environment segment appears only after
the owning provisioning workflow resolves it from server-authorized selection;
the context crumb never claims an unresolved target.

Settings is a separate shell destination. It presents only sections the server
projects as visible:

```text
Settings
  Personal preferences
  Members and roles             (authorized administrators only)
  Governance                    (authorized administrators only)
  Cloud services                (authorized administrators only)
  Notifications
  Audit history                 (authorized readers only)
```

Every governed setting displays its value, scope, inheritance source, and
whether it is inherited or locally tightened. For example: `Production
approval: required — inherited from Organization`. The UI may submit a typed
change request, but the server re-evaluates scope administration and creates
the required workflow/audit record before a value changes.

## Safe projections and mutation boundary

The server projects safe labels, effective values, their source scope, and
permitted navigation/actions. It omits credentials, tokens, raw grants,
provider execution identities, raw IdP claims, internal policy evaluator
traces, and any setting the user cannot read. Unauthorized scope and setting
lookups fail non-enumeratingly.

Settings mutations are explicit workflow actions. The browser never calculates
effective policy, inheritance, or whether a change is allowed. The owning
workflow validates current actor, membership, administration eligibility,
scope lifecycle, parent guardrails, version/staleness, and any approval
requirement before writing an auditable revision.
