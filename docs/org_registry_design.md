# Org Registry — Design

## Status
Design only. Resolves a gap referenced 25+ times across 9 other docs
but never itself designed — every prior mention was a one-line pointer
back to `docs/HARNESS_DESIGN.md`'s single sketch: *"a config store
mapping `org_id → [{bu_id, agentId, workspace_bundle_ref}]"*. This is
what that store actually needs to hold, and the onboarding sequence it
implies but never stated.

## Part A: What has to live here — pulled together from everywhere it's been assumed
| Data | Already designed in | Prior status |
|---|---|---|
| Org identity/metadata (name, allowed domains/channels) | `docs/HARNESS_DESIGN.md`'s `orgs.yaml` sketch | Named, never schemad |
| BU membership: `{bu_id, agent_id, workspace_bundle_ref}` | Same doc's core sketch | The one part with real shape |
| Org-level skills directory (`orgs/<org_id>/skills/`) | `docs/skills_and_workspace_design.md` | Path convention only |
| Org-level `IacSourceRef` default | `docs/iac_based_discovery.md` — explicitly *"blocked on the... org-registry work"* | Named as blocked |
| Cloud hierarchy anchors — AWS OU, GCP folder, Azure management group | `docs/multi_account_per_bu_design.md` Part A | Named as a mapping, never stored |
| Azure Entra tenant ID | `docs/multi_account_per_bu_design.md`'s tenant constraint | Referenced as a rule, never registry data |
| Org-level `review_policy` defaults | Implied by every BU-level mention | Never stated explicitly at org level before now |
| Required isolation level (BU/Org/Host scope) | `docs/HARNESS_DESIGN.md`'s isolation table | Never attached to a specific org's entry |

## Part B: The onboarding sequence — never laid out end to end before
`docs/account_vending_machine_design.md` designed how to vend a **BU's
cloud account**, implicitly assuming a target AWS OU / GCP folder /
Azure management group already existed to vend into. Nothing designed
who creates that anchor, or when — an org-registry-level problem, one
step above account vending:

```
1. Org registration        — org_id, metadata, isolation level decided
2. Org-level cloud anchors  — AWS OU, GCP folder, Azure mgmt group +
                               Entra tenant, created ONCE per org
3. Org-level defaults set  — skills, IacSourceRef, review_policy
4. BU onboarding (repeatable)   — BOOTSTRAP.md ritual, mints agent_id +
                                    workspace_bundle_ref
5. Account vending (repeatable, per BU) — the AFT-shaped pipeline from
                                            docs/account_vending_machine_design.md,
                                            vending INTO the anchor from step 2
```
`docs/account_vending_machine_design.md` only ever covered step 5.
Steps 1–3 are new; step 4 already existed as the `BOOTSTRAP.md`
sketch (`docs/skills_and_workspace_design.md`) but had no registry to
record itself into.

## Part C: `OrgMember` — the missing org-level actor
`TeamMember` (`docs/skills_and_workspace_design.md`) is entirely scoped
to a `WorkspaceBundle` — `role`×`scope` only make sense *within* a BU.
Nothing today expresses "who can create a new BU under this org" or
"who can change an org-level default." `docs/personas_and_tool_blueprints.md`
named the "Org Admin" persona with nowhere to attach it. This closes
that: a small, separate concept parallel to `TeamMember`, scoped to
`org_id` instead of `bu_id`. Org-level actions are inherently
high-stakes, so a single `role="admin"` is sufficient — none of
`TeamMember`'s three-tier requester/approver/admin nuance is needed
here.

## Part D: Schema
```python
class BuMembership(BaseModel):
    bu_id: str
    agent_id: str
    workspace_bundle_ref: str

class OrgMember(BaseModel):
    channel_user_id: str
    display_name: str
    role: str = "admin"

class OrgRegistryEntry(BaseModel):
    org_id: str
    name: str
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_channels: list[str] = Field(default_factory=list)
    business_units: list[BuMembership] = Field(default_factory=list)
    members: list[OrgMember] = Field(default_factory=list)

    # Cloud hierarchy anchors — created once, Part B step 2, before any
    # BU vends an account into them
    aws_ou_id: Optional[str] = None
    gcp_folder_id: Optional[str] = None
    azure_management_group_id: Optional[str] = None
    azure_entra_tenant_id: Optional[str] = None

    # Org-level defaults — BU overrides per the bundled→org→BU
    # precedence already established for skills (docs/skills_and_workspace_design.md)
    # and IacSourceRef (docs/iac_based_discovery.md)
    default_iac_source: Optional["IacSourceRef"] = None
    default_review_policy_ref: Optional[str] = None

    isolation_level: str = "bu_scope"  # "bu_scope" | "org_scope" | "host_scope"
    runtime_namespace_ref: Optional[str] = None  # populated only when
                                                   # isolation_level demands
                                                   # a dedicated runtime
```

## Part E: Storage — applying, not re-deciding, `docs/config_storage_backend.md`
That doc already decided *how* config storage should split (YAML+git
for self-hosted, a database for managed multi-org SaaS) — it never
applied the decision to this specific data. Applied here:
- **Self-hosted, single org**: `OrgRegistryEntry` is a single YAML
  file, barely more than what `docs/HARNESS_DESIGN.md` already
  sketched as `orgs.yaml`.
- **Managed SaaS**: `OrgRegistryEntry` is the **first row created** in
  whatever database `docs/config_storage_backend.md`'s `DbConfigLoader`
  uses — every other per-org record (`WorkspaceBundle`,
  `FoundationRecord`, `CloudAccountBinding`) hangs off `org_id` as a
  foreign key into this table, not a separately-bootstrapped store.

## Open questions / not yet decided
- Whether `OrgMember` needs its own audit trail distinct from
  `TeamMember`'s, given org-level actions (creating a BU, changing a
  default) are rarer but higher-blast-radius than most BU-level ones —
  not decided.
- **Answered in `docs/org_bootstrap_privilege_boundary.md`**: step 2
  (cloud anchor creation) turns out not to be a "how" question at all —
  it's structurally out-of-band, a one-time human-applied Terraform
  module, never the harness's own automation identity, for both a
  bootstrapping-paradox reason (no `org_id` exists yet to route a
  request through) and a privilege-boundary reason (creating an OU/
  folder/management-group is the highest-blast-radius action in this
  whole design).
- Whether `isolation_level` should be settable only at org creation
  time (immutable) or changeable later — changing it after BUs already
  exist under the org has real migration implications not analyzed
  here.

## How this relates to the existing docs
- Directly resolves the open item every one of the following docs
  pointed at without designing: `docs/HARNESS_DESIGN.md` (the original
  sketch and its "Adoption story"/open-questions sections),
  `docs/iac_based_discovery.md` (explicitly blocked on this),
  `docs/skills_and_workspace_design.md` (org-level skills directory),
  `docs/multi_account_per_bu_design.md` (cloud hierarchy anchors),
  `docs/personas_and_tool_blueprints.md` (the Org Admin persona).
- Sits one layer above `docs/account_vending_machine_design.md` in the
  onboarding sequence — that doc's pipeline is Part B step 5 here, not
  a competing design.
- Applies, without changing, the storage-backend decision in
  `docs/config_storage_backend.md`.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
