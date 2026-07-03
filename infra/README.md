# infra/

`iam-policy.json` is the allow-list the MCP server and the
`security-review-checklist` skill both check actions against — this is the
single source of truth for "what this agent is allowed to touch."

**Caveat to verify before using against a real account:** the
`aws:RequestTag/Name` condition is illustrative of intent (scope actions to
resources tagged for this demo) but S3 `CreateBucket` and CloudFront
`CreateDistribution` have inconsistent support for request-tag conditions at
creation time. Test this policy against your sandbox account with the
principle of least privilege in mind, and tighten `Resource: "*"` to specific
ARNs/prefixes once bucket/distribution naming is finalized, rather than
relying on the tag condition alone.

Attach this policy to a dedicated IAM user/role used only by the MCP server —
never to a broadly-privileged account.
