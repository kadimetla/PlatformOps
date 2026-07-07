# Infra Discovery, Corrected IAM Tiers, and the Platform/App Persona Split

## Status
Research + design corrections — resolves open questions and fixes an
inaccuracy in `docs/foundation_app_layering_and_iam_tiers.md`, verified
against live AWS docs (see Sources). Nothing here is built.

## Part A: Discovering existing infra, not just creating it

### The read path is wider than this project currently uses
`awslabs.ccapi-mcp-server` — already integrated
(`mcp_server/external_servers.py`'s `CCAPI_MCP_SERVER`) — has a
`list_resources()` capability that works across **arbitrary**
CloudFormation-style resource types, not just the two this project
currently allow-lists. Confirmed example from AWS's own announcement:
"Find all of my EC2 instances and tell me which ones have an instance
type that is not t2.large." The discovery capability already exists in
a tool this repo already depends on — it's narrowed today only because
`infra/allowed-resource-types.json` gates **read and write with the
same flat list**.

That's worth changing. Discovering what exists has a materially smaller
blast radius than creating or modifying it — reading `AWS::EC2::VPC`
doesn't risk anything the way creating one does. The allow-list should
split:
```json
{
  "read_resource_types": ["*"],
  "write_resource_types": [
    {"type": "AWS::S3::Bucket", "tier": "app"},
    {"type": "AWS::CloudFront::Distribution", "tier": "app"}
  ]
}
```
`security-review-checklist` and `harness/tool_dispatcher.py` both
already treat "resource type on the list" as the gating question for
*mutating* calls — this doesn't change that. It just stops that same
check from also blocking `get_resource`/`list_resources` calls that
were never going to mutate anything.

### Account-wide discovery: AWS Resource Explorer, not a bespoke MCP tool
**AWS Resource Explorer** is a real AWS service — not something built
for this project — enabled by default account-wide since October 2025,
aggregating via AWS Config + Cloud Control API, searchable by tag/name/
type across an account/region. This is the better fit for "gather
everything in this account" than iterating `ccapi-mcp-server`'s
per-resource-type `list_resources` one type at a time. Whether an
MCP-wrapped path to it exists (vs. calling the Resource Explorer API
directly from a discovery tool) is not confirmed — flagged to verify.

### A near-miss worth naming so it doesn't get assumed later
**AWS Knowledge MCP Server** surfaced in research under "CFN Explorer"
and looked promising, but on closer read it isn't infra discovery — it's
a documentation/region-metadata search tool (`search_documentation`,
`get_regional_availability`, `list_region`). The "CFN Explorer"
capability described in AWS's own blog post about it is a **custom
orchestrator built on top of** AWS APIs + Bedrock, not a built-in tool
of that server. Do not reach for AWS Knowledge MCP Server when the goal
is "what CloudFormation stacks exist" — it can't answer that.

### The real design problem: two sources of truth that can disagree
If infra was created via this project's Terraform path, the
authoritative "what exists" record is **Terraform state**
(`terraform state list`/`show`, via the already-integrated
`terraform-mcp-server`) — not a live AWS API query. If it was created
via the CDK/CCAPI path, or by anything outside this harness entirely
(manually, by another tool), state doesn't exist or doesn't know about
it, and `ccapi-mcp-server`'s live discovery is the only source. **These
two sources can disagree — drift.** A harness that needs to "gather all
information about existing infra" needs a reconciliation story, not an
assumption that one query answers the question:

1. If a `FoundationRecord` (`docs/foundation_app_layering_and_iam_tiers.md`
   Part D) references a Terraform-managed foundation, check state first.
2. Always cross-check against a live `list_resources`/Resource Explorer
   query.
3. A mismatch (state says it exists, live API says it doesn't, or vice
   versa) is itself a finding to surface, not silently resolve one way —
   likely worth its own audit-log entry, the same "don't silently
   resolve, log the disagreement" instinct already applied everywhere
   else in this project's audit design.

## Part B: Foundation-layer IAM is four roles, not three
`docs/foundation_app_layering_and_iam_tiers.md` Part B described three
IAM tiers (provisioning credentials / foundation-runtime / app-workload).
AWS's own EKS documentation is more specific, and splits
"foundation-runtime" into two **separate, non-interchangeable** roles:

1. **Operator/agent's own permissions** to call the creation APIs —
   `eks:CreateCluster`, `eks:DescribeCluster`, `eks:UpdateClusterConfig`,
   `ec2:Describe*`, plus `iam:PassRole` (see the rule below).
2. **EKS cluster service role** — what the cluster itself assumes at
   runtime (`AmazonEKSClusterPolicy` or a custom equivalent).
3. **Node IAM role** — a **separate** role for worker nodes. AWS states
   this as a hard rule, not a recommendation: *"you can't use the same
   role that is used to create any clusters."*
4. **App/workload IAM via IRSA** — unchanged from the prior design.

`docs/foundation_app_layering_and_iam_tiers.md` should be read with this
correction: what it called "foundation-runtime IAM" (one tier) is
actually two distinct roles (#2 and #3) with an explicit AWS rule
against merging them.

### New rule: `iam:PassRole` must be scoped, not wildcarded
`iam:PassRole` is a well-known AWS privilege-escalation vector — a
principal that can pass *any* role to a service can, in effect, grant
itself that role's permissions by handing it to something that will use
it on the principal's behalf. The existing `AWS::IAM::Role`
permissions-boundary rule (Part B of the prior doc) bounds what a
*created* role can do — it says nothing about what the *operator* is
allowed to hand off. Both are needed:
- Every agent-created `AWS::IAM::Role` requires a permissions boundary
  (existing rule, unchanged).
- **New**: the operator's own `iam:PassRole` grant must carry a
  resource-ARN condition scoping it to exactly the cluster-role and
  node-role ARNs this BU is allowed to create/pass — never
  `Resource: "*"`. This is a gap in the existing IAM design, not a
  restatement of it; without it, the permissions-boundary rule alone
  doesn't close the escalation path `iam:PassRole` opens.

## Part C: `TeamMember` needs a second dimension — layer scope, not just role
`docs/skills_and_workspace_design.md`'s `TeamMember.role`
(`"requester"|"approver"|"admin"`) is a single ladder — more authority
as you go up. What foundation-vs-app deploys actually need is a
**different, orthogonal axis**: which layer someone is allowed to touch
at all, independent of how much authority they have within it. This
matches a well-established pattern, not something invented here — the
platform-team/application-team split used across Azure landing zones,
HashiCorp's own platform-team writing, and platformengineering.org: a
platform team owns the landing zone (identity, networking,
connectivity — this project's foundation layer) and defines guardrails;
application teams self-serve deploys into their own scoped landing zone,
*"with little to no concern about breaking things,"* because blast
radius is contained by construction, not by trusting people not to
touch what they shouldn't.

### Corrected `TeamMember` sketch
```python
class TeamMember(BaseModel):
    channel_user_id: str
    display_name: str
    role: str    # "requester" | "approver" | "admin" — unchanged
    scope: str   # "foundation" | "app" | "both" — new

# Added to WorkspaceBundle (unchanged from the original sketch):
members: list[TeamMember] = Field(default_factory=list)
```
A person could be `role="admin", scope="app"` — full control over their
own app-layer namespace/deploys — with **zero** access to
foundation-layer changes, regardless of role. This is not expressible
today: the existing single-dimension `role` field conflates "how much
authority" with "over what," and foundation-vs-app needs both answered
independently. `harness/tool_dispatcher.py`'s eventual `scope` check
would be structurally identical to today's `resource_type` allow-list
check — deny by default unless the requester's `TeamMember.scope`
covers the tier of what they're requesting.

## Open questions / not yet decided
- Whether an MCP-wrapped path to AWS Resource Explorer exists, or
  whether the Gateway should call its API directly — not confirmed.
- Exact shape of the drift-reconciliation record (Part A, step 3) — a
  new table, or an extension of the audit log — not decided.
- Whether `scope="both"` should require `role="admin"` (i.e., nobody
  gets cross-layer access without also being fully trusted) — a
  reasonable-sounding default, not yet decided as a hard rule.

## How this relates to the existing docs
- **Corrects** `docs/foundation_app_layering_and_iam_tiers.md` Part B's
  three-tier IAM model to four roles, and adds the `iam:PassRole`
  scoping rule that model was missing.
- **Extends** `docs/skills_and_workspace_design.md`'s `TeamMember`
  sketch with the `scope` dimension.
- **Extends** `docs/eks_helm_mcp_integration.md`'s tool inventory with
  the discovery-specific capabilities of `ccapi-mcp-server` and AWS
  Resource Explorer, which that doc didn't cover (it focused on
  creation/deployment, not discovery).
- See `docs/foundation_and_app_deploy_flow_example.md` for a worked
  example tracing a platform engineer setting up a foundation and an
  app developer deploying onto it, using everything in this doc plus
  `FoundationRecord` end to end.

## Sources
- [Introducing AWS Cloud Control API MCP Server — AWS blog](https://aws.amazon.com/blogs/devops/introducing-aws-cloud-control-api-mcp-server-natural-language-infrastructure-management-on-aws/)
- [What is AWS Resource Explorer? — AWS docs](https://docs.aws.amazon.com/resource-explorer/latest/userguide/welcome.html)
- [Accelerate Region expansion with the AWS Knowledge MCP server — AWS blog](https://aws.amazon.com/blogs/infrastructure-and-automation/accelerate-region-expansion-with-the-aws-knowledge-mcp-server/)
- [Amazon EKS cluster IAM role — AWS docs](https://docs.aws.amazon.com/eks/latest/userguide/cluster-iam-role.html)
- [Amazon EKS node IAM role — AWS docs](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html)
- [What are the minimum permissions/actions required for creating, modifying and deleting EKS clusters? — AWS re:Post](https://repost.aws/questions/QUaSgSCnGDTyWguEyaZl76aA/what-are-the-minimum-permissions-actions-required-for-creating-modifying-and-deleting-eks-clusters)
- [What is a platform team and what problems do they solve? — HashiCorp](https://www.hashicorp.com/en/resources/what-is-a-platform-team-and-why-do-we-need-them)
- [What is an Azure landing zone? — Microsoft Learn](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/)
