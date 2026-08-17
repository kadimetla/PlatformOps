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
| `ApprovalRequest`/`ApprovalRecord` (Payload section below) | Real, added 2026-07-31 as `gateway/approval.py` — schema only, matches this doc's fields exactly; the approval gate node that would create/persist these does not exist |
| Provision workflow the executor plugs into | Designed only (capability-shaped graph, below) |
| Approval gate (self-looping interrupt node, `approval_groups` policy, staleness rechecking) | Designed only |
| Executor sub-graph (dispatch/acquire/invoke/poll/verify/record, `ExecutionRequest`, digest binding, failure taxonomy) | Designed only |
| `CloudAccessAdapter` Protocol + AWS/Azure/GCP implementations | Designed only — recommended build order: contract + all-three fixtures first, real depth AWS-only; AWS discovery half (`resolve_principal`/`resolve_execution_grants`) now has its own deep-dive doc, see [AWS_PROVIDER_DISCOVERY.md](AWS_PROVIDER_DISCOVERY.md) (introduces `gateway/policy/capability_mappings.yaml`, a new file distinct from `access_templates.yaml`) |
| Contract-test fixtures (AWS/Azure/GCP, built from already-verified API response shapes) | Not implemented — buildable now, no live provider account needed |

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

This diagram shows one acquisition, which is accurate for
`ccapi`/`hcp_terraform`/Azure/GCP as written — but not for the local
toolchains (`opentofu_local`/`terraform_local` in
`PROVISION_WORKFLOW.md`): running either engine
locally means a plan-phase acquisition (plan-tier — non-resource-
mutating, but **not** strictly read-only: a locked plan writes state
coordination data, and with this design's `use_lockfile = true` backend
that lock is an S3 object write; corrected 2026-08-14 and generalized
to both local engines 2026-08-16, see that doc's
plan-credential section — discarded before the approval pause) and a
separate apply-phase acquisition (after resume, apply-tier), not one
acquisition at a single execution moment.
That doc's "Two credential acquisitions, not one" covers the mechanism
and why it doesn't apply to the toolchains above.

The AWS session tags matter beyond hygiene: tagging the assumed
session with `actor` means CloudTrail shows **which human's request
drove each API call**, even though that human never held any
credential — this is the audit story that makes the whole
no-user-credentials model
([ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)'s
core decision) defensible.

## CloudAccessAdapter — A Shared Contract, Build Strategy
Decided this session: validate all three providers early, go deep on
one. Not "AWS only" — that risks the shared abstraction being
accidentally AWS-shaped and only discovered wrong once Azure/GCP are
attempted later. Not "all three fully" either — that means solving
identity federation, credential acquisition, state-backend
conventions, IAM/RBAC semantics, allow-lists, env injection, and
failure modes for three clouds simultaneously, burying the actual
PlatformOps workflow under provider setup noise.

```python
class CloudAccessAdapter(Protocol):
    def resolve_principal(
        self, claims: OIDCClaims
    ) -> ProviderPrincipal: ...                          # ACCESS_POLICY_AND_IAM_DISCOVERY.md

    def resolve_execution_grants(
        self, principal: ProviderPrincipal, groups: list[str],
        registry: ProjectRegistry,
    ) -> list[ExecutionGrant]: ...                        # ACCESS_POLICY_AND_IAM_DISCOVERY.md

    def acquire_plan_credentials(
        self, identity: ExecutionIdentityRef, request: CredentialRequest,
    ) -> CredentialLease: ...                             # this doc / PROVISION_WORKFLOW.md

    def acquire_apply_credentials(
        self, identity: ExecutionIdentityRef, request: CredentialRequest,
    ) -> CredentialLease: ...                             # this doc / PROVISION_WORKFLOW.md

    def describe_current(
        self, scope: Scope, identity: ExecutionIdentityRef,
    ) -> CurrentStateSnapshot: ...                        # PROVISION_WORKFLOW.md
```
`registry: ProjectRegistry` is passed in, not loaded by the adapter
itself — dependency injection, not a hidden lookup, matching this
project's general discipline of explicit inputs over implicit global
state. `OIDCClaims`, `ProviderPrincipal`, `ProjectRegistry`,
`ExecutionIdentityRef`, `CredentialRequest`, `CredentialLease`,
`CurrentStateSnapshot` are forward-referenced type names, not yet
added to `gateway/schemas.py` — `ExecutionGrant` likewise, though it's
been used informally elsewhere in this doc set already. Concrete
Pydantic definitions are implementation work, not decided here.

Concretely, three implementations of one Protocol:
```
AwsAccessAdapter:    Identity Store / IAM Identity Center / STS AssumeRole
AzureAccessAdapter:  Entra object id / RBAC assignedTo() / managed
                     identity or SP token
GcpAccessAdapter:    principal email/groups / IAM policy scan / service
                     account impersonation
```

**One adapter per cloud provider (AWS/Azure/GCP), not per toolchain.**
The Protocol is a shared *calling convention* — method signatures — not
shared *behavior*. Every provider-specific asymmetry already designed
stays exactly as different as it needs to be inside each
implementation: AWS's `ListAccountAssignmentsForPrincipal` →
`DescribePermissionSet` two-call resolution, Azure's `assignedTo()`
requirement (not `principalId eq`, for group-transitivity), GCP's
inheritance walk (no equivalent name-resolution step, a structurally
different problem). A shared interface is not a claim that the
internals converge — stated explicitly so it doesn't get read that way
later.

**Which toolchain calls which methods differs, and that's expected —
by phase:**
```
opentofu_local:
  login:     resolve_principal, resolve_execution_grants
  plan:      acquire_plan_credentials     (discarded before approval)
  apply:     acquire_apply_credentials    (fresh after resume)
  describe:  describe_current

terraform_local:
  login:     resolve_principal, resolve_execution_grants
  plan:      acquire_plan_credentials     (discarded before approval)
  apply:     acquire_apply_credentials    (fresh after resume)
  describe:  describe_current
  -- same credential phases as opentofu_local, different sealed
     engine/version/state-owner identity; never a fallback alias

ccapi:
  login:     resolve_principal, resolve_execution_grants
  execute:   acquire_apply_credentials    (one call, no separate plan
                                          phase needing its own credential)
  describe:  describe_current

hcp_terraform:
  login:      resolve_principal, resolve_execution_grants
  execution:  NO cloud credential acquisition by PlatformOps —
             HCP's dynamic provider credentials replace that role
             entirely; the adapter's credential methods are simply
             never called for this toolchain
```
Discovery (`resolve_principal`/`resolve_execution_grants`) is
toolchain-independent — every toolchain uses it identically at login;
only the execution-time methods vary by toolchain.

### Build order: contract depth vs. execution depth, two different axes
```
VALIDATE EARLY, ACROSS ALL THREE (cheap — no live mutation, no live
Azure/GCP account needed):
  - grant normalization: permission-set/role/binding -> capability,
    per provider (already verified shapes exist to build fixtures
    from — see ACCESS_POLICY_AND_IAM_DISCOVERY.md's Sources)
  - group-derived grants: AWS group PrincipalType calls, Azure
    assignedTo() transitivity, GCP group bindings
  - registry field shape per provider (account_id/region/role_arn;
    tenant_id/subscription_id/resource_group/client_id;
    project_id/region/service_account_email)
  - credential-acquisition METHOD SIGNATURES (not live calls)
  - local IaC env-injection shape per provider (AWS_*; ARM_*;
    GOOGLE_*/impersonation config)
  - all via CONTRACT TESTS against STATIC FIXTURES built from the
    already-verified real API response shapes -- no live provider
    account required for any of the three

GO DEEP, AWS ONLY (matches PROVISION_WORKFLOW.md's Recommended Build
Order, unchanged by this):
  - real mutation (opentofu_local + AWS apply)
  - full failure handling (all three taxonomy classes, exercised for
    real)
  - the actual S3 state backend
  - end-to-end apply, verify, evidence
```

Live smoke tests come after contract tests pass, staged by risk:
AWS gets a real dev-stack apply; Azure/GCP get read-only
describe/plan-only smoke tests only — no live Azure/GCP apply until
the AWS path has proven the model out. This surfaces gaps in the
shared adapter contract early and cheaply, without turning the first
build into three parallel platform projects.

## Execution-time checks — the full pre-flight sequence
Immediately before provisioning, in order:

```
1. verify approval_digest == the digest that was actually approved
                                             (cheapest check, fails fast —
                                              catches plan/policy/identity/
                                              allow-list drift in one shot,
                                              see Digest Binding below)
2. recompute requester effective_access      (grants may have been
                                              revoked while the
                                              approval gate sat paused)
3. recompute approver authority              (same staleness risk;
                                              mechanics designed fully
                                              under The Approval Gate)
4. re-check plan against the allow-list      (deterministic, local)
5. resolve execution identity from registry
6. obtain short-lived token (Layer 2)
7. optional provider permission simulation / drift check
   (get_token_permissions on the Terraform path — verified tool;
    sts:GetCallerIdentity + policy simulation on AWS)
8. execute (the executor sub-graph, below)
9. record evidence
```

Ordering is deliberate: the free, local, deterministic check (digest
match) runs before the potentially-live ones (steps 2–3 may involve
fresh IdP/policy lookups per The Approval Gate's staleness design) —
fail fast on a cheap check before paying for an expensive one. Step 1
is what couples "human approved" to "what actually executes"; without
it, approval and execution are only loosely related. Steps 2–3 are the
resume-time re-validation: the approval `interrupt()` can sit paused
for hours or days, and "it was valid when asked" is not "it is valid
now." Fail closed on any downgrade.

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
  workflow builds a plan -> plan_digest, approval_digest, vibe_diff
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
    if len(state["approvals"]) >= state["required_approvals"]:  # static — the count
        return Command(goto="execute")                          # baked into approval_digest;
    return Command(goto="approval_gate")                # a policy change is caught once,
                                                          # authoritatively, by the digest
                                                          # check at execution pre-flight
                                                          # (Executor Node, below) — not by
                                                          # live recomputation in this loop
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
    plan_digest: str                   # identifies the plan artifact alone
    approval_digest: str               # full seven-input hash; see
                                       # PROVISION_WORKFLOW.md for current formula
                                       # — THIS is what approval actually binds
                                       # to; see Digest Binding under Executor Node
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
approval_digest, scope, capability_required
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

**Corrected — superseded by digest binding, not a live-recomputed
count.** The original rule here was
`effective_required_approvals = max(original_required_approvals, current_required_approvals)`
— letting an in-flight approval loop absorb a stricter policy by
collecting one more approval, live-recomputed each time. A simpler
mechanism covers the same case for free: extend what the approval
digest binds (see "Digest Binding" under Executor Node, below) to
include the policy snapshot, execution identity, and allow-list
version — not just the plan bytes. A `required_approvals` change is
then just one more kind of drift the *existing* digest-mismatch check
already catches:

The following is the historical four-input base used to explain this
specific policy-drift correction; it is not the current implementation
contract. The canonical seven-input form appears under "Digest Binding."

```
approval_digest = hash(plan + policy_snapshot + execution_identity
                        + allow_list_version)

policy changed (incl. required_approvals) -> approval_digest mismatch
                                              -> stop -> new plan +
                                                 new approval, full
                                                 restart, not a
                                                 top-up
```

One mechanism (digest binding) now covers plan drift, policy drift,
execution-identity drift, and allow-list drift uniformly, instead of
digest-binding handling plan drift while a separate live-recompute
rule handled policy drift. `original_required_approvals` is still
recorded for audit (what was true at plan time), but it no longer
gates anything — the digest match/mismatch does.

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

## Executor Node
Reached only after every pre-flight check above passes. This is the
only node in the whole design that can obtain a real cloud credential
and the only node allowed to mutate cloud state — and it is
deliberately **not intelligent**: it does not decide what to deploy,
whether it's safe, which identity to use, or whether approval is
sufficient. It executes a checked, approved, digest-bound plan using a
registry-resolved identity, nothing more.

Reused verbatim by [BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md)'s
Level 2 `execute` step — same sub-graph, only
`ExecutionRequest.execution_identity` differs (the bootstrap identity,
not a workspace's) and the toolchain targets the disjoint bootstrap
allow-list instead of app resources. Not two similar mechanisms; one.

It is a small sub-graph, not one node:

```
execute
  -> dispatch_by_toolchain
  -> acquire_credentials
  -> invoke
  -> poll_status
  -> terminal_check
  -> verify_created
  -> record_evidence
  -> END
```

### Input contract
The executor accepts a structured envelope only — **never raw user
text or LLM output**:

```python
class ExecutionRequest(BaseModel):
    request_id: str
    workflow_kind: str
    scope: Scope
    actor: ActorRef
    capability_required: Capability
    plan_digest: str
    approval_digest: str              # must match what was approved —
                                      # see Digest Binding below
    execution_identity: ExecutionIdentityRef
    provider: CloudProvider
    toolchain: Toolchain              # ccapi | hcp_terraform |
                                      # opentofu_local | terraform_local
                                      # -- see PROVISION_WORKFLOW.md's
                                      # "Four toolchains"
    toolchain_identity_digest: str    # seventh approval-digest input;
                                      # recomputed before execution
    local_engine_identity: LocalEngineIdentity | None
                                      # required only for a local toolchain;
                                      # must exactly match the sealed plan
    cloud_stack_publication: CloudStackPublicationRef | None
                                      # required for catalog-derived provision;
                                      # exact release/publication/snapshot
                                      # digests, never a mutable catalog row
    artifact_path: str
    approval_records: list[ApprovalRecord]
```

`CloudStackPublicationRef` is owned by
[CLOUD_STACK_CATALOG.md](CLOUD_STACK_CATALOG.md). It is required for a
catalog-derived provision execution and absent for unrelated workflow kinds;
the executor may verify its sealed digests but cannot perform catalog search,
promotion, or version selection.

### Digest Binding — one mechanism covers every bound drift input
```python
approval_digest = hash(
    plan_json,
    current_state_fingerprint,
    policy_snapshot,
    allow_list_version,
    execution_identity,
    artifact_provenance,
    toolchain_identity_digest,
)
```

Binding the approval to this broader hash, rather than the plan bytes
alone, means plan drift, policy drift (including a
`required_approvals` change — see The Approval Gate's corrected
Staleness section, above), execution-identity drift, and allow-list
drift are all caught by the *same* digest-mismatch check instead of
needing a separate live-recompute rule per kind of drift. Any mismatch
means: stop, no partial credit, a fresh plan and a fresh approval
cycle from zero.

The fifth through seventh inputs are specified by
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md). The fifth,
`current_state_fingerprint`, covers a kind of drift outside the first
four inputs — those four are
all drift in PlatformOps's *own* state; existing-stack changes (as
opposed to new-stack creation, which has nothing to drift from) can
also drift because someone else changed the live infrastructure while
approval sat paused. That doc covers the mechanism (Terraform state
serial/lineage vs. a CCAPI snapshot hash) and why it matters more for
changes to existing stacks specifically. The sixth is an
artifact-provenance input — `template_version` for a monolithic
template or `topology_digest` for a composed deployment. The latter
covers the normalized topology plus profile, unit, and template
versions. Both catch an IaC-library or composition change between plan
and apply even when the rendered `plan.json` happens to look unchanged.
The seventh is `toolchain_identity_digest`:
the canonical toolchain plus its trusted resolved adapter identity. For local
runs that includes exact engine/version/platform and dependency-lock/backend
digests, preventing cross-engine or version-drift apply. The full seven-input
formula and rationale live in that doc's "Local IaC Runners" section — not
repeated here.

### The fork that matters: CCAPI is per-resource, plan engines are per-run
Kept explicit rather than hidden behind a generic "execute tool" call,
because their failure semantics genuinely differ:

```
CDK-native path (ccapi-mcp-server)         Terraform path (terraform-mcp-server, HCP)
───────────────────────────────            ───────────────────────────────────────────
one CreateResource/UpdateResource/         one create_run(workspace, plan) call for
  DeleteResource call PER RESOURCE           the WHOLE plan
  — imperative, sequential
each call returns a request token,         one run_id; poll get_apply_details /
  poll GetResourceRequestStatus per          get_apply_logs (verified tools,
  resource until terminal                    TERRAFORM_MCP_SERVER.md) until terminal
partial failure is a REAL, common          Terraform's own state file already
  case — resource 3 of 5 fails,              handles partial application more
  1–2 already exist, must be recorded        gracefully; the run itself reports what
  exactly                                    applied vs. errored
```

### `poll_status` is not `interrupt()`
Every other pause in this design (`approval_gate`, intake's
clarification loop) is human-in-the-loop — exactly what
`interrupt()`/checkpointer exists for. Waiting on a cloud API to
finish is not that: there's no human to ask, just time passing. Using
`interrupt()` here would durably checkpoint a "waiting" state that
isn't meaningfully paused on anything.

```
approval  = human pause    -> interrupt() / checkpointer
cloud wait = time passing  -> bounded async polling / backoff, NOT interrupt()

MVP:    poll synchronously inside the node, with backoff and a hard
        timeout (e.g. 30 min) — exceeding it fails closed, not "keep
        waiting"
later:  a scheduler/timer suspends and re-invokes rather than
        blocking — real added complexity, correctly deferred until
        concurrent long-running executions actually need it
```

### Failure taxonomy — three classes, not one blanket rule
```
retryable (bounded auto-retry inside poll_status, no new approval needed):
    provider API timeout, Terraform backend lock, HCP run queue delay,
    a transient polling hiccup — nothing has meaningfully happened yet

needs_new_approval (stop; approval_digest mismatch forces a full restart):
    plan changed, policy snapshot changed, execution identity changed,
    allow-list version changed, OR a partial apply left an unknown
    created-state that the original plan no longer describes

hard_fail_closed (stop; no retry, no partial credit, escalates):
    no execution identity resolvable, token acquisition denied,
    approver/requester unauthorized, credential-shaped pattern
    detected in tool output
```

No auto-rollback (deleting what succeeded is itself an unreviewed
destructive action) and no blind retry after a partial mutation, ever
— a new plan must be built against the real current state, not assumed
against the intended one.

### After a failure: read-only re-describe, automatically
```
failure -> describe_current (read-only, no mutation, no retry)
        -> attach observed_state_summary to the ExecutionRecord
```
Automatic because it's read-only and directly useful (the human
deciding what to do next shouldn't have to separately ask "what
actually exists now"); never mutating, never retrying, never
rollback-triggering on its own.

### Credential handling — a concrete implication for existing code
Tokens exist only in: executor process memory, the child process
environment, the provider SDK/client. Never in: LangGraph state,
checkpoint, approval payload, logs, registry, or the plan artifact.

`acquire_credentials` constructs the MCP server's environment **fresh,
per request** — this is a real, concrete change from what's on disk
today: `mcp_server/external_servers.py` currently launches
`ccapi-mcp-server`/`terraform-mcp-server` with a **static** env
(`AWS_PROFILE` read once from `os.environ` at import time). The
executor design requires `StdioServerParameters(env={...})` to be
built dynamically at execution time instead, populated with the
JIT-acquired temporary credentials
(`AccessKeyId`/`SecretAccessKey`/`SessionToken`/`AWS_REGION` for AWS;
`ARM_CLIENT_ID`/`ARM_TENANT_ID`/`ARM_SUBSCRIPTION_ID` plus the
selected managed identity for Azure — exact current env-var
conventions flagged under Verify before build) — a small, real change
to a real file, not a redesign.

### Evidence — `ExecutionRecord`, persisted independently of checkpoint state
Same rule as `ApprovalRecord`: the checkpointer is for resume
mechanics, not the audit database.

```
request_id, approval_id(s), approval_digest, provider, toolchain,
toolchain_identity_digest, local_engine_identity (for local runs),
cloud_stack_publication_id, cloud_stack_publication_target,
cloud_stack_id, cloud_stack_release_version, cloud_stack_content_digest,
cloud_stack_publication_digest, cloud_stack_registry_snapshot_digest,
execution_identity, credential_expiry, started_at, ended_at, status,
resource_ids_touched (ARNs/IDs actually created/updated/deleted —
  matters for audit, reconciliation, and future teardown),
partial_success list, failure_class, log_summary, observed_state_summary
  (if a failure triggered describe_current, above)
```

Raw logs are summarized and scrubbed — for credential-shaped
patterns specifically, not just generically redacted — before
anything is persisted. **Streaming raw logs to a live viewer is
explicitly skipped for MVP**: it's a real leak surface (secrets or
overly specific resource detail echoed mid-stream) for a feature that
isn't required — status updates plus a scrubbed summary are the safer
default; live redacted streaming is a later feature, not designed
further here.

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
  id, plan digest, approval digest. Never the token.

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
fields; the example above predates that refinement. Further extended
by [INQUIRY_WORKFLOW.md](INQUIRY_WORKFLOW.md): a single
`execution_identity` per workspace is the simplest case — a workspace
whose only reachable tier is its ceiling; workspaces with multiple
inspectable tiers need a tier-keyed `execution_identities` map instead,
since inquiry always requires a read-only identity distinct from the
mutation-capable one.) Prod restraint is enforced in the identity
itself: `invoices-prod-reader` *lacks* mutation permissions —
"technically impossible," not "told not to."

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
- Terraform/CDK provider env-var conventions: exact current names
  (`AWS_ACCESS_KEY_ID` family; `ARM_CLIENT_ID`/`ARM_TENANT_ID`/
  `ARM_SUBSCRIPTION_ID`/`ARM_USE_MSI` vs. newer OIDC-based Azure
  provider auth conventions, which have changed across provider
  versions) before wiring `acquire_credentials`.
- CCAPI: exact `CreateResource`/`UpdateResource`/`DeleteResource`/
  `GetResourceRequestStatus` tool names and schemas as exposed by
  `ccapi-mcp-server` — not yet freshly verified in this session's work
  (unlike the Terraform MCP server, verified in
  `TERRAFORM_MCP_SERVER.md`).

## How this relates to the existing docs
Third act of the access design:
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md)
resolves WHO (login-time discovery, capability grants, the registry);
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) resolves WHERE/WHAT
(routing, `effective_access` at request time); this doc is the only
place cloud credentials actually appear, and only ever short-lived,
after approval. `CloudAccessAdapter` unifies both docs' provider-facing
methods into one Protocol, defined here since this doc already covers
Layer 0–2 generically across providers/toolchains — its
`resolve_principal`/`resolve_execution_grants` methods are
`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s territory implemented, its
`acquire_*_credentials`/`describe_current` methods are
`PROVISION_WORKFLOW.md`'s. Reuses
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s verified tool
inventory (`create_run`, `action_run`, `get_token_permissions`).
Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
