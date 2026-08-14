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
`DescribePermissionSet`'s `Name` string is org-defined free text — AWS
gives no structured capability field. Map `Name -> Capability` via a
lookup table stored in `gateway/policy/access_templates.yaml`
(`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s Recommended Storage, not yet
created — currently only `ceiling.py` exists under `gateway/policy/`).
Example shape:

```yaml
aws_permission_set_capability:
  PlatformOpsViewer: describe
  PlatformOpsPlanner: plan
  PlatformOpsOperator: apply_limited
  PlatformOpsAdmin: apply_full
```

Unrecognized `Name` values must resolve to `Capability.NONE`, not raise
and not default upward — an unmapped permission set is exactly the
"fail closed on the unknown" case the rest of this project's access
design already commits to (`ACCESS_POLICY_AND_IAM_DISCOVERY.md`'s core
decision).

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
| `gateway/policy/access_templates.yaml` | Does not exist |
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
