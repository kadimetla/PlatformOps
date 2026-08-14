## Status
Designed only — no code. This is the reference deployment contract for
the first real `workflows/provision/` slice: S3+CloudFront (static
frontend) + an existing EKS cluster (API backend), AWS-only,
`opentofu_local`-only. Per explicit instruction, **no code is written
until this contract is accepted** — this doc exists to make that
acceptance a reviewable decision, not a verbal one. Three AWS claims
verified against current docs 2026-08-14 (OAC-over-OAI, EKS Fargate
limitations, AWS Load Balancer Controller) — see Sources. Everything
else here is design synthesis, reconciled against — not duplicating —
`PROVISION_WORKFLOW.md`, `EXECUTION_CREDENTIALS.md`, and
`BOOTSTRAP_WORKFLOW.md`, which already designed most of the mechanics
this doc's flow depends on. **Updated same day**: all three blocking
open questions resolved (see the Open Questions table — Kubernetes
allow-list decided, EKS auth verified, skill-entry-point decided); the
"Skill composition" tree is superseded by
`COMPOSABLE_PROVISIONER.md`'s repository shape. The contract is now
unblocked for acceptance.

## Real vs. Designed
| Area | Status |
|---|---|
| `workflows/provision/` (any node) | Does not exist — confirmed, only `workflows/intake/` exists |
| `templates/aws/kubernetes-static-web/` | Does not exist |
| `ApplicationProvisionRequest` schema | Does not exist |
| `security-review-checklist` skill's Kubernetes/`opentofu_local` section | Does not exist — confirmed by reading the skill: it has "Checks common to both paths" + `cdk` + `terraform` sections only, no `opentofu_local` awareness at all, let alone Kubernetes |
| `infra/allowed-resource-types.json`'s Kubernetes-kind analog | Does not exist — confirmed the real file is CloudFormation-resource-type-shaped (`AWS::S3::Bucket`), and `infra/README.md` explicitly scopes it to "the CDK/CCAPI path" |
| `skills/provision-infra/SKILL.md`'s Path C (`opentofu_local`) | Does not exist — matches `PROVISION_WORKFLOW.md`'s own Real-vs-Designed row; that skill is CDK/CCAPI + Terraform/HCP-shaped and predates the LangGraph workflow architecture |
| `effective_access` composite ceiling this doc's step 5 depends on | Designed 2026-08-14 in `BOOTSTRAP_WORKFLOW.md`, not implemented — `ceiling.py` still only reads `org_bu_policy.yaml` |

## Reference architecture
```
User
 |
 v
CloudFront
 |                    \
 v                     v
S3 static assets       ALB
                         |
                         v
                    Kubernetes Ingress
                         |
                         v
                    Kubernetes Service
                         |
                         v
                    API Deployment
                         |
                         v
                    Pods
```
S3 stays private; CloudFront reaches it via **Origin Access Control**
(OAC), scoped to one distribution — verified current AWS guidance,
not OAI (legacy, explicitly no-longer-recommended). The bucket policy
condition is `AWS:SourceArn` matching the specific distribution ARN,
per AWS's own example. ACM certificate for a CloudFront custom domain
must be requested in `us-east-1` regardless of where the API/EKS
cluster runs — a CloudFront-specific constraint, not a general ACM
one.

In the composable design, that bucket policy is its own
`aws.s3.cloudfront_oac_policy` join unit. It consumes both the bucket ID
and distribution ARN; placing it inside either upstream unit would
create a render-time dependency cycle.

**EKS managed node groups, not Fargate, for the first target** —
verified: Fargate doesn't support DaemonSets, privileged containers,
`hostNetwork`/`hostPort`, and requires private subnets with NAT
gateway access. Those constraints complicate common controllers
(including the AWS Load Balancer Controller's own DaemonSet-adjacent
pieces in some setups) and observability agents. AWS's own EKS
best-practices guide recommends the **AWS Load Balancer Controller**
(not the legacy in-tree Service Controller) to reconcile Kubernetes
`Service`/`Ingress` into ALB/NLB — verified, and the controller itself
is a platform-bootstrap prerequisite (below), not something the
application provision workflow installs. Fargate becomes a later
toolchain/profile option once managed-node deployment works, not a
day-one choice.

## The three-way workflow boundary
Extends, doesn't replace, `BOOTSTRAP_WORKFLOW.md`'s existing two-way
split (Decision 1's disjoint allow-lists: bootstrap = identity/
scaffolding only, normal provision = app resources only, `AWS resource
types excluded`/`identity types excluded` respectively). This adds a
third category that doc's allow-list language doesn't currently name
at all:

```
Platform bootstrap:     VPC, EKS cluster, node groups, IAM, AWS Load
                         Balancer Controller, OIDC/pod-identity setup
                         -- BOOTSTRAP_WORKFLOW.md's existing scope,
                         Level 0-2 of its ladder

Application provisioning: S3+CloudFront+ACM+Route53, Kubernetes
                         deployment/service/ingress/etc inside an
                         existing registered namespace --
                         THIS doc's scope

Application release:    build image, push to ECR, upload frontend
                         build, update the image digest/artifact URI
                         a provisioning request references -- NOT
                         designed here, explicitly deferred (see
                         "Application artifacts" below)
```
**Not creating EKS/VPC in the first application workflow is the core
scoping decision this doc makes** — mixing platform bootstrap with
application deployment in one first slice makes failures undiagnosable
(is it the cluster or the app?) and re-mixes exactly the identity/
app-resource disjointness `BOOTSTRAP_WORKFLOW.md`'s Decision 1 already
committed to keeping separate. The application workflow **fails with a
clear prerequisite error** if the registry has no entry for the target
cluster/workspace — it does not attempt to create one.

## What must already exist (platform prerequisites, not built here)
AWS account, region, VPC + subnets, EKS cluster, node group/Fargate
profile, AWS Load Balancer Controller, ECR access, OIDC provider/pod
identity, Route 53 hosted zone, OpenTofu state bucket + locking,
PlatformOps execution role, a PlatformOps runner with network reachability
to the EKS API, an existing application namespace, **EKS access entry for
that execution role + namespace-scoped Kubernetes RBAC** (added 2026-08-14 with resolved
Q2 below — bootstrap outputs the application workflow consumes, never
creates). Represented in the project registry
(extending the shape `BOOTSTRAP_WORKFLOW.md`'s "Registry row —
canonical field set" already established):
```yaml
project: invoices
workspace: dev
cloud: aws
region: us-east-1
cluster_name: platformops-dev
namespace: invoices-dev
cluster_endpoint_mode: private
runner_ref: platformops-executor-vpc
toolchain: opentofu_local
state_key: aiq/it/invoices/dev/tofu.tfstate
```

## What the application workflow creates
**AWS**: S3 bucket (+ encryption, public-access blocking), CloudFront
OAC, CloudFront distribution, the CloudFront→S3 bucket policy, ACM
certificate (`us-east-1`), Route 53 records, ECR repository (if
missing).

**Kubernetes**: ServiceAccount, Deployment, Service,
Ingress, ConfigMap, Secret reference/`ExternalSecret` (never a raw
secret value — matches `EXECUTION_CREDENTIALS.md`'s "nothing secret in
graph state" rule, extended to Kubernetes manifests: reference a
pre-existing secret manager, don't place values in OpenTofu variables,
plan artifacts, LangGraph state, or logs), HorizontalPodAutoscaler,
PodDisruptionBudget, NetworkPolicy, ResourceQuota, LimitRange.

**Application artifacts — consumed, never built here**: the workflow
takes immutable inputs (`frontend_artifact_uri: s3://...`,
`container_image: ...@sha256:...`) and never builds application code
during infrastructure execution. Build/publish is a separate, not-yet-
designed release workflow — named above as the third boundary category
specifically so this doesn't get folded into provisioning by default
later.

## `ApplicationProvisionRequest`
```python
class ApplicationProvisionRequest(BaseModel):
    scope: Scope                  # reuses gateway/schemas.py's real
                                   # Scope (org/bu/project/workspace)
                                   # directly -- no new model needed
    frontend_artifact_uri: str
    backend_image_digest: str
    frontend_hostname: str
    replicas: int
    cpu_request: str
    memory_request: str
```
Cluster, namespace, region, state key, and execution identity are derived
from `scope` through the workspace registry, never supplied by the user.
The requested hostname must fall under the registry's allowed DNS zone.
Missing application values become clarification questions — this is
exactly the workflow-specific Stage 2 extraction
`INTAKE_HITL_ROUTING.md`'s C2 correction already deferred out of intake
and into "each target workflow" (`PROVISION_WORKFLOW.md`'s
`extract_desired_spec` step); intake itself only resolves
`intent=provision` and the `Scope`, same as today.

## End-to-end flow
Numbered 1-16 below; each step notes whether it **reuses** an
already-designed mechanic or is **new**.

1. **User submits a request** (free text, org/bu/project/workspace/
   app name/artifact/image/hostname/replicas/limits). *New wording,
   same intake shape.*
2. **Intake classifies** `intent=provision`, `target=Scope` — does not
   choose a role, invent infrastructure, or execute anything. *Reuses
   `workflows/intake/` exactly as it exists today.*
3. **Provision workflow extracts `ApplicationProvisionRequest`**,
   clarifying missing fields. *New schema, reuses the deferred-
   clarification pattern.*
4. **Match a reviewed template** — `templates/aws/kubernetes-static-web/`,
   containing S3/CloudFront/ACM/Route53/ECR/deployment/
   service/ingress modules. **Reuses `PROVISION_WORKFLOW.md`'s
   template-first rule verbatim**: the runtime renders an
   already-reviewed template with validated parameters — it never asks
   an LLM to generate OpenTofu. A new template needs normal code
   review before use, matching that doc's Level 1/2/3 split exactly.
5. **Resolve access**:
   ```
   effective_access = min(user_execution_grant,
                           workspace_max_capability,
                           policy_ceiling)
   ```
   **This is not new** — it's the exact three-term composite
   `BOOTSTRAP_WORKFLOW.md` resolved 2026-08-14 (`workspace_ceiling =
   min(org_bu ceiling, registry max_capability)`, then `min()`'d
   against the execution grant), captured here as a consumer of that
   resolution, not a re-derivation. Still undesigned-until-implemented
   at the `ceiling.py` level (see Real vs. Designed). Deployment
   requires `effective_access >= apply_limited`. Execution identity
   comes from the registry — the user never chooses it.
6. **Validate prerequisites** deterministically (account/region/
   cluster/namespace/runner-reachability/state-key/domain/image-digest-immutability/
   artifact-existence/template-version/naming/size-limits) — stops
   before any AWS contact if invalid. *Reuses `PROVISION_WORKFLOW.md`'s
   "template match happens before any cloud read" ordering, extended
   with Kubernetes-specific checks (cluster/namespace) — see Open
   Question 1 below on what backs the resource-type-allowed check
   specifically.*
7. **Render OpenTofu files** into `provision_artifacts/<request_id>/`
   (`main.tf`/`variables.tf`/`outputs.tf`/`backend.tf`/
   `terraform.tfvars.json`). **Exactly** the directory
   `PROVISION_WORKFLOW.md` already designed as
   `ExecutionRequest.artifact_path`'s target — no new shape. Same
   credential-never-in-these-files rule already stated there.
8. **Acquire plan credentials** (STS AssumeRole → short-lived read/
   plan-capable creds → `tofu init`/`validate`/`plan -out=plan.bin`,
   discarded after). **Exactly** `PROVISION_WORKFLOW.md`'s
   `opentofu_local` two-credential-acquisition design — see Open
   Question 2 below on the Kubernetes-provider half specifically.
9. **Build and inspect the plan** — reject unexpected deletes or
   changes outside the requested scope. *Reuses the existing
   `describe_current`/`build_plan` diff shape.*
10. **Deterministic security checks** — resource types/region/cost/
    no-unapproved-deletes/state-key/cluster+namespace/IAM-changes-
    absent/public-S3-disabled/OAC-in-use/image-immutable/resource-
    limits-present. *Extends `security-review-checklist`, which today
    has no `opentofu_local` or Kubernetes section at all — confirmed by
    reading the skill file. See Open Question 4.*
11. **Create an approval request** (scope, requester, IaC artifact
    provenance (`topology_digest` for this composed deployment), plan
    digest, current-state fingerprint, policy snapshot, plain-
    English summary, required approval count). **Reuses**
    `EXECUTION_CREDENTIALS.md`/`PROVISION_WORKFLOW.md`'s six-input
    `approval_digest` formula directly — no new fields needed, the plan
    digest already covers a Kubernetes-inclusive `plan.json`. No apply
    credential exists during the pause.
12. **Revalidate on resume** — access, approver authority, digest
    match, policy/template drift, infrastructure drift, execution
    identity still exists. *Reuses the existing resume revalidation
    step verbatim.*
13. **Acquire apply credentials**, scoped to the registered workspace
    and allow-list. *Reuses the existing apply-phase acquisition.*
14. **Execute** — `tofu init -input=false` / `tofu apply -input=false
    plan.bin`. Executor is non-intelligent: no resource/role choice, no
    plan modification, no destructive retries, no free text, no
    approval bypass. *Reuses `EXECUTION_CREDENTIALS.md`'s existing
    executor-non-intelligence rule, restated for this path.*
15. **Verify independently** — CloudFront deployed, S3 private,
    CloudFront can read via OAC, DNS exists, Deployment available, pods
    ready, Service has endpoints, Ingress has an address, health
    endpoint responds. A clean OpenTofu exit code alone is not
    sufficient. *New verification list, same "verify, don't trust exit
    code" principle already used elsewhere in this design set.*
16. **Record evidence and report** — request ID, actor, scope,
    template version, plan digest, approval IDs, execution role,
    credential expiry, OpenTofu version, state key, resources changed,
    outputs, verification results, failure details; user sees
    deployment status, CloudFront URL, app URL, namespace, revision,
    verification results. *Reuses the existing evidence-record shape.*

## Skill composition
```
provision-application
  +-- extract-application-spec
  +-- select-reviewed-iac-template
  +-- provision-static-assets      (S3, CloudFront, ACM, Route 53)
  +-- provision-kubernetes-workload (namespace, SA, deployment,
  |                                  service, ingress, HPA)
  +-- security-review-checklist
  +-- opentofu-plan
  +-- approval-gate
  +-- opentofu-apply
  +-- verify-application-deployment
  +-- record-evidence
```
**First implementation should not create every leaf as a separate
skill** — one `provision-application` workflow plus deterministic
helper modules; split into skills only once something is independently
reused. See Open Question 3 on this tree's relationship to the
existing `provision-infra` skill.

## Open questions — all resolved 2026-08-14
Originally three blocking questions; resolved same day, decisions
recorded here in place (the original question text kept for the
reasoning trail):

| # | Question | Resolution |
|---|---|---|
| 1 | **What backs the Kubernetes "resource types are allowed" check?** Original options: (a) a parallel Kubernetes allow-list file, or (b) template-scoping alone. This doc originally leaned (b). | **Resolved: both controls, not (b) alone — template matching is not sufficient by itself.** New `infra/kubernetes-allowed-resources.json` (parallel to the existing CloudFormation-shaped file, entries shaped `{"api_version", "kind", "actions"}`), initial entries: Deployment/Service/Ingress/HPA/ConfigMap, `create`+`update` only — **deletes denied by default** (same action-verb extension `PROVISION_WORKFLOW.md`'s Gap 3 already designed for the AWS list). Namespace is cluster-scoped and therefore bootstrap-owned; Secrets, RBAC, CRDs, other cluster-wide resources, and IAM changes are excluded from the first application template entirely. Additionally the template declares its own expected resources, and the plan validator checks **three** things per resource: globally allowed, allowed by this template, and inside the target namespace/scope — preserving deny-by-default at every layer. |
| 2 | **How does OpenTofu's `kubernetes` provider authenticate to the EKS API?** Flagged as a potential credential-leak surface. | **Resolved and verified** (see `COMPOSABLE_PROVISIONER.md`'s Kubernetes-layer section for the full mechanics + sources): the provider's `exec` block runs `aws eks get-token`, which inherits the same short-lived STS credentials from the process environment — the documented mechanism for short-lived cloud tokens per the provider's own docs; no bearer token ever lands in variables/state/plan/LangGraph state. The two permission planes stay distinct: the AWS credential authorizes AWS-provider resources; cluster authorization comes from an **EKS access entry** (verified: AWS's stated successor to `aws-auth`) mapping the execution role to namespace-scoped RBAC. **The namespace, access entry, and namespace RBAC are bootstrap outputs** — added to the prerequisites list above; the application workflow only consumes them and never creates cluster access dynamically. |
| 3 | **Does `provision-application` retire `skills/provision-infra/SKILL.md`?** | **Resolved: no second top-level provisioning entry point.** `skills/provision-infra/SKILL.md` stays the single catalog trigger, rewritten around the real workflow (select profile → select template → render → plan → security review → approval → apply → verify), with deployment profiles and reusable units under the provider-namespaced structure `COMPOSABLE_PROVISIONER.md` defines. This doc's "Skill composition" tree above is **superseded** by that structure — kept below unedited for the reasoning trail, but `COMPOSABLE_PROVISIONER.md`'s repository shape is the target. |
| 4 | `security-review-checklist`'s missing `opentofu_local`/Kubernetes section. | Confirmed as originally noted: extend the existing skill file with a third path-specific section following its own `cdk`/`terraform` pattern; no new skill file. |

## What should be implemented first
1. `ApplicationProvisionRequest`.
2. The reviewed OpenTofu template contract.
3. Request extraction + clarification.
4. Template rendering.
5. `opentofu_local` plan-only execution.
6. Deterministic plan checks using the resolved global + template +
   namespace controls from Question 1.
7. Approval pause/resume.
8. AWS short-lived plan credentials, with the Kubernetes provider using
   the resolved exec-token path from Question 2.
9. Apply credentials + apply.
10. Post-apply verification.
11. Evidence reporting.
12. EKS/VPC/bootstrap workflows — later, separate.

## Sources
- [AWS: Restrict access to an Amazon S3 origin (OAC vs. OAI)](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html) — verified 2026-08-14: OAC explicitly recommended over legacy OAI; bucket-policy `AWS:SourceArn` condition scopes access to one distribution
- [AWS: EKS Fargate considerations](https://docs.aws.amazon.com/eks/latest/userguide/fargate.html) — verified 2026-08-14: no DaemonSets, no privileged containers, no `HostPort`/`HostNetwork`, private-subnet+NAT requirement
- [AWS: EKS best practices — Load Balancing](https://docs.aws.amazon.com/eks/latest/best-practices/load-balancing.html) — verified 2026-08-14: AWS Load Balancer Controller explicitly recommended over the legacy in-tree Service Controller for reconciling `Service`/`Ingress`

## How this relates to the existing docs
Reuses, doesn't duplicate: `PROVISION_WORKFLOW.md`'s template-first IaC
rule, `provision_artifacts/<request_id>/` directory shape,
`opentofu_local`'s two-phase credential acquisition, and the six-input
`approval_digest` formula; `EXECUTION_CREDENTIALS.md`'s executor-
non-intelligence rule and no-secrets-in-state rule (extended here to
Kubernetes manifests); `BOOTSTRAP_WORKFLOW.md`'s 2026-08-14 composite
`effective_access` resolution and Decision 1's disjoint-allow-list
pattern (extended to a third, "application release" category). Adds,
net-new: the S3+CloudFront+EKS reference architecture itself, the
three-way bootstrap/provisioning/release workflow boundary, OAC/ACM/
Fargate-vs-managed-node specifics, `ApplicationProvisionRequest`, and
the `provision-application` skill tree. Not yet indexed from
`HARNESS_DESIGN.md` pending acceptance of the open questions above.
