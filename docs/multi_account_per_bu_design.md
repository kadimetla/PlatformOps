# Multi-Account Per BU — `CloudAccountBinding`

## Status
Design only. Corrects the prior turn's recommendation ("one BU = one
AWS account / GCP project / Azure subscription") — grounded against
AWS's own multi-account guidance, that was too narrow. Nothing here is
built; `WorkspaceBundle` (`harness/schemas.py:25-36`) still has the flat
single-account shape this doc proposes replacing.

## Part A: The correction — multiplicity is on the BU side, not the sharing side
AWS's own guidance, confirmed directly: *"use different accounts for
different environments like development, staging, and production"* and
*"assign a single workload to each production account or assign a
small set of closely related workloads to each production account."*
One team, several accounts, by design — not an edge case.

The invariant this project already enforces at the `agent_id` level
(*"never reuse `agentId` across BUs... it causes auth/session
collisions,"* `docs/HARNESS_DESIGN.md`) is narrower than "one account
per BU." The actual rule: **no single account/project/subscription is
ever shared across two different BUs.** Multiplicity on one BU's side
is fine and expected; sharing across BUs never is.

Multi-cloud within one BU is common, not hypothetical — confirmed
*"87% of enterprises are multi-cloud today,"* though often *"by
accident from different teams choosing different providers, M&A
activity, or SaaS adoption"* rather than deliberate design. This design
has to handle deliberate and accidental multi-cloud identically — a
`CloudAccountBinding` doesn't record *why* an account exists, just that
it does.

## Part B: `CloudAccountBinding` — replaces the flat single-account fields
```python
class CloudAccountBinding(BaseModel):
    binding_id: str
    org_id: str
    bu_id: str
    cloud_provider: str          # "aws" | "gcp" | "azure"
    account_identifier: str      # AWS account ID | GCP project ID | Azure subscription ID
    purpose: str                 # "prod" | "dev" | "staging" | org-defined convention
    region: Optional[str] = None # per-binding, not per-BU — accounts can differ by region
    auth_ref: dict
    # role_arn (AWS, via sts:AssumeRole) | service_account_email (GCP,
    # via impersonation) | pim_role_definition_id (Azure, via
    # just-in-time PIM activation) — the authentication mechanics
    # already designed, now scoped per-binding instead of per-BU
    is_default: bool = False
```
`WorkspaceBundle` gains `cloud_accounts: list[CloudAccountBinding]`,
replacing the current flat `aws_region`/`aws_profile`/`tfe_workspace`
fields (`harness/schemas.py:27-31`) that implied exactly one account.
This is a structural change to a *real, currently-built* schema, not an
additive sketch on top of a design-only one — worth flagging explicitly
since most prior schema proposals in this doc set were additive.

## Part C: `FoundationRecord` needs to know *which* account, not just which cloud
A BU with two AWS accounts (dev + prod) needs its network→compute→
identity chain (`docs/foundation_layer_decomposition.md`) tracked
**independently per account** — two chains, potentially different
`compute_paradigm` choices per account
(`docs/compute_paradigm_layering.md`), not one chain disambiguated only
by `cloud_provider`.
```python
class FoundationRecord(BaseModel):
    ...  # existing fields (foundation_id, org_id, bu_id, cloud_provider,
    #      layer, depends_on_foundation_id, compute_paradigm, resource_type,
    #      resource_identifier, approved_plan_id, status, provenance,
    #      discovered_capabilities)
    cloud_account_binding_id: str  # NEW — which CloudAccountBinding this
                                    # layer belongs to; cloud_provider alone
                                    # is no longer sufficient disambiguation
```

## Part D: Discovery runs per binding, not per BU
`docs/foundation_discovery_and_capability_matching.md`'s three-branch
flow (reuse / create-new / adopt-unmanaged) now runs once per
`CloudAccountBinding`, independently. A BU's dev account might be
freshly created, its prod account discovered-and-reused, and a third
region-specific account found unmanaged and needing adoption review —
all simultaneously, all legitimate, none of it collapsible into one
BU-level discovery pass the way the prior design assumed.

## Part E: Routing has to resolve *which* binding, with a safety rule for ambiguity
A request that doesn't explicitly name an environment can fall back to
`is_default=True` for low-risk app-tier work. **New rule**: default
fallback is disallowed — explicit selection required — whenever
multiple bindings could plausibly match, or whenever the target
resource type's `review_policy` sits at a tier where silently landing
in the wrong account (especially `purpose="prod"`) would be dangerous.
This gives `review_policy` a second axis, independent of the
foundation/app tier already established: **a `purpose="prod"` binding
can require the external-ticket approval path
(`docs/external_ticket_approval_integration.md`) regardless of resource
type**, not just because a resource happens to be foundation-tier.

## Part F: New-account provisioning reuses the existing onboarding design
AWS's own recommendation — *"don't create accounts manually, use an
account vending machine that applies security baselines
automatically"* — matches what this project already sketched as the
`BOOTSTRAP.md`-equivalent BU onboarding ritual
(`docs/skills_and_workspace_design.md`: *"a `BOOTSTRAP.md`-equivalent
ritual, run once when a new `agent_id` is minted, collecting cloud
account, initial `allowed_resource_types`, initial cost ceiling..."*).
**Extension, not a new mechanism**: minting a new `CloudAccountBinding`
for an *existing* BU (a new environment, a new region, a new cloud)
should go through the same automated, baseline-applying ritual —
scoped to one binding instead of the whole BU's first onboarding.

## Open questions / not yet decided
- Whether `cost_ceiling_usd`/`allowed_resource_types` should also become
  per-binding (a prod account plausibly needs a different ceiling and a
  tighter allow-list than dev) rather than staying BU-level — likely
  yes eventually, not decided as a hard requirement here.
- Exact ambiguity-detection rule for Part E ("multiple bindings could
  plausibly match") — sketched as a principle, not a concrete algorithm.
- Whether `purpose` should be a closed enum (`"prod"|"staging"|"dev"`)
  or free-text per org convention — leaning free-text with `"prod"`
  specifically recognized by the routing/policy logic, not decided.

## How this relates to the existing docs
- Corrects the "one BU = one account" framing from the prior design
  turn (not written up as its own doc, so this is the first place that
  framing appears in writing, immediately superseded here).
- Extends `FoundationRecord` (`docs/foundation_app_layering_and_iam_tiers.md`
  Part D, `docs/foundation_layer_decomposition.md`,
  `docs/compute_paradigm_layering.md`) with `cloud_account_binding_id`.
- Extends `docs/foundation_discovery_and_capability_matching.md`'s
  discovery flow from per-BU to per-binding.
- Extends `docs/external_ticket_approval_integration.md`'s
  `review_policy` with a `purpose`-based axis, independent of resource
  tier.
- Extends `docs/skills_and_workspace_design.md`'s BU onboarding ritual
  to cover per-binding onboarding, not just first-time BU setup.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Organizing Your AWS Environment Using Multiple Accounts — AWS whitepaper](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/organizing-your-aws-environment.html)
- [Design principles for your multi-account strategy — AWS whitepaper](https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/design-principles-for-your-multi-account-strategy.html)
- [Best practices for a multi-account environment — AWS Organizations docs](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_best-practices.html)
