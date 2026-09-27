# AWS Provider Service: Live-Adapter Readiness

Checked 2026-09-23. This is a research record, **not** an enabled live
integration. `gateway.provider_connections` registers no adapters by default;
tests use only scripted fakes.

## Decision

AWS Organizations is the candidate AWS-first provider-control API. A future
adapter must call the Organizations API from a server-side, brokered workload
identity. It must not take customer account IDs, role ARNs, profiles, tokens,
or an MCP tool choice from a browser or ordinary provisioning request.

The existing `ccapi-mcp-server` is not appropriate for this control-plane
operation: its own documentation marks it deprecated, and AWS Cloud Control
API is limited to CRUDL in the caller's own account and has no resource-level
IAM permissions. It remains unrelated to this provider-connection readiness
decision. A live Organizations adapter needs a dedicated, deterministic
integration rather than model-directed MCP invocation.

## Read-only verification and inquiry

| Purpose | AWS API | Required behavior | Minimum action |
| --- | --- | --- | --- |
| Verify the configured organization boundary | `DescribeOrganization` | Compare returned Organization `Id` and management-account identity with the registry-controlled boundary reference. | `organizations:DescribeOrganization` |
| Discover member accounts | `ListAccounts` | Run only through the verified connection; follow `NextToken` until null, including after an empty page; use `State`, not the retiring `Status` field. | `organizations:ListAccounts` |
| Revalidate selected candidate | `DescribeAccount` | Confirm the 12-digit account ID and current `State` before reviewed attachment. | `organizations:DescribeAccount` |

`ListAccounts` is callable only by an Organizations management account or a
delegated administrator. The adapter must capture the verified organization
ID, not infer ownership from a user-supplied account number.

## Privileged account bootstrap

| Step | AWS API | Required behavior | Minimum action |
| --- | --- | --- | --- |
| Start account creation | `CreateAccount` | Invoke only after PlatformOps policy and recorded approval. Store the returned create-request ID as non-secret workflow evidence. | `organizations:CreateAccount` |
| Poll outcome | `DescribeCreateAccountStatus` | Treat creation as asynchronous. Do not expose or attach a new account until the returned state is successful and an account ID exists. | `organizations:DescribeCreateAccountStatus` |
| Tag at creation, if enabled | `CreateAccount` tags | Restrict tag keys/values through PlatformOps policy. | `organizations:TagResource` |

AWS documents `CreateAccount` as management-account-only and asynchronous. It
also creates a management-account-access role in the new member account by
default. The future adapter must explicitly choose and document the role name
and its least-privilege post-bootstrap policy; this change does not make that
role usable or grant it to ordinary provisioning.

## Required pre-implementation checks

1. Validate a dedicated sandbox organization's ID, management-account ID, and
   delegated-administrator behavior using the exact workload identity.
2. Confirm the role's least-privilege policy with the AWS IAM policy simulator
   and CloudTrail evidence for each API above.
3. Exercise pagination, empty page with continuation token, account failure,
   and asynchronous create polling against a sandbox.
4. Add a dedicated live-adapter change with no model-selected tools and no
   default activation; the fake-adapter contract tests remain required.

## Official sources

- [DescribeOrganization API](https://docs.aws.amazon.com/organizations/latest/APIReference/API_DescribeOrganization.html)
- [ListAccounts API](https://docs.aws.amazon.com/organizations/latest/APIReference/API_ListAccounts.html)
- [DescribeAccount API](https://docs.aws.amazon.com/organizations/latest/APIReference/API_DescribeAccount.html)
- [CreateAccount API](https://docs.aws.amazon.com/organizations/latest/APIReference/API_CreateAccount.html)
- [Creating a member account](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_accounts_create.html)
- [Cloud Control API security and account-scope limits](https://docs.aws.amazon.com/cloudcontrolapi/latest/userguide/security.html)
- [AWS CCAPI MCP Server documentation](https://awslabs.github.io/mcp/servers/ccapi-mcp-server)
