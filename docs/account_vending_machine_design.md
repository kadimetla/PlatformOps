# Account Vending — AFT's Real Mechanics, and the Honest Gap Across Clouds

## Status
Design only, grounded in real tooling research. Answers
`docs/multi_account_per_bu_design.md` Part F's open item — minting a
new `CloudAccountBinding` — by borrowing AWS's actual Account Factory
for Terraform (AFT) pipeline shape, and states plainly where there is
**no equivalent prior art** to borrow for GCP/Azure, rather than
assuming symmetry that doesn't exist.

## Part A: How AWS's account vending machine actually works
Confirmed from AFT's real module documentation:

1. **GitOps request, not an API call**: a requester creates an
   *account request Terraform file* in a dedicated repo
   (`aft-account-request`) — the request itself is a version-controlled
   file.
2. **Pipeline**: pushing it triggers CodePipeline → CodeBuild, which
   writes a DynamoDB record, which triggers a Lambda that enqueues the
   request onto **SQS** — explicitly so multiple account requests can be
   batched, not processed one at a time.
3. **Orchestration**: SQS triggers Step Functions, driving the actual
   account creation through Control Tower's Account Factory — itself
   built on Service Catalog + Organizations + IAM Identity Center. The
   "vending machine" name comes from Account Factory being *"built as
   an abstraction on top of provisioned products in AWS Service
   Catalog."*
4. **Per-account roles, created automatically**: dedicated pipeline
   roles (`AWSAFTAdmin`, `AWSAFTExecution`, `AWSAFTService`) plus a
   **new execution role created inside the newly-vended account
   itself**, so a second, account-scoped customization pipeline can
   configure it further without reusing the vending pipeline's own
   broader credentials.
5. **State and audit**: S3 + DynamoDB + KMS track every request;
   CloudWatch/SNS/CloudTrail cover monitoring and failure notification.

## Part B: The honest negative result — no cross-cloud vending tool exists
Checked Crossplane specifically, the obvious candidate — it isn't one,
for this problem. Confirmed directly from its docs: *"Providers enable
Crossplane to provision infrastructure on an external service"* —
every example is a resource **inside** an already-existing account (an
RDS instance, a service account). Nothing in Crossplane's core
documentation covers creating the account/project/subscription itself.
Whether a Terraform-schema-derived AWS provider variant exposes
`aws_organizations_account` as a CRD wasn't confirmed either way — even
if it did, that would be one CRD among hundreds, not a purpose-built
vending system the way AFT is.

**State this plainly rather than paper over it**: there is no mature,
widely-adopted, cross-cloud account-vending tool to copy. AFT is
AWS-specific, built entirely on Control Tower. GCP and Azure have no
equivalent open-source project with AFT's adoption. `CloudAccountBinding`
and the per-provider vending logic this project needs are filling a
**real gap**, not duplicating existing tooling.

## Part C: One thing worth keeping from Crossplane anyway
Not the account-vending piece — its **Provider/`ProviderConfig`
separation**: *"Providers are responsible for all aspects of connecting
to non-Kubernetes resources... authentication, making external API
calls."* That's the exact separation `CloudAccountBinding.auth_ref`
already makes — "how do I authenticate to this account" kept distinct
from "what's being provisioned." A mature, independent system
converging on the same shape is a validating signal, not a tool to
adopt. See `docs/crossplane_comparison_and_pattern_reuse.md` for the
fuller comparison, including why Crossplane's execution model
specifically (not just its account-vending gap) shouldn't be adopted.

## Part D: Mapping AFT's shape onto `CloudAccountBinding` onboarding
Not AFT's code — its *shape*, the same "borrow the shape, not the code"
principle already used for OpenClaw's Gateway design
(`docs/HARNESS_DESIGN.md`):

| AFT concept | PlatformOps equivalent |
|---|---|
| Account request Terraform file (durable record) | A "vend account" request — reuses `RequestEnvelope`/`PlanRecord`/`ApprovalRecord`, not a new file-based system; the durability AFT gets from Git+DynamoDB, this project already gets from its own schemas |
| SQS queue (batchable) | Not a new queue — `ToolIntent` with a distinct `operation` value for account creation, flowing through the existing dispatcher, which already has audit/durability built in |
| Step Functions orchestration | The per-provider vending mechanism itself (Part E) |
| Fresh per-account execution role, created atomically with the account | `CloudAccountBinding.auth_ref` — must be created **as part of** the vending step, never as an afterthought reusing a broader role |
| Account-specific customization pipeline | The existing `BOOTSTRAP.md`-equivalent onboarding ritual (`docs/skills_and_workspace_design.md`), scoped to one binding |

**Approval bar**: account creation is more foundational than anything
tier-classified so far — an account is the *container* for a BU's
entire foundation chain (`docs/foundation_layer_decomposition.md`).
This should default to the strictest treatment available:
`review_policy.approval_mode = "unanimous"`
(`docs/control_ui_approval_queue_design.md` Part C), not just the
standard foundation-tier "always human, any-of-N" default — creating a
new billing/security boundary warrants more scrutiny than adding a
resource to an existing one.

## Part E: What GCP/Azure equivalents have to build from scratch
No AFT-equivalent exists to copy, so each needs its own vending
mechanism built on its own native APIs. **Sketched from established API
shapes, not independently re-verified this session** — flagged for the
same "verify before relying on it" reason every other new integration
claim in this project gets flagged:

- **GCP — confirmed exact sequence (`docs/gcp_azure_verification_pass.md`)**:
  Cloud Resource Manager's `projects.create()`, under a folder (mapping
  to `org_id`), **does not** link billing — a separate
  `projects.updateBillingInfo()` call is required, needing
  `billing.resourceAssociations.create` on the billing account *and*
  `resourcemanager.projects.createBillingAssignment` on the project.
  (2) explicit **API enablement** — many GCP services require
  per-project `serviceusage.services.enable` calls before they're
  callable at all, unlike AWS services which are available by default.
  Org Policy inheritance itself *is* automatic through the resource
  hierarchy, same as AWS SCPs — that part doesn't need extra work.
- **Azure — confirmed exact API and a real gotcha (`docs/gcp_azure_verification_pass.md`)**:
  subscription creation via `Microsoft.Subscription/aliases` (PUT),
  `billingScope` set to the Enrollment Account ID. Confirmed: ARM-
  template-created subscriptions land in the **root management group by
  default** — the *"must be explicitly placed into the correct
  management group"* step below isn't optional, it's the default
  behavior being wrong for this project's purposes. A real, documented
  Azure REST API issue reports an API-version/authorization mismatch
  for exactly this operation — a known pain point, not hypothetical.
  Since same-org subscriptions share one Entra tenant (the tenant
  constraint established in the prior account/authentication-mechanics
  discussion, folded into `docs/multi_account_per_bu_design.md` Part A),
  no new identity federation is needed for a same-org vend, only for
  the harder cross-tenant/managed-SaaS case already flagged as unsolved.

## Open questions / not yet decided
- Whether the "vend account" `ToolIntent.operation` needs its own
  dispatcher check distinct from the existing resource-type/region
  checks, given it's creating the container those checks apply within
  — likely yes, not designed.
- **Resolved by web-research verification, `docs/gcp_azure_verification_pass.md`**
  — not the same first-party rigor as a real sandbox run (no GCP/Azure
  account access was available in this environment), but independently
  checked rather than left as an unverified sketch. Still not a tested
  integration end to end.
- Whether billing-account linkage (GCP) and management-group placement
  (Azure) should be separate approval-gated steps from the account
  creation itself, or one atomic operation — leaning atomic (matching
  AFT's "fresh role created as part of vending, not after"), not
  decided.

## How this relates to the existing docs
- Directly answers the open item in `docs/multi_account_per_bu_design.md`
  Part F ("minting a new `CloudAccountBinding` for an existing BU...
  should go through the same automated, baseline-applying ritual") with
  a concrete, real-world-grounded shape.
- Reuses `docs/control_ui_approval_queue_design.md`'s `approval_mode`
  field, recommending `"unanimous"` as account-vending's default rather
  than the standard foundation-tier default.
- Reuses `docs/HARNESS_DESIGN.md`'s "borrow the shape, not the code"
  principle, already applied once to OpenClaw, now applied to AFT.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Overview of AWS Control Tower Account Factory for Terraform (AFT) — AWS Control Tower docs](https://docs.aws.amazon.com/controltower/latest/userguide/aft-overview.html)
- [aws-ia/terraform-aws-control_tower_account_factory — GitHub](https://github.com/aws-ia/terraform-aws-control_tower_account_factory)
- [Manage your AWS multi-account environment with Account Factory for Terraform (AFT) — AWS blog](https://aws.amazon.com/blogs/mt/manage-your-aws-multi-account-environment-with-account-factory-for-terraform-aft/)
- [Providers · Crossplane docs](https://docs.crossplane.io/latest/packages/providers/)
