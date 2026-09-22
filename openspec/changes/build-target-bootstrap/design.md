# Design

## Context

The current provision preflight accepts a legacy scope hint and has no durable
registry for PlatformOps ownership, target authorization, or cloud-container
routing. See `proposal.md` and the three capability specifications for the
behavioral contract. The existing inquiry workflow is designed as read-only;
it must not become an implicit attach or cloud-creation path.

## Goals / Non-Goals

**Goals:**

- Separate the PlatformOps ownership hierarchy from identity groups, cloud
  provider resource hierarchies, and application runtime destinations.
- Allow a PlatformOps Project and its environment Resource Scopes to govern
  multiple approved Cloud Resource Containers without exposing cloud routing
  selection to callers.
- Make authorization and binding selection deterministic, auditable, and
  fail-closed.

**Non-Goals:**

- This change does not implement user registration, organization claiming,
  SCIM synchronization, cloud account/project/subscription creation, or cloud
  mutation.
- A runtime Deployment Destination—such as a Kubernetes cluster and namespace,
  ECS service, Cloud Run service, or Lambda function—is not represented by a
  Resource Scope and is not selected by this change.
- Cloud Resource Container inquiry, attaching an existing container, and
  creating a new container are distinct later workflows. Inquiry is read-only;
  it SHALL NOT create authority, attach a container, or create a provider
  resource.

## Decisions

### PlatformOps Project is logical; provider projects are bindings

The hierarchy is:

```text
Organization → BU → Team → PlatformOps Project → Environment
                                      ↓
                                Resource Scope
                                      ↓
                       Cloud Resource Container bindings (0..n)
```

The `project` segment names the logical PlatformOps Project. Its Resource
Scope is the full `org:bu:team:project:env` context and carries `scope_id`.
It is not a GCP project, AWS account, Azure subscription, or deployed runtime.
Those provider-specific boundaries are Cloud Resource Containers bound to a
scope. This prevents provider naming from redefining PlatformOps ownership and
allows one project/environment to span approved providers.

The rejected alternative is using a provider project/account as the PlatformOps
Project identifier. That ties the control-plane hierarchy to one provider and
cannot represent an application that legitimately uses more than one provider.

### Governance guardrails inherit; authority and cloud bindings do not

Organization is the hierarchy root. Business Units, Teams, PlatformOps
Projects, and Environments are descendants. Organization policy establishes a
non-bypassable ceiling; descendant policy can retain or narrow that ceiling but
cannot expand it. The effective governance policy is the restrictive
intersection of applicable Organization, BU, Team, Project, and Environment
guardrails, with any explicit deny taking precedence.

```text
effective policy = org ceiling ∩ BU ceiling ∩ team ceiling
                   ∩ project ceiling ∩ environment conditions
```

For example, an Organization can allow AWS and GCP while Commerce narrows its
projects to AWS. Commerce cannot permit a provider that the Organization
prohibits.

This automatic restrictive inheritance deliberately does not apply to all
records:

- Role bindings grant authority only at the exact scope or when the binding
  explicitly enables descendant inheritance. Production normally uses an exact
  environment-level grant.
- An Organization provider connection is an available, verified control-plane
  relationship, not permission for every project to use it.
- Cloud Resource Containers are usable only through an explicit active binding
  to a Resource Scope; they are never inherited by descendant projects or
  environments.

The rejected alternative is automatic inheritance of every parent role and
cloud connection. It makes effective access hard to review and can silently
give a new project production authority or cloud reach it did not request.

### Resource Scope is not a Deployment Destination

“Deployment target” has provider-specific meanings, often an actual compute or
runtime destination. PlatformOps therefore uses **Resource Scope** for the
logical authorization boundary. A later application-deployment contract can
define a **Deployment Destination** inside an already resolved Cloud Resource
Container. Provisioning profiles create or manage cloud resources within the
resolved container; they do not derive a runtime destination from the scope.

### Cloud Resource Container binding is a separate, versioned record

Each binding has a stable `binding_id`, `scope_id`, provider, provider container
type/reference, execution-identity reference, optional provider workspace,
lifecycle state, and version/digest. A scope may have multiple active bindings.
The registry is the only source of these values; request, token, and model
fields are untrusted routing hints and cannot establish a binding.

The first implementation supports only explicitly reviewed binding kinds. It
does not implement generic provider/container plugins or account vending.

### Deterministic policy selects a binding, never the requester

A request supplies an action and `scope_id`; it does not choose provider,
account, project, subscription, execution identity, or binding ID. Deterministic
profile/provider policy selects exactly one active binding after scope access
is authorized. Zero matching bindings or more than one equally eligible binding
returns a non-routable result. This preserves deny-by-default behavior while
allowing future multi-cloud scopes.

### Inquiry discovers candidates but cannot change governance

A separately authorized, read-only inquiry may enumerate existing AWS accounts,
GCP projects, or Azure subscriptions only within an organization’s already
connected provider boundary. The response is a candidate list, not a grant or
binding. Attaching a candidate requires a later target-bootstrap administrator
action with verification and review. Creating a new Cloud Resource Container is
a different privileged provider-bootstrap workflow, subject to organization
policy and approval.

This separation avoids turning a discovery response into access escalation or a
cloud-creation action.

### Authorization uses role bindings on the logical hierarchy

Human users, identity groups, and services are principals. A login establishes
a principal only. Deterministic role bindings grant actions at an exact Resource
Scope or an explicitly inheritable ancestor. Evaluation is:

```text
authenticate principal
→ confirm active organization membership
→ resolve active Resource Scope
→ gather exact and explicitly inherited allow bindings
→ evaluate conditions and deny guardrails
→ resolve exactly one policy-selected container binding
→ snapshot authorization and binding versions for the provision run
```

No matching allow, any applicable deny, an unmet condition, or ambiguous
binding selection denies the operation. The provider execution identity is
separate from the authenticated human principal.

## Risks / Trade-offs

- [Risk] Multiple bindings make routing ambiguous → Mitigation: require
  deterministic profile/provider policy to resolve exactly one binding; fail
  closed otherwise.
- [Risk] Provider terminology leaks into PlatformOps ownership → Mitigation:
  retain logical PlatformOps Project and Resource Scope identifiers, using
  provider identifiers only in internal bindings.
- [Risk] Inquiry reveals cloud inventory → Mitigation: use read-only connected
  provider identities, authorize inquiry at a Resource Scope, and return only
  candidates within the authorized organization boundary.
- [Risk] Attach/create flows acquire too much authority → Mitigation: keep them
  outside inquiry and ordinary provisioning; require separate verified,
  approval-controlled bootstrap changes.

## Migration Plan

1. Introduce Resource Scope and Cloud Resource Container terminology in new
   gateway contracts while preserving no durable legacy `workspace` field.
2. Register reviewed scopes and bindings in a non-routable state, then enable
   only records that pass lifecycle and authorization checks.
3. Migrate provision preflight from legacy scope lookup to `scope_id`-based
   resolution and seal the selected binding version into later plans.
4. Retire legacy `workspace` edge parsing after callers use `env` and
   `scope_id`.
