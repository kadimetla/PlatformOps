# Foundation Discovery & Creation: An Annotated Chat Walkthrough

## Status
Synthesis, not a build log — same role as `docs/end_to_end_flow_example.md`
and `docs/foundation_and_app_deploy_flow_example.md`, but presented as a
literal annotated chat transcript rather than a numbered step list, and
specifically fleshing out one thing no prior doc made concrete: **what
"generating code" for the foundation layer actually produces** —
`PlanRecord.plan_text`'s literal content, not just its existence.
Introduces no new decisions; every mechanism referenced already exists
in the docs cited inline. Nothing here is built.

## Scenario
Priya, a platform engineer at Acme (`TeamMember(role="admin",
scope="foundation")`), checks what infrastructure the Orders BU has,
then stands up a new foundation for the Fulfillment BU, which has none.

## Turn 1 — Discovery, an existing foundation is found

> **Priya:** "What infrastructure do we have set up for the Orders team
> on AWS?"

**Under the hood:**
- `TeamMember` scope check: Priya's `scope="foundation"` permits this
  question at all (`docs/infra_discovery_and_platform_app_split.md`
  Part C).
- `IacSourceRef` lookup for `org=acme, bu=orders, cloud_provider=aws`
  resolves to a BU-level override, `tfe_workspace="acme-orders-foundation"`
  (`docs/iac_based_discovery.md` Part B).
- Discovery Step 0, IaC-first per the corrected priority
  (`docs/iac_based_discovery.md` Part C): query Terraform state via
  `terraform-mcp-server` against that workspace first — finds 1 VPC, 1
  EKS cluster, tagged subnets. Cross-check against live API
  (`awslabs.eks-mcp-server` read tools + `ccapi-mcp-server list_resources`)
  — matches, no drift.
- `FoundationRecord` already exists, `status="active"` → branch 1,
  reuse (`docs/foundation_discovery_and_capability_matching.md` Part A).

> **Harness:** "Orders has an active AWS foundation: VPC `vpc-0abc…`
> (`10.20.0.0/16`), EKS cluster `orders-prod` (v1.31), OIDC provider
> registered for IRSA, add-ons: `aws-load-balancer-controller`,
> `ebs-csi-driver`. 3 namespaces in use: `orders-api`, `orders-worker`,
> `orders-shared`."

That response is `discovered_capabilities` rendered as prose
(`docs/foundation_discovery_and_capability_matching.md` Part C) — the
stored capability record, not a fresh query dressed up as one.

## Turn 2 — Discovery, nothing found

> **Priya:** "What about Fulfillment?"

**Under the hood:**
- Same scope check, different BU.
- `IacSourceRef` lookup for `fulfillment` — nothing BU-level; falls
  through to the org-level shared landing-zone reference per the
  bundled→org→BU precedence (`docs/iac_based_discovery.md` Part B) —
  the org has a shared module, but Fulfillment never instantiated it.
- Discovery Step 0: Terraform state check finds nothing for this BU;
  tag-scoped live API cross-check finds nothing either → branch 2,
  genuinely absent (`docs/foundation_discovery_and_capability_matching.md`
  Part A).

> **Harness:** "No foundation found for Fulfillment. I can set one up —
> this always requires human approval regardless of size or cost, since
> foundation-tier changes never auto-approve."

The approval requirement is stated up front, not discovered as a
surprise later — `docs/foundation_app_layering_and_iam_tiers.md` Part
A's tier rule.

## Turn 3 — Creation, with the code-generation mechanics made concrete

> **Priya:** "Yes — same shape as Orders, but in us-west-2."

**Under the hood:**

1. `resolve_skill()` matches `provision-foundation` (bundled tier).
2. **Toolchain choice**: Fulfillment's org-level `IacSourceRef` points
   at a shared Terraform module, not a raw native path — the agent
   drafts by instantiating that module, not hand-writing HCL from
   scratch. It pulls the module's variable schema via
   `terraform-mcp-server`'s module-docs tools first, then generates:
   ```hcl
   module "fulfillment_foundation" {
     source  = "acme/landing-zone/aws"
     version = "2.3.0"
     bu      = "fulfillment"
     region  = "us-west-2"
     vpc_cidr = "10.21.0.0/16"   # next available block, not Orders' 10.20.0.0/16
   }
   ```
   **This block *is* `PlanRecord.plan_text`.** `plan_hash` is its
   SHA256. This is what "the harness generates code for the foundation
   layer" concretely means:
   - **When a shared landing-zone module exists** (this scenario): a
     module instantiation block, parameterized per-BU.
   - **When no shared module exists, on the AWS-native path**: a
     CloudFormation template from `awslabs.eks-mcp-server`'s
     `manage_eks_stacks`, which literally *"generates CloudFormation
     templates for EKS clusters, embedding specified cluster names"*
     (confirmed capability, `docs/eks_helm_mcp_integration.md` Part A).

   Which of the two happens depends on the BU's `IacSourceRef`/toolchain
   — the shape downstream (draft → hash → review → approve → dispatch)
   is identical either way.
3. `vibe_diff`: *"Creates 1 VPC (`10.21.0.0/16`, 3 AZs) + 1 EKS cluster
   (v1.31, matching Orders' version) + separate cluster/node IAM roles
   (never the same role — `docs/infra_discovery_and_platform_app_split.md`
   Part B) + an OIDC provider for IRSA. Est. $X/month."*
4. `security_agent` reviews — but for a foundation-tier resource the
   outcome is fixed regardless of findings: mandatory human approval,
   no autonomous path exists for this tier.
5. Priya approves. `ApprovalRecord.human_approved=True`,
   `human_reviewer="priya@acme.com"`.
6. `BrokeredToolDispatcher.evaluate_intent()` — resource type
   allow-listed, `plan_hash` matches the approved record, region
   matches. Allowed.
7. Execution: `create_run` + `action_run` against the Terraform
   workspace (or `manage_eks_stacks --allow-write` on the native path).
8. A new `FoundationRecord` is written — `discovered_capabilities`
   populated **directly from the plan just applied**, not re-discovered
   after the fact, since the harness already knows exactly what it
   built.

> **Harness:** "Done. Fulfillment's foundation is live: VPC `vpc-0def…`,
> EKS cluster `fulfillment-prod`, matching Orders' config. Recorded and
> available for app-layer deploys."

## Turn 4 — The GCP variant, same chat shape, three concrete differences
Everything above holds structurally for a GCP request; three things
change, all already researched elsewhere:
- **No toolchain choice to make in step 2.** Terraform is the only
  write path — GKE's own MCP server is read-only, full stop
  (`docs/multi_cloud_foundation_and_iam.md` Part B) — so drafting
  always produces HCL, never a native-tool alternative.
- **Generated resources**: `google_compute_network` +
  `google_container_cluster`, not `AWS::EC2::VPC`/`AWS::EKS::Cluster`.
- **The ceiling enforced isn't a permissions boundary.** GCP has no
  identity-attached equivalent
  (`docs/multi_cloud_foundation_and_iam.md`'s correction) — a custom
  Org Policy constraint + IAM Deny policy is checked instead, via the
  GCP `CloudIAMAdapter` implementation.

## What's real vs. design in this walkthrough
| Piece | Status |
|---|---|
| `TeamMember.scope` check | Design only |
| `IacSourceRef` resolution (bundled→org→BU) | Design only |
| Discovery Step 0 (IaC-first, live-API cross-check) | Design only; `terraform-mcp-server`/`ccapi-mcp-server`/`eks-mcp-server` themselves are real, maintained third-party tools, not yet integrated into this repo's `mcp_server/external_servers.py` |
| `provision-foundation` skill, always-human-approval tier rule | Design only |
| Module-instantiation or CFN-template plan drafting | Design only — no `plan_request(envelope)` wrapper exists yet (`docs/planned_implementation.md` Phase 3) |
| `security_agent` foundation-tier override | Design only |
| `BrokeredToolDispatcher.evaluate_intent()` | **Real, tested** (`harness/tool_dispatcher.py`) — the checks it runs in this walkthrough are its existing logic, just not yet wired to a live foundation-tier `ToolIntent` |
| `FoundationRecord` write with `discovered_capabilities` | Design only |
| GCP `CloudIAMAdapter` ceiling check | Design only |

## How this relates to the existing docs
- Same synthesis role as `docs/end_to_end_flow_example.md` and
  `docs/foundation_and_app_deploy_flow_example.md`, presented as chat
  dialogue specifically to make the code-generation step concrete —
  those docs describe the mechanism, this one shows the literal
  artifact (`plan_text`'s actual HCL/CFN content).
- Exercises `docs/iac_based_discovery.md`'s `IacSourceRef` precedence,
  `docs/foundation_discovery_and_capability_matching.md`'s three-branch
  discovery flow (branches 1 and 2 only — the unmanaged-foundation
  branch isn't dramatized here either, same gap noted in the prior
  worked-example doc), and `docs/multi_cloud_foundation_and_iam.md`'s
  per-provider differences.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
