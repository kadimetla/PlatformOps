# Foundation vs. App Layer, IAM Tiers, and Helm-to-EKS as a New Execution Backend

## Status
Design only — nothing here is built. Extends the provisioning model
beyond what `README.md:255-257` explicitly scopes out today
("compute workloads (Lambda/ECS/EC2/GCE/Azure VMs) beyond static
hosting... not yet designed"). This is that design, for the specific
shape of compute the project is now heading toward: VPC/EKS as a
foundation, app workloads deployed onto it via Helm or as standalone
Lambda functions.

## Where today's model actually stops
Grounded in what exists, not assumption:
- **Scope**: `AWS::S3::Bucket` + `AWS::CloudFront::Distribution` only
  (`infra/allowed-resource-types.json:3-6`). Static hosting, nothing
  compute-shaped.
- **IAM**: one flat policy (`infra/iam-policy.json`) scoped to S3/
  CloudFront actions plus CCAPI's meta-actions, attached once to one
  dedicated role. No tiering of any kind.
- **Provisioning path**: `provision-infra` has two *tool* paths (CDK/
  CCAPI vs. Terraform, `skills/provision-infra/SKILL.md`) — not two
  *architectural* layers. Both provision standalone resources with no
  ordering or dependency concept between them; `allowed_resource_types`
  is a flat, unordered list.

Everything below is new ground, not a gap in something already
designed elsewhere.

## Part A: Foundation layer vs. app layer are a different axis than CDK vs. Terraform
VPC/EKS and "deploy an app onto it" are two layers with fundamentally
different risk profiles and lifecycles — not two more tool-choice paths
like CDK vs. Terraform:

| | Foundation layer (VPC, EKS cluster, subnets, node groups) | App layer (workload deployed onto that foundation) |
|---|---|---|
| Change frequency | Rare — provisioned once, changed occasionally | Frequent — every deploy |
| Blast radius | High — misconfiguring or deleting breaks everything running on top | Scoped to one app, ideally |
| Approval bar | Always human-required, never autonomous | Can be autonomous once the foundation + IAM scoping are already approved |
| Execution backend | CCAPI/Terraform — same shape as today's model | **Two different mechanisms depending on target compute** — Helm for EKS, CCAPI/Terraform for Lambda (see Part C) |

### `allowed-resource-types.json` needs a tier, not just a longer flat list
```json
{
  "resource_types": [
    {"type": "AWS::S3::Bucket", "tier": "app"},
    {"type": "AWS::CloudFront::Distribution", "tier": "app"},
    {"type": "AWS::Lambda::Function", "tier": "app"},
    {"type": "AWS::EC2::VPC", "tier": "foundation"},
    {"type": "AWS::EKS::Cluster", "tier": "foundation"},
    {"type": "AWS::EKS::Nodegroup", "tier": "foundation"},
    {"type": "AWS::IAM::Role", "tier": "app", "requires_permissions_boundary": true}
  ]
}
```
The `tier` field is what lets `security-review-checklist` apply a
different rule per tier — foundation-tier resource types always route
to mandatory human approval, regardless of cost or naming compliance,
the same risk-tier concept `docs/HARNESS_DESIGN.md`'s Control UI section
already names ("low-risk resource types can stay fully autonomous;
higher-risk types... route to a human reviewer") but has never had a
concrete resource-type split to apply it to until now.

### New skill: `provision-foundation`, sibling to `provision-infra`
Following the exact pattern `README.md:238-240`'s roadmap already
establishes for adding a cloud/tool combination ("`provision-infra`
skill routes to it; `security-review-checklist` gets a path-specific
check block") — foundation provisioning gets its own skill rather than
a third path bolted onto `provision-infra`, because its approval rule
(always human, no exception) is categorically different from app-tier's
conditional rule, not just a different tool choice.

## Part B: IAM has to layer into four roles, not one
**Corrected by research** — see `docs/infra_discovery_and_platform_app_split.md`
Part B for the sourced detail. What's below was originally written as
three tiers; AWS's own EKS docs split "foundation-runtime" into two
separate, non-interchangeable roles, and add a scoping rule this
section originally missed entirely.

1. **Provisioning credentials** (exists today, extend) — what the
   agent/MCP server itself can call to create resources:
   `iam-policy.json`'s current scope, extended with
   `eks:CreateCluster`, `ec2:CreateVpc`, `lambda:CreateFunction`, and
   (carefully — see below) `iam:CreateRole` **and a scoped
   `iam:PassRole`** — a well-known privilege-escalation vector if
   granted as `Resource: "*"` instead of scoped to the exact role ARNs
   this BU is allowed to create/pass. See
   `docs/infra_discovery_and_platform_app_split.md` Part B for why this
   is a separate rule from the permissions-boundary one below, not
   covered by it.
2. **EKS cluster service role** — what the cluster itself assumes at
   runtime.
3. **Node IAM role** — a **separate** role for worker nodes. AWS states
   this as a hard rule: *"you can't use the same role that is used to
   create any clusters."* Roles #2 and #3 were originally lumped into
   one "foundation-runtime IAM" tier here — they're two distinct,
   non-reusable roles.
4. **App/workload IAM** (the trickiest tier) — least-privilege,
   per-app roles so a deployed workload reaches only the resources it
   needs, not everything the provisioning credentials could touch. On
   EKS this is IRSA (IAM Roles for Service Accounts — a pod assumes a
   role scoped to its own service account, not the node's role); for
   Lambda it's a per-function execution role.

### `AWS::IAM::Role` is not just another allow-listed resource type
Every other resource type on the allow-list bounds what can be
*created*. `AWS::IAM::Role` is different in kind: a role is a mechanism
for granting access, including — if unbounded — access that exceeds
what the agent's own provisioning credentials have. Allow-listing the
type is necessary but not sufficient. The additional rule:
**`security-review-checklist` must reject any `AWS::IAM::Role` creation
that doesn't attach a permissions boundary**, capping what that role can
ever be escalated to, independent of what policy gets attached to it
later. This is the one resource type in the whole system where "is it
on the allow-list" isn't the whole check — matches the existing project
habit of treating some checks as structurally different from others
(the same way `infra/README.md:23-29` already explains why the
resource-type allow-list is separate from, not redundant with, the IAM
policy).

**Mechanism specified in `docs/iam_permissions_boundary_implementation.md`**:
this rule was originally stated without a concrete implementation — that
doc gives it one: the exact `iam-policy.json` condition that forces the
boundary at creation time, why omitting `iam:DeleteRolePermissionsBoundary`
from the allow-list prevents removing it afterward, and the
`BrokeredToolDispatcher` check that enforces this independent of AWS
IAM's own enforcement.

## Part C: Helm-to-EKS is a third execution backend, not a third tool path
CCAPI and Terraform both talk to **AWS's control plane** — that's why
they share a shape (`ToolIntent`, resource type + operation, checked by
`BrokeredToolDispatcher`). Helm talks to **the Kubernetes API server**
running inside the EKS cluster — a different control plane entirely,
reached through the cluster's own auth (IRSA / OIDC), not AWS
credentials in the same sense. A Helm release also isn't a single
resource the way an S3 bucket is — it's a chart (from a repo, itself a
supply-chain surface) applied as a set of Kubernetes manifests, with its
own upgrade/rollback semantics CCAPI/Terraform don't have.

### New skill: `deploy-to-k8s`
**Renamed from `deploy-to-eks`** — `docs/multi_cloud_foundation_and_iam.md`
found that `kubernetes-mcp-server`'s Helm tools talk directly to the
Kubernetes API, not any cloud-specific control plane, so this skill was
never actually AWS-specific; it just hadn't been checked against GCP/
Azure yet when it was named. A sibling skill to `provision-infra`, not a
path inside it — the procedure genuinely doesn't resemble CDK/CCAPI or
Terraform:
1. Confirm the target cluster (EKS, GKE, or AKS) is an **approved
   foundation** for this BU (see Part D — this is the actual new
   mechanism, not just a procedure step).
2. Confirm the chart source is from an approved repo — same
   supply-chain-shaped concern `docs/skills_and_workspace_design.md`
   already raises for promoted skills ("version-pinned," not silently
   upgraded underneath a consumer) applies directly to chart versions.
3. Confirm the target namespace is allow-listed for this BU (namespace
   is the Kubernetes-side equivalent of the resource-type allow-list —
   it bounds blast radius the way `allowed-resource-types.json` does on
   the AWS side).
4. Produce the Vibe Diff — for Helm, this is a `helm diff`/dry-run
   output, not a CloudFormation/Terraform plan.
5. Wait for `security_agent` approval — unchanged shape, different plan
   format underneath.
6. Execute via `helm upgrade --install`.

**Researched — see `docs/eks_helm_mcp_integration.md`**: no single MCP
server covers both foundation-layer EKS lifecycle and app-layer Helm
deploys. `awslabs.eks-mcp-server` handles cluster create/describe/delete
but has confirmed **no Helm support**; `containers/kubernetes-mcp-server`
has real `helm_install`/`helm_list`/`helm_uninstall` tools. That doc also
surfaces a new cross-BU isolation risk (kubeconfig context scoping) not
previously named here, and confirms neither server creates IAM roles —
`AWS::IAM::Role` still goes through the existing CCAPI/Terraform path as
designed above.

## Part D: The missing piece today's model has no concept of — dependency ordering
An app-layer deploy (Helm or Lambda) has a hard, load-bearing dependency
on its foundation existing and having been approved. Today's flat
`allowed_resource_types` list has no way to express "this can't proceed
until that other thing exists" at all. New mechanism:

```python
class FoundationRecord(BaseModel):
    foundation_id: str
    org_id: str
    bu_id: str
    cloud_provider: str          # "aws" | "gcp" | "azure" — added in docs/multi_cloud_foundation_and_iam.md
    resource_type: str           # e.g. "AWS::EKS::Cluster" | "google_container_cluster" | "Microsoft.ContainerService/managedClusters"
    resource_identifier: str
    approved_plan_id: str        # the PlanRecord that created/adopted it, always human-approved
    status: str = "active"       # "active" | "decommissioned"
    discovered_capabilities: Dict[str, Any] = Field(default_factory=dict)
    # what an app-layer deploy needs to pick a compatible stack — see
    # docs/foundation_discovery_and_capability_matching.md Part C for the shape
```
**Canonical version** — `docs/multi_cloud_foundation_and_iam.md` and
`docs/foundation_discovery_and_capability_matching.md` both sketched
additions to this schema separately; this is the merged, single source
of truth. Update here, not in either of those docs, if this schema
changes again.

**Superseded by `docs/foundation_layer_decomposition.md`**: what this
section calls "the foundation layer" (one record) is actually a
network → compute → identity chain, each layer independently
discoverable/adoptable. That doc adds `layer` and
`depends_on_foundation_id` fields and a recursive dispatcher check —
this schema stays the base shape, that doc is what it needs to become
before it's accurate for anything beyond a single-cluster BU.

`ToolIntent` (for a Lambda deploy) and its Helm equivalent both gain an
optional `depends_on_foundation_id: Optional[str]`.
`BrokeredToolDispatcher.evaluate_intent()` gains one more check, in the
same deny-by-default shape as its existing region/resource-type/
approval checks: if `depends_on_foundation_id` is set, look up the
`FoundationRecord` and deny unless `status == "active"`. This is the
same pattern already used everywhere else in the dispatcher — turning an
implicit assumption ("the cluster is obviously already there") into an
explicit, checked precondition — just applied to a dependency between
plans instead of a single plan's own fields.

## What's real vs. designed
| Piece | Status |
|---|---|
| Static hosting (S3/CloudFront) provisioning | Real |
| Foundation/app tier distinction, tiered `allowed-resource-types.json` | Design only |
| `provision-foundation` skill | Design only |
| Three-tier IAM model, permissions-boundary rule for `AWS::IAM::Role` | Design only |
| `deploy-to-k8s` skill / Helm execution backend | Design only — MCP server integration researched (`docs/eks_helm_mcp_integration.md`), confirmed cloud-agnostic (`docs/multi_cloud_foundation_and_iam.md`) |
| `FoundationRecord` + dependency-ordering dispatcher check | Design only |

## Open questions / not yet decided
- Which MCP server (if any) fronts Helm — needs research the way the
  Terraform server integration already got, before this is buildable.
- Whether `AWS::IAM::Role`'s permissions-boundary requirement should be
  enforced by `security-review-checklist` (prompt-level, like everything
  else that skill checks today) or by the dispatcher (code-level,
  matching the project's general direction of moving enforcement out of
  prompts) — leaning dispatcher, given how much is riding on this one
  check, not yet decided.
- Whether `FoundationRecord` needs its own decommission workflow (what
  happens to app-layer deploys that depend on a foundation being torn
  down) — not designed.
- Same open storage-backend question as config/`SkillProposal`/
  `MemoryEntry`: `FoundationRecord` likely belongs in the same store
  those converge on, not a new one — not decided until that store itself
  is chosen.

## How this relates to the existing docs
- Extends, doesn't contradict, `README.md`'s roadmap section — this is
  the design for the "compute workloads... not yet designed" line there.
- Reuses `docs/HARNESS_DESIGN.md`'s risk-tier Control UI concept, giving
  it its first concrete resource-type split (foundation vs. app) to
  apply to.
- Reuses `docs/skills_and_workspace_design.md`'s version-pinning
  principle (for skills), applied to Helm chart versions instead.
- Reuses the dependency-checking *shape* already established by
  `harness/tool_dispatcher.py`'s deny-by-default checks, extended with
  one new check rather than a new enforcement mechanism.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3) —
  same relationship every doc in this set has to it: additive, not a
  prerequisite.
