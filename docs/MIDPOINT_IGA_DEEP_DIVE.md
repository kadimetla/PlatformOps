## Status

Research/design note captured 2026-08-19. No midPoint instance,
connector, REST integration, or PlatformOps access-request adapter
exists in this repo.

This document deep-dives on how Evolveum midPoint would fit the
PlatformOps IAM/access-request story if PlatformOps chooses an
open-source IGA tool instead of building the full self-service access
workflow itself.

## Product Fit

midPoint is an IGA/IDM system. In this architecture it is not the same
thing as Authentik.

```text
midPoint
  access request, role catalog, approval workflow, assignment lifecycle,
  access review/certification, audit, provisioning orchestration

Authentik
  login, users/groups, OIDC/SAML, device-code flow, group claims, SCIM

PlatformOps
  provisioning runtime, stack catalog, workflow authorization checks,
  policy ceilings, execution evidence
```

The Saviynt-like experience lives in midPoint: a user goes to a
self-service access UI, searches for an access role, submits a request,
gets routed through approval, and receives access when the request is
implemented.

PlatformOps should consume the result. It should not become a second
source of truth for who has access.

## User Login and Request Experience

There are two viable login shapes.

Preferred enterprise shape:

```text
user opens midPoint self-service UI
  -> midPoint redirects to corporate IdP / Authentik through OIDC or SAML
  -> user completes SSO/MFA there
  -> midPoint receives authenticated identity
  -> user sees self-service pages such as My Access / Request Access
```

Simpler lab/MVP shape:

```text
user opens midPoint self-service UI
  -> user authenticates directly to midPoint
  -> user requests access
```

For PlatformOps, the preferred shape is the first one. Authentik remains
the login authority for both PlatformOps and midPoint, so the user has
one identity and group source across both systems.

The user journey should look like:

```text
1. User needs deploy access to aiq:it/invoices/dev.
2. User opens midPoint self-service.
3. User searches for "invoices dev deploy" or browses the PlatformOps
   role catalog.
4. User selects "PlatformOps Invoices Dev Operator".
5. User optionally sets validity, e.g. 30 days.
6. User submits the request.
7. midPoint routes approval to the configured approver.
8. Approver approves.
9. midPoint assigns the role and provisions the backing group or
   entitlement.
10. Authentik/cloud identity propagation completes.
11. User refreshes or logs in to PlatformOps again.
12. PlatformOps discovers the grant and allows the matching workflow.
```

The user does not need to know the underlying group name, AWS
permission set, Kubernetes RBAC binding, or provider role. Those are
implementation details behind the requestable role.

## Role Catalog Shape

midPoint's role catalog is the natural place to expose PlatformOps
permissions in user-facing terms.

Example role names:

```text
PlatformOps: Invoices Dev Viewer
PlatformOps: Invoices Dev Planner
PlatformOps: Invoices Dev Operator
PlatformOps: Invoices Prod Approver
```

Example role metadata:

```yaml
display_name: PlatformOps: Invoices Dev Operator
description: Deploy approved static web and application stack changes
target_scope:
  org: aiq
  bu: it
  project: invoices
  workspace: dev
capability: apply_limited
validity:
  max_duration: 30d
implementation:
  group_or_entitlement: aiq-it-invoices-dev-operator
approval:
  approver_role: PlatformOps: Invoices Dev Owner
```

The exact schema is midPoint-specific implementation work, but the
important product boundary is stable: users request business-readable
roles, not raw groups.

## Mapping midPoint Roles to PlatformOps Grants

For execution authority:

```text
midPoint requestable role
  -> approved midPoint assignment
  -> provision user into Authentik/cloud group or provider entitlement
  -> provider IAM/permission-set assignment is visible
  -> PlatformOps login-time discovery normalizes to ExecutionGrant
```

For approval authority:

```text
midPoint requestable role
  -> approved midPoint assignment
  -> provision user into Authentik approver group
  -> Authentik emits group in OIDC claim
  -> PlatformOps approval_groups mapping creates ApprovalGrant
```

This preserves the existing PlatformOps rule:

```text
execution_grants come from provider discovery
approval_grants come from PlatformOps approval policy keyed by IdP group
```

midPoint may orchestrate both assignments, but PlatformOps still builds
its session grants through the normal auth/discovery path.

## Integration Options

Option A: midPoint provisions to Authentik groups.

```text
midPoint role assignment
  -> Authentik group membership update
  -> Authentik OIDC group claim / SCIM propagation
  -> PlatformOps session refresh
```

This is conceptually clean if Authentik is the central IdP/group store.
The implementation question is whether midPoint manages Authentik
through SCIM, LDAP, REST, or a custom connector.

Option B: midPoint provisions directly to cloud identity systems.

```text
midPoint role assignment
  -> AWS IAM Identity Center / Entra / GCP group or role assignment
  -> PlatformOps provider discovery sees execution capability
```

This is closer to enterprise IGA ownership: midPoint owns the target
entitlement directly. Authentik still handles login, but not every
authorization group needs to live there.

Option C: PlatformOps submits requests to midPoint but does not mutate
identity stores.

```text
PlatformOps chat/UI detects missing access
  -> creates midPoint access request or deep link
  -> midPoint owns approval/provisioning
  -> PlatformOps waits for next login/session refresh
```

This is the safest integration point for PlatformOps. It lets users ask
from the PlatformOps UI while midPoint remains the authority for access
governance.

## Request From PlatformOps Chat

If a user asks PlatformOps:

```text
I need deploy access to invoices dev.
```

PlatformOps should not add a group directly. It should resolve a
candidate access item and route to midPoint:

```text
1. classify intent = access_request
2. resolve target scope = aiq:it/invoices/dev
3. find requestable access item = PlatformOps: Invoices Dev Operator
4. show what will be requested
5. create midPoint request or present midPoint deep link
6. return external_request_ref
```

The model can help translate "deploy access" to a candidate role name,
but deterministic lookup must confirm the role is requestable for that
user and target scope. The model must not choose an arbitrary group or
entitlement ID.

## Approval and Implementation

midPoint owns the access-request case:

```text
request created
  -> approval workflow starts
  -> approver approves/rejects
  -> implementation/provisioning phase runs
  -> request reaches final state
```

The requester should be able to monitor request state in midPoint. If
PlatformOps created the request, PlatformOps can show the external
request reference and poll/read status later, but midPoint remains the
state owner.

PlatformOps should not treat "request approved" as a runtime grant by
itself. It waits for the grant to appear through login/session refresh
and provider discovery. That avoids a second authority path.

## What Happens on Next PlatformOps Login

After midPoint completes implementation:

```text
user logs in to PlatformOps
  -> Authentik authenticates user
  -> PlatformOps validates OIDC token
  -> PlatformOps reads groups from claims
  -> PlatformOps resolves approval_grants from approval policy
  -> PlatformOps runs provider discovery for execution_grants
  -> ActorSession is rebuilt
```

Then provision authorization works the same as today/future design:

```text
request target scope
  -> route tenant policy
  -> resolve workspace
  -> effective_access = min(execution grant, policy ceiling)
  -> allow draft/plan/apply only up to that capability
```

## Modeling Project Permissions

PlatformOps project/workspace permissions should be represented in
midPoint as requestable roles or services, not free-form text.

Recommended catalog hierarchy:

```text
PlatformOps
  aiq
    it
      invoices
        dev
          Viewer
          Planner
          Operator
        prod
          Viewer
          Approver
```

Each requestable item maps to one PlatformOps scope and one capability.
If a role applies to many projects or workspaces, model that explicitly
as a broader role with a broader policy ceiling. Do not use naming
conventions alone as the security boundary.

## MVP Spike

The first midPoint spike should prove one narrow path:

```text
1. Configure Authentik as the login IdP for midPoint, or document why
   direct midPoint login is used temporarily.
2. Create one requestable role:
   PlatformOps: Invoices Dev Operator.
3. Attach an approver.
4. Submit a request as a normal user through midPoint self-service.
5. Approve it.
6. Provision the user into one backing group or entitlement.
7. Refresh PlatformOps login.
8. Confirm PlatformOps sees the expected grant through the normal path.
```

Success means the user can request project access in midPoint without
knowing IAM internals, and PlatformOps can consume the outcome without
owning access-governance state.

## Risks and Open Questions

- Which system is authoritative for Authentik groups: Authentik itself,
  midPoint, or another directory?
- Does midPoint provision to Authentik, to cloud identity systems, or
  both?
- Can the chosen connector model represent expiry and revocation
  cleanly?
- How does PlatformOps create a midPoint request: REST API, deep link,
  or manual handoff?
- Can midPoint's role catalog cleanly model
  `org/bu/project/workspace/capability` without excessive role sprawl?
- Which roles are self-requestable, which require manager/app-owner
  approval, and which require bootstrap/admin-only handling?
- How are separation-of-duty conflicts represented and enforced?
- What is the reconciliation source when midPoint and provider
  discovery disagree?

## Sources

- midPoint access request process:
  `https://docs.evolveum.com/midpoint/features/current/access-request-process/`
- midPoint access request methodology:
  `https://docs.evolveum.com/midpoint/methodology/iga/processes/access-request/`
- midPoint self-service UI:
  `https://docs.evolveum.com/midpoint/reference/master/admin-gui/self-service/`
- midPoint request access UI:
  `https://docs.evolveum.com/midpoint/reference/before-4.8/admin-gui/request-access/`
- midPoint access request REST example:
  `https://docs.evolveum.com/midpoint/reference/support-4.8/interfaces/rest/operations/examples/access-request/`
- midPoint flexible authentication concepts:
  `https://docs.evolveum.com/midpoint/reference/master/security/authentication/flexible-authentication/concept/`
- midPoint group synchronization methodology:
  `https://docs.evolveum.com/midpoint/methodology/group-synchronization/`

## How this relates to the existing docs

`OPEN_SOURCE_IGA_OPTIONS.md` identifies midPoint as the first external
IGA candidate to evaluate. This document details how that candidate
would handle the user-facing request/approval path.

`OPS_IAM_FLOW.md` remains the fallback internal PlatformOps workflow if
no external IGA tool is used. `IDP_SELECTION.md` still owns Authentik
as the IdP choice. `ACCESS_POLICY_AND_IAM_DISCOVERY.md` still owns the
login-time grant-resolution path consumed by PlatformOps.
