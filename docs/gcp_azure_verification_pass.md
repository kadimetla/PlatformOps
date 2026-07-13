---
last_updated: 2026-07-09
owner: platformops-agent maintainers
scope: GCP/Azure verification — resolves docs/remaining_deep_dives.md Tier 1 #1
reviewed_by: unreviewed (first draft)
---

# GCP/Azure Hands-On Verification Pass

## Status
Research, closing `docs/remaining_deep_dives.md`'s largest Tier 1
cluster — six previously-unconfirmed GCP/Azure claims scattered across
six docs. No real GCP/Azure account access available in this
environment, so this is web-research verification (like most of this
project's cloud-specific claims), not direct API/SDK inspection the way
`docs/plan_request_verified_implementation.md` achieved for ADK. Each
item below is resolved, partially resolved, or confirmed still open —
stated plainly per item, not glossed over.

## 1. GCP `serviceAccountTokenCreator`/`serviceAccountUser` escalation — CONFIRMED real
Resolves `docs/multi_cloud_foundation_and_iam.md`'s "stated by analogy
to `iam:PassRole`, not independently verified" flag. Confirmed:
- `iam.serviceAccountTokenCreator` grants impersonation and **can be
  chained** — Identity A impersonates B impersonates C, reaching a
  high-privilege account. Real, documented attack technique, not
  hypothetical.
- Mitigation matches what this project already designed by analogy:
  *"assign these roles to a user for a specific service account, rather
  than at a project level or above."* The existing `CloudIAMAdapter`
  design (`docs/multi_cloud_foundation_and_iam.md` Part D) had this
  right without confirmation; now confirmed.
- **New finding, not previously in this design**: every impersonation
  event is logged in Cloud Audit Logs (Admin Activity), showing
  principal, target SA, and action taken. Worth reconciling this
  project's own audit design against — GCP already gives you the
  audit trail natively for this specific risk, may reduce what the
  harness needs to log separately for GCP-specific impersonation events.
- **New finding**: VPC Service Controls (service perimeters) add a
  containment layer independent of IAM scoping — limits blast radius
  even if a service account is compromised. Not currently part of the
  `CloudIAMAdapter` design; worth a future addition.

## 2. Cloud Run MCP — CONFIRMED write-capable; Cloud Functions MCP — still not found
Resolves `docs/compute_paradigm_layering.md`'s "not confirmed either
way" for the managed-containers row:
- `GoogleCloudPlatform/cloud-run-mcp` is real, official, and
  **write-capable** — `deploy-file-contents` and `deploy-local-folder`
  tools genuinely deploy, not just read. Same tier as AWS's ECS MCP
  server, unlike GKE MCP's confirmed read-only limitation.
- Required IAM: `roles/run.developer`, `roles/iam.serviceAccountUser`,
  `roles/artifactregistry.reader`. **Directly ties to finding #1** —
  Cloud Run deployment itself *requires* the exact role whose
  escalation risk was just confirmed, reinforcing why the ARN-scoping-
  equivalent rule matters practically here, not just theoretically.
- Cloud Functions: no dedicated MCP server found, even on a fresh
  targeted search. Still unconfirmed/likely absent — flagged, not
  assumed either way.

**Update to `docs/compute_paradigm_layering.md`'s Part A table**: GCP's
"managed containers" row should move from "not confirmed" to
confirmed-write-capable (Cloud Run), while "serverless" (Cloud
Functions) stays unconfirmed.

## 3. GCP project + billing linkage — CONFIRMED, exact two-call sequence
Sharpens `docs/account_vending_machine_design.md` Part E's "explicit
billing account linkage" note with the actual mechanics:
1. `projects.create()` — creates the project, **does not** link
   billing.
2. `projects.updateBillingInfo()` — a **separate, required** call,
   needing `billing.resourceAssociations.create` on the billing
   account **and** `resourcemanager.projects.createBillingAssignment`
   on the project.

Not one step with an extra flag — two calls, two different permission
grants, on two different resources. The account-vending automation
(`docs/account_vending_machine_design.md`) needs both permissions
provisioned to whatever identity runs it, not just project-creation
rights.

## 4. Azure subscription creation — CONFIRMED, exact API and a real gotcha
Sharpens the same doc's Azure row:
- `Microsoft.Subscription/aliases` — PUT to
  `https://management.azure.com/providers/Microsoft.Subscription/aliases/{aliasName}`,
  requiring a `billingScope` parameter set to the Enrollment Account ID
  (confirms and names the exact parameter for "scoped to a billing
  account").
- **Confirms a design point precisely**: ARM-template-created
  subscriptions land in the **root management group by default** — the
  *"must be explicitly placed into the correct management group"* step
  already flagged in `docs/account_vending_machine_design.md` Part E is
  not optional, it's the default behavior being wrong for this
  project's purposes.
- **Real, documented failure mode worth flagging operationally**: a
  GitHub issue on the actual Azure REST API spec repo reports
  *"subscription in the Enrollment Account is not created using the
  latest API - User is not authorized to create subscriptions on this
  enrollment account"* — an API-version/permission mismatch that's
  apparently a known pain point, not a hypothetical edge case.

## 5. Helm chart version-pinning — CONFIRMED supported
Resolves `docs/eks_helm_mcp_integration.md`'s open item. `helm_install`
supports OCI registry references and a `--version` flag; real best
practice: *"always pin chart versions in production... never use
unversioned chart references in CI/CD."* Closes the supply-chain
concern already flagged in `docs/foundation_app_layering_and_iam_tiers.md`
Part C step 2 — the tooling supports what the design already required.

## 6. GCP VPC-discovery MCP gap — CORRECTED, narrower than stated
**This was genuinely incomplete research, not a confirmed absence.**
The original search looked for an MCP wrapper specifically around
`gcloud compute networks`/`subnets` commands and found nothing — but
never checked Google's own managed **Cloud Asset Inventory** MCP server
(`cloudasset.googleapis.com`), which has a real, documented `list_assets`
tool covering `compute.googleapis.com/Network` and
`compute.googleapis.com/Subnetwork` asset types directly, scoped at
project/folder/org level. For **existence-level discovery** — does a
given network resource exist, list everything of this type in this
project — the gap is closed, verified by direct inspection of the tool's
documented parameters (`docs/cross_project_network_sharing.md` Part H
has the detail).

**What remains genuinely gapped**: Cloud Asset Inventory's relationship
data doesn't clearly expose Shared VPC host/service project
relationships specifically (the "XpnResource" relationship type) —
relationship queries need Security Command Center Premium/Enterprise
tier, and the Shared VPC relationship wasn't confirmed as one of the
supported types even at that tier. So `getXpnHost`/`listUsable`
(`docs/cross_project_network_sharing.md` Part D) remain necessary for
resolving *which host project a service project is attached to* — a
narrower, real gap than "no live discovery path for the network layer
at all," which was the original, overstated claim.
`docs/foundation_discovery_and_capability_matching.md`'s original
finding and `docs/iac_based_discovery.md`'s Terraform-state-first /
Config-Connector fallback paths remain valid for what they were
actually verifying, just not the whole story.

## 7. Continuous-validation equivalents — confirmed, and one correction to the original framing
`docs/post_apply_smoke_testing.md` asked whether GCP/Azure have native
equivalents to Terraform's `check` blocks. **The framing itself was
slightly off**: `check` blocks are a Terraform-language feature,
provider-agnostic by construction — they already work identically for
GCP/Azure-managed resources, no separate "equivalent" is needed for
that specific mechanism.

What GCP/Azure *do* have, confirmed, is native **pre-apply policy
validation** (the layer `spec/check_compliance.py`/`cfn-guard` occupy
for AWS):
- **GCP**: `gcloud beta terraform vet` — validates a Terraform plan
  against Rego policies before apply, successor to the now-archived
  `terraform-validator`. **Reusable directly**: GCP's Policy Library
  ships *"100+ pre-built Rego policies... covering storage bucket
  public access to IAM privilege escalation prevention"* — this
  project's GCP-side compliance rules could adopt these rather than
  hand-writing GCP equivalents of `spec/reference_architecture.md`'s
  AWS-specific scenarios from scratch.
- **Azure**: Azure Policy, implementable as code via Terraform
  (`azurerm_policy_definition`) — already known from
  `docs/multi_cloud_foundation_and_iam.md`'s `CloudIAMAdapter` design,
  confirmed again here as the right mechanism, no new tool found beyond
  it.

## Summary: what changed, what's still open
| Item | Status after this pass |
|---|---|
| GCP impersonation-role escalation risk | **Resolved** — confirmed real, mitigation validated |
| Cloud Run MCP write capability | **Resolved** — confirmed real |
| Cloud Functions MCP | Still unconfirmed/likely absent |
| GCP project+billing linkage sequence | **Resolved** — exact two-call sequence confirmed |
| Azure subscription creation mechanics | **Resolved** — exact API, default-MG behavior, and a real failure mode confirmed |
| Helm chart version-pinning | **Resolved** — confirmed supported |
| GCP VPC-discovery MCP wrapper | **Corrected, later** — existence-level discovery closed by Google's own Cloud Asset Inventory MCP server (`list_assets`), not previously considered; Shared VPC host/service *relationship* resolution specifically remains gapped. See item 6's correction above and `docs/cross_project_network_sharing.md` Part H. |
| GCP/Azure "check block equivalent" | **Reframed** — check blocks are provider-agnostic; the real equivalent need was pre-apply policy validation, which does exist (`terraform vet` + Policy Library for GCP, Azure Policy for Azure) |

Five of eight resolved outright, one reframed into a better-fitting
answer, one corrected later to be narrower than originally claimed (not
unresearched, just incomplete — a real tool existed that wasn't
checked), one still open.

## How this relates to the existing docs
Updates the specific flags in `docs/multi_cloud_foundation_and_iam.md`,
`docs/compute_paradigm_layering.md`, `docs/account_vending_machine_design.md`,
`docs/eks_helm_mcp_integration.md`,
`docs/foundation_discovery_and_capability_matching.md`, and
`docs/post_apply_smoke_testing.md` — all six cross-linked back to this
doc. Resolves the first item in `docs/remaining_deep_dives.md`'s Tier 1.

## Sources
- [GCP Privilege Escalation: Exploiting TokenCreator Roles — Medium](https://medium.com/@spydernox/gcp-privilege-escalation-exploiting-tokencreator-roles-4b21677f9e57)
- [Google Cloud Platform (GCP) Service Account-based Privilege Escalation paths — Praetorian](https://www.praetorian.com/blog/google-cloud-platform-gcp-service-account-based-privilege-escalation-paths/)
- [GoogleCloudPlatform/cloud-run-mcp — GitHub](https://github.com/GoogleCloudPlatform/cloud-run-mcp)
- [Host MCP servers on Cloud Run — Google Cloud docs](https://docs.cloud.google.com/run/docs/host-mcp-servers)
- [Method: projects.create — Resource Manager, Google Cloud](https://cloud.google.com/resource-manager/reference/rest/v1/projects/create)
- [Enable, disable, or change billing for a project — Cloud Billing, Google Cloud docs](https://docs.cloud.google.com/billing/docs/how-to/modify-project)
- [Alias - Create — REST API (Azure Subscription), Microsoft Learn](https://learn.microsoft.com/en-us/rest/api/subscription/alias/create?view=rest-subscription-2021-10-01)
- [Programmatically create Azure Enterprise Agreement subscriptions — Microsoft Learn](https://learn.microsoft.com/en-us/azure/cost-management-billing/manage/programmatically-create-subscription-enterprise-agreement)
- [Microsoft.Subscription/aliases creation authorization issue — Azure/azure-rest-api-specs GitHub #14093](https://github.com/Azure/azure-rest-api-specs/issues/14093)
- [containers/kubernetes-mcp-server — GitHub](https://github.com/containers/kubernetes-mcp-server)
- [Policy validation — Terraform on Google Cloud docs](https://cloud.google.com/docs/terraform/policy-validation)
- [GoogleCloudPlatform/terraform-validator — GitHub (archived, migrate to `gcloud beta terraform vet`)](https://github.com/GoogleCloudPlatform/terraform-validator)
- [GCP Infrastructure Testing: Terratest, Config Validator, and Policy Library — Yuri Kan](https://yrkan.com/blog/gcp-infrastructure-testing/)
