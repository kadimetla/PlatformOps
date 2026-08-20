## Status

Designed 2026-08-19. No `access_request` intent, guest chat route,
midPoint request adapter, or internal access-request workflow exists
yet.

This document captures the chat-first access request flow for users who
cannot yet use the normal PlatformOps operations surface.

## Decision

PlatformOps should allow a limited chat experience for access requests
even when the user has no provisioning or inquiry grants. This is not a
back door into operations. It is a governed request front door.

Separate three user states:

| State | Identity | Allowed chat surface |
|---|---|---|
| Anonymous visitor | No verified identity | Login help or account/access onboarding request only |
| Authenticated guest | Verified IdP identity, no PlatformOps execution grants | Access request creation and own request status |
| Authorized PlatformOps user | Verified identity with execution and/or approval grants | Normal routes allowed by policy, plus access request |

The primary target is the authenticated guest. They have proven who
they are through Authentik/SSO, but PlatformOps discovered no usable
`execution_grants` for the requested project/workspace. They can ask
for access; they cannot inspect protected inventory, provision
resources, approve changes, or infer whether hidden workspaces exist.

## Route Model

The route policy must distinguish operational routes from access
request routes:

```text
unauthenticated
  -> login
  -> account_request only if explicitly enabled

authenticated, no grants
  -> access_request
  -> own_access_request_status

authenticated, has grants
  -> provision / inquiry / access_request according to effective policy
```

Normal `provision` and `inquiry` continue to require target scope
authorization. `access_request` is different: it exists specifically so
a verified user can request the missing grant.

## Chat Flow

Example user request:

```text
I need deploy access to invoices dev.
```

The chat workflow should produce a structured access request:

```text
1. authenticate user, or stop at login/account-request handoff;
2. classify intent = access_request;
3. collect target org/BU/project/workspace;
4. collect requested role/capability in user-facing terms;
5. collect duration and justification;
6. resolve the requested item against a requestable-access catalog;
7. run deterministic eligibility checks;
8. submit to midPoint or PlatformOps's internal IGA backend;
9. return request id, status, and next action;
10. tell user to refresh/relogin after approval and propagation.
```

Example structured object:

```yaml
request_type: access_request
requester: adi@example.com
target_scope:
  org: aiq
  bu: it
  project: invoices
  workspace: dev
requested_role: operator
requested_capability: apply_limited
duration: 30d
justification: deploy frontend changes
source: platformops_chat
```

The model may translate plain language such as "deploy access" into a
candidate role. Deterministic code must confirm the candidate exists,
is requestable, and is safe to disclose for the requester.

## End-to-End Runtime Steps

The complete guest access-request path is:

```text
1. User opens PlatformOps chat.
2. If unauthenticated, PlatformOps presents only login/account-request
   guidance.
3. User signs in through Authentik or the configured corporate IdP.
4. PlatformOps builds an ActorSession from OIDC claims and grant
   discovery.
5. If no operational grants exist, PlatformOps marks the user as an
   authenticated guest.
6. User asks for access in plain language.
7. Intake classifies the request as access_request.
8. The access-request workflow collects missing fields:
   org, BU, project, workspace, role/capability, duration,
   justification.
9. Deterministic lookup maps the request to a reviewed requestable
   access item.
10. Deterministic checks verify requestability, ceilings, requester
    eligibility, and non-enumeration rules.
11. PlatformOps submits the request to the configured backend:
    midPoint, PlatformOps internal, or a future IGA connector.
12. Backend owns approval and entitlement implementation.
13. PlatformOps returns request id, status, and next action.
14. After approval and propagation, the user refreshes or logs in again.
15. PlatformOps rebuilds ActorSession through the normal login-time
    grant-resolution path.
16. Only then do provision/inquiry routes see the new grants.
```

No step patches the current session with newly requested access. The
session becomes stronger only through the standard authenticated
login/refresh path.

## Implementation Steps

Build this in small slices:

```text
1. Add Intent.ACCESS_REQUEST and a trusted route id.
2. Add route policy that allows authenticated guests to reach only
   access_request and own_access_request_status.
3. Add AccessRequest / AccessRequestDraft schemas.
4. Add a requestable-access catalog contract:
   scope pattern, display role, capability, duration limits,
   backend entitlement reference, disclosure policy.
5. Add deterministic lookup and eligibility checks.
6. Add LangGraph access_request preflight:
   resolve identity -> collect fields -> lookup requestable item ->
   produce draft.
7. Add AccessRequestBackend protocol.
8. Implement a no-op/manual backend first, returning a request record
   without mutating IdP or cloud state.
9. Add midPoint backend spike:
   create request or produce deep link, store external_request_ref.
10. Add own-request status lookup.
11. Add tests for anonymous, authenticated guest, authorized user,
    unknown target, unauthorized target, and successful request.
12. Add evidence records and audit fields.
13. Only if using the internal backend, add approval gate and narrow
    Authentik group mutation.
```

The first real milestone should stop at request creation. Approval,
group mutation, expiry, and revocation should not be hidden inside the
same slice.

## Anonymous Visitor Boundary

Anonymous users should not get the same access-request surface. Without
verified identity, PlatformOps cannot know who is requesting access or
which enterprise tenant they belong to.

Allowed anonymous actions:

- start login;
- explain that corporate SSO is required;
- collect a minimal account-onboarding request if the product enables
  that path;
- submit only public, non-sensitive contact metadata.

Forbidden anonymous actions:

- workspace/project enumeration;
- role catalog browsing;
- requestable group discovery;
- approval status lookup;
- provisioning/inquiry routing;
- any claim that a target exists.

The product can still feel conversational, but the response must be
uniform and non-enumerating:

```text
Sign in with your company account to request PlatformOps access.
```

## Authenticated Guest Boundary

An authenticated guest may create an access request for a target they
name, but PlatformOps must avoid leaking inventory.

If the target is unknown, unauthorized, or not requestable, return a
uniform response:

```text
I could not create an access request for that target. Check the
org/project/workspace or contact your platform administrator.
```

Do not reveal which condition failed. If policy allows a broader
request flow, route to an admin triage queue instead of confirming
existence.

Allowed authenticated-guest actions:

- create access request for a named target;
- answer clarification questions about requested role, duration, and
  justification;
- view status of their own access requests;
- receive a midPoint deep link or request ID.

Forbidden authenticated-guest actions:

- list all projects/workspaces;
- list all privileged roles;
- inspect infrastructure;
- create plans;
- approve requests;
- mutate IdP groups directly;
- bypass midPoint/internal IGA approval.

## Backend Options

Use the same chat workflow front end with a pluggable backend:

```text
AccessRequestBackend
  midpoint
  platformops_internal
  future: saviynt / service-now / jira
```

midPoint backend:

```text
chat access_request workflow
  -> resolve requestable role
  -> create midPoint access request or deep link
  -> midPoint owns approval, provisioning, expiry, revocation, audit
```

Internal backend:

```text
chat access_request workflow
  -> resolve access template
  -> deterministic checks
  -> PlatformOps approval gate
  -> narrow Authentik group membership update
  -> evidence and expiry/revocation job
```

The chat workflow should emit the same internal `AccessRequest` shape
for both backends, so choosing midPoint does not leak midPoint-specific
objects into the rest of PlatformOps.

## midPoint Handoff

When midPoint is the backend, PlatformOps should prefer one of two
handoff modes.

Create request by API:

```text
PlatformOps
  -> calls midPoint REST API with requester, role, scope, duration,
     justification
  -> returns external_request_ref and status/deep link
```

Deep link:

```text
PlatformOps
  -> resolves the requestable role
  -> sends the user to midPoint self-service with enough context to
     finish the request there
```

API creation gives the best chat UX. Deep links are simpler for an MVP
or when midPoint request APIs need more implementation review.

In both modes, midPoint owns approval and assignment lifecycle. A
midPoint "approved" state is not itself a PlatformOps runtime grant.
The grant becomes active only after the standard login/session refresh
and provider discovery path sees the resulting assignment.

## Security Invariants

- A guest route can create a request, not grant access.
- The LLM never chooses raw IdP group names or entitlement IDs.
- Requestable roles come from reviewed catalog/policy data.
- Unknown and unauthorized targets are externally indistinguishable.
- A user cannot self-approve their own access request.
- The current session is not patched with newly approved grants.
- Expiry and revocation remove the underlying assignment, then the next
  session refresh reflects the lower capability.
- Normal provision/inquiry routes still fail closed until
  `ActorSession` contains the required grants.

## How this relates to the existing docs

`OPS_IAM_FLOW.md` owns the day-two IAM lifecycle. This document adds the
chat entry point for users who have no PlatformOps operational grants
yet.

`MIDPOINT_IGA_DEEP_DIVE.md` owns the external midPoint request and
approval path. `OPEN_SOURCE_IGA_OPTIONS.md` owns the tool comparison.
`AUTH_BOUNDARY.md` still owns the rule that authentication happens
before workflows, and `ACCESS_POLICY_AND_IAM_DISCOVERY.md` still owns
session grant resolution.
