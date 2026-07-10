# Personas, Tool-Specific Blueprints, and the Sandbox Gap

## Status
Design + synthesis. Part A catalogs personas that were implicit across
20+ docs but never formally listed together. Part B lays the existing
per-tool discovery/creation mechanics side by side for the first time —
not new design, a consolidation. Part C is new: a sandbox/experimentation
tier, grounded in AWS's own named "Sandbox OU" pattern, closing a real
gap — every prior doc assumed a request either goes through full
approval or is denied, with nothing between.

## Part A: Persona catalog, with flow-step touchpoints
Synthesized from `TeamMember.role`/`.scope` (`docs/skills_and_workspace_design.md`,
`docs/infra_discovery_and_platform_app_split.md`) plus every other actor
named across this design set. Flow steps reference `spec/flow_steps/01`–`08`.

| Persona | Role/scope | What they do | Primary flow-step touchpoints | Interface |
|---|---|---|---|---|
| **Platform/Foundation Engineer** | `admin`/`approver`, `scope="foundation"` | Sets up/maintains network→compute→identity chains, approves foundation-tier changes, defines org-level shared IaC modules | Step 1 (as requester for foundation work), Step 6 (as approver) | Chat + Control UI |
| **Application Developer** | `requester`, `scope="app"` | Deploys apps onto existing foundations — the day-to-day majority user | Step 1, occasionally Step 6 if also `role="approver"` | Chat/CLI/CopilotKit UI |
| **Approver/Reviewer** | `approver`, either scope | Reviews Vibe Diffs in the queue; never the requester (self-review prevention, `docs/control_ui_approval_queue_design.md` Part B) | Step 5 (consumes `security_agent` output), Step 6 | Control UI, or external ticket |
| **Org Admin** | `OrgMember(role="admin")` — `docs/org_registry_design.md` Part C | Onboards a new org, sets org-level policy/skill/`IacSourceRef` defaults | Outside the 8-step flow — `docs/org_registry_design.md`'s 5-step onboarding sequence | Not built |
| **BU Admin** | `admin` | Runs the `BOOTSTRAP.md`-equivalent ritual, manages team roster, `CloudAccountBinding` list | Triggers account-vending requests (`docs/account_vending_machine_design.md`) — Step 1-shaped but outside the normal request flow | Onboarding tooling, not fully built |
| **Security/Compliance Reviewer** | `approver`, distinct from general approval | Sets `review_policy`, audits `security_agent` findings, owns the ticket-based approval path for regulated changes | Step 3 (defines the policy Step 3 checks against), Step 6 (external ticket path) | Control UI Config Health, external ticketing |
| **Skill Author** | any | Proposes a new `SkillProposal` from an observed pattern | Step 4, on the no-skill-match branch | Chat, implicit during normal use |
| **Skill Promotion Reviewer** | `admin`, higher bar | Reviews a BU-level skill for promotion to org/bundled tier | Outside the 8-step flow — a separate skill-promotion review process | Not built |
| **Break-glass Operator** | `admin`, time-limited | Emergency override, always identity+reason-logged | Step 6, alternate path bypassing normal approval | Control UI break-glass panel |
| **Auditor** (read-only) | none of the above — **not previously named** | Consumes Audit log/Config Health; never acts, only observes | Step 8, read-only across all steps | Control UI, read-only |
| **Sandbox Experimenter** (new, Part C) | `requester`, under *automated* limits, not human approval | Free-form experimentation | Step 1 through Step 8, but Step 6 is automated, not human, for this persona | Chat/CLI against a sandbox `CloudAccountBinding` |
| **Business Stakeholder / UAT Approver** (new, `docs/environment_promotion_pipeline.md` Part E) | Not a `TeamMember` role at all — evaluates application behavior, not infra changes, so `role`/`scope` don't apply | Interacts with the deployed UAT environment, signs off via `UatSignoff` | The UAT stage of a `PromotionPipeline` specifically, no other touchpoint | The deployed app itself, not the harness's chat/CLI/UI surfaces |

## Part B: Tool-specific blueprints — source of truth differs per tool
Not new design — the existing per-tool mechanics from four separate
docs, laid out side by side for the first time. Maps directly onto
`IacSourceRef.tool` (`docs/iac_based_discovery.md`), which exists
precisely because discovery's source of truth depends on which tool
created the infra:

| Tool | Discovery source of truth | Creation mechanism |
|---|---|---|
| **CDK + CloudFormation** | The CFN stack itself — `ccapi-mcp-server list_resources`/`get_resource`, or `awslabs.eks-mcp-server`'s `manage_eks_stacks` for foundation-tier | `aws-iac-mcp-server` drafts, `ccapi-mcp-server` executes per-resource via Cloud Control API |
| **Terraform** | Terraform state (`terraform-mcp-server`, `IacSourceRef.tfe_workspace`) — preferred over live API per the corrected priority in `docs/iac_based_discovery.md` Part C | `terraform-mcp-server`'s `create_run`/`action_run`, or module instantiation against a shared landing-zone module |
| **GCP Config Connector** | Live K8s resource status via `kubernetes-mcp-server` (`docs/iac_based_discovery.md` Part A) | K8s manifest apply, reconciled by Config Connector's own controller |

## Part C: Sandbox/experimentation — the new gap this closes
Every prior doc assumed a request either goes through full approval or
is denied — nothing between. AWS's own multi-account whitepaper names
this gap explicitly: a dedicated **"Sandbox OU (Experimental)."**
Confirmed mechanics: *"in exchange for more open AWS permissions,
developers agree to work within guardrails defined by security and
compliance teams"* — the **opposite** tradeoff shape from foundation-
tier (foundation = tight permissions + mandatory human review; sandbox
= loose permissions + strict *automated* limits instead of human
review). Concretely: SCPs blocking high-cost/production services,
automated budget enforcement (warning at 80%, auto-terminate at 100%),
automated periodic teardown, and accounts get **frozen, not deleted**,
at limits — preserving work rather than destroying it.

### Three schema extensions this requires
```python
# docs/multi_account_per_bu_design.md's CloudAccountBinding.purpose
# gains a fourth value:
purpose: str  # "prod" | "staging" | "dev" | "sandbox"

# docs/control_ui_approval_queue_design.md's review_policy.approval_mode
# gains a third value:
approval_mode: str  # "any" | "unanimous" | "automated"
# "automated" = no human review at all; gated instead by hard cost/time
# limits enforced at the CloudAccountBinding level, matching AWS's
# Sandbox OU budget-warning/auto-terminate pattern

# docs/foundation_layer_decomposition.md's FoundationRecord.status
# gains a third value:
status: str = "active"  # "active" | "decommissioned" | "frozen"
```

### Behavioral consequence for the recursive chain check
`docs/foundation_layer_decomposition.md` Part C's
`_foundation_chain_active()` must treat `"frozen"` the same as
inactive — **only** `"active"` passes, consistent with deny-by-default.
The distinction between `"frozen"` and `"decommissioned"` is that a
frozen foundation can be **unfrozen** (reactivated) without full
re-creation, matching the "preserve work, don't destroy it" behavior
AWS's own sandbox pattern uses — decommissioned implies gone for good,
frozen implies paused.

## Open questions / not yet decided
- Exact automated-limit enforcement mechanism (who/what actually
  triggers the freeze at 100% budget — a scheduled check, a billing
  webhook, a CloudWatch alarm equivalent per cloud) — sketched at the
  AWS level from research, not designed for GCP/Azure or for this
  project's own dispatcher.
- Whether `"automated"` `approval_mode` needs its own audit-event shape
  distinct from a human-approved or agent-approved decision, so a
  compliance review can tell the three apart at a glance — not decided.
- Whether Org Admin/BU Admin/Skill Promotion Reviewer personas need
  their own `TeamMember.scope` value (a third axis beyond
  `"foundation"`/`"app"`/`"both"`) since their work is largely outside
  the 8-step request flow entirely — flagged, not designed.

## How this relates to the existing docs
- Part A is pure synthesis — no existing doc changes as a result of it,
  it's the first place these personas are listed together.
- Part B is pure consolidation of mechanics already established in
  `docs/iac_based_discovery.md`, `docs/eks_helm_mcp_integration.md`,
  and `docs/foundation_discovery_and_capability_matching.md`.
- Part C extends `docs/multi_account_per_bu_design.md`'s `CloudAccountBinding`,
  `docs/control_ui_approval_queue_design.md`'s `review_policy`, and
  `docs/foundation_layer_decomposition.md`'s `FoundationRecord` —
  three schema touches in one doc, cross-linked from each source.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Sandbox OU (Experimental) — AWS multi-account whitepaper](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/sandbox-ou.html)
- [Best practices for creating and managing sandbox accounts in AWS — AWS blog](https://aws.amazon.com/blogs/mt/best-practices-creating-managing-sandbox-accounts-aws/)
- [Provision sandbox accounts with budget limits using AWS Control Tower — AWS blog](https://aws.amazon.com/blogs/mt/provision-sandbox-accounts-with-budget-limits-to-reduce-costs-using-aws-control-tower/)
- [Innovation Sandbox on AWS — AWS Solutions](https://docs.aws.amazon.com/solutions/latest/innovation-sandbox-on-aws/solution-overview.html)
