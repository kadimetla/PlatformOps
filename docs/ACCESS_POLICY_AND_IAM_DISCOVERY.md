## Status
Designed only. No auth layer, `gateway/`, or workflow code exists on
this branch. Every provider API cited below was verified against
current docs on 2026-07-28 (see Sources) — not recalled from training
data, per `AGENTS.md`'s hard rule on third-party integrations. Three
real gaps were found and corrected during that verification (marked
**gap found** below): AWS and Azure discovery APIs return opaque
references needing a second resolve call, and Azure's
`principalId eq` filter misses group-derived assignments. Extends
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s "Cloud Roles and
Access Flow" section: that section keeps the request-time flow
(intake → policy → workflow → approval → executor); this doc owns
everything upstream — login, access discovery, capability
normalization, and the credential model. Designed from a clean slate;
no prior credential artifact in this repo was treated as a baseline.

## Real vs. Designed
| Area | Status |
|---|---|
| Auth/session layer (any) | Not implemented — none exists on this branch |
| OIDC login + claims → `Actor` | Designed only |
| Login-time provider access discovery | Designed only |
| Capability ladder + normalization mapping | Designed only |
| PlatformOps policy registry (`gateway/policy/*.yaml`) | Designed only |
| Discovery identity (per cloud, read-only, org-wide) | Designed only — new requirement identified this session |
| Execution identity (per workspace + capability tier) | Designed only |
| `spec/check_compliance.py` | Real, deterministic, unrelated — the only currently-executable check in the repo |

## Problem
Two distinct questions, both needed before any workflow runs, neither
answerable by an LLM:

```
WHO is this, and what are THEY entitled to?         (this doc)
WHERE does this request target, and is that target
  within PlatformOps's own policy ceiling?           (INTAKE_HITL_ROUTING.md)
```

Cloud IAM does not naturally store access as
`user -> project -> workspace -> capability` — each provider stores it
differently, so PlatformOps must translate provider-native
roles/assignments/bindings into its own capability model. Two cases
shape the design differently:

```
existing project/workspace
  -> discover current provider-side access
  -> normalize into PlatformOps capability
  -> enforce PlatformOps's own policy ceiling on top

new project/workspace
  -> no discovery possible (nothing exists yet)
  -> admin/bootstrap path only, never LLM-routed
  -> baseline access templates applied
  -> result recorded into the registry
```

## The Capability Ladder
```
none -> describe -> plan -> propose_change -> apply_limited -> apply_full -> admin
```

| Level | Allowed |
|---|---|
| `none` | Cannot see or act on the workspace |
| `describe` | Read metadata, list resources, explain stack shape |
| `plan` | Generate a Terraform/CDK/CloudFormation plan, no mutation |
| `propose_change` | Prepare a PR/change request, no direct apply |
| `apply_limited` | Apply only allow-listed resource/action types, after approval |
| `apply_full` | Broader mutation after approval, still not unrestricted cloud admin |
| `admin` | Manage workspace permissions/policies — rare, effectively the bootstrap capability |

Every provider-native role/permission-set/binding is normalized onto
this one ladder — the only vocabulary `resolve_route` and approval
gates ever reason about. Nothing downstream needs to know what an AWS
permission set or an Azure role definition actually was.

Example per-workspace tiering this enables (the motivating case):

```
invoices/dev  -> apply_limited    (build, approve, apply allow-listed resources)
invoices/uat  -> propose_change   (describe, plan, open change proposal — no apply)
invoices/prod -> describe         (read-only; "cannot deploy" is a capability
                                   fact, not an instruction the LLM must obey)
```

Prod restraint is enforced twice: the capability caps what routes, and
the prod execution identity (below) lacks mutation permissions
entirely — "technically impossible," not "told not to."

## The `effective_access` Invariant
```
WHO:   actor.execution_grants[best match for (org_bu, project, workspace)]
         -> capability this user is entitled to (discovery, this doc)
WHAT:  org_bu_policy.ceiling[(org_bu, project, workspace, intent)]
         -> PlatformOps's own governance cap, independent of any user
WHERE: resolved separately by intake (INTAKE_HITL_ROUTING.md)

effective_access = min(actor.execution_grants[...], org_bu_policy.ceiling[...])
```

If a provider over-grants, PlatformOps's ceiling still caps behavior.
If PlatformOps's policy allows an action the user's real cloud
entitlement doesn't cover, the lower wins. Both must pass — the one
sentence to keep unchanged through every later revision of this doc.

## Core Decision: No User-Supplied Cloud Credentials, Ever
```
NOT THIS (rejected):
  user separately connects/authenticates to AWS/Azure/GCP
    -> PlatformOps receives a user-delegated cloud token
    -> PlatformOps acts as that user

THIS:
  user authenticates ONCE, via PlatformOps's corporate-IdP login
    -> PlatformOps's OWN standing, read-only discovery identity
       (one per cloud) asks the provider "what does user X have" —
       the user presents no cloud credential and is not involved
    -> normalized into actor.execution_grants, cached in the session
```

The discovery APIs themselves confirm this is the intended shape: all
three take a **principal ID as a parameter** — built for a privileged
introspection caller asking about *someone else*, not "what's my own
access" self-service.

**Delegated user-token model rejected for MVP** — a valid pattern
elsewhere, rejected here for: per-user/per-provider token custody and
refresh; OAuth/device-flow integration ×3 clouds; a muddier audit
story (was the action the user's or the agent's?); the risk of broad
user cloud credentials entering PlatformOps at all; and three
inconsistent delegation models where the chosen design has one.

## Three Identities, Strictly Separated
| | Discovery identity | Execution identity | User identity |
|---|---|---|---|
| Purpose | Answer "is user X entitled to capability Y" | Perform the plan/apply | Prove who is asking |
| Scope | Org-wide, READ-only, one per cloud | Narrow, per workspace + capability tier | Never used as a cloud executor |
| Held by | PlatformOps backend, standing | PlatformOps backend, assumed at execution time only | The user's own IdP session |
| Used | Once per login | Once per approved mutating action | Once, at login |

The discovery identity is the single most sensitive credential in this
design: read-only, but with org-wide visibility into every role
assignment across every cloud. A leak is an information-disclosure
risk across the whole org's IAM, unbounded by any one workspace's
blast radius — it needs its own `security-review-checklist` entry,
distinct from (and arguably higher-severity than) any execution
identity. A third, separate **bootstrap identity** exists only for the
new-project path (below).

## Login Flow
PlatformOps is a registered OIDC/SAML client in the company's IdP
(Okta / Entra ID / Google Workspace / Auth0 / Keycloak). It never
stores passwords; MFA/SSO happen at the IdP.

```
1. user opens PlatformOps -> redirect to corporate IdP
2. user authenticates there (password/MFA/SSO — at the IdP, not here)
3. IdP redirects back with an auth code
4. PlatformOps exchanges code for tokens, validates signature
5. claims read from the ID token:
     { "sub": "00uabc123", "email": "adi@example.com",
       "groups": ["aiq-it-invoices-dev-operator", ...],
       "oid": "<entra-object-id-if-azure>" }
   -> Actor(user_id, email, groups) — same rule as
      INTAKE_HITL_ROUTING.md's A1: identity from the authenticated
      session, never parsed from raw_text
6. resolve provider principal ids        (own step + risk — see below)
7. per cloud in the org_bu's registry, discovery calls in parallel
8. provider-side expansion               (resolve opaque refs / walk
                                          inheritance — see per-provider)
9. normalize -> capability ladder        (mapping table WE maintain)
10. actor.execution_grants built, stored in the session
11. actor.approval_grants ALSO resolved — same claims, different
    source: PlatformOps-native policy/IdP groups directly, NO
    provider call at all (see "Two Grant Sets" below)
    │
    ▼
EVERY intake or approval-gate check this session: pure local read of
actor.execution_grants / actor.approval_grants — zero live provider
calls per request
```

**Precedence rule, per grant set — each has exactly one authoritative
source, and the two sources differ on purpose:**

| Grant set | Authoritative source | IdP group claims' role |
|---|---|---|
| `actor.execution_grants` | Provider discovery (this doc's Login Flow, steps 6–9) | Feed principal resolution + group-based discovery queries only — **never** a second, parallel source of execution grants |
| `actor.approval_grants` | PlatformOps's own policy config (`gateway/policy/approvers.yaml` or equivalent), keyed by IdP group name directly | Are the direct, sole source — no provider round-trip |

Without stating each set's one authoritative source explicitly, the
two would eventually disagree and nothing would say which wins. See
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s approval-gate
section for why approval authority is deliberately PlatformOps-native
rather than cloud-grounded: approving a change is a governance act,
not a provider API capability, and a prod approver does not need prod
write access — they need standing PlatformOps approval authority on
that scope.

Session refresh rides the OIDC token-refresh mechanism — nothing new
to build. Mid-session revocation takes effect at next login/refresh,
not instantly: the standard tradeoff of every session-based system.

## Principal-ID Mapping — Its Own Step, Its Own Risk
**Architecture assumption, stated explicitly**: all providers federate
identity from the *same* corporate identity source.

```
Corporate IdP
  -> Azure Entra identity                   (IS the IdP, if Entra is used)
  -> AWS IAM Identity Center                (via SCIM sync from that IdP)
  -> GCP principal email / Workspace domain (same corporate email)
```

| Provider | Resolution when assumption holds | Cost when it breaks |
|---|---|---|
| Azure | Free — the `oid` claim **is** the principal id | Federated-into-Entra still resolves in one hop; a fully separate directory doesn't |
| AWS | Identity Store UUID already known via SCIM sync — or one lookup (`identitystore` GetUserId/ListUsers by email) at login | Without SCIM, that lookup is mandatory — an extra call the first draft of this design hadn't accounted for |
| GCP | Free — corporate email **is** the GCP principal email | Unsynced GCP identity source = its own separate integration project, not a lookup fix |

## Group Membership — Part of Discovery on All Three Clouds
Most real-org access is granted to **groups**, not individual users.
Discovery keyed only on the user silently returns a fraction of their
real access. Per provider:

- **AWS**: `ListAccountAssignmentsForPrincipal(PrincipalType="USER")`
  returns direct user assignments only. Assignments made to the user's
  groups need separate calls with `PrincipalType="GROUP"`, one per
  group — the user's group list (IdP claims, SCIM-synced into the
  Identity Store) is a required input, not an optimization.
- **Azure** (**gap found and corrected**): filter choice decides this.
  Verified against current docs: `$filter=assignedTo('{objectId}')`
  "lists role assignments for a specified user... If the user is a
  member of a group that has a role assignment, that role assignment
  is also listed. This filter is transitive for groups."
  `$filter=principalId eq '{objectId}'` — which this design originally
  specified — returns only assignments made directly to that exact
  principal. Use `assignedTo()`; group resolution then comes free.
- **GCP**: a binding to `group:platform-team@company.com` will not
  match `policy:"user:alice@..."` — bindings must also be checked for
  each of the user's groups.

## Per-Provider Discovery Mechanics

### AWS — verified against current AWS docs
Precondition: **IAM Identity Center**. Plain IAM roles/users have no
"list this user's access everywhere" call at all — Identity Center is
what makes workforce-access discovery possible on AWS. Access is
stored as `principal (user/group) + AWS account + permission set`.

```
ListAccountAssignmentsForPrincipal(
    InstanceArn=<Identity Center instance ARN>,
    PrincipalId=<Identity Store UUID>,
    PrincipalType="USER",         # + one call per group, type GROUP
)
-> [{AccountId, PermissionSetArn, PrincipalId, PrincipalType}, ...]
```
Paginated (max 100/page); must be called from the Identity Center
**management account**, not a member account.

**Gap found and corrected**: the response carries only an opaque
`PermissionSetArn` — no name to normalize against. A second, required
call resolves it (verified: `Name` is a real response field):

```
DescribePermissionSet(InstanceArn, PermissionSetArn)
-> PermissionSet{Name, Description, ...}
```

Full chain: `ListAccountAssignmentsForPrincipal -> PermissionSetArn ->
DescribePermissionSet -> Name -> capability`. Example:

```
PlatformOpsDevOperator  -> apply_limited
PlatformOpsUatPlanner   -> propose_change
PlatformOpsProdReader   -> describe
```

### Azure — verified against current Microsoft Learn docs
Access is stored as role assignments:
`principal + role definition + scope` (management group /
subscription / resource group / resource).

```
GET {scope}/providers/Microsoft.Authorization/roleAssignments
    ?api-version=2022-04-01&$filter=assignedTo('{objectId}')
```
Called once at the tenant root **management group**, the
`principalId`-style filters return assignments "at, above, or below
the scope" — one call covers the tenant. Caller (PlatformOps's app
registration / managed identity) needs
`Microsoft.Authorization/roleAssignments/read` at that scope. Use
`assignedTo()`, not `principalId eq` (see Group Membership above).

**Gap found and corrected, same shape as AWS**: the response carries
only `properties.roleDefinitionId` — an opaque
`/providers/Microsoft.Authorization/roleDefinitions/{guid}` path. A
second, required call resolves it (verified: `properties.roleName` is
a real response field, alongside the concrete `permissions` list):

```
GET https://management.azure.com/{roleDefinitionId}?api-version=2022-04-01
-> RoleDefinition{ properties.roleName, properties.permissions, ... }
```

Full chain: `roleAssignments (assignedTo) -> roleDefinitionId ->
role-definition GET -> roleName -> capability`. Example:

```
Reader                            -> describe
Contributor (scoped to a dev RG)  -> apply_limited
Custom "Planner" role             -> plan / propose_change
Owner                             -> admin — probably blocked or capped by policy
```

### GCP — verified against current Cloud docs; different kind of gap
Access is stored as allow-policy bindings on resources:
`resource + role + principal`, inherited down
org → folder → project → resource.

```
searchAllIamPolicies(
    scope="organizations/<org_id>",
    query='policy:"user:alice@company.com"',   # + one query per group
)
```

**No second resolve-to-name call needed** — unlike AWS/Azure, returned
role identifiers are already self-describing strings (`roles/viewer`;
`projects/X/roles/platformopsPlanner` where the suffix is the
creator-chosen name). Treating GCP as needing the same two-hop
expansion would overstate one gap and bury the real one:

**The real GCP gap is inheritance.** The docs are explicit: "This
request only returns the roles that [the user] is granted on the
project. It doesn't include roles that [the user] inherited through
policy inheritance." A folder-level grant won't appear when checking
the child project. PlatformOps must walk its own known
org → folder → project hierarchy (held in the registry) and check
returned bindings against every **ancestor** of the target project —
an inheritance-resolution problem, structural and unavoidable.

MVP scope-down: check only projects/workspaces the registry already
knows, via `getIamPolicy` per known project (matching bindings for the
user's email *and* groups), rather than an org-wide
`searchAllIamPolicies` scan. Cheaper; the inheritance walk is the same
either way. Example normalization:

```
roles/viewer                 -> describe
roles/browser                -> describe
custom platformopsPlanner    -> plan
custom platformopsOperator   -> apply_limited
```

### HCP Terraform
Team/project/workspace permissions, read via the tools already
verified in [TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)
(`list_workspaces`, `get_workspace_details`,
`get_workspace_policy_sets`, `get_token_permissions`) — not
re-verified here. `get_token_permissions` doubles as the natural
pre-apply drift-check tool (below), since it reports what the
*current* token can actually do.

## What the Session Stores
```json
{
  "actor": {
    "user_id": "00uabc123",
    "email": "adi@example.com",
    "execution_grants": [
      { "org_bu": "aiq:it", "project": "invoices", "workspace": "dev",
        "provider": "aws", "capability": "apply_limited" },
      { "org_bu": "aiq:it", "project": "invoices", "workspace": "prod",
        "provider": "aws", "capability": "describe" }
    ],
    "approval_grants": [
      { "org_bu": "aiq:it", "project": "invoices", "workspace": "prod",
        "max_capability": "apply_limited" }
    ],
    "resolved_at": "2026-07-28T10:00:00Z"
  }
}
```
`execution_grants` are what `resolve_route` and the executor consult.
`approval_grants` are what the approval gate consults (see
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)) — a prod
approver here holds no `aws` execution grant on prod at all, only
approval standing. `resolved_at` is what any staleness/TTL policy
keys off — three tiers, increasingly strict, all already designed
elsewhere in this doc set rather than one uniform rule: **(1)** simple
MVP — changes apply at next login/session refresh (this doc's
accepted tradeoff, above); **(2)** stricter — refresh the specific
actor's grants at the approval gate or immediately before execution
([EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s live
`approver_currently_authorized` reload and pre-flight step 1); **(3)**
strictest — short session TTL plus forced refresh on high-risk
actions specifically, not designed further here. Ordinary intake
reads stay fast and local (tier 1); the approval gate and execution
resume are where tier 2 already applies. Intake reads only
`execution_grants`. Worked example (request-time flow itself lives in
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)):

```
user: "deploy invoices to prod"
intake:  intent=provision, project=invoices, workspace=prod
policy:  effective_access = min(grant=describe, ceiling=describe) = describe
outcome: cannot deploy; can describe the prod stack, or prepare a
         change proposal if capability allows — downgrade, not a dead end
```

## New Project/Workspace Bootstrap Flow
No discovery is possible for something that doesn't exist. This is a
categorically different, rarer operation — gated at `admin`, and kept
out of the LLM-routed intake path entirely (per
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md): "v1 intake shouldn't
route 'create a new project' anywhere at all").

```
1. intent = create_project — admin-only, never LLM-classified into a
   route the way provision/inquiry/compliance_check are
2. policy: may this org_bu create projects? which environments?
   which baseline template applies?
3. bootstrap identity: tightly controlled, used ONLY for scaffolding —
   distinct from both discovery and execution identities
4. create: cloud project/account/resource group/workspace; tags,
   labels, name prefixes; baseline IAM roles matching the ladder from
   day one (prod gets a read-only role at creation — never "full
   access, restricted by policy only"); HCP Terraform
   workspace/project if on the Terraform path
5. record: registry entry, provider target identifiers, execution
   identity references, audit evidence
```

Example baseline template, `project = invoices`:
```
dev:  capability_ceiling = apply_limited,  execution_identity = invoices-dev-provisioner
uat:  capability_ceiling = propose_change, execution_identity = invoices-uat-planner
prod: capability_ceiling = describe,       execution_identity = invoices-prod-reader
```

## Recommended Storage
```
gateway/policy/
  org_bu_policy.yaml      # POLICY[(org_bu, project, workspace, intent)] -> capability ceiling
  project_registry.yaml   # provider targets, execution identity refs, capability ceilings
  access_templates.yaml   # baseline templates for bootstrap
```

Conceptual shape:
```yaml
projects:
  invoices:
    owner: aiq:it
    workspaces:
      dev:
        cloud: aws
        provider_target: "123456789012/us-east-1"
        execution_identity: "arn:aws:iam::123456789012:role/platformops-invoices-dev-provisioner"
        max_capability: apply_limited
      uat:
        max_capability: propose_change
      prod:
        max_capability: describe
```

Plus, as deployment configuration rather than registry content: the
OIDC/SAML client config for the corporate IdP, per-provider principal
resolution config, the discovery identities' credential references,
and the role/permission-set/role-definition → capability mapping
table.

Stores IDs, scopes, ARNs/service-principal IDs/service-account emails,
and capability ceilings — **never credentials**. Credentials stay in
each provider's identity system (or a secrets manager for the
discovery/execution identities' own short-lived tokens), per
`AGENTS.md`'s "never hardcode credentials."

One narrow live check belongs in the request path: immediately before
an `apply_limited`/`apply_full` action — not before `describe`/`plan`,
not per-request generally — re-fetch the target execution identity's
actual permissions (`get_token_permissions` on the Terraform path;
`sts:GetCallerIdentity` + policy simulation on AWS; provider
equivalents elsewhere) to catch drift between the cached registry and
what the cloud enforces now. Highest-stakes point; the one place a
stale cache is most dangerous.

## Open Questions
| Question | Current recommendation |
|---|---|
| Discovery timing: synchronous in the login callback, or async right after? | Parallel across providers either way; seconds of login latency are fine once per session |
| Group explosion on AWS (one `ListAccountAssignmentsForPrincipal` call per group): cache group→assignment results across users? | Defer — measure first; per-login cost is bounded by the user's group count |
| Does `admin` need its own capability semantics, or is "has repo/config write access" enough for now? | Deferred — no second admin persona exists to justify it |
| GCP: org-wide `searchAllIamPolicies` vs registry-scoped `getIamPolicy`? | Registry-scoped for MVP; the inheritance walk is needed either way |
| Provider identity source NOT synced to the corporate IdP? | Not designed here — a separate per-provider integration project when real, not before |
| Periodic audit of the discovery identity's own access/usage? | Not designed here — flagged for `security-review-checklist`, given its org-wide read blast radius |

## Sources
- [AWS: ListAccountAssignmentsForPrincipal](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_ListAccountAssignmentsForPrincipal.html)
- [AWS: DescribePermissionSet](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_DescribePermissionSet.html)
- [AWS IAM Identity Center features](https://aws.amazon.com/iam/identity-center/features/)
- [Azure: Role Assignments — List For Subscription](https://learn.microsoft.com/en-us/rest/api/authorization/role-assignments/list-for-subscription?view=rest-authorization-2022-04-01)
- [Azure: Role Definitions — Get By Id](https://learn.microsoft.com/en-us/rest/api/authorization/role-definitions/get-by-id?view=rest-authorization-2022-04-01)
- [Azure: List role assignments using the REST API](https://learn.microsoft.com/en-us/azure/role-based-access-control/role-assignments-list-rest) — source of the `assignedTo()` vs `principalId eq` group-transitivity distinction
- [GCP: Searching IAM policies (Cloud Asset Inventory)](https://docs.cloud.google.com/asset-inventory/docs/searching-iam-policies)
- [GCP: gcloud policy-troubleshoot](https://docs.cloud.google.com/sdk/gcloud/reference/policy-troubleshoot)

## How this relates to the existing docs
Extends [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s "Cloud
Roles and Access Flow" section — that section keeps the request-time
flow (intake → `POLICY` lookup → workflow → deterministic checks →
human approval → executor); this doc owns everything upstream
(login-time discovery) plus the credential model those steps assume.
The execution-time half of that credential model — how the executor
actually obtains short-lived tokens — is
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md).
Its capability ladder replaces the coarser viewer/operator persona
sketch explored earlier in this session (briefly captured in that
doc's Real-vs-Designed table, now corrected there in place). Reuses
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s verified tool
inventory for the HCP Terraform path rather than re-verifying it.
Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
