# Org Bootstrap — Why Steps 1–2 Are Out-of-Band, Not Just Unautomated

## Status
Design only. Answers `docs/org_registry_design.md`'s open item ("exact
process for step 2... needs hands-on verification") with a conclusion
sharper than "not yet automated": the first two steps of the onboarding
sequence **cannot and should not** go through the harness's own
agent-driven flow at all, for two independent reasons — a structural
bootstrapping paradox and a privilege-boundary argument. Verified the
real APIs exist (`CreateOrganizationalUnit`, `folders.create`, Azure
Management Groups) — see Sources — but the finding here is about
*where this belongs*, not the API calls themselves.

## Part A: The chicken-and-egg problem
Every request in this design — `RequestEnvelope`, the entire 8-step
flow in `spec/flow_steps/` — assumes `org_id`/`bu_id` are already
resolved via a binding lookup (`config/bindings.yaml`, or the org
registry once it exists). **Org registration is the act of creating
that `org_id` in the first place.** There is no binding to resolve to
yet. Step 1 (org registration), and step 2 (cloud anchor creation,
which depends on step 1 already existing), structurally cannot be
modeled as a request going through the normal flow — not a missing
integration, an incompatible shape.

## Part B: The privilege problem — the sharper of the two
Even setting Part A aside: should the harness's own automation identity
(the STS-assumed role / impersonated service account / PIM-activated
role designed in the account/authentication-mechanics work) ever be
granted the privilege to create an AWS OU, a GCP folder, or an Azure
management group? **No.** This is the single highest-blast-radius
privilege in the entire design — not "modify one BU's resources," but
"restructure the container every org's isolation boundary depends on."
Confirmed by the research itself: cloud guidance emphasizes designing
OU/folder/management-group structure around **policy needs specifically
because SCPs and policies attach to the hierarchy** — a compromised or
malfunctioning agent with this privilege could affect every policy
inheriting through it, across every BU, in every org.

## Part C: The conclusion — out-of-band by design, with real precedent
Not a gap to close — the correct shape, and one this project's own
research already implied without stating explicitly. **AFT itself
doesn't create the AWS Organization.** It assumes Control Tower is
already running, set up once by a human with actual org-root access,
before AFT's own automation starts at all.
`docs/account_vending_machine_design.md` already scoped its design to
begin *after* that anchor exists (Part B step 5 of the five-step
sequence) — this doc makes explicit what was already implicit there.

The dividing line, consistent with every other boundary already drawn
in this design: **"creates a new isolation boundary"** (human,
out-of-band, once) vs. **"operates within an existing one"** (harness,
automated, repeatable). Steps 3–5 of `docs/org_registry_design.md`'s
sequence stay exactly as designed — org-level defaults are config
writes gated by `OrgMember(role="admin")`, BU onboarding and account
vending were already fully designed as harness-automatable.

## Part D: The concrete mechanism
Reuses what's already established rather than inventing a new tool
category:

1. **A one-time Terraform module**, `platformops/org-bootstrap`,
   applied manually by a human holding their own already-privileged
   cloud credentials — never the harness's automation identity, never
   through `BrokeredToolDispatcher`. Consistent with this project's
   IaC-first bias (`IacSourceRef`, `docs/iac_based_discovery.md`)
   rather than a bespoke script:
   ```hcl
   module "org_bootstrap" {
     source  = "platformops/org-bootstrap/aws"  # or /gcp, /azure
     org_id  = "acme"
     org_name = "Acme Corp"
   }
   # outputs: aws_ou_id, gcp_folder_id, azure_management_group_id,
   #          azure_entra_tenant_id — fed directly into OrgRegistryEntry
   ```
2. **`OrgRegistryEntry` creation is harness-automatable** — writing a
   config record from the module's outputs is not a privileged cloud
   operation, unlike creating the anchor itself.
3. **A new diagnostic CLI command**, fitting the family
   `docs/HARNESS_DESIGN.md` already sketched (`platformops doctor`,
   `platformops bindings list --effective`):
   `platformops org bootstrap --verify` — checks the anchors referenced
   in an `OrgRegistryEntry` actually exist and are correctly scoped,
   without ever being the thing that creates them. A read-only
   verification tool, not a provisioning one.

## Open questions / not yet decided
- Whether `platformops/org-bootstrap`'s Terraform module should be one
  module with provider-conditional logic, or three separate per-cloud
  modules (`-aws`, `-gcp`, `-azure`) — sketched as separate above,
  leaning toward that for the same reason `CloudIAMAdapter` is one
  interface with per-provider implementations rather than one
  monolithic function, not fully decided.
- Who holds the "own already-privileged cloud credentials" in practice
  for a managed SaaS deployment (this project's own operator?) vs. a
  self-hosted deployment (the adopting org's own admin) — the trust
  model differs by deployment mode and isn't fully worked out.
- Whether `platformops org bootstrap --verify` should also detect and
  flag anchor-level policy drift (someone manually changed an SCP at
  the OU level outside the bootstrap module) — not designed, a natural
  extension of the drift-reconciliation pattern already established in
  `docs/infra_discovery_and_platform_app_split.md` Part A, but not
  applied here yet.

## How this relates to the existing docs
- Directly answers `docs/org_registry_design.md`'s open item on step 2's
  process — with a conclusion (out-of-band, not harness-automated) it
  hadn't reached.
- Makes explicit what `docs/account_vending_machine_design.md` already
  implied by only ever covering step 5 of the sequence.
- Extends the diagnostic-CLI family named in `docs/HARNESS_DESIGN.md`'s
  "Borrow: health, doctor, and runtime inspection" section with one new
  command.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [CreateOrganizationalUnit — AWS Organizations API Reference](https://docs.aws.amazon.com/organizations/latest/APIReference/API_CreateOrganizationalUnit.html)
- [Set up a Google Cloud organization resource — Google Cloud docs](https://docs.cloud.google.com/resource-manager/docs/creating-managing-organization)
- [gcp.organizations.Folder — Pulumi Registry](https://www.pulumi.com/registry/packages/gcp/api-docs/organizations/folder/)
