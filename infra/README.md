# infra/

Two allow-lists, enforced at two different layers, because the CDK/CCAPI
path's tool interface has a wider blast radius than a hand-rolled server:

## `iam-policy.json` — what the credentials can do
The underlying per-service actions (S3, CloudFront) plus the Cloud Control
API "meta actions" (`cloudformation:CreateResource`, `GetResource`,
`UpdateResource`, `DeleteResource`, `ListResources`, ...) that
`ccapi-mcp-server` itself needs to operate at all. This is enforced by AWS,
not by our code — a request outside this policy fails at the API layer
regardless of what the agent decides.

**Caveat to verify before using against a real account:** the
`aws:RequestTag/Name` condition is illustrative of intent (scope actions to
resources tagged for this demo) but S3 `CreateBucket` and CloudFront
`CreateDistribution` have inconsistent support for request-tag conditions at
creation time. Test this policy against your sandbox account with the
principle of least privilege in mind, and tighten `Resource: "*"` to specific
ARNs/prefixes once bucket/distribution naming is finalized, rather than
relying on the tag condition alone.

## `allowed-resource-types.json` — which resource types the agent may request
CCAPI's tools accept an arbitrary CloudFormation-style resource type string
(e.g. `AWS::EC2::Instance`) as a parameter. Being IAM-permitted to call
`cloudformation:CreateResource` in general doesn't by itself bound *which*
resource types get created — that's an application-level decision, so it's
enforced by the `security-review-checklist` skill checking this file, not by
IAM. Treat this as equally load-bearing as the IAM policy, not a nice-to-have.

## Terraform path scope
The Terraform path has no equivalent resource-type allow-list file yet —
scope is currently bounded by (a) which HCP Terraform workspace `TFE_TOKEN`
has access to, and (b) `ENABLE_TF_OPERATIONS` being explicitly set by the
operator, not toggled by the agent. Tightening this further (e.g., a
workspace-specific token, a policy-as-code check via Sentinel/OPA before
`action_run`) is a documented gap, not yet built.

## Applying this
Attach `iam-policy.json` to a dedicated IAM user/role used only by these MCP
servers — never to a broadly-privileged account. Never touches root or admin
credentials.
