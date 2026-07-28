## Status
Designed only. No provision workflow, diff builder, or auth code
exists on this branch. Covers what's specific to the `provision`
intent's planning logic — diffing, drift, and action-level policy —
distinct from [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md),
which owns credential acquisition and stays that doc's exclusive
concern. CCAPI's lack of a native plan/dry-run primitive is stated as
believed-true, not verified this session — see Verify before build.

## Real vs. Designed
| Area | Status |
|---|---|
| Provision workflow (any node) | Not implemented |
| CCAPI diff builder (`current_state + desired_spec -> ordered operations`) | Not implemented — identified this session as non-trivial, separate work |
| `current_state_fingerprint` in `approval_digest` | Designed only — extends `EXECUTION_CREDENTIALS.md`'s formula, corrected there in place |
| Action-verb allow-list (`infra/allowed-resource-types.json`'s eventual successor) | Designed only — current real file is resource-type-only, no action-verb distinction |
| Terraform `get_plan_json_output` | Real tool, verified in `TERRAFORM_MCP_SERVER.md` — the diff engine CCAPI lacks |

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
`get_plan_json_output`/`get_plan_details`/`get_apply_details` tools
rather than re-verifying them. Shares the executor sub-graph and
failure taxonomy with
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) unchanged — this
doc only adds a fifth input to the digest and an action dimension to
the allow-list, nothing about execution mechanics itself. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
