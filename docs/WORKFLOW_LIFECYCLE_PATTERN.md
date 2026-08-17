## Status
Designed only — a naming/synthesis layer over the workflow contracts
(`INTAKE_HITL_ROUTING.md`, `ACCESS_POLICY_AND_IAM_DISCOVERY.md`,
`CLOUD_STACK_CATALOG.md`, `PROVISION_WORKFLOW.md`,
`INQUIRY_WORKFLOW.md`, `BOOTSTRAP_WORKFLOW.md`, `EXECUTION_CREDENTIALS.md`)
plus one genuinely new rule (steps may be skipped, never reordered).
No doc previously named this sequence; grounded against actual repo
state 2026-07-31 to correct several claims that were more/less built,
or in one case entirely invented, than first stated. Runtime-status rows
were refreshed 2026-08-16 after intake routing and provision preflight landed.

## Real vs. Designed
| Item | Status |
|---|---|
| The 7-step lifecycle as a named sequence | New synthesis, not previously written down anywhere |
| `intake` classification and intent routing | Real — a two-node `classify_workflow -> resolve_route -> END` graph; scope/policy dispatch remains outside intake |
| provision request preflight | Real — `resolve_scope -> select_profile -> extract_profile_request`, with fail-closed conditional exits, produces `ProvisionDraft` only |
| `context` (grant/ceiling resolution, login/provider-discovery, state fingerprint) | Each piece designed separately (see table below); "context" as a unifying name is new here |
| `plan` / `approval` / `executor` | Designed only, per-workflow docs below |
| `evidence` — `ExecutionRecord` | Designed only — `EXECUTION_CREDENTIALS.md` |
| `evidence` — `InquiryRecord` | Designed only — `INQUIRY_WORKFLOW.md:177-186` |
| `evidence` — a bootstrap-specific record | **Not designed at all** — no `BootstrapRecord` or equivalent exists in `BOOTSTRAP_WORKFLOW.md` or anywhere else; this doc does not invent one |
| `reporting` | Not designed at all — no aggregation/metrics/dashboard-over-evidence concept exists anywhere in `docs/` |
| `workflows/inquiry`, `workflows/bootstrap` | Do not exist; `workflows/intake/` and the partial `workflows/provision/` do exist |

## The Pattern
Every PlatformOps workflow — provision, inquiry, bootstrap, and any
future one — follows the same seven-step shape. Individual steps may
be skipped (inquiry skips approval; bootstrap skips LLM-routed intake);
**none may be reordered**. This is a new rule, stated here for the
first time — nothing in the per-workflow docs contradicts it, but none
of them state it as a cross-workflow constraint either.

```
intake -> context -> plan -> approval? -> executor? -> evidence -> reporting
```

| Step | What it means | Where it's actually designed |
|---|---|---|
| **intake** | Classify intent, ask clarification, route | `INTAKE_HITL_ROUTING.md` — classification and intent routing are real in `workflows/intake/`; scope/policy dispatch remains downstream |
| **context** | Resolve actor grants/ceiling, workspace facts, authorized reusable stack release, and current state | `resolve_route`'s `effective_access = min(grant, ceiling)`; login/provider discovery; `CLOUD_STACK_CATALOG.md`'s authorization-first exact-release resolution; `PROVISION_WORKFLOW.md`'s `current_state_fingerprint` |
| **plan** | Instantiate reusable content, then generate a fresh target/state-bound provider plan—or produce an inquiry answer | `CLOUD_STACK_CATALOG.md`'s release/deployment boundary; `PROVISION_WORKFLOW.md`'s `build_plan`/toolchains; `INQUIRY_WORKFLOW.md`'s answer-shape logic |
| **approval** | Human gate for risky/mutating work | `EXECUTION_CREDENTIALS.md`'s interrupt-based approval node; policy-driven `required_approvals` (`BOOTSTRAP_WORKFLOW.md:133-142`) |
| **executor** | Run the approved action | `PROVISION_WORKFLOW.md`'s toolchains (`ccapi`/`hcp_terraform`/`opentofu_local`/`terraform_local`); the local pair shares one runner contract but seals different engine/version/state-owner identities; read-only describe calls for inquiry |
| **evidence** | Record what happened | `ExecutionRecord`, `InquiryRecord` (both designed); no bootstrap-specific record exists yet |
| **reporting** | Aggregate outcomes over time | Not designed at all, any workflow |

## Per-Workflow Mapping

### Provision
```
intake:     "deploy invoices to dev"
context:    actor grants, policy ceiling, project registry,
            exact authorized CloudStackRelease, current_state_fingerprint
plan:       instantiate CloudStackDeployment, render reviewed IaC,
            create a fresh provider plan, compute plan_digest
approval:   approver reviews vibe_diff + approval_digest
executor:   acquire short-lived credential, run tofu apply
evidence:   ExecutionRecord — actor, approver, plan digest, resources changed
reporting:  not designed — would cover deployment success rate, failed applies, resources created
```

### Inquiry
```
intake:     "what is running in invoices prod?"
context:    check describe access, fetch current state
plan:       decide answer shape / summarize state
approval:   skipped — read-only, no mutation
executor:   scoped read-only describe call
evidence:   InquiryRecord (INQUIRY_WORKFLOW.md:177-186)
reporting:  not designed — would cover who inspected prod, inquiry volume, denied queries
```

### Bootstrap
```
intake:     not LLM-routed — explicit admin action
context:    org/BU policy, cloud containers, templates
plan:       identity/scaffolding IaC plan
approval:   required_approvals from policy (BOOTSTRAP_WORKFLOW.md:133-142) —
            schema supports 2 from day one; 1 for dev/MVP velocity,
            2 for prod changes and any teardown — not merely "possibly two"
executor:   bootstrap identity creates execution identities/registry rows
evidence:   no bootstrap-specific record designed yet (gap, not an oversight to paper over)
reporting:  not designed — would cover onboarded projects, identity drift, policy changes
```

## What This Doc Deliberately Does Not Do
It does not invent a `BootstrapRecord` to make the evidence column look
complete, and it does not design the reporting layer — both are real
gaps in the current design, left as gaps. It also does not redesign
anything the source documents already cover; every "designed"
attribution above points at an existing doc rather than restating its
reasoning.

## How this relates to the existing docs
Cross-cutting index over
[INTAKE_HITL_ROUTING.md](INTAKE_HITL_ROUTING.md),
[ACCESS_POLICY_AND_IAM_DISCOVERY.md](ACCESS_POLICY_AND_IAM_DISCOVERY.md),
[CLOUD_STACK_CATALOG.md](CLOUD_STACK_CATALOG.md),
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md),
[INQUIRY_WORKFLOW.md](INQUIRY_WORKFLOW.md),
[BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md), and
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md) — names a pattern
those docs already implement piecemeal, changes none of their designs,
and adds one new cross-workflow rule (skip, don't reorder). Any future
workflow doc should state where it fits this sequence and which steps
it skips, rather than re-deriving the shape from scratch. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
