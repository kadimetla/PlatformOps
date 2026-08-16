## Status
Partially real. `workflows/provision/` resolves scope, selects a profile,
and extracts a typed application request, then stops at `ProvisionDraft`.
No topology runner, renderer, provider-plan adapter, approval/apply path,
or diff builder exists yet. This document covers what's specific to the
`provision` intent's downstream planning logic — diffing, drift,
action-level policy, IaC generation, and toolchain selection —
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) still owns the
general credential-acquisition mechanics (Layers 0/1/2, the approval
gate, the executor sub-graph); this doc's "Local IaC Runners"
section is the one exception, since those toolchains' two-phase
credential acquisition is inseparable from their planning mechanics.
CCAPI's lack of a native plan/dry-run primitive is stated as
believed-true, not verified this session. OpenTofu-specific claims
were verified 2026-07-30. Terraform saved-plan/apply and S3
`use_lockfile` behavior were verified against current HashiCorp docs
2026-08-16 — see Sources/Verify before build.

## Real vs. Designed
| Area | Status |
|---|---|
| Provision request preflight (`resolve_scope`, `select_profile`, `extract_profile_request`) | Real and tested; stops at `ProvisionDraft` |
| Topology load/run, rendering, provider plan, approval, apply, and verification | Not implemented |
| CCAPI diff builder (`current_state + desired_spec -> ordered operations`) | Not implemented — identified this session as non-trivial, separate work |
| `current_state_fingerprint` in `approval_digest` | Designed only — extends `EXECUTION_CREDENTIALS.md`'s formula, corrected there in place |
| Action-verb allow-list (`infra/allowed-resource-types.json`'s eventual successor) | Designed only — current real file is resource-type-only, no action-verb distinction |
| Terraform `get_plan_json_output` | Real tool, verified in `TERRAFORM_MCP_SERVER.md` — the diff engine CCAPI lacks |
| Template library (`skills/provision-infra/templates/`) | Not implemented — directory doesn't exist |
| `skills/provision-infra/SKILL.md`'s Path A step 1 ("draft the CDK app") | Real, current, and now contradicted by this doc's template-first design — flagged, not yet updated |
| `skills/provision-infra/SKILL.md`'s Path C (`opentofu_local`) | Not implemented — the file only has Paths A/B today; this toolchain has no skill entry yet |
| `skills/provision-infra/SKILL.md`'s Path D (`terraform_local`) | Not implemented — local Terraform must not be conflated with its existing HCP Terraform path |
| `opentofu_local` runner (state backend, runner directory, two-phase credential acquisition) | Designed only, verified against current OpenTofu docs 2026-07-30 |
| `terraform_local` runner | Designed only 2026-08-16; shares the local-runner contract but has a distinct binary/version/state-owner identity |
| `Toolchain`/`LocalEngineIdentity` schemas and executor dispatch | Designed only — no runtime enum, runner, or executor package exists |
| IaC artifact provenance in `approval_digest` | Designed only — sixth input is `template_version` for a monolithic template or `topology_digest` for a composed deployment |
| Toolchain identity in `approval_digest` | Designed 2026-08-16 — seventh input binds the resolved executor/toolchain configuration; for local runs it includes exact engine/version/platform and dependency-lock/backend identities |
| `migrate_workspace_to_opentofu` admin workflow | Designed only |
| Registry `toolchain`/`iac_engine`/`engine_version`/`state_owner`/`previous_state_owner`/`migrated_at` fields | Designed only — trusted selection and state-writer identity, never user/model input |
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

The concrete designed mechanism for this coder role is
`COMPOSABLE_PROVISIONER.md`'s "Offline use — Slice 15 sandboxed Level 2
authoring": an isolated Deep Agent may inspect trusted provider contracts and
reviewed authoring skills, edit a module/renderer and its contract tests, and
run formatting, `tofu validate`, pytest, and deterministic compliance checks.
It receives no cloud credentials and cannot merge, push, approve, or apply;
it exports only a patch or PR artifact for normal human review. This is an
optional authoring-time tool, not a node in the provision graph and not a
runtime dependency of composition Slices 13 or 14. Only a human-reviewed,
merged result can enter the runtime registry. Slice 15 in
`PROVISION_IMPLEMENTATION_PLAN.md` tracks its independent acceptance.

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

### Four toolchains, four sealed execution identities
`Toolchain` has four canonical values — never the abbreviations
`tofu_local` or a generic `terraform`:

```python
class Toolchain(str, Enum):
    CCAPI = "ccapi"
    HCP_TERRAFORM = "hcp_terraform"
    OPENTOFU_LOCAL = "opentofu_local"
    TERRAFORM_LOCAL = "terraform_local"
```

`hcp_terraform`, `terraform_local`, and `opentofu_local` may consume
the same reviewed HCL, but they are different execution authorities.
HCP owns the remote run and state for `hcp_terraform`; PlatformOps owns
the process boundary, credential injection, runner isolation, and
remote-state coordination for both local engines. Toolchain selection
comes only from the trusted workspace registry. A user or model may
request Terraform/OpenTofu as a preference, but cannot override the
workspace's recorded state owner.

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

terraform_local:
  Same local-process security footprint and two acquisition phases as
  opentofu_local, but PlatformOps invokes the pinned `terraform`
  binary. It has a separate engine/version identity, saved plan, and
  state owner. It is not an alias or fallback for opentofu_local.

ccapi:
  unchanged — PlatformOps holds a real cloud credential directly,
  the same one-acquisition direct-cloud credential shape as before.
```

**Corrected 2026-08-16:** an earlier paragraph said nothing is acquired
until after approval. That is impossible for plan-based toolchains: HCP
needs its planning API access, and both local engines need plan-tier
provider/backend access, before an approvable plan exists. The invariant
is: least-privilege planning access before approval, immediately
discarded; mutation-capable apply access only after approval and resume
revalidation; no credential material in graph state.

## Local IaC Runners (`opentofu_local` and `terraform_local`)
`opentofu_local` remains the recommended MVP build order for AWS. The
shared boundary below is designed once, while engine-specific command
names, version probes, plan artifacts, and state ownership stay exact.

### One runner contract, no cross-engine plan reuse

```python
class LocalEngine(str, Enum):
    OPENTOFU = "opentofu"
    TERRAFORM = "terraform"

class LocalEngineIdentity(BaseModel):
    toolchain: Literal["opentofu_local", "terraform_local"]
    engine: LocalEngine
    executable_name: Literal["tofu", "terraform"]
    version: str
    platform: str

class LocalPlanResult(BaseModel):
    engine_identity: LocalEngineIdentity
    revision_id: str
    artifact_digest: str
    dependency_lock_digest: str
    backend_config_digest: str
    plan_path: str
    plan_digest: str
    plan_json_path: str
    plan_json_digest: str
    current_state_fingerprint: str
```

The executable name is resolved by trusted runner configuration and
verified with the engine's version command; it is never a user/model-
supplied path. Plan and apply must use the same `toolchain`, engine,
exact version, platform, dependency-lock digest, backend digest, and
rendered-artifact digest. Any mismatch invalidates the sealed plan and
requires a new plan and approval. This exact-match rule is PlatformOps's
own conservative invariant; it does not claim Terraform and OpenTofu
document plan-file portability across products or releases.

The local plan file is opaque and potentially sensitive. Hash it
immediately, restrict its filesystem permissions, never put its bytes or
contents in LangGraph state/events/logs, and delete it according to the
evidence-retention policy after the run. The normalized JSON view is the
policy input; the binary file is the only apply input. HashiCorp's current
Terraform docs explicitly warn that saved plans can contain sensitive
values in cleartext, and confirm that applying a saved plan performs its
recorded operations without another CLI confirmation or new planning
options. PlatformOps's approval gate is therefore the authority—the CLI's
saved-plan behavior is not an approval mechanism.

The command adapter is the only engine-specific branch in the local
spine:

| Operation | `opentofu_local` | `terraform_local` |
|---|---|---|
| Probe | `tofu version` | `terraform version` |
| Initialize | `tofu init -input=false` | `terraform init -input=false` |
| Validate | `tofu validate -no-color` | `terraform validate -no-color` |
| Plan | `tofu plan -input=false -out=plan.bin` | `terraform plan -input=false -out=plan.bin` |
| JSON | `tofu show -json plan.bin` | `terraform show -json plan.bin` |
| Apply | `tofu apply plan.bin` | `terraform apply plan.bin` |

Exact supported flags and minimum versions are probed and pinned before
build. Do not construct commands by substituting an arbitrary executable
string into a shell command; the runner uses an argv list selected from
the closed engine enum.

### Runner boundary — one isolated directory per request
Never run from the repo root; the directory is disposable, one per
request, and doubles as `ExecutionRequest.artifact_path` (in the
schema since `EXECUTION_CREDENTIALS.md`, defined by the render step
already designed above):

```
provision_artifacts/<request_id>/
  main.tf / variables.tf / outputs.tf   -- from template rendering
  backend.tf                            -- local toolchains only
  terraform.tfvars.json
  plan.bin / plan.json                  -- local toolchains only,
                                        -- populated by build_plan
```
CCAPI and `hcp_terraform` populate the same directory's IaC files but
never `backend.tf`/`plan.bin`/`plan.json` — CCAPI has no state file of
its own, and `hcp_terraform`'s plan artifacts live in HCP, not on
PlatformOps's disk.

### State backend — remote, locked, never local
Local state is not acceptable for real provisioning. S3 backend with
native S3 locking is the AWS local-runner default. `use_lockfile` is
verified current for both engines as of 2026-08-16; minimum supported
versions still must be pinned independently rather than inferred from
shared syntax:

```hcl
terraform {
  backend "s3" {
    bucket       = "platformops-iac-state"
    key          = "aiq/it/invoices/dev/iac.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
```
The `key` is built directly from `Scope` — `org:bu/project/workspace`
— giving state isolation the exact same shape as everything else in
this design; a stack's state path is derivable from its scope, not a
separate naming decision. The state filename is deliberately engine-
neutral because ownership lives in registry metadata, not the object
name. DynamoDB locking is engine/version-specific: current Terraform
docs mark it deprecated in favor of S3 lockfiles, while the previously
checked OpenTofu docs retained it. The pinned engine adapter validates
the reviewed backend contract instead of assuming parity. Bucket
versioning remains an `infra`-level bootstrap concern, not a per-request
option.

### Two credential acquisitions, not one — a real consequence of running locally
This is both local toolchains' call pattern against
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s
`CloudAccessAdapter` Protocol — both `acquire_plan_credentials` and
`acquire_apply_credentials` get called, unlike `ccapi` (one call) or
`hcp_terraform` (neither, for execution). The concrete cost of not
delegating to HCP: a local plan refreshes real provider state
as part of building the plan, so it needs live cloud read access — a
requirement that simply doesn't
exist for `hcp_terraform`, where HCP does that read internally.

```
PLAN PHASE:
  acquire a short-lived, plan-tier credential -- non-resource-mutating,
  but NOT strictly read-only: it must be able to write the state
  lock object (see the correction under "the credential tier for
  each phase", below)
  <engine> init -input=false
  <engine> validate -no-color
  <engine> plan -input=false -lock-timeout=5m -out=plan.bin
  <engine> show -json plan.bin > plan.json
  DISCARD the credential — do not hold it across the approval pause,
  in state OR in process memory (stricter than the existing
  never-in-state rule: a long-running executor process could
  otherwise keep a live Python reference alive across a multi-day
  pause even though it was never checkpointed)

  ... approval gate, no credential alive anywhere during the wait ...

APPLY PHASE (after approval, after full resume revalidation):
  acquire a FRESH, apply-capable credential
  <SAME engine identity/version> apply -input=false -no-color plan.bin
  DISCARD immediately after
```
Verified for both engines' current docs: a saved plan file applies
without another interactive confirmation. Terraform documents that no
new planning options are accepted in saved-plan mode; OpenTofu documents
that `-auto-approve` is ignored. This is *why* the binary is invoked only
after PlatformOps's own approval gate—it is not a redundant second
confirmation.

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

**Corrected 2026-08-14 and generalized 2026-08-16 — "plan-tier" is NOT
"strictly read-only", and writing that IAM policy literally breaks a
locked local plan.** Earlier
wording here and in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) called the
plan-phase credential "read-only". Current Terraform and OpenTofu
documentation both support S3 lockfiles; Terraform explicitly requires
`s3:GetObject`, `s3:PutObject`, and `s3:DeleteObject` on the `.tflock`
path. Both local adapters therefore treat locking as an **S3 object
write**, not metadata. Planning also refreshes live provider state by
default and writes `plan.bin`/`plan.json` to local disk.

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

**Implementation gate added 2026-08-16:** this technically accurate lock
requirement conflicts with root `AGENTS.md`'s broader rule that every mutating
action requires recorded approval. The saved-plan approval cannot authorize
the state-lock write needed to create that plan. Slice 9 must not be enabled
until maintainers explicitly choose one policy: recognize the bounded lock
lease as an allow-listed plan operation under recorded preauthorization and
amend the root rule; initially use `<engine> plan -lock=false` with before/after
state-fingerprint rejection; or add a separate pre-plan approval. This doc
does not silently pick an exception. The decision and its tests are tracked in
`PROVISION_IMPLEMENTATION_PLAN.md`'s Slice 9 implementation sequence.

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

### Approval digest gains artifact and toolchain identity inputs
**Corrects `EXECUTION_CREDENTIALS.md`'s formula again, in place, not
silently.** Gap 2 above extended the original four-input formula to
five with `current_state_fingerprint`; artifact provenance added the
sixth. The four-toolchain contract adds a seventh so approval cannot be
resumed under a different executor/engine identity:
```
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
For a monolithic reviewed template, `artifact_provenance` is its
`template_version`. For a composed deployment it is the
`topology_digest` defined by `COMPOSABLE_PROVISIONER.md`, covering the
normalized topology, profile version, participating unit versions, and
template digests. Either form catches a library or composition change
between plan and apply even when the rendered `plan.json` happens to
look unchanged — provenance, not just content, is part of what approval
attaches to.

`toolchain_identity_digest` covers the canonical `Toolchain` plus its
trusted resolved adapter configuration. For a local run it covers
`LocalEngineIdentity`, dependency-lock digest, and backend-config digest;
for HCP it covers the resolved HCP workspace/run configuration version;
for CCAPI it covers the selected reviewed adapter configuration version.
Resume re-resolves and compares this digest before credentials or apply.

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
retryable:          local-engine lock timeout, transient provider API errors
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
`terraform_local` is the second local adapter, implemented only after this
spine passes. It must reuse the same runner protocol and policy/sealing tests;
adding a second copy of the lifecycle graph is not acceptable.

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

### Local engine ownership, onboarding, and migration
A workspace already managed by local Terraform may be onboarded as
`terraform_local` without changing engines: freeze writes, back up state,
probe the pinned Terraform version, initialize against the reviewed backend,
require a no-change plan, and record ownership before PlatformOps may plan or
apply. Onboarding is not permission to substitute OpenTofu.

Migration from `terraform_local` to `opentofu_local` is a distinct admin
workflow. It is **treated as a one-way handoff, by policy** — not
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
  terraform_local reads/writes BEFORE migration
  OpenTofu reads Terraform state DURING migration only
  opentofu_local writes AFTER migration
  terraform_local stops writing, permanently, for that workspace
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

No reverse `opentofu_local -> terraform_local`, local↔HCP, or CCAPI↔stateful
engine migration is designed. Those fail closed as unsupported admin
operations until separately specified and verified. Runtime dispatch never
performs migration and never falls back to another engine when the registered
binary is missing or its version mismatches; it stops before planning.

Registry fields this adds — same incremental-growth pattern the
registry has already followed twice (the `account_id`/`region` split,
the `state`/`routable` lifecycle fields):
```yaml
toolchain: opentofu_local
iac_engine: opentofu
engine_version: "<pinned exact version>"
state_owner: opentofu_local
previous_state_owner: terraform_local
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

This gap originally added the fifth input. The current implementation
contract also includes the subsequently designed artifact-provenance and
toolchain-identity inputs; do not implement the historical five-input form:

```
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
- Terraform version constraint: current Terraform docs support S3
  `use_lockfile`, saved-plan apply, and JSON inspection, but the minimum
  version for the exact selected flags/backend schema must be probed and
  pinned before enabling `terraform_local`.
- Cross-engine compatibility: verify migrations separately. Never use
  configuration/state compatibility as evidence that a Terraform-created
  binary plan is applyable by OpenTofu or vice versa; PlatformOps forbids
  cross-engine plan reuse regardless.

## Sources
- [OpenTofu: S3 backend](https://opentofu.org/docs/language/settings/backends/s3/) — `use_lockfile` syntax, DynamoDB-still-supported confirmation, bucket versioning recommendation
- [OpenTofu: `apply` command](https://opentofu.org/docs/cli/commands/apply/) — saved-plan-file behavior (no interactive prompt, `-auto-approve` ignored)
- [OpenTofu: backend configuration](https://opentofu.org/docs/language/settings/backends/configuration/) — verified verbatim: `-backend-config`/hardcoded credentials leak into `.terraform/` and plan files; environment variables recommended instead
- [OpenTofu: migration from Terraform](https://opentofu.org/docs/intro/migration/) and [v1.9-specific migration guide](https://opentofu.org/docs/v1.9/intro/migration/terraform-1.9/) — checked for a stated one-way state-compatibility limitation; **no such statement found** in either. The "never alternate Terraform/OpenTofu writers" rule in this doc is PlatformOps's own operational policy, not a cited OpenTofu constraint.
- [Terraform: `plan` command](https://developer.hashicorp.com/terraform/cli/commands/plan) — verified 2026-08-16: `-out` produces a saved plan for later apply; saved plans may contain sensitive values in cleartext
- [Terraform: `apply` command](https://developer.hashicorp.com/terraform/cli/commands/apply) — verified 2026-08-16: saved-plan mode executes without another prompt and accepts no new planning options
- [Terraform: S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3) — verified 2026-08-16: `use_lockfile`, `.tflock`, required S3 Get/Put/Delete permissions; DynamoDB locking deprecated in current Terraform docs

## How this relates to the existing docs
Sits between [INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md) (routes
into `provision`) and
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) (owns credential
acquisition mechanics; local plan-tier access occurs before approval and
apply-tier access after it) — this doc owns what happens in
between: `describe_current`, `build_plan`, and the `approval_digest`
extension credentials mechanics assumes but doesn't itself define.
Corrects `EXECUTION_CREDENTIALS.md`'s `approval_digest` formula in
place (noted there, not silently changed). Reuses
[TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s verified
`create_run`/`action_run`/`get_plan_json_output`/`get_plan_details`/
`get_apply_details` tools rather than re-verifying them. "IaC
Generation" clarifies (not corrects — `EXECUTION_CREDENTIALS.md`'s
Layer 1/2 tables were already accurate for `hcp_terraform`) that
`hcp_terraform`, `opentofu_local`, and `terraform_local` are distinct
toolchains. The two local engines share one runner contract and two-phase
credential footprint but never share a saved plan or state-writer identity.
Adds `opentofu_local` and `terraform_local` as explicit `Toolchain` values
there, corrected in place. Flags
`skills/provision-infra/SKILL.md`'s Path A step 1 (free-form IaC
drafting) as needing an update, and now also flags that file as
missing Path C for `opentofu_local` and Path D for `terraform_local` —
none applied yet,
pending `workflows/provision/`'s actual build. Shares the executor
sub-graph and failure taxonomy with
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) unchanged — this
doc adds a sixth artifact-provenance input and seventh toolchain-identity
input to the digest
(`template_version` for one template; `topology_digest` for a composed
deployment, extending Gap 2's fifth), an action dimension to the allow-list, the
template-first IaC generation model, and the local toolchains'
two-phase credential acquisition, nothing about the shared
execution mechanics themselves. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
