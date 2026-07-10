# Post-Apply Smoke Testing — Existence vs. Function

## Status
Design only. Closes a gap that ran through this project's whole
provisioning design: every validation step designed so far
(`spec/check_compliance.py`, `cfn-lint`/`cfn-guard`, Terraform
plan/diff) is a **pre-apply, static** check — does the syntax parse,
does it comply with policy, what *would* change. Nothing validates
that a created resource actually *works* after it exists.
`skills/provision-infra/SKILL.md`'s current "verify with
`get_resource`/`list_resources`" step only confirms **existence**.
Grounded against real infra-testing practice (Terratest, Terraform's
native `check` blocks) and one concrete March 2026 finding (CDK's
drift-aware deploy) — see Sources.

## Part A: Existence and function are different claims
A Lambda function can deploy successfully and still fail on every real
invocation. An EKS cluster can report `ACTIVE` while its node group
never reaches `Ready`. Real practice draws a sharp, named line between
two different things: deterministic compliance checks confirm a *plan*
is compliant; **smoke tests** confirm the *result* actually works —
the textbook example, confirmed directly: *"whether you can SSH into
an EC2 instance."* This project's design has only ever checked the
weaker claim.

## Part B: `SmokeTestResult` — a new post-apply check, harness-orchestrated
For paradigms without a native check mechanism (CDK/CloudFormation,
GCP Config Connector, Azure ARM):
```python
class SmokeTestResult(BaseModel):
    plan_id: str
    tool_intent_id: str
    resource_identifier: str
    check_type: str   # "connectivity" | "invocation" | "health_endpoint" | "resource_state"
    passed: bool
    details: str
    checked_at: datetime.datetime
```
What check runs is a function of `resource_type`, declared in a new
config family (`smoke_test_policy.yaml`), same shape as
`allowed-resource-types.json`: `AWS::Lambda::Function` → invoke with a
test event; `AWS::EKS::Cluster` → poll node group status until `Ready`
or timeout; `AWS::S3::Bucket` → a `HeadBucket`/tagged-object round trip.
Runs as part of `spec/flow_steps/08_execution_and_audit.md`, immediately
after the real cloud call succeeds, before the plan/skill is considered
"confirmed."

### Terraform path: use the native mechanism, don't reimplement it
Terraform ships `check` blocks natively — *"continuous validation...
runs check blocks in your configuration on a schedule."* For the
Terraform toolchain, the drafting agent should emit the `check` block
**as part of the generated `.tf` file itself**, not as a separate
harness-level system — the smoke test travels with the script, reusable
by anyone who runs the module again, not bolted on by the harness after
the fact. `SmokeTestResult` still gets written to the audit trail
(reading the check's pass/fail state), but the check logic itself lives
in Terraform, not in the harness.

## Part C: Corrects `docs/skill_proposal_execution_and_templating.md`'s definition of "confirmed"
That doc gates `SkillProposal` review behind *"a real `get_resource`/
`list_resources` check"* — existence, the weaker claim. **Corrected
here**: `SkillProposal.status` transitions from
`"pending_execution_confirmation"` to `"pending_review"` only after a
**passing `SmokeTestResult`**, not just a successful dispatch + existence
check. A pattern that creates a resource successfully but produces
something non-functional shouldn't become eligible for reuse just
because the resource exists — that would poison the skill library with
a *functionally* broken pattern that looked like a success.

## Part D: Sandbox-first validation for novel `SkillProposal` drafts
Terratest's actual pattern: *"deploys real infrastructure, validates it
works correctly, then destroys it"* — in a disposable sandbox, not
production. Maps directly onto the sandbox tier already designed
(`docs/personas_and_tool_blueprints.md` Part C): a freshly-drafted,
never-before-seen pattern (the no-skill-match branch,
`docs/skills_and_workspace_design.md` Part C) should run its smoke test
in a `purpose="sandbox"` `CloudAccountBinding` first, under automated
limits, **before** ever being proposed as a `SkillProposal` against a
production account. This turns "is this pattern safe to reuse" from a
human-reviewed guess into something actually tested first — the human
reviewer (`docs/skills_and_workspace_design.md` Part C step 2) reviews
a draft that already passed a real smoke test in a disposable
environment, not just a plan that looks right on paper.

## Part E: Drift monitoring — a native mechanism to reuse, not build
Concrete, recent (March 2026) finding: `cdk deploy` now supports a
*"drift-aware change set that brings your actual resource state back in
line with your template"*, plus `--revert-drift` to fix drifted
resources in one command. This is a native implementation option for
the drift-reconciliation pattern already designed
(`docs/infra_discovery_and_platform_app_split.md` Part A), specific to
the CDK/CloudFormation path — worth using directly rather than
hand-building drift detection for that toolchain.

## Open questions / not yet decided
- Exact `smoke_test_policy.yaml` schema and default checks per resource
  type — sketched at the concept level (Part B), not itemized per
  `allowed-resource-types.json` entry.
- Timeout/retry policy for smoke tests that need to poll for eventual
  consistency (e.g., EKS node readiness can take several minutes) — not
  designed.
- Whether a failed smoke test should trigger automatic rollback, or
  just block the `SkillProposal`/audit-confirm step and leave the
  resource in place for human investigation — leaning toward the
  latter (don't compound a failure with an automated destructive
  action), not decided as a hard rule.
- **Reframed in `docs/gcp_azure_verification_pass.md`**: `check` blocks
  are a Terraform-language feature, provider-agnostic by construction —
  no separate GCP/Azure equivalent is needed for that specific
  mechanism. The real equivalent need was pre-apply policy validation,
  which does exist natively: GCP's `gcloud beta terraform vet` plus a
  100+-policy Policy Library (directly reusable for this project's
  GCP-side compliance rules), and Azure Policy (already known from
  `docs/multi_cloud_foundation_and_iam.md`).

## How this relates to the existing docs
- Corrects `docs/skill_proposal_execution_and_templating.md` Part B's
  definition of "confirmed successful execution."
- Extends `spec/flow_steps/08_execution_and_audit.md` with a new
  post-apply validation sub-step, between the real cloud call and the
  audit-log write.
- Ties into the sandbox tier from `docs/personas_and_tool_blueprints.md`
  Part C as the environment novel patterns should be smoke-tested in
  before ever reaching production.
- Gives `docs/infra_discovery_and_platform_app_split.md` Part A's
  drift-reconciliation design a concrete, native implementation option
  for the CDK/CloudFormation path.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Terraform Testing Guide: Tools, Tactics, and Pitfalls — Medium](https://medium.com/@noel.benji/testing-terraform-deployments-tools-tactics-traps-6d92a413d6a6)
- [Use checks to validate infrastructure — Terraform tutorials, HashiCorp Developer](https://developer.hashicorp.com/terraform/tutorials/configuration-language/checks)
- [Tests - Configuration Language — Terraform docs, HashiCorp Developer](https://developer.hashicorp.com/terraform/language/tests)
- [AWS CDK policy validation at synthesis time — AWS CDK v2 docs](https://docs.aws.amazon.com/cdk/v2/guide/policy-validation-synthesis.html)
- [CDK update - March 2026 — DEV Community](https://dev.to/aws/cdk-update-march-2026-1ga8)
