## Status
Designed only. No executor, workflow, or auth code exists on this
branch. Third act of the access design:
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)
covers login-time discovery (WHO),
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) covers request-time
routing (WHERE/WHAT) — this doc covers execution time: how the
approved action actually obtains a cloud credential and runs.
Mechanisms here are standard, stable provider primitives
(`sts:AssumeRole`, GCP service-account impersonation, Azure
managed-identity tokens, HCP Terraform runs) stated from general
knowledge, **not** freshly web-verified this session — the specific
items that must be verified against current provider docs before any
implementation are listed in "Verify before build" below, per
`AGENTS.md`'s hard rule. The HCP Terraform tool names cited are the
exception: already verified in
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md).

## Real vs. Designed
| Area | Status |
|---|---|
| Executor / credential acquisition code | Not implemented |
| Runtime root identity (Layer 0) | Not implemented — no deployment exists to hold one |
| Per-workspace execution identities (Layer 1) | Not implemented — created by the bootstrap path (see ACCESS_POLICY_AND_IAM_DISCOVERY.md) |
| Registry (`gateway/policy/project_registry.yaml`) | Designed only, shared with ACCESS_POLICY_AND_IAM_DISCOVERY.md |
| Provision workflow the executor plugs into | Designed only (capability-shaped graph, below) |

## Core principle
It is not enough that the *user* has access. The PlatformOps backend
itself must be independently allowed to obtain a temporary credential
for the target workspace — user entitlement (discovery doc) and
runtime delegation (this doc) are two separate trust relationships,
and both must exist. Per provider/workspace, seven things must be true
before a single operation can run:

```
1. a PlatformOps runtime identity            (Layer 0)
2. a target execution identity               (Layer 1, bootstrap output)
3. a trust/delegation relationship between them
4. minimal permissions on the target scope
5. a registry entry mapping workspace -> execution identity
6. runtime code that requests the token just-in-time
7. an audit record: who asked, what was approved, which identity ran
```

## Layer 0 — the runtime's own root identity
The chicken-and-egg: to obtain any short-lived token, the runtime must
already *be* someone. This is the only credential that cannot be
fetched; three options, best first:

```
best:      ambient cloud identity — EC2/EKS instance role, Azure
           managed identity, GCP attached service account. No stored
           secret exists anywhere.
portable:  OIDC workload identity federation — the runtime presents
           its own OIDC token; each cloud is configured to trust it
           (AWS IAM OIDC provider + role, Azure federated credential
           on the app registration, GCP workload identity pool).
           Secretless from anywhere, but per-cloud setup work.
fallback:  long-lived secret in a secrets manager. Weakest — reserve
           for what cannot federate (realistically: the HCP Terraform
           team token).
```

## Layer 1 — pre-provisioned per workspace tier
One-time bootstrap-path output
([ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
new-project flow, step 4):

| | AWS | Azure | GCP | HCP Terraform |
|---|---|---|---|---|
| Target identity | IAM role per workspace tier | User-assigned managed identity / service principal **per workspace tier** (see asymmetry below) | Service account per workspace tier | Workspace + team permissions |
| Its permissions | Permissions policy: allow-listed actions, tag/region conditions | Role assignment at resource-group/subscription scope | Limited IAM roles on the target project | Workspace settings; `ENABLE_TF_OPERATIONS` on the executor path only |
| Delegation to runtime | Trust policy naming the runtime principal + `sts:TagSession` (required for session tags) + ExternalId condition | Runtime allowed to acquire tokens *as* that MI/SP | `roles/iam.serviceAccountTokenCreator` granted to the runtime **on that specific service account only** — per-SA scoping *is* the narrowing mechanism; a project-wide TokenCreator grant would collapse it | Team token scoped to the project/workspaces |
| Cloud-side extras | — | — | — | **Dynamic provider credentials**: the workspace federates into the cloud itself; PlatformOps never holds cloud tokens on this path — it creates a run (`create_run`/`action_run`, verified in TERRAFORM_MCP_SERVER.md) and monitors it |

### The Azure asymmetry — real, not a detail
AWS and GCP have true just-in-time *identity switching*: the runtime
holds one identity and assumes/impersonates a narrower per-workspace
one (`sts:AssumeRole`, `generateAccessToken`). Azure does not — a
token acquired by an identity *is* that identity's token, and Azure
Resource Manager evaluates that identity's RBAC at request time. If
one app registration held role assignments on every workspace, every
token it acquires could touch all of them: no per-request narrowing,
which silently breaks the narrow-execution-identity principle on
Azure only. Restoring parity requires one user-assigned managed
identity (or service principal) per workspace tier, with the runtime
selecting which identity to acquire a token *as* — accepted identity
sprawl, named here so nobody later "simplifies" it back into one
broad identity.

## Layer 2 — just-in-time acquisition, per approved action
```
resolve execution_identity from registry        (local data, no call)
  AWS:   sts:AssumeRole(
             RoleArn=<from registry>,
             RoleSessionName="platformops-<request-id>",
             Tags={actor, project, workspace})
         -> AccessKeyId/SecretAccessKey/SessionToken + Expiration
  Azure: acquire ARM token AS the workspace's MI/SP
         (RBAC evaluated by ARM at request time, not baked into token)
  GCP:   generateAccessToken on the workspace service account
         -> short-lived OAuth access token
  HCP:   create run; workspace's dynamic provider credentials handle
         the cloud side; PlatformOps monitors the run
inject into the Terraform/CDK/CCAPI process environment
  -- NEVER into graph state (see below)
```

The AWS session tags matter beyond hygiene: tagging the assumed
session with `actor` means CloudTrail shows **which human's request
drove each API call**, even though that human never held any
credential — this is the audit story that makes the whole
no-user-credentials model
([ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
core decision) defensible.

## Execution-time checks — the full pre-flight sequence
Immediately before provisioning, in order:

```
1. recompute requester effective_access      (grants may have been
                                              revoked while the
                                              approval gate sat paused)
2. recompute approver authority              (same staleness risk;
                                              approver model itself
                                              still open — below)
3. re-check plan against the allow-list      (deterministic, local)
4. verify plan digest == approved digest     (approval binds to exact
                                              bytes; regenerated plan
                                              after approval = start over)
5. resolve execution identity from registry
6. obtain short-lived token (Layer 2)
7. optional provider permission simulation / drift check
   (get_token_permissions on the Terraform path — verified tool;
    sts:GetCallerIdentity + policy simulation on AWS)
8. execute
9. record evidence
```

Steps 1–2 are the resume-time re-validation: the approval
`interrupt()` can sit paused for hours or days, and "it was valid when
asked" is not "it is valid now." Fail closed on any downgrade. Step 4
is what couples "human approved" to "what actually executes" — without
the digest check they are only loosely related.

## Nothing secret in graph state — a LangGraph-specific rule with teeth
The approval gate uses `interrupt()` + a checkpointer, and **the
checkpointer persists all graph state durably**. A temporary
credential placed in state is a credential written to the checkpoint
store, surviving the run. Therefore:

- Tokens live only in the executor's process memory — closed over by
  the execute node's constructor, never a state key.
- Graph state and logs carry **evidence only**: execution identity
  used, token expiration, cloud account/project/subscription, request
  id, approval id, plan digest. Never the token.

This also weighs on the capability-shaped provision graph (explored
2026-07-28, not yet captured in a doc): the same closure-over-state
argument applies to `effective_access` — routers comparing against a
compile-time-bound closure can't be influenced by any node, LLM-driven
or otherwise. Both open questions from that exploration remain open
(listed below).

## Registry shape (shared with the access doc)
```yaml
projects:
  invoices:
    workspaces:
      dev:
        provider: aws
        target_scope: "123456789012/us-east-1"
        execution_identity: "arn:aws:iam::123456789012:role/platformops-invoices-dev-provisioner"
        max_capability: apply_limited
      prod:
        provider: aws
        target_scope: "123456789012/us-east-1"
        execution_identity: "arn:aws:iam::123456789012:role/platformops-invoices-prod-reader"
        max_capability: describe
```
Same file as
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
`gateway/policy/project_registry.yaml` — one registry, read by both
the policy layer (ceilings) and the executor (identities). Prod
restraint is enforced in the identity itself: `invoices-prod-reader`
*lacks* mutation permissions — "technically impossible," not "told
not to."

## Open Questions
| Question | Current state |
|---|---|
| Approver authority model — does approving `invoices/prod` require the approver to hold capability on that workspace? Can a requester self-approve? | Open. The capability ladder describes *doers*, not *approvers*; separation-of-duties (approver ≠ requester, approver has standing on the target scope) is the expected answer but nothing expresses it yet. |
| Capability-shaped graph: conditional edges reading state (Option A) vs. builder wiring only reachable nodes (Option B) vs. capability closed over in router functions (middle path, current lean)? | Open — deliberately undecided until the provision workflow is actually built. |
| Token TTL policy — long enough for the longest expected apply, short enough to be worthless if leaked? | Undecided; provider defaults (e.g. 1h) as the starting point. |

## Verify before build
Stable mechanisms, but exact shapes not freshly verified this session
— check current provider docs before implementation:

- AWS: exact trust-policy shape for `sts:TagSession` + session tags +
  ExternalId conditions; session-tag propagation to CloudTrail.
- Azure: whether one compute instance can hold and select among many
  user-assigned managed identities at token-request time (the
  asymmetry mitigation depends on it).
- GCP: `generateAccessToken` lifetime limits and constraints.
- HCP Terraform: dynamic provider credentials setup specifics per
  cloud.

## How this relates to the existing docs
Third act of the access design:
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)
resolves WHO (login-time discovery, capability grants, the registry);
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) resolves WHERE/WHAT
(routing, `effective_access` at request time); this doc is the only
place cloud credentials actually appear, and only ever short-lived,
after approval. Reuses
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s verified tool
inventory (`create_run`, `action_run`, `get_token_permissions`).
Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
