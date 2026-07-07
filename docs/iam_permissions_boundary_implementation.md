# IAM Permissions Boundary — Concrete Implementation

## Status
Design only — nothing here is built. Two prior docs
(`docs/foundation_app_layering_and_iam_tiers.md`,
`docs/infra_discovery_and_platform_app_split.md`) asserted
"`AWS::IAM::Role` requires a permissions boundary" as a rule without ever
specifying the mechanism. This is that mechanism, verified against AWS's
own prescriptive guidance (see Sources) rather than asserted.

## What a permissions boundary actually is
A managed policy that caps the **maximum effective permissions** of
whatever it's attached to — the role's real permissions become the
*intersection* of its identity policy (what's directly attached) and its
boundary. Attaching `AdministratorAccess` to a role with a narrow
boundary doesn't make it an admin; effective permissions collapse to
whatever the boundary allows, regardless of what's attached alongside it.

## The part every prior doc here skipped: attaching it once isn't enough
A permissions boundary is a **two-part requirement**, not a single
checkbox:
1. **Forced at creation time** — via a condition on the *creator's own*
   IAM policy, not a property the agent optionally remembers to set.
2. **Un-removable afterward** — otherwise a role gets created correctly,
   then the boundary is simply detached in a second call, and part 1's
   protection was theater.

### The real pattern, sourced from AWS Prescriptive Guidance
```yaml
DeveloperBoundary:
  Type: "AWS::IAM::ManagedPolicy"
  Properties:
    PolicyDocument:
      Statement:
        - Sid: AllowModifyIamRolesWithBoundary
          Effect: Allow
          Action:
            - "iam:CreateRole"
            - "iam:AttachRolePolicy"
            - "iam:PutRolePolicy"
            - "iam:PutRolePermissionsBoundary"
          Resource: "arn:aws:iam::ACCOUNT:role/app/*"
          Condition:
            ArnEquals:
              "iam:PermissionsBoundary": "arn:aws:iam::ACCOUNT:policy/PermissionsBoundary"
        - Sid: OverlyPermissiveAllowedServices
          Effect: Allow
          Action: ["lambda:*", "s3:*", "logs:*", "..."]
          Resource: "*"
```
Two mechanics worth being precise about, since together they're the
whole protection:
- **Self-referential condition**: the boundary policy's own ARN appears
  inside its own `ArnEquals` condition — `iam:CreateRole` only succeeds
  if the role being created is *itself* getting this exact boundary
  attached in the same call. This forces requirement 1.
- **`iam:DeleteRolePermissionsBoundary` is absent from the allow-list.**
  Because this is a narrow, default-deny allow-list policy, omitting the
  action is sufficient — no explicit `Deny` statement is required, though
  it's a reasonable belt-and-suspenders addition (see Open questions).
  This achieves requirement 2.

## Concrete implementation for this project

### New file: `infra/permissions-boundary-policy.json`
The ceiling policy, referenced by ARN, attached to every agent-created
role. Its `Action` list must be a **subset** of `infra/iam-policy.json`'s
own scope — a boundary can never be looser than the credential creating
it, or it isn't actually a ceiling:
```json
{
  "_comment": "Ceiling policy attached via PermissionsBoundary to every AWS::IAM::Role this project's agents create. A role bounded by this policy can never exceed what's listed here, regardless of what identity policy gets attached to it later. Must stay a subset of infra/iam-policy.json's own action scope.",
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PlatformOpsDemoWorkloadCeiling",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket",
        "cloudfront:GetDistribution"
      ],
      "Resource": "*",
      "Condition": {
        "StringLike": {
          "aws:RequestTag/Name": "platformops-demo-*"
        }
      }
    }
  ]
}
```

### `infra/iam-policy.json` gains a new statement
Same pattern as the sourced example, adapted to this project's existing
`platformops-demo-*` naming convention:
```json
{
  "Sid": "PlatformOpsDemoRoleCreationRequiresBoundary",
  "Effect": "Allow",
  "Action": [
    "iam:CreateRole",
    "iam:AttachRolePolicy",
    "iam:PutRolePolicy",
    "iam:PutRolePermissionsBoundary"
  ],
  "Resource": "arn:aws:iam::*:role/platformops-demo-*",
  "Condition": {
    "ArnEquals": {
      "iam:PermissionsBoundary": "arn:aws:iam::ACCOUNT_ID:policy/PlatformOpsDemoPermissionsBoundary"
    }
  }
}
```
`iam:DeleteRolePermissionsBoundary` intentionally stays absent — same
mechanism as the sourced example.

### `WorkspaceBundle` gains a per-BU boundary reference
```python
class WorkspaceBundle(BaseModel):
    ...
    permissions_boundary_arn: Optional[str] = Field(
        None,
        description=(
            "IAM policy ARN attached as PermissionsBoundary to every role "
            "this BU's agents create. Required if AWS::IAM::Role is ever "
            "in allowed_resource_types for this BU."
        ),
    )
```
Per-BU, not global — the same shape as `cost_ceiling_usd` and
`aws_profile` are already scoped per-BU. A stricter BU (e.g., a
PCI-scoped Payments BU) can reference a tighter boundary than a
less-regulated one, rather than one boundary fitting every tenant.

### `BrokeredToolDispatcher.evaluate_intent()` gains a new check
The application-level layer — catches a malformed agent-drafted request
*before* it ever reaches AWS, rather than relying solely on the IAM
condition to reject it. Same deny-by-default style as the dispatcher's
existing resource-type/region checks (`harness/tool_dispatcher.py:63-75`):
```python
if resource_type == "AWS::IAM::Role":
    boundary_arn = bundle.permissions_boundary_arn
    if not boundary_arn:
        self._log_audit(
            intent, "DENY",
            f"BU {bu_id} has no permissions_boundary_arn configured; cannot create IAM roles",
        )
        return False
    payload_boundary = intent.get("payload", {}).get("PermissionsBoundary")
    if payload_boundary != boundary_arn:
        self._log_audit(
            intent, "DENY",
            f"AWS::IAM::Role intent missing or mismatched PermissionsBoundary (expected {boundary_arn})",
        )
        return False
```
This slots in alongside the existing resource-type and region checks,
before the approval-record lookup — same position in the function, same
fail-closed shape.

## Four layers, not one
Matches this project's existing defense-in-depth framing
(`docs/current_architecture.md`):

| Layer | What it catches | Bypassable by an app bug? |
|---|---|---|
| 1. AWS IAM itself (`ArnEquals` condition) | Any `CreateRole` call missing the exact boundary, enforced at the API layer | No — outside this codebase entirely |
| 2. The boundary policy's own ceiling | A role that somehow got an overly-permissive identity policy attached later | No — AWS-enforced at every call the role makes |
| 3. `BrokeredToolDispatcher` (new check above) | A malformed `ToolIntent` missing/wrong `PermissionsBoundary`, before it reaches AWS at all | Yes, if the dispatcher itself has a bug — this is why layer 1 exists too |
| 4. `security-review-checklist` | A sanity-check reasoning step | Yes — prompt-level, weakest layer, last resort only |

## Open questions / not yet decided
- **Unconfirmed**: whether Cloud Control API's `create_resource` for
  `AWS::IAM::Role` accepts `PermissionsBoundary` the same way
  CloudFormation does. Confirmed for CloudFormation directly (the sourced
  example uses it); CCAPI operates over the same resource-provider
  schemas `ccapi-mcp-server` already uses, so this should carry through,
  but no CCAPI-specific confirmation was found. Verify hands-on before
  relying on it — same habit already applied to every other new MCP
  integration in this project.
- Whether to add an explicit `Deny` statement for
  `iam:DeleteRolePermissionsBoundary` on top of simply omitting it from
  the allow-list — the sourced AWS example relies on omission alone;
  adding an explicit deny is stricter and survives a future edit that
  accidentally adds the action to some other statement. Leaning toward
  adding it, not decided.
- Whether every BU needs its own `permissions_boundary_arn`, or whether
  a shared default is acceptable until a BU actually needs
  `AWS::IAM::Role` in its `allowed_resource_types` — not decided.

## How this relates to the existing docs
- **Fills in the mechanism** `docs/foundation_app_layering_and_iam_tiers.md`
  Part B asserted without specifying ("must reject any `AWS::IAM::Role`
  creation that doesn't attach a permissions boundary") — that doc's rule
  is unchanged, this is what implements it.
- **Fills in the mechanism** `docs/infra_discovery_and_platform_app_split.md`
  Part B referenced the same way, alongside its separate `iam:PassRole`
  scoping rule — the two rules are complementary, not redundant: this
  doc bounds what a *created* role can do; that doc bounds what the
  *operator* is allowed to hand off via `PassRole`.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Creating a permissions boundary — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/transitioning-to-multiple-aws-accounts/creating-a-permissions-boundary.html)
- [Prevent Privilege Escalation with IAM Permissions Boundary: A Practical Guide — DEV Community](https://dev.to/mvandongen/prevent-privilege-escalation-with-iam-permissions-boundary-a-practical-guide-40nc)
- [AWS IAM Permission Boundaries Explained (2026) — securebin.ai](https://securebin.ai/blog/aws-iam-permission-boundaries-explained/)
- [GitHub — aws-samples/example-permissions-boundary](https://github.com/aws-samples/example-permissions-boundary)
