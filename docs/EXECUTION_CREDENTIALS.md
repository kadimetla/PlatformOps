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
| Approval gate (self-looping interrupt node, `approval_groups` policy, staleness rechecking) | Designed only |

## Identity timeline — which identity is active at each phase
The whole access design in one table. Alice proves identity to
PlatformOps; PlatformOps proves authority to the cloud; the cloud's
audit trail links the action back to Alice through session
tags/evidence. She never logs into a cloud provider through
PlatformOps, and the cloud never sees her as a caller.

| Phase | Active identity | Cloud credential exists? |
|---|---|---|
| Bootstrap | admin/bootstrap identity | Yes — the one privileged setup moment |
| Login | user identity (to IdP) + discovery identity (to clouds, read-only) | Read-only introspection only |
| Request/intake | user session grants only | No — purely local |
| Planning | workflow auth context | No mutation credential |
| Approval | approver identity | No |
| Execution | runtime identity → workspace execution identity → short-lived token | Yes — the only mutation-capable moment, expiring |
| Audit | — | Cloud shows the execution identity + human/session tags |

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

### Delegation is standing; only the token request is ad hoc
Two independent things attach to every execution identity, and both
must exist (they are the table's Permissions and Delegation columns,
stated as a rule):

```
permissions policy  = what the execution identity CAN DO
delegation/trust    = who may USE the execution identity

identity without delegation        -> PlatformOps cannot use it
delegation without narrow perms    -> usable but useless
broad permissions + broad delegation -> the dangerous case bootstrap
                                        exists to prevent
```

Nothing about *who may use which identity* is decided at execution
time. Bootstrap configures the delegation once (trust policy /
TokenCreator grant / identity-use assignment); execution time merely
exercises it — `sts:AssumeRole` / `generateAccessToken` / a token
request that the provider grants *only because the standing
configuration already allows it*, and that fails outright if bootstrap
never ran. That failure is the cloud-side enforcement of "bootstrap
must precede provisioning."

### AWS is cross-account by design
The runtime identity lives in PlatformOps's own account; workspace
execution roles live in each target workload account:

```
arn:aws:iam::999999999999:role/platformops-runtime          (PlatformOps account)
  -> sts:AssumeRole ->
arn:aws:iam::123456789012:role/platformops-invoices-dev-provisioner   (workload account)
```

The workload role's trust policy names the runtime principal and
should carry ExternalId and session-tag conditions — the cross-account
boundary is exactly where the ExternalId condition earns its keep
(confused-deputy protection). The Layer 1 table implies this shape;
stated explicitly here so the trust-policy design assumes two accounts,
not one.

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
             Tags={actor, project, workspace, request_id})
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
the digest check they are only loosely related. Step 2's mechanics —
what approver authority even is, and how it's rechecked — are designed
fully below.

## The Approval Gate
Two distinct time scopes, easy to conflate: **setup time** defines who
may approve what; **request time** is one specific paused workflow run
asking one specific question. Bootstrap never blocks on an approval
gate itself — it configures the rules a later gate enforces.

```
SETUP TIME (org/BU bootstrap; see BOOTSTRAP_WORKFLOW.md)
  admin writes an approval_groups policy row, e.g.:
    aiq-it-prod-approvers:
      org_bu: aiq:it
      workspaces: ["prod"]
      max_capability: apply_limited
  IdP has a matching group; people are added to it by normal company
  access management — no cloud provider token involved, this is pure
  PlatformOps governance config

REQUEST TIME (one workflow run)
  intake resolves effective_access, approval_required=true
  workflow builds a plan -> plan_digest, vibe_diff
  graph reaches approval_gate -> pauses, emits a payload
  an approver resumes it -> graph revalidates -> records -> continues
  or waits for another approver, per required_approvals
```

### Authority is PlatformOps-native, not cloud-grounded
Decided: approval authority is `actor.approval_grants`, resolved at
login from PlatformOps's own `approval_groups` policy keyed by IdP
group name — **not** discovered from any cloud provider's IAM (see
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
"Two Grant Sets"). Approving a change is a governance act, not a
provider API capability: a prod approver needs standing PlatformOps
approval authority on that scope, not AWS prod write access — often
exactly the opposite of what they hold.

### The graph: a self-looping interrupt node
`required_approvals` means the gate collects approvals rather than
pausing once:

```python
def approval_gate(state) -> Command:
    decision: ApprovalDecision = interrupt(build_payload(state))

    if decision.approver_id == state["requester"].user_id:
        return Command(goto="approval_gate")          # self-approval: reject, ask again
    if decision.approver_id in {a.approver_id for a in state["approvals"]}:
        return Command(goto="approval_gate")          # same approver can't count twice
    if not approver_currently_authorized(               # LIVE recheck — see Staleness below
            decision.approver_id, state["scope"], state["capability_required"]):
        return Command(goto="approval_gate")           # unauthorized: reject, ask again
    if decision.verdict == "reject":
        return Command(goto="rejected_end")            # any rejection hard-stops (MVP choice)

    record_approval_evidence(state, decision)           # persistent store, NOT just state — below
    state["approvals"].append(evidence_only(decision))
    if len(state["approvals"]) >= effective_required_approvals(state):  # see Staleness below
        return Command(goto="execute")
    return Command(goto="approval_gate")                # wait for the next approver
```

Each loop re-emits a fresh payload showing progress ("1 of 2
approvals collected") — visible audit trail as the run proceeds.
**Rejection is a deliberate MVP simplification**: any single rejection
hard-stops immediately rather than waiting to see if remaining
approvers could still reach quorum — simpler, auditable, matches this
project's fail-closed instinct. A vote-policy alternative (reject just
decrements the pool) is a later option, not designed now.

### Payload
```python
class ApprovalRequest(BaseModel):
    request_id: str
    scope: Scope                       # org_bu/project/workspace
    intent: str
    capability_required: Capability    # e.g. apply_limited
    plan_digest: str
    vibe_diff: str                     # human-readable plan summary — reused
                                       # from design/harness-architecture's
                                       # PlanRecord.vibe_diff precedent, not
                                       # invented here; raw HCL/CFN isn't the
                                       # review surface, only linked by digest
    requester: ActorRef
    approvals_so_far: list[ApprovalRecord]
    required_approvals: int
    approval_expires_at: datetime | None = None   # nullable now; MVP leaves
                                                   # unset (plan-digest
                                                   # freshness does most of the
                                                   # work); prod/bootstrap can
                                                   # set a TTL later with no
                                                   # schema change
```

### Approval records are persisted independently of graph state
The checkpointer is for *resume mechanics*, not the audit database.
Relying on it as the only store means graph storage becomes your audit
database by accident. Each recorded approval also writes a durable
`ApprovalRecord` (evidence only, same no-credentials rule as
everywhere else in this doc):

```
request_id, approver_id, verdict, timestamp, plan_digest,
scope, capability_required
```

### Staleness — approval permission changes mid-flight
Approval authority can change two ways while a request sits paused:
an IdP group membership change, or a PlatformOps `approval_groups`
policy change (different required count, different group name). A
session's cached `approval_grants` may be stale until next
login/refresh — normal for session systems, but **not acceptable to
trust blindly at the single highest-stakes moment in the whole
design**. The rule: authority is rechecked live at resume time, not
carried forward from when the request was created.

```
Monday:    Alice requests prod deploy. Bob has approval authority.
           Workflow pauses.
Tuesday:   Bob is removed from aiq-it-prod-approvers.
Wednesday: Bob clicks approve. Gate reloads Bob's CURRENT authority
           (fresh, not session-cached) -> no longer authorized ->
           approval rejected -> graph keeps waiting for a valid
           approver.
```

A required-approvals *count* change while paused needs its own
fail-closed rule, since "what was required when the plan was created"
and "what's required now" can differ:

```
effective_required_approvals = max(original_required_approvals,
                                    current_required_approvals)

policy became stricter  -> the stricter (current) count applies,
                           even retroactively to an in-flight request
policy became looser    -> keep the ORIGINAL stricter count; a
                           relaxation never retroactively un-strictens
                           an already-paused request
policy removed access   -> reject / fail closed, full stop
```

Both `original_required_approvals` (kept for audit — what was true at
plan time) and the live-recomputed current value are stored; the
`max()` is what actually gates progression.

```python
def approver_currently_authorized(approver_id, scope, capability) -> bool:
    policy = load_policy()                    # fresh read, not session cache
    approver = load_actor(approver_id)         # fresh read, not session cache
    grants = resolve_approval_grants(actor=approver, policy=policy)
    return can_approve(grants, scope, capability)
```

**Tiered by stakes, not uniform**: for MVP, ordinary approvals may ride
the same session-refresh cadence execution grants already use
(`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s "mid-session revocation takes
effect at next login/refresh"). Prod and bootstrap approvals — the
`required_approvals: 2` tier — deserve the fully live reload sketched
above; the cost of one extra fresh lookup is trivial next to the blast
radius it's checking.

## Nothing secret in graph state — a LangGraph-specific rule with teeth
The approval gate uses `interrupt()` + a checkpointer, and **the
checkpointer persists all graph state durably**. A temporary
credential placed in state is a credential written to the checkpoint
store, surviving the run. Therefore:

- Tokens live only in the executor's process memory — closed over by
  the execute node's constructor, never a state key.
- Short-lived credentials never appear in: the intake result, LangGraph
  state, logs, approval records, or any persistent DB. Approval records
  deserve the explicit mention — they're durable and human-reviewed.
- All of those carry **evidence only**: execution identity used, token
  expiration, cloud account/project/subscription, request id, approval
  id, plan digest. Never the token.

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
the policy layer (ceilings) and the executor (identities). (Corrected
by [BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md): the canonical row
splits `target_scope` into separate `account_id`/`region` fields — the
executor needs them separately — and adds `state`/`routable` lifecycle
fields; the example above predates that refinement.) Prod
restraint is enforced in the identity itself: `invoices-prod-reader`
*lacks* mutation permissions — "technically impossible," not "told
not to."

## Open Questions
| Question | Current state |
|---|---|
| Approver authority model | **Resolved** — see "The Approval Gate" above: PlatformOps-native `approval_grants`, separate from execution grants; self-approval and duplicate-approval both blocked in the graph node. |
| Capability-shaped graph: conditional edges reading state (Option A) vs. builder wiring only reachable nodes (Option B) vs. capability closed over in router functions (middle path, current lean)? | Open — deliberately undecided until the provision workflow is actually built. |
| Token TTL policy — long enough for the longest expected apply, short enough to be worthless if leaked? | Undecided; provider defaults (e.g. 1h) as the starting point. |
| `approval_groups` policy file location — own file next to `org_bu_policy.yaml`, or a section within it? | Undecided; leaning own file, same allow-list-vs-template separation reasoning as `BOOTSTRAP_WORKFLOW.md`'s allow-list decision, not yet settled. |

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
