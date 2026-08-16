## Status
Designed only. No provision workflow, diff builder, or auth code
exists on this branch. Covers what's specific to the `provision`
intent's planning logic — diffing, drift, action-level policy, IaC
generation, and toolchain selection —
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) still owns the
general credential-acquisition mechanics (Layers 0/1/2, the approval
gate, the executor sub-graph); this doc's "OpenTofu Local Runner"
section is the one exception, since that toolchain's two-phase
credential acquisition is inseparable from its planning mechanics.
CCAPI's lack of a native plan/dry-run primitive is stated as
believed-true, not verified this session. OpenTofu-specific claims
(S3 backend `use_lockfile`, saved-plan `apply` behavior) verified
against current docs 2026-07-30 — see Sources/Verify before build.

## Real vs. Designed
| Area | Status |
|---|---|
| Provision workflow (any node) | Not implemented |
| CCAPI diff builder (`current_state + desired_spec -> ordered operations`) | Not implemented — identified this session as non-trivial, separate work |
| `current_state_fingerprint` in `approval_digest` | Designed only — extends `EXECUTION_CREDENTIALS.md`'s formula, corrected there in place |
| Action-verb allow-list (`infra/allowed-resource-types.json`'s eventual successor) | Designed only — current real file is resource-type-only, no action-verb distinction |
| Terraform `get_plan_json_output` | Real tool, verified in `TERRAFORM_MCP_SERVER.md` — the diff engine CCAPI lacks |
| Template library (`skills/provision-infra/templates/`) | Not implemented — directory doesn't exist |
| `skills/provision-infra/SKILL.md`'s Path A step 1 ("draft the CDK app") | Real, current, and now contradicted by this doc's template-first design — flagged, not yet updated |
| `skills/provision-infra/SKILL.md`'s Path C (`opentofu_local`) | Not implemented — the file only has Paths A/B today; this toolchain has no skill entry yet |
| `opentofu_local` runner (state backend, runner directory, two-phase credential acquisition) | Designed only, verified against current OpenTofu docs 2026-07-30 |
| IaC artifact provenance in `approval_digest` | Designed only — sixth input is `template_version` for a monolithic template or `topology_digest` for a composed deployment |
| `migrate_workspace_to_opentofu` admin workflow | Designed only |
| Registry `iac_engine`/`state_owner`/`previous_state_owner`/`migrated_at` fields | Designed only — third incremental registry extension |
| Backend-config-must-never-carry-credentials rule | Verified verbatim against current OpenTofu docs 2026-07-31; not previously violated but not previously stated as a rule either |

## Same Access Flow for New and Existing Stacks
No separate grant model needed for "create a new stack" vs. "update an
existing one" — both are `provision` intent, both hit the identical
path:

```
intake -> intent = provision -> resolve project/workspace ->
effective_access -> provision workflow -> plan -> checks -> approval
-> executor
```

The workflow itself decides which case it's in by reading current
state — not a different mechanism, a different *input* to the same
one:

```
NEW STACK                            EXISTING STACK
describe_current -> empty/not found  describe_current -> real current resources
build_plan -> creates all desired    build_plan -> diff: create/update/delete
resources
approval_digest -> binds create      approval_digest -> binds diff + current
plan + policy snapshot                 state fingerprint + policy snapshot
executor -> apply creates            executor -> apply diff
```

## IaC Generation: Template-First, Never Free-Form
A gap this design hadn't addressed: `build_plan` needs actual IaC
content to diff and apply, and nothing so far said where that content
comes from. **This corrects real, current repo content** —
`skills/provision-infra/SKILL.md`'s Path A step 1 currently reads
"Draft the CDK app / CloudFormation template for the requested
resources" — free-form generation, no template library. That skill
predates the LangGraph stack decision and needs updating when
`workflows/provision/` is actually built; not fixed here, flagged for
that point.

Three levels, only the first two exist at request time:

```
Level 1: Template rendering       -- MVP default, deterministic, every
                                     real request uses this
Level 2: Coder-assisted template  -- authoring time only, produces a
         authoring                  PR against the template library,
                                     reviewed like any code change --
                                     NOT a runtime pipeline artifact
Level 3: Executor                 -- runs an approved plan built from
                                     an ALREADY-MERGED, human-reviewed
                                     template; never runs freshly
                                     generated, unreviewed IaC
```

Proven precedent already in this project's own history, not a new
pattern: `design/harness-architecture`'s `check_structured_match()` →
`run_deterministic_skill_fill()` is the same deterministic-template
mechanism, already real and built there.

### Level 2 produces a template-library PR, not a capped runtime artifact
The stronger invariant, worth being precise about: when no template
matches, the workflow does **not** generate IaC and route it through
`build_plan`/`approval_gate` at a lower capability — it stops, and a
coder-assisted proposal creates a PR against
`skills/provision-infra/templates/<type>/` instead. That PR gets
normal software code review (a human reads the generated HCL/CDK line
by line, same as any PR) — categorically more scrutiny than
`approval_gate`'s review of a `vibe_diff` summary, which is the right
depth for a plan built from an *already-vetted* template but not
enough for code nobody has reviewed yet. Only after merge does the
template become Level-1-renderable. **The executor never runs freshly
generated, unreviewed IaC — not "capped," never.**

**Modified 2026-08-16, not silently**: the hard stop above gains a
designed (not enabled) alternative ending.
`COMPOSABLE_PROVISIONER.md`'s "Resource-primitive authoring" level lets
a coding agent assemble raw provider resources at runtime when no
reviewed module matches — under strictly more validation (exact
per-resource config schemas, per-provider resource allow-lists, a
bounded `tofu validate` repair loop, then the unchanged
plan/policy/approval chain). The executor invariant itself is intact:
the LLM emits typed resource data only; HCL still comes exclusively
from reviewed renderer functions in a trusted registry. What changes is
solely that "no match" may compose primitives instead of terminating —
an explicit authority expansion with its own acceptance gate (Slice 14),
disabled by policy until accepted.

The coder role in Level 2 inherits every constraint already designed
for anything outside the executor: no credentials, no execution
authority, no choice of execution role, no allow-list bypass — it
produces template files, nothing else, matching the existing
executor/credential isolation exactly (`EXECUTION_CREDENTIALS.md`:
"the executor is not intelligent... does not decide what to deploy").

### Where template matching sits: before any cloud read, not after
Ordering matters for the same fail-fast reason the digest check runs
before the live-recompute checks: template match happens immediately
after `extract_desired_spec`, **before** `describe_current` even runs.
A missing template means stopping before spending a single cloud read,
not partway through planning.

```
extract_desired_spec   -> a typed request model, NOT IaC yet
                          (missing required fields -> clarify HERE,
                          not at intake -- this is exactly the
                          workflow-specific Stage 2 structure
                          extraction INTAKE_HITL_ROUTING.md's C2
                          correction deferred out of intake and into
                          "each target workflow")
match_template          -> no match -> stop, open a Level 2 PR, END
                          -> match -> continue
render_iac               -> fill the matched template with validated
                          parameters, write to a request-scoped
                          artifact directory:
                            provision_artifacts/<request_id>/
                              main.tf / variables.tf /
                              terraform.tfvars.json / outputs.tf
                          (this IS what ExecutionRequest.artifact_path,
                          already in EXECUTION_CREDENTIALS.md's
                          envelope, points to -- not previously defined)
describe_current        -> as designed above (empty for new, real
                          state for existing)
build_plan               -> diff, as designed above
```

### Three toolchains, three credential footprints
`Toolchain` has three values, not two — `ccapi` | `hcp_terraform` |
`opentofu_local`. `hcp_terraform` and `opentofu_local` are genuinely
different systems, not the same Terraform-language stack running in
two places: `hcp_terraform` is HashiCorp's own managed platform
running HashiCorp Terraform; `opentofu_local` runs the OpenTofu
binary — the open-source fork — directly, as a PlatformOps-owned
process. Decided this session: both exist as toolchain options,
selected per project/workspace in the registry, not one replacing the
other.

```
NOT THIS (CCAPI's model, wrong for hcp_terraform):
  PlatformOps runtime -> sts:AssumeRole(workspace execution role)
    -> temporary AWS credentials -> inject into local `terraform`
    process env -> `terraform apply`

hcp_terraform (the real, already-decided model for that toolchain):
  PlatformOps acquires only an HCP Terraform API/team token (not an
  AWS credential) -> create_run(workspace_id, plan) [verified tool,
  TERRAFORM_MCP_SERVER.md] -> poll get_plan_details/
  get_plan_json_output -> action_run(apply) [verified tool] -> poll
  get_apply_details/get_apply_logs until terminal
  -- AWS credentials for the actual apply come from HCP's own dynamic
  provider credentials, configured once at Layer 1 bootstrap time.
  PlatformOps's process never holds an AWS credential for this
  toolchain at all.

opentofu_local (a genuinely different footprint — see below):
  PlatformOps runs `tofu` itself, taking on four things HCP would
  otherwise handle: cloud credentials, state backend + locking,
  runner isolation, execution audit. This DOES need PlatformOps to
  hold real cloud credentials, same shape as CCAPI's — but at TWO
  separate points, not one (see "Two Credential Acquisitions" below).

ccapi:
  unchanged — PlatformOps holds a real cloud credential directly,
  same as opentofu_local's shape, one acquisition at execution time.
```

Both `hcp_terraform` and `opentofu_local` still follow the same rule —
nothing acquired until after approval, nothing in graph state — just
via different concrete tokens and, for `opentofu_local`, a different
*number* of acquisitions.

## OpenTofu Local Runner (Third Toolchain)
Chosen as the recommended MVP build order for AWS specifically (see
"Recommended Build Order," below) — real technical claims below
verified against current OpenTofu docs (2026-07-30).

### Runner boundary — one isolated directory per request
Never run from the repo root; the directory is disposable, one per
request, and doubles as `ExecutionRequest.artifact_path` (in the
schema since `EXECUTION_CREDENTIALS.md`, defined by the render step
already designed above):

```
provision_artifacts/<request_id>/
  main.tf / variables.tf / outputs.tf   -- from template rendering
  backend.tf                            -- opentofu_local only
  terraform.tfvars.json
  plan.bin / plan.json                  -- opentofu_local only,
                                        -- populated by build_plan
```
CCAPI and `hcp_terraform` populate the same directory's IaC files but
never `backend.tf`/`plan.bin`/`plan.json` — CCAPI has no state file of
its own, and `hcp_terraform`'s plan artifacts live in HCP, not on
PlatformOps's disk.

### State backend — remote, locked, never local
Local state is not acceptable for real provisioning. S3 backend with
native S3 locking, verified current syntax (OpenTofu 1.12.x+ — pin
this version constraint, `use_lockfile` is a newer feature, not
universally available on older releases):

```hcl
terraform {
  backend "s3" {
    bucket       = "platformops-tofu-state"
    key          = "aiq/it/invoices/dev/tofu.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
```
The `key` is built directly from `Scope` — `org:bu/project/workspace`
— giving state isolation the exact same shape as everything else in
this design; a stack's state path is derivable from its scope, not a
separate naming decision. DynamoDB-table locking remains a fully
supported alternative (`dynamodb_table`), not deprecated — a
per-workspace choice, not designed further here. Bucket versioning is
recommended (OpenTofu's own docs: state recovery from accidental
deletion) — an `infra`-level bootstrap concern, not per-request.

### Two credential acquisitions, not one — a real consequence of running locally
This is `opentofu_local`'s specific call pattern against
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s
`CloudAccessAdapter` Protocol — both `acquire_plan_credentials` and
`acquire_apply_credentials` get called, unlike `ccapi` (one call) or
`hcp_terraform` (neither, for execution). The concrete cost of not
delegating to HCP: a local `tofu plan` refreshes real provider state
as part of building the plan, so it needs live cloud read access — a
requirement that simply doesn't
exist for `hcp_terraform`, where HCP does that read internally.

```
PLAN PHASE:
  acquire a short-lived, plan-tier credential -- non-resource-mutating,
  but NOT strictly read-only: it must be able to write the state
  lock object (see the correction under "the credential tier for
  each phase", below)
  tofu init -input=false
  tofu validate -no-color
  tofu plan -input=false -lock-timeout=5m -out=plan.bin
  tofu show -json plan.bin > plan.json
  DISCARD the credential — do not hold it across the approval pause,
  in state OR in process memory (stricter than the existing
  never-in-state rule: a long-running executor process could
  otherwise keep a live Python reference alive across a multi-day
  pause even though it was never checkpointed)

  ... approval gate, no credential alive anywhere during the wait ...

APPLY PHASE (after approval, after full resume revalidation):
  acquire a FRESH, apply-capable credential
  tofu apply -input=false -no-color plan.bin
  DISCARD immediately after
```
Verified: a saved plan file applies without interactive prompting —
`tofu apply plan.bin` treats the plan file itself as the approval,
and `-auto-approve` is explicitly ignored in that mode; this is *why*
it's the right primitive to use only after PlatformOps's own approval
gate has already run, not a redundant second confirmation.

The credential tier for each phase follows the same rule
`INQUIRY_WORKFLOW.md` already established —
`acquired_capability = min(actor's grant, what THIS operation needs)`
— applied across two phases of one workflow instead of across two
different workflows:

```
requester has describe:      plan credential = plan-tier; no apply phase reached
requester has plan:          plan credential = plan-tier; no apply phase
requester has apply_limited: plan credential = plan-tier (NOT
                              apply-tier, even though the requester
                              could go higher) -> after approval,
                              apply credential = apply-tier
```
For MVP, one `apply_limited` role may serve both phases in dev if a
separate planner identity doesn't exist yet; prod should use a
plan-tier identity for the plan phase regardless of what the
requester's own grant allows — same per-request-not-per-actor
discipline as the inquiry design.

**Corrected 2026-08-14 — "plan-tier" is NOT "strictly read-only", and
writing that IAM policy literally would break `tofu plan`.** Earlier
wording here and in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) called the
plan-phase credential "read-only". Verified against current OpenTofu
docs: `tofu plan` **acquires a state lock by default** (`-lock=false`
is the opt-out, and `-lock-timeout` exists precisely because locking is
on), and this design's own backend block sets `use_lockfile = true` —
so the lock is an **S3 object write**, not a metadata operation. Plan
also refreshes against live provider APIs by default (`-refresh=false`
opts out) and writes `plan.bin`/`plan.json` to local disk.

The accurate property is **non-resource-mutating**: the plan identity
never creates, updates, or deletes a managed resource, but it does
need
```
read  on the target resources being refreshed
read  on the state object
WRITE on the lock object in the state bucket (s3:PutObject +
      s3:DeleteObject on the .tflock path)
KMS decrypt/encrypt if the state bucket uses SSE-KMS
```
A policy built from `Get*`/`List*`/`Describe*` alone fails at lock
acquisition before it ever produces a plan. Left as an explicit
correction rather than a silent reword because "read-only" is the
natural thing to write into a real IAM policy from the old wording.

### Deterministic checks, extended for a local plan.json
In addition to the existing action-verb allow-list (Gap 3, below):
```
resource types allowed
action verbs allowed (create/update/delete)
delete explicitly allowed if present
names/tags/prefixes valid
workspace scope matches the backend key (catches a
  misconfigured/copy-pasted backend block before it touches the
  wrong state file)
no credential-like strings in rendered files or tool output
provider/account/region matches the registry entry
```

### Approval digest gains a sixth input: IaC artifact provenance
**Corrects `EXECUTION_CREDENTIALS.md`'s formula again, in place, not
silently.** Gap 2 above extended the original four-input formula to
five with `current_state_fingerprint`. This adds a sixth:
```
approval_digest = hash(
    plan_json,
    current_state_fingerprint,
    policy_snapshot,
    allow_list_version,
    execution_identity,
    artifact_provenance,
)
```
For a monolithic reviewed template, `artifact_provenance` is its
`template_version`. For a composed deployment it is the
`topology_digest` defined by `COMPOSABLE_PROVISIONER.md`, covering the
normalized topology, profile version, participating unit versions, and
template digests. Either form catches a library or composition change
between plan and apply even when the rendered `plan.json` happens to
look unchanged — provenance, not just content, is part of what approval
attaches to.

**Refined 2026-08-16 for fluid topology authoring:** approval attaches to
one sealed, immutable topology revision, not to a mutable provision request.
Before sealing, an agent or human may produce successor revisions; every
change invalidates the prior rendered artifact, saved plan, policy result,
and planning credential. Once an `ApprovalRequest` exists, a requested
topology change marks it `superseded` and creates a new revision followed by
a fresh render/plan/check/approval cycle. Historical approval records remain
immutable evidence but cannot authorize the successor. Resume-time digest
and current-state-fingerprint checks remain the final enforcement backstop.

### Failure taxonomy — toolchain-specific examples, same three classes
No new classes, matching `EXECUTION_CREDENTIALS.md`'s existing
retryable / needs_new_approval / hard_fail_closed taxonomy exactly:
```
retryable:          tofu lock timeout, transient provider API errors
                     before any mutation happened
needs_new_approval:  state changed, plan changed, policy changed,
                     partial apply left an unknown created-state
hard_fail_closed:    cannot acquire a credential, a forbidden action
                     in the plan, a credential-shaped leak detected
                     in tool output
```

### Recommended Build Order
Not a design decision, a sequencing note for whoever implements this
next (matching the incremental-slice approach already used for the
intake classification build): AWS first, `opentofu_local` only,
`ccapi`/`hcp_terraform`/Azure/GCP deferred until this toolchain's
executor abstraction is proven —
```
opentofu_local runner + S3 remote state + S3 lockfile locking +
sts:AssumeRole + one reviewed static_site template + plan.json
checks + manual approval gate + apply saved plan
```

### Backend config must never carry credentials — verified, and a real gap in what's already on disk
Verified against current OpenTofu docs: *"If you use `-backend-config`
or hardcode these values directly in your configuration, OpenTofu will
include these values in both the `.terraform` subdirectory and in
plan files. This can leak sensitive credentials."* The mechanism is
specific: `.terraform/terraform.tfstate` captures the backend config
at init time, and **every plan file captures that same snapshot** — a
saved plan applied later (`tofu apply plan.bin`) uses the backend
config baked in at plan time, not current settings.

This lands directly on an artifact this design already produces:
`provision_artifacts/<request_id>/plan.bin` sits on disk for the
entire approval-pause duration (hours to days, per the design's own
staleness handling). The S3 backend block above is already
credential-free (bucket/key/region only; credentials arrive via
environment variables per Layer 2's two-phase acquisition) — so
nothing is currently violated, but nothing said so explicitly either.
Stated as an explicit rule, extending
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s "nothing secret
in graph state" to a second location: **backend config blocks and
plan artifacts on disk must never carry credentials, only environment
variables may** — a future "parameterize the backend via
`-backend-config` for flexibility" change would silently reintroduce
this leak if this rule isn't stated somewhere it'll be checked
against.

### Migrating an existing Terraform-managed workspace to OpenTofu
A real scenario this design hadn't addressed: a workspace already
managed by real Terraform (not OpenTofu), onboarded into PlatformOps
after the fact. **Treated as a one-way handoff, by policy** — not
because OpenTofu's docs mandate it (checked; no such statement found
in the general or version-specific migration guides), but because
alternating writers between two different tools on one state file is
unsound regardless of what either tool's compatibility currently
claims:

```
NEVER THIS:
  terraform apply Monday -> tofu apply Tuesday -> terraform apply
  Wednesday -- alternating writers on the same state

THIS, once, per workspace:
  Terraform reads/writes BEFORE migration
  OpenTofu reads Terraform state DURING migration only
  OpenTofu writes AFTER migration
  Terraform stops writing, permanently, for that workspace
```

Same shape as [BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md)'s Level 2
— not a new pattern, a control-plane change (which engine owns a
workspace's state) applied through the same admin-gated, never-LLM-
routed, plan-then-approve machinery bootstrap already established:

```
migrate_workspace_to_opentofu (admin-gated; not reachable via intake)
  1. freeze the workspace -- no Terraform applies, no PlatformOps
     applies, no manual changes, for the duration
  2. terraform plan -> MUST show no changes; unresolved drift stops
     the migration here, before anything else happens
  3. back up state (local: file copy; remote: backend-native
     snapshot, restore procedure verified before proceeding)
  4. tofu init; tofu plan -> MUST also show no changes; any
     unexpected diff stops the migration and rolls back to Terraform,
     nothing committed
  5. APPROVAL GATE -- same mechanics as every other approval in this
     design; a no-op plan is still a real state-ownership change and
     gets the same scrutiny
  6. tofu apply (no-op) -- lets OpenTofu claim/rewrite state metadata;
     proves the workspace is now OpenTofu-operable
  7. update the registry: state ownership recorded, not inferred
  8. from this point on, only opentofu_local may write this
     workspace's state
```

Registry fields this adds — same incremental-growth pattern the
registry has already followed twice (the `account_id`/`region` split,
the `state`/`routable` lifecycle fields):
```yaml
iac_engine: opentofu
state_owner: opentofu
previous_state_owner: terraform
migrated_at: "2026-07-31T00:00:00Z"
```

## Gap 1: Terraform Has a Diff Engine; CCAPI Doesn't
Terraform's `plan` *is* a diff against real state —
`get_plan_json_output` (verified in
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)) returns the
create/update/destroy breakdown directly. AWS Cloud Control API has no
equivalent: `CreateResource`/`UpdateResource`/`DeleteResource` are
pure imperative calls with no dry-run/plan primitive of their own
(believed true, flagged for verification — not asserted as checked
fact).

For an existing-stack change on the CCAPI path, PlatformOps itself
must build the diff:

```
current_state + desired_spec -> ordered resource operations
```

This is real, non-trivial logic, not yet designed further than naming
what it requires:

- resource identity matching (which current resource corresponds to
  which desired one)
- property diffing (what actually changed)
- dependency ordering (what must happen before what)
- replacement vs. update decisions (some property changes force a
  delete+recreate, not an in-place update — provider-specific, not
  designed here)
- delete detection (desired spec no longer names a resource that
  currently exists)

**MVP recommendation**: Terraform is the safer first path for
existing-stack changes specifically, precisely because this diff
engine already exists and is already verified. The CCAPI diff builder
is real future work, not something to build defensively ahead of a
concrete need — same discipline used throughout this design (don't
build what nothing yet requires).

## Gap 2: Concurrent Drift During Approval — the biggest issue
`approval_digest` (designed in `EXECUTION_CREDENTIALS.md`) already
catches drift in PlatformOps's *own* state: plan, policy, execution
identity, allow-list version. It does not catch a fifth kind, one that
only exists once there's a real stack to drift: **someone else changes
the actual infrastructure while this request sits paused at the
approval gate.** A teammate applies an out-of-band fix, or a different
PlatformOps request against the same workspace completes first — the
plan being approved now describes a diff against a stack that no
longer exists in that shape. New-stack creation can't have this
problem (nothing to drift from); existing-stack changes can, routinely
— approval can sit paused for hours or days.

**Corrects `EXECUTION_CREDENTIALS.md`'s `approval_digest` formula in
place** — extended, not replaced, with a fifth input:

```
approval_digest = hash(
    plan_json,
    policy_snapshot,
    execution_identity,
    allow_list_version,
    current_state_fingerprint,
)
```

At resume (the same pre-flight step 1 that already checks
`approval_digest`, in `EXECUTION_CREDENTIALS.md`): recompute
`current_state_fingerprint`; if it changed, stop — same outcome as any
other digest mismatch, a fresh plan and a fresh approval cycle, no
partial credit.

```
Terraform path:  the state file's own serial/lineage, which increments
                 on every apply — cheap to read, already exists, no
                 new mechanism needed
CCAPI path:      no equivalent version counter exists; use a hash over
                 the normalized describe_current snapshot's resource
                 properties instead
```

## Gap 3: Delete Needs Its Own Policy Gate
The capability ladder's `apply_limited` is currently defined purely by
resource-*type* allow-listing (`AWS::S3::Bucket`,
`AWS::CloudFront::Distribution` — matching the real, existing
`infra/allowed-resource-types.json` shape today), with no distinction
by action *verb*. Irrelevant for new-stack creation (nothing to
delete); real risk for existing-stack changes — deleting a live,
possibly traffic-serving resource is categorically higher-stakes than
creating a new one, and nothing today would stop an `apply_limited`
actor from deleting something just because its resource *type* is
allow-listed.

**Chosen fix: extend the allow-list's shape, not the capability
ladder.** Smaller and more surgical than adding a new tier:

```json
// current shape (infra/allowed-resource-types.json, real today):
["AWS::S3::Bucket", "AWS::CloudFront::Distribution"]

// extended shape:
[
  { "type": "AWS::S3::Bucket", "actions": ["create", "update"] },
  { "type": "AWS::CloudFront::Distribution", "actions": ["create", "update"] }
]
```

Delete requires an explicit `"delete"` entry in a resource type's
allowed actions, or escalation to `apply_full`/`admin` — not designed
further here (which of those two is a policy call, not an
architecture one). **This check belongs in `deterministic_checks`,
before the approval gate** — an unauthorized delete is rejected
deterministically and never reaches a human approver's attention at
all, the same "don't waste approval capacity on something that should
never have gotten there" placement every other deterministic check in
this design already follows. The ladder itself is unchanged; only the allow-list
schema gains an action dimension. Bootstrap's own allow-list
(`infra/bootstrap-allowed-resource-types.json`,
[BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md)) doesn't need this same
extension — bootstrap is create-only by design, and teardown is
already a deliberately separate, undesigned admin path (that doc's
Decision 6) rather than a delete action within bootstrap's own
allow-list.

## Verify before build
- AWS Cloud Control API: confirm it genuinely has no dry-run/plan
  primitive before committing to "PlatformOps must build its own
  diff engine" as a hard requirement for the CCAPI path.
- Terraform state serial/lineage: confirm the exact field(s) and
  access path via the verified MCP tool inventory
  (`get_plan_details`/`get_apply_details` in
  `TERRAFORM_MCP_SERVER.md`) before relying on it as
  `current_state_fingerprint`.
- Provider-specific replace-vs-update semantics (which property
  changes force AWS/Azure/GCP resource replacement) — needed for the
  CCAPI diff builder's "replacement vs update decisions" item, not
  designed here.
- OpenTofu version constraint: the S3 backend's `use_lockfile`
  argument is confirmed current for OpenTofu 1.12.x+, but the docs
  don't state which release introduced it — pin an explicit minimum
  version before relying on it rather than assuming it's available on
  whatever version ships by default.

## Sources
- [OpenTofu: S3 backend](https://opentofu.org/docs/language/settings/backends/s3/) — `use_lockfile` syntax, DynamoDB-still-supported confirmation, bucket versioning recommendation
- [OpenTofu: `apply` command](https://opentofu.org/docs/cli/commands/apply/) — saved-plan-file behavior (no interactive prompt, `-auto-approve` ignored)
- [OpenTofu: backend configuration](https://opentofu.org/docs/language/settings/backends/configuration/) — verified verbatim: `-backend-config`/hardcoded credentials leak into `.terraform/` and plan files; environment variables recommended instead
- [OpenTofu: migration from Terraform](https://opentofu.org/docs/intro/migration/) and [v1.9-specific migration guide](https://opentofu.org/docs/v1.9/intro/migration/terraform-1.9/) — checked for a stated one-way state-compatibility limitation; **no such statement found** in either. The "never alternate Terraform/OpenTofu writers" rule in this doc is PlatformOps's own operational policy, not a cited OpenTofu constraint.

## How this relates to the existing docs
Sits between [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) (routes
into `provision`) and
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) (owns credential
acquisition once a plan is approved) — this doc owns what happens in
between: `describe_current`, `build_plan`, and the `approval_digest`
extension credentials mechanics assumes but doesn't itself define.
Corrects `EXECUTION_CREDENTIALS.md`'s `approval_digest` formula in
place (noted there, not silently changed). Reuses
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s verified
`create_run`/`action_run`/`get_plan_json_output`/`get_plan_details`/
`get_apply_details` tools rather than re-verifying them. "IaC
Generation" clarifies (not corrects — `EXECUTION_CREDENTIALS.md`'s
Layer 1/2 tables were already accurate for `hcp_terraform`) that
`hcp_terraform` and `opentofu_local` are two distinct toolchains with
different credential footprints, decided this session to coexist
rather than one replacing the other — adds `opentofu_local` as a third
`Toolchain` value there, corrected in place. Flags
`skills/provision-infra/SKILL.md`'s Path A step 1 (free-form IaC
drafting) as needing an update, and now also flags that file as
missing a Path C for `opentofu_local` — neither applied yet, both
pending `workflows/provision/`'s actual build. Shares the executor
sub-graph and failure taxonomy with
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) unchanged — this
doc adds a sixth artifact-provenance input to the digest
(`template_version` for one template; `topology_digest` for a composed
deployment, extending Gap 2's fifth), an action dimension to the allow-list, the
template-first IaC generation model, and the `opentofu_local`
toolchain's two-phase credential acquisition, nothing about the shared
execution mechanics themselves. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
