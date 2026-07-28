## Status
Designed only — no bootstrap workflow, IaC stack, or identity exists.
Fourth act of the access design: this doc covers how the identities
that [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) assumes
pre-exist actually get created, at every level from company onboarding
down to adding a workspace. Provider mechanisms named here
(permissions boundaries, Organizations account vending, Azure/GCP
role-ceiling constraints) are standard but **not freshly web-verified**
— see "Verify before build." Design converged over a 2026-07-28
explore session; decisions below were each made deliberately, with
alternatives noted where they were real.

## Real vs. Designed
| Area | Status |
|---|---|
| Bootstrap workflow (any level) | Not implemented |
| Bootstrap allow-list (`infra/bootstrap-allowed-resource-types.json`) | Not implemented — file does not exist yet |
| Contracts (`BootstrapRequest`, `BootstrapPlan`, `WorkspaceIdentitySpec`, `ProjectRegistryEntry`) | Designed only — the recommended first build |
| Org/BU onboarding | Designed as PR-reviewed config editing for MVP, not automated |
| Teardown paths | Explicitly deferred — separate admin path, not designed |
| Existing `infra/allowed-resource-types.json` | Real — the normal-provisioning allow-list this design's disjointness rule builds on |

## The Bootstrap Ladder
Each level's output is exactly what makes the next level's bootstrap
possible:

```
Level -1  PlatformOps itself           runtime identity, discovery identities,
          (once, ever)                 org-level bootstrap identity, IdP app
                                       registration
                                       -> MANUAL / landing-zone by definition;
                                          no workflow can create its own root

Level 0   Org onboarding               cloud org trust (AWS Organization link,
          (once per company)           Entra tenant, GCP organization), IdP
                                       federation + SCIM, org row in config

Level 1   BU onboarding                BU container + guardrails: AWS OU
          (rare)                       (+ account vending), Azure management
                                       group, GCP folder; BU policy rows;
                                       IdP group namespace (aiq-it-*)

Level 2   Project bootstrap            execution identities per workspace
          (occasional)                 tier, trust/delegation, registry rows

Level 3   Workspace addition           same machinery as Level 2, additive
```

**The nesting invariant**: each level's bootstrap can only create
children inside the boundary its parent row defines. BU bootstrap is
constrained by the org row; project bootstrap by the BU row (a BU
whose row caps at `apply_limited` can never mint an `apply_full`
workspace); workspace addition by the project's template. No row at
level N = nothing creatable at level N+1 — the same `POLICY`-presence
fail-closed rule intake uses, applied recursively to creation itself.
The full chain, ending where routing begins: no org row → no BU can be
created → no project can be bootstrapped → no workspace can be added →
normal provisioning cannot route.

**MVP split — git is the approval gate for the rare levels:**

```
Levels 0-1:  a human edits org_bu_policy.yaml in a PULL REQUEST.
             Review = approval gate (separation of duties, free).
             Git history = audit log (free). Merge = "this BU exists."
             Cloud-side OU/account work done by the platform team
             alongside. Automating once-per-company events is
             speculative machinery — same "no registry before a third
             workflow" discipline.
Levels 2-3:  the automated workflow below. Contract-first
             (BootstrapRequest, BootstrapPlan, WorkspaceIdentitySpec,
             ProjectRegistryEntry), then ONE provider path — AWS,
             since the repo already has AWS allow-lists and
             Terraform/CDK context.
```

## Decision 1 — Bootstrap IS provisioning, with a disjoint allow-list
Same graph mechanics as the provision workflow
(plan → deterministic checks → approval → execute → verify →
evidence), three swaps:

| | Normal provision | Bootstrap |
|---|---|---|
| Allow-list | App resources (S3, CloudFront, ...) — **identity types excluded** | Identity/scaffolding only (IAM roles/policies, Azure MI/SP/RBAC assignments, GCP SAs/bindings, HCP workspaces) — **app resources excluded** |
| Execution identity | Workspace execution role | The bootstrap identity |
| Entry | LLM-routed via intake | Never LLM-routed; explicit admin action |

The disjointness is the point: a normal deploy can never mint
privilege, and bootstrap can never become a general app deployer —
neither can do the other's job even if everything upstream fails.

**Allow-list location** (decided): a separate file next to the
existing one — `infra/bootstrap-allowed-resource-types.json`, NOT
buried inside `access_templates.yaml`. Allow-list = safety boundary;
template = desired shape. Templates are *checked against* the
allow-list, never contain it.

## Decision 2 — Never LLM-routed
Free-text intake must not reach bootstrap. Entry is an explicit admin
CLI command / admin UI form / approved change. When intake sees
"create a new project," it emits an outcome —
`unsupported: admin_bootstrap_required` — and stops. Routing a
new-blast-radius-boundary creation through a classifier would put an
LLM judgment exactly where `AGENTS.md`'s hard rules forbid one.

## Decision 3 — Registry written last, with lifecycle state
Registry presence is what makes a workspace routable, so it's written
only after `verify` confirms cloud-side reality matches the plan.
Refinement: during creation, a **non-routable row** gives admins
visibility without creating the partial-state hazard:

```yaml
# during creation (or no row at all):
state: bootstrapping
routable: false
# after verify passes:
state: active
routable: true
```

Intake/dispatch honor `routable`, never `state` prose. Execution
failing midway leaves no routable row; bootstrap retries idempotently
(Decision 4 is what makes the retry safe).

## Decision 4 — IaC, not imperative calls
The bootstrap stack is Terraform/CDK, not direct
`iam:CreateRole`/`az role assignment`/`gcloud` calls, because
bootstrap needs exactly what IaC provides: idempotent retry, a plan
digest, approval binding to that digest, drift detection, and a
reviewable diff for the highest-stakes approval in the system. The
one exception is Level -1 — creating PlatformOps's own identities is
manual/landing-zone work by definition.

## Decision 5 — Approvals: schema supports 2, bootstrap defaults high
`required_approvals: int` on the policy entry, not a hardcoded rule:

```
normal apply_limited dev     -> 1 approver
bootstrap create             -> 2 approvers (may run at 1 for MVP
                                velocity; the SCHEMA supports 2 from
                                day one)
prod changes / any teardown  -> 2 approvers
```

Bootstrap creates *future authority* — friction is justified in
proportion.

## Decision 6 — Teardown is a separate admin path
`bootstrap_create_project` and `bootstrap_decommission_project` share
machinery but are separate paths, because teardown has different
checks: no active workspaces/runs, state archived, resources destroyed
or transferred, identity deletion order, registry tombstone (not row
deletion — audit retention), evidence retention. Deliberately not
designed further yet.

## What stops bootstrap minting a super-role — per-cloud ceilings
The bootstrap identity necessarily holds create-identity permissions —
the classic escalation vector (create a role stronger than yourself,
assume it). The invariant, enforced differently per cloud: **bootstrap
can only mint identities weaker than a declared ceiling.**

| Cloud | Mechanism |
|---|---|
| AWS | **Permissions boundary** — the bootstrap identity's policy allows `iam:CreateRole`/`AttachRolePolicy` *only when the request attaches the mandatory boundary*; the boundary caps everything any created role can ever do. Escalation becomes structurally impossible. (`AGENTS.md`'s own `permissions_boundary_arn` example — "one field, added because a workflow actually needs it now" — this is the workflow that needs it.) |
| Azure | No boundary primitive exists. Constrain instead: bootstrap SP may only assign roles from an allow-list of role-definition IDs (never Owner), scoped to the target RG; Azure Policy as backstop. |
| GCP | Allow-list of grantable roles + org-policy constraints. |

Asymmetric mechanisms, one invariant — same pattern as the Azure
execution-identity asymmetry in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md).

## The Level 2 graph
```
bootstrap_create_project (admin CLI/form entry; no LLM anywhere)
  │
  ▼ validate_request     org_bu row exists + allows project creation?
  │                      names legal per convention? project absent
  │                      from registry AND cloud-side?
  │                      + verify the BU's cloud containers are
  │                      reachable (e.g. OrganizationAccountAccessRole
  │                      into a vended account) — one cheap read,
  │                      don't trust the BU row blindly
  ▼ instantiate_template access_templates.yaml + params -> concrete
  │                      spec. Deterministic substitution — nothing
  │                      to interpret, hence no LLM
  ▼ generate_plan        IaC plan: every role, trust policy, boundary,
  │                      MI/SA, RG, HCP workspace, name, tag — as
  │                      reviewable text; digest computed
  ▼ deterministic_checks bootstrap allow-list; naming convention;
  │                      every created role carries the mandatory
  │                      ceiling (boundary / role-allow-list); trust
  │                      policies name only the runtime principal
  │                      + ExternalId
  ▼ APPROVAL GATE        interrupt; required_approvals from policy
  ▼ execute              the SAME executor sub-graph normal provisioning
  │                      uses (EXECUTION_CREDENTIALS.md's Executor Node:
  │                      dispatch_by_toolchain -> acquire_credentials ->
  │                      invoke -> poll_status -> terminal_check ->
  │                      verify_created -> record_evidence) — only the
  │                      ExecutionRequest.execution_identity differs
  │                      (the BOOTSTRAP identity, not a workspace's) and
  │                      the toolchain targets the disjoint bootstrap
  │                      allow-list (Decision 1), not app resources
  ▼ verify_created       read back; compare to plan (part of the reused
  │                      sub-graph, not a separate step — shown here for
  │                      continuity with the Level 2 graph narrative)
  ▼ write_registry       LAST; state: active, routable: true
  ▼ END                  evidence: plan digest, approval digest,
                         approvals, ARNs created
```

## Registry row — canonical field set
Bootstrap's output, refining the earlier examples in
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)/
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) (which showed a
combined `target_scope` string — split here because the executor needs
account and region separately for AssumeRole and region selection, and
lifecycle fields per Decision 3):

```yaml
projects:
  invoices:
    owner: aiq:it
    workspaces:
      dev:
        provider: aws
        account_id: "123456789012"
        region: us-east-1
        execution_identity: arn:aws:iam::123456789012:role/platformops-invoices-dev-provisioner
        max_capability: apply_limited
        state: active
        routable: true
```

**Account strategy is a per-BU template choice, recorded in the BU
row**, resolving the RBAC-vs-account-boundary tiering question
deferred earlier in the intake design:

```
account_strategy: shared    # one account, tiers by role — MVP,
                            # matches the single-sandbox reality
account_strategy: per_env   # separate dev/prod accounts — the
                            # blast-radius isolation prod deserves,
                            # via Organizations account vending
```

## Open Questions
| Question | Current state |
|---|---|
| BU offboarding / teardown at every ladder level | Deferred (Decision 6) — orphaned execution identities are standing risk; needs its own design |
| Does the bootstrap workflow need its own drift-check cadence (does cloud-side still match registry)? | Open — IaC drift detection makes it cheap; when to run it is undecided |
| Who may edit `access_templates.yaml` / the bootstrap allow-list themselves? | Same PR-review gate as org/BU rows for MVP; unresolved beyond that |

## Verify before build
- AWS: exact delegated-IAM-administration pattern — `iam:CreateRole`
  conditioned on a mandatory `PermissionsBoundary`; Organizations
  `CreateAccount` + `OrganizationAccountAccessRole` behavior.
- Azure: constraining a principal to assign only allow-listed role
  definitions (mechanism + enforcement point); Azure Policy backstop
  patterns.
- GCP: grantable-roles constraints and org-policy equivalents.
- HCP Terraform: workspace/project/team creation via API and dynamic
  provider credentials setup (also flagged in
  EXECUTION_CREDENTIALS.md).

## How this relates to the existing docs
Fourth act of the access design.
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)
sketched the new-project bootstrap flow (its 5-step version stands;
this doc is that flow designed fully — ladder, decisions, ceilings,
graph). [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) defines
the identities this workflow creates and the Layer -1 manual
exception this doc inherits.
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md)'s rule that intake
never routes project creation gets its outcome name here
(`admin_bootstrap_required`). Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
