## Status
Designed only. No code exists at `gateway/auth/providers/aws.py` — the
directory itself doesn't exist yet (confirmed via `find gateway -iname
"*provider*"`, empty). AWS API shapes verified 2026-08-14 directly
against current AWS docs (see Sources) for every call this doc
specifies. First deep dive on the AWS `CloudAccessAdapter`
implementation, per `EXECUTION_CREDENTIALS.md`'s build-order guidance
("contract + all-three fixtures first, real depth AWS-only").

## Decision: boto3, scoped to discovery only
`pyproject.toml` and `mcp_server/external_servers.py` record a
deliberate move away from boto3 for **provisioning** — CCAPI/CDK/
Terraform calls now route through `awslabs.aws-iac-mcp-server`,
`awslabs.ccapi-mcp-server`, and HashiCorp's `terraform-mcp-server`
instead. That reasoning does not transfer to discovery. Checked every
AWS MCP server this project uses or could plausibly adopt:

| Server | Covers IAM Identity Center / SSO Admin discovery? |
|---|---|
| `awslabs.aws-iac-mcp-server` (wired) | No — CDK docs/validation/lint only |
| `awslabs.ccapi-mcp-server` (wired) | No — Cloud Control API resource CRUDL; account assignments aren't a CCAPI-modeled resource type |
| HashiCorp `terraform-mcp-server` (wired) | No — Terraform-specific |
| `awslabs.iam-mcp-server` (not wired) | No — classic IAM (users/roles/policies/groups) only, explicitly not Identity Center |
| `awslabs.aws-api-mcp-server` (not wired, itself superseded) | Technically yes (generic AWS-CLI wrapper covering all commands), but needs the exact same IAM credentials boto3 would, and its own docs flag it as built for LLM-driven, prompt-injectable, single-tenant CLI invocation — the wrong threat model for deterministic, no-LLM-in-the-loop, login-time backend calls |

**Decision** (confirmed with the user 2026-08-14): reintroduce `boto3`
as a dependency scoped narrowly to `gateway/auth/providers/aws.py` —
read-only `sso-admin`/`identitystore` calls only. Provisioning stays
MCP-only; this doesn't touch that path. The distinction that matters:
provisioning is agentic (an LLM decides which mutating call to make on
a live request — MCP's subprocess/tool-call model fits), discovery is
deterministic plumbing (a fixed two-hop read sequence that must run
identically on every login — a Protocol method, not an LLM tool).

`pyproject.toml`'s "boto3 is no longer a direct dependency" comment
needs updating once this is implemented, to state the narrowed scope
rather than a blanket claim.

## Scope
This doc covers `CloudAccessAdapter.resolve_principal` and
`resolve_execution_grants` only (`EXECUTION_CREDENTIALS.md`'s Protocol,
`docs/EXECUTION_CREDENTIALS.md:201`). `acquire_plan_credentials`/
`acquire_apply_credentials`/`describe_current` are execution-time,
belong to a separate (Layer 1/2) identity, and are out of scope here —
see `EXECUTION_CREDENTIALS.md`'s Identity timeline.

## Call sequence
Five AWS calls, two services (`sso-admin`, `identitystore`), one
two-hop resolve. Verified against current AWS API docs 2026-08-14.

```
1. (config, not per-login) sso-admin:ListInstances
     -> InstanceArn, IdentityStoreId
     One IAM Identity Center instance per AWS Organization is the
     normal case; resolve once at deploy/config time, not per login.
     Response caps at 10 instances (API-documented max) -- if this
     account ever has more than one, config must disambiguate, this
     doc doesn't design that case.

2. identitystore:GetUserId(IdentityStoreId, AlternateIdentifier)
     -> UserId
     AlternateIdentifier.UniqueAttribute.AttributePath must be
     "userName" or "emails.value" (the API's only two valid paths --
     verified; no free-form claim mapping). Use "emails.value" against
     OIDCClaims.email, since Authentik SCIM-provisions the Identity
     Store user and email is the stable cross-system key already used
     elsewhere in this project's principal-ID mapping design
     (ACCESS_POLICY_AND_IAM_DISCOVERY.md's Principal-ID Mapping table:
     "AWS needs SCIM or lookup").

3. identitystore:ListGroupMembershipsForMember(IdentityStoreId,
   MemberId={UserId})
     -> GroupId[] (paginated, MaxResults <= 100, follow NextToken)
     Needed because account assignments can target a group principal,
     not just the user directly (ACCESS_POLICY_AND_IAM_DISCOVERY.md's
     Group Membership section: "AWS needs per-group
     ListAccountAssignmentsForPrincipal calls").

4. sso-admin:ListAccountAssignmentsForPrincipal(InstanceArn,
   PrincipalId, PrincipalType) -- once for PrincipalType=USER with the
   UserId, once more per GroupId from step 3 with PrincipalType=GROUP
     -> [{AccountId, PermissionSetArn}] (paginated, follow NextToken)
     Must be called from the IAM Identity Center management account
     (or a delegated administrator account) -- API-documented
     constraint, not this project's choice. The discovery identity's
     credentials must resolve to that account.

5. sso-admin:DescribePermissionSet(InstanceArn, PermissionSetArn) --
   once per unique PermissionSetArn seen across all of step 4's results
   (de-dupe first; the same permission set is commonly assigned across
   many accounts)
     -> Name
     Name is the only usable signal for capability normalization --
     PermissionSetArn is opaque, per ACCESS_POLICY_AND_IAM_DISCOVERY.md's
     Per-Provider Discovery Mechanics for AWS.
```

Total calls per login: `1 (cached) + 1 + 1 + (1 + groups) +
unique_permission_sets` — dominated by group count and distinct
permission-set count, not account count.

## Capability normalization
**Corrected 2026-08-14**: this section originally proposed storing the
mapping below in `access_templates.yaml`. That name was already taken
— `BOOTSTRAP_WORKFLOW.md` defines `access_templates.yaml` as
bootstrap-time workspace templates (tier → ceiling/execution-identity
pattern, consumed by `instantiate_template` when creating a *new*
project), a different concern from normalizing what an *existing*
permission set already grants. Caught while deep-diving that file's
schema; moved to its own name below rather than overloading one file
with two unrelated jobs (same reasoning `INTAKE_HITL_ROUTING.md:127`
already applied to the `gateway/policy.py` vs. `gateway/policy/`
collision — reconcile, don't pick one silently).

`DescribePermissionSet`'s `Name` string is org-defined free text — AWS
gives no structured capability field. Map `Name -> Capability` via a
lookup table stored in `gateway/policy/capability_mappings.yaml` (new
— not in `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s original Recommended
Storage list, added there now; see that doc's note). Per-provider,
since Azure's `roleName` and GCP's role strings need the same kind of
mapping (`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Per-Provider Discovery
Mechanics) — nest under an `aws:`/`azure:`/`gcp:` top key so one file
serves all three rather than one per provider.

### Boundary — what this file answers and what it deliberately doesn't
`capability_mappings.yaml` is a **trusted, versioned mapping from
provider-native access names to the PlatformOps capability ladder**. It
must never become a second source of user grants.

```
AWS permission assignment
  -> permission-set name
  -> capability_mappings.yaml normalization
  -> Capability
  -> account/project registry resolves Scope
  -> ExecutionGrant
```

It answers **"what does this provider role mean to PlatformOps?"** —
never "which users have this role" (provider discovery), "which
projects exist" (`project_registry.yaml`), "what is the policy
ceiling" (`org_bu_policy.yaml`), or "which credentials should be used"
(the `CloudAccessAdapter` credential methods). Contributes only the
first term of `effective_access` — and does so indirectly, through
`ExecutionGrant`, never by constructing one itself.

### Schema (v1)
```yaml
version: 1

providers:
  aws:
    permission_sets:
      - name: PlatformOpsViewer
        capability: describe
      - name: PlatformOpsPlanner
        capability: plan
      - name: PlatformOpsOperator
        capability: apply_limited
      - name: PlatformOpsAdmin
        capability: admin

  azure:
    role_definitions:
      - name: "<azure-role-definition-id-or-resolved-roleName>"
        capability: describe

  gcp:
    roles:
      - name: roles/viewer
        capability: describe
      - name: roles/editor
        capability: apply_limited
```
For the immediate AWS slice, the file can start with just the `aws:`
section — `azure`/`gcp` sections are additive, not required day one.

**Azure's `name` field, called out explicitly**: unresolved which
identifier goes here — the opaque `roleDefinitionId` (stable across
renames, matches how AWS's `PermissionSetArn` is opaque) or the
resolved `roleName` string (human-authorable, matches how this file
matches AWS by `Name` not ARN). Deferred — Azure discovery isn't
designed to two-hop-resolution depth yet
(`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Per-Provider Discovery
Mechanics names the same `roleDefinitionId -> GET -> roleName` shape
AWS has, so whichever this project picks for AWS's `Name` field should
probably decide Azure's too, when that doc gets its own deep dive).

### Exact matching only — no regex, no wildcards
```
PlatformOpsViewer -> describe        # correct
*Admin* -> admin                     # do not do this
```
Role/permission-set names are **organization-controlled input**, not
PlatformOps-controlled. A wildcard rule can silently reclassify a
permission set nobody reviewed against this file — the opposite of the
fail-closed posture the rest of this design commits to. Unknown names
must resolve to `Capability.NONE`, never raise and never default
upward; the discovery code (not this file) should also record an
evidence message — `unmapped AWS permission set 'BillingPowerUser' ->
none` — so a real access gap is visible in evidence, not silently
dropped.

### Pydantic shape
```python
class AccessMapping(BaseModel):
    name: str = Field(min_length=1)
    capability: Capability


class AwsAccessMappings(BaseModel):
    permission_sets: list[AccessMapping] = Field(default_factory=list)


class AzureAccessMappings(BaseModel):
    role_definitions: list[AccessMapping] = Field(default_factory=list)


class GcpAccessMappings(BaseModel):
    roles: list[AccessMapping] = Field(default_factory=list)


class ProviderAccessMappings(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unsupported provider
                                                # sections must raise,
                                                # not silently no-op
    aws: AwsAccessMappings = Field(default_factory=AwsAccessMappings)
    azure: AzureAccessMappings = Field(default_factory=AzureAccessMappings)
    gcp: GcpAccessMappings = Field(default_factory=GcpAccessMappings)


class CapabilityMappingConfig(BaseModel):
    version: Literal[1]
    providers: ProviderAccessMappings
```

### Validation must reject
| Case | Why |
|---|---|
| Missing or unsupported `version` | Free (required field, no default — forces every real file to declare it, unlike the `path is None` empty-config case a loader handles separately) |
| Blank names | `Field(min_length=1)` |
| Unknown capabilities | Free — `Capability` is a `str` `Enum`, pydantic rejects unrecognized values |
| Duplicate names within a provider's list | Needs a `model_validator` — **any** duplicate, even one where both rows agree on the same capability, since an accidental duplicate is still an authoring mistake worth surfacing, and there's no cost to full strictness on a file this security-sensitive |
| Duplicate mappings with different capabilities | Subsumed by the rule above — no separate check needed once *any* duplicate name is rejected |
| Unsupported provider sections (e.g. a typo`awss:`) | `ConfigDict(extra="forbid")` on `ProviderAccessMappings` |

**Do not silently keep the last duplicate YAML key** — PyYAML's
default `safe_load` already does this for literal duplicate mapping
keys before pydantic even sees the data, which is exactly the failure
mode the duplicate-name validator exists to catch at the list level
(YAML's own dict-key collision only protects against duplicate
*top-level* keys, not duplicate `name:` values inside a list — the
shape this file actually uses).

### Worked example — the one `AWS_PROVIDER_DISCOVERY.md`'s call sequence produces
```
AWS discovery returns:
  {"AccountId": "123456789012",
   "PermissionSetArn": "arn:aws:sso:::permissionSet/...",
   "PermissionSetName": "PlatformOpsOperator"}

PlatformOpsOperator
  -> capability_mappings.yaml            -> apply_limited
  -> account_id 123456789012
  -> project_registry.yaml reverse lookup -> aiq:it/invoices/dev
  -> ExecutionGrant(
       scope=Scope(org="aiq", bu="it", project="invoices", workspace="dev"),
       provider="aws",
       capability=Capability.APPLY_LIMITED,
     )
```
This is the same `AccountId -> Scope` reverse-lookup dependency on
`project_registry.yaml` flagged above — shown here end-to-end to make
the full chain concrete.

## AccountId -> Scope: the reverse lookup this design needs and doesn't have yet
Step 4 returns `AccountId` per assignment; `ExecutionGrant.scope`
(`gateway/auth/schemas.py:78`) needs a `Scope` (org/bu/project/
workspace — `gateway/schemas.py:34`), not an AWS account ID. The
recommended `project_registry.yaml` is keyed the other direction
(`Scope -> account_id/region/role_arn`, per
`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Recommended Storage). Building
`resolve_execution_grants` therefore also needs an `account_id ->
Scope` reverse index built from that registry at load time. Not
designed further here — flagged as a dependency of this doc's scope,
not a gap in this doc alone, since `project_registry.yaml` itself
doesn't exist yet either.

## Required IAM permissions — the discovery identity
Per Layer 0 in `EXECUTION_CREDENTIALS.md`'s Identity timeline: a
runtime root identity, narrow and read-only, distinct from any Layer 1
per-workspace execution identity.

```
sso-admin:ListInstances
sso-admin:ListAccountAssignmentsForPrincipal
sso-admin:DescribePermissionSet
identitystore:GetUserId
identitystore:ListGroupMembershipsForMember
```

No write actions. No `sts:AssumeRole` needed for discovery itself —
that's Layer 1/2's concern, not this doc's. Credentials for this
identity come from the runtime's own environment (env vars / instance
profile / whatever `EXECUTION_CREDENTIALS.md`'s Layer 0 resolves to),
never from the logging-in user — consistent with
`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s "No User-Supplied Cloud
Credentials, Ever."

## Real vs. Designed
| Piece | Status |
|---|---|
| `gateway/auth/providers/` package, `aws.py` | Does not exist |
| `boto3` as a dependency | Not present — `ModuleNotFoundError` confirmed via `.venv/bin/python -c "import boto3"` 2026-08-14 |
| `gateway/policy/capability_mappings.yaml` | Does not exist |
| `gateway/policy/project_registry.yaml` (+ account_id reverse index) | Does not exist |
| AWS API call shapes in this doc | Verified against current AWS docs 2026-08-14 (see Sources) — design only, unimplemented |

## Open questions
| Question | Why it's open |
|---|---|
| Does Authentik's SCIM provisioning to AWS Identity Center guarantee `emails.value` is populated and matches the OIDC claim's email exactly? | Unverified against a live SCIM sync — `IDP_SELECTION.md` picked Authentik partly for SCIM fit but this project has no live AWS Identity Center to test against yet |
| Cache discovery results across a session, or re-run all 5 calls every login? | No caching layer designed; likely fine to leave per-login for MVP given call count is small, revisit if group-membership fan-out gets large |
| Multiple IAM Identity Center instances in one AWS Organization | `ListInstances` caps at 10; this doc assumes exactly one and doesn't design disambiguation |

## Sources
- [ListAccountAssignmentsForPrincipal](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_ListAccountAssignmentsForPrincipal.html)
- [DescribePermissionSet](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_DescribePermissionSet.html)
- [ListInstances (SSO Admin)](https://docs.aws.amazon.com/singlesignon/latest/APIReference/API_ListInstances.html)
- [GetUserId (Identity Store)](https://docs.aws.amazon.com/singlesignon/latest/IdentityStoreAPIReference/API_GetUserId.html)
- [ListGroupMembershipsForMember (Identity Store)](https://docs.aws.amazon.com/singlesignon/latest/IdentityStoreAPIReference/API_ListGroupMembershipsForMember.html)
- [AWS IAM MCP Server](https://awslabs.github.io/mcp/servers/iam-mcp-server)
- [AWS API MCP Server](https://awslabs.github.io/mcp/servers/aws-api-mcp-server)

## How this relates to the existing docs
Implements the AWS half of `ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s
Per-Provider Discovery Mechanics section and `EXECUTION_CREDENTIALS.md`'s
`CloudAccessAdapter` build-order recommendation ("real depth
AWS-only"). Doesn't repeat either doc's capability-ladder or
precedence-rule reasoning — see those docs directly. Corrects nothing
in place; the boto3-avoidance comments in `pyproject.toml` and
`mcp_server/external_servers.py` remain accurate for provisioning, this
doc just scopes discovery as an explicit exception rather than
contradicting them.
