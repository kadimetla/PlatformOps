## Status

Designed 2026-08-19. No self-service access-request workflow,
Authentik admin client, SCIM reconciliation job, or provider-group
mutation adapter exists yet. This document captures the operational IAM
flow that sits between bootstrap and normal workflow execution.

`ACCESS_POLICY_AND_IAM_DISCOVERY.md` owns login-time discovery and
capability normalization. `BOOTSTRAP_WORKFLOW.md` owns creation of the
org/BU/project/workspace scaffolding, groups, execution identities, and
registry rows. This document owns day-two access changes: how a user
asks for a role, how that request is approved, how Authentik/IdP group
membership changes, and how PlatformOps sees the new capability.
`OPEN_SOURCE_IGA_OPTIONS.md` compares whether an external IGA tool such
as midPoint or OpenIAM should own this lifecycle instead of PlatformOps
building the MVP workflow itself.
`GUEST_ACCESS_REQUEST_CHAT.md` defines the limited chat surface for
authenticated users who have no PlatformOps grants yet but need to
request them.

## Decision

PlatformOps should provide an operational IAM access-request flow, but
it must not grant access from ordinary chat intent or from an LLM
decision. Access changes create or remove authority. They are admin
governance mutations and require deterministic policy checks, approval,
evidence, and revocation/expiry behavior.

Use this authority chain:

```text
bootstrap policy and registry
  -> requestable access templates
  -> user access request
  -> deterministic eligibility checks
  -> approver approval
  -> IdP group membership update
  -> optional SCIM/provider propagation
  -> next login/session refresh
  -> ActorSession grants
```

The user can request access in natural language or through a UI form,
but the executable change is a structured access request resolved
against reviewed templates. The model may help classify intent and
explain which role is appropriate. It must not select an arbitrary IdP
group, edit membership, bypass approvers, or mint cloud permissions.

## Two Grant Sets Stay Separate

Execution and approval authority have different sources:

| Grant set | What it controls | Source of truth |
|---|---|---|
| `execution_grants` | Describe, plan, propose, or apply infrastructure in a workspace | Provider discovery, normalized at login |
| `approval_grants` | Approve another user's requested change | PlatformOps approval policy keyed by IdP group membership |

IdP groups are still central to both flows, but not in the same way.

For execution authority:

```text
Authentik group membership
  -> SCIM sync / cloud identity-system assignment
  -> provider IAM or permission-set assignment
  -> PlatformOps login-time provider discovery
  -> ExecutionGrant
```

For approval authority:

```text
Authentik group membership
  -> OIDC group claim
  -> PlatformOps approval_groups policy
  -> ApprovalGrant
```

`gateway/auth/grants.py` already enforces this split for real code:
group mapping can create approval grants only; execution grants must
come from provider discovery.

## Bootstrap Output Required Before Requests

Access requests can only target identities and roles that bootstrap has
already made legitimate. At org/BU bootstrap and project/workspace
bootstrap, platform admins define:

- org/BU policy rows and sector/governance classification;
- project/workspace registry rows;
- workspace execution identities and maximum capability ceilings;
- requestable role templates;
- Authentik/IdP group naming conventions;
- cloud-side assignments or permission-set bindings connected to those
  groups;
- approval groups and required approval counts;
- optional maximum duration, renewal, and emergency-break-glass rules.

Example groups:

```text
aiq-it-invoices-dev-viewer
aiq-it-invoices-dev-planner
aiq-it-invoices-dev-operator
aiq-it-invoices-prod-approvers
```

Example capabilities:

```text
viewer     -> describe
planner    -> plan
operator   -> apply_limited
approver   -> ApprovalGrant, not cloud execution authority
```

No bootstrap row means no requestable access target. No access template
means the user cannot ask PlatformOps to invent one at runtime.

## Access Request Flow

The normal self-service request is:

```text
1. user asks for access
2. PlatformOps resolves exact org/BU/project/workspace
3. PlatformOps resolves requested role/capability from templates
4. deterministic checks verify requestability and ceilings
5. approval gate collects required approver decisions
6. approved request updates the IdP group membership
7. evidence records who requested, who approved, what changed, and why
8. user refreshes or logs in again
9. login discovery rebuilds ActorSession grants
```

Example structured request:

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
```

Example resolved action after checks:

```yaml
idp: authentik
group_to_add: aiq-it-invoices-dev-operator
required_approver_group: aiq-it-invoices-dev-owners
max_capability: apply_limited
expires_at: 2026-09-18T00:00:00Z
```

The approval decision does not immediately make an already-running
session stronger. The user must refresh or start a new session so the
standard login-time grant-resolution path remains the single place that
builds `ActorSession`.

## Deterministic Checks

An access request fails closed unless all checks pass:

- requester is authenticated;
- target org/BU/project/workspace exists and is routable;
- requester can see the target enough to request access, or an admin is
  filing the request on their behalf;
- requested role exists in the access template;
- requested capability does not exceed org/BU, workspace, or role
  ceilings;
- target group is managed by PlatformOps and matches the naming
  convention;
- group mutation is within the configured IdP boundary;
- required approver set is non-empty;
- requester cannot self-approve;
- duplicate approver decisions do not count twice;
- expiry/renewal policy is satisfied;
- emergency or break-glass roles require the stricter bootstrap/admin
  path, not normal self-service.

These checks are plain code and policy data. No LLM result can satisfy
or waive them.

## Authentik as the IdP Boundary

Authentik is the recommended MVP IdP in `IDP_SELECTION.md`, but
PlatformOps still treats it as an external identity authority, not as a
workflow database.

Authentik owns:

- users;
- groups;
- OIDC application/provider configuration;
- device-code login flow;
- group claims in ID tokens;
- SCIM provisioning where configured.

PlatformOps owns:

- access templates;
- project/workspace registry;
- policy ceilings;
- approval policy;
- access-request records;
- session snapshots;
- execution/approval evidence.

The IdP mutation performed by this workflow should be narrow:

```text
add or remove user X from managed group Y
```

It should not edit Authentik flows, providers, applications, global
policies, or arbitrary groups. Those remain platform-admin operations.

## Propagation and Session Refresh

Access changes are eventually visible:

```text
approved access request
  -> Authentik group update
  -> OIDC claims include group on next login/refresh
  -> SCIM/provider propagation updates cloud-side assignments
  -> provider discovery resolves execution grants
```

Execution access may require both IdP and provider propagation before
it appears in `execution_grants`. Approval access may appear as soon as
the OIDC group claim is present and PlatformOps approval policy maps
that group.

Do not special-case a just-approved request by injecting grants into the
current session. That would create a second authority path. The access
request result may tell the user to refresh, but the next session must
still be derived from Authentik claims and provider discovery.

## Revocation, Expiry, and Audit

Temporary grants should be modeled as access records with an expiry,
plus either:

- scheduled group removal; or
- periodic reconciliation that removes expired memberships from managed
  groups.

Revocation follows the same boundary:

```text
revoke request / expiry
  -> remove user from managed IdP group
  -> propagation completes
  -> next login/refresh loses the grant
```

High-stakes approval checks may re-read current approver authority at
approval resume time, as `EXECUTION_CREDENTIALS.md` designs. Normal
sessions may tolerate refresh-time staleness, but mutation apply must
still revalidate policy, approval digest, execution identity, and
current capability before any cloud action.

Each access request writes evidence:

- requester;
- target scope;
- requested role and capability;
- resolved IdP group;
- policy/template version;
- approver records;
- expiry;
- final IdP mutation result;
- correlation IDs for Authentik/provider operations when available.

## Non-Goals for MVP

- No free-form IAM policy authoring by users.
- No LLM-selected IdP group names.
- No direct cloud execution grant from PlatformOps YAML.
- No normal provision workflow path that creates new roles, permission
  sets, or provider IAM bindings.
- No bypass of bootstrap for new projects/workspaces.
- No mutation of unmanaged IdP groups.

## How this relates to the existing docs

This doc fills the operational gap between:

- `BOOTSTRAP_WORKFLOW.md`, which creates the governed access universe;
- `IDP_SELECTION.md`, which selects Authentik and defines the IdP
  integration expectations;
- `AUTH_BOUNDARY.md`, which keeps auth/session construction outside
  LangGraph workflows;
- `ACCESS_POLICY_AND_IAM_DISCOVERY.md`, which resolves provider-backed
  execution grants at login;
- `EXECUTION_CREDENTIALS.md`, which uses approval grants at mutation
  approval time.

It does not replace any of those documents. It defines the missing
admin-governance workflow that changes the IdP/provider inputs those
documents consume.
