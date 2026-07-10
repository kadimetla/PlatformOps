# Compute Paradigms — Not One Layer, a Choice With Different Foundation Shapes

## Status
Design only. Every prior doc's "compute layer" (`docs/foundation_layer_decomposition.md`,
`docs/foundation_app_layering_and_iam_tiers.md`) implicitly meant
Kubernetes (EKS/GKE/AKS) without ever stating that was a choice among
several compute paradigms. This names the others, and — the part that
actually changes prior design — shows the network→compute→identity
chain from `docs/foundation_layer_decomposition.md` is specifically
Kubernetes's shape, not a universal one.

## Part A: Four compute paradigms, per provider
| Paradigm | AWS | GCP | Azure |
|---|---|---|---|
| **Kubernetes** (heaviest) | EKS — `awslabs.eks-mcp-server`, write-capable | GKE — MCP read-only (`docs/eks_helm_mcp_integration.md`) | AKS — write path is the ARM MCP Server |
| **VMs** | EC2 — generic via `ccapi-mcp-server` | Compute Engine — **GCE MCP server, confirmed write-capable**, *"provisioning and resizing as discoverable tools"* | Azure VMs — generic via ARM MCP Server |
| **Managed containers** | ECS/Fargate — a **dedicated, purpose-built AWS MCP server**: *"automatically containerize applications and manage their deployments on Amazon ECS... Fargate and Application Load Balancers"* | Cloud Run — **confirmed write-capable**: `GoogleCloudPlatform/cloud-run-mcp` (official), `deploy-file-contents`/`deploy-local-folder` tools, same tier as AWS's ECS server (`docs/gcp_azure_verification_pass.md`) | Container Apps — generic via ARM MCP Server |
| **Serverless** (lightest) | Lambda — generic via `ccapi-mcp-server` (`AWS::Lambda::Function` is an ordinary CFN resource type) | Cloud Functions — not confirmed | Azure Functions — generic via ARM MCP Server |

## Part B: The tooling finding — allow-list gap, not tool gap
`ccapi-mcp-server` (already integrated) is generic across nearly every
CloudFormation resource type via Cloud Control API — it was never
S3/CloudFront-specific. `infra/allowed-resource-types.json` limiting it
to 2 types was a deliberate demo scope choice, not a tooling
limitation. **Adding EC2 or Lambda support is an allow-list change, not
a new integration.** The one genuinely new tool worth adding is the
ECS-specific server, because it's purpose-built with better guardrails
than raw CCAPI — the same reasoning already used for preferring
`eks-mcp-server`'s `manage_eks_stacks` over generic CCAPI for EKS
specifically (`docs/eks_helm_mcp_integration.md` Part A).

## Part C: The foundation chain is paradigm-specific, not universal
`docs/foundation_layer_decomposition.md`'s network → compute → identity
chain is Kubernetes's shape. It doesn't generalize:

| Paradigm | Network layer | Compute layer | Identity |
|---|---|---|---|
| **Kubernetes** | Required | Required (control plane + node pools) | Required, **federation-based** (IRSA/Workload Identity/Azure AD Workload Identity) — genuinely shared, multiple future workloads bind to the same OIDC setup |
| **VM** | Required | Required, **no separate "cluster" sub-layer** — the VM record *is* the compute layer, it schedules itself | Direct-attach (instance profile/service account/managed identity), **1:1 with the VM**, not shared |
| **Managed containers** | Required | Required but lighter — a logical cluster grouping, no node-group management (Fargate is serverless underneath) | Direct-attach (per-task/per-service role), **1:1 with the task**, not shared |
| **Serverless** | **Optional** — a function doesn't need a VPC by default; attachment is opt-in, only for reaching VPC-private resources | Required (the function/deployment itself) | Direct-attach (per-function execution role), **1:1**, not shared |

### The generalizable principle this surfaces
Whether something deserves its own trackable `FoundationRecord` layer
depends on whether it's **shared** (reusable across multiple future
resources) or **1:1** (created alongside, and only ever used by, one
specific compute resource) — not on whether it's conceptually "IAM."
Network is always shared. Kubernetes identity (an OIDC provider) is
shared. VM/serverless/managed-container identity is **not** shared —
one execution role per function/instance/task — so for those
paradigms, identity collapses into an attribute of the compute layer's
own record, not a separate chain-tracked `FoundationRecord`.

## Part D: Schema addition
```python
class FoundationRecord(BaseModel):
    ...  # existing fields (docs/foundation_layer_decomposition.md)
    compute_paradigm: Optional[str] = None
    # "kubernetes" | "vm" | "managed_containers" | "serverless"
    # only meaningful when layer == "compute"; determines whether a
    # network-layer FoundationRecord is required (kubernetes/vm/
    # managed_containers) or optional (serverless), and whether identity
    # gets its own FoundationRecord (kubernetes only) or stays an
    # attribute of this record (everything else)
```

## Open questions / not yet decided
- **Partially resolved in `docs/gcp_azure_verification_pass.md`**:
  Cloud Run's MCP tooling is confirmed write-capable. Cloud Functions
  still has no dedicated MCP server found, even on a fresh targeted
  search — remains unconfirmed/likely absent, not just unverified.
- Whether a serverless deploy that *does* need VPC attachment (reaching
  a private RDS/Cloud SQL instance) should then require the full
  network-layer `FoundationRecord` the way VM/managed-container
  paradigms do, or a lighter "VPC attachment" record distinct from a
  full network foundation — not decided.
- Whether `compute_paradigm` should be a closed enum or extensible —
  same open question already noted for `layer` in
  `docs/foundation_layer_decomposition.md`, same answer likely applies
  (closed for now, extend on a real case).

## How this relates to the existing docs
- Corrects the implicit Kubernetes-only framing in
  `docs/foundation_layer_decomposition.md` and
  `docs/foundation_app_layering_and_iam_tiers.md` — their network→
  compute→identity chain is one paradigm's shape among four, not the
  universal one.
- Extends `docs/multi_cloud_foundation_and_iam.md`'s per-provider
  write-capability table with three more compute paradigms it didn't
  cover (that doc was Kubernetes-only).
- Reuses `docs/eks_helm_mcp_integration.md`'s "prefer the purpose-built
  tool over generic CCAPI when one exists" reasoning, applied to ECS.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Amazon ECS MCP Server — AWS Labs MCP docs](https://awslabs.github.io/mcp/servers/ecs-mcp-server)
- [Automating AI-assisted container deployments with the Amazon ECS MCP Server — AWS blog](https://aws.amazon.com/blogs/containers/automating-ai-assisted-container-deployments-with-amazon-ecs-mcp-server/)
