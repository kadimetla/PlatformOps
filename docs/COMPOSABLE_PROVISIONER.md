## Status
Designed only — no code, no directory restructuring performed. This doc
captures the composable-provisioner shape converged on 2026-08-14 (a
multi-round design discussion that evolved through three iterations —
per-deployment units under `skills/provision-infra/`, then top-level
domain directories, then the final provider-namespaced form below; the
final form is what this doc records, the intermediates are superseded).
Two integration claims verified against current sources this session
(Kubernetes provider exec auth, EKS access entries — see Sources).
Everything here is the *target* shape for `workflows/provision/` and a
`skills/` reorganization; nothing below exists yet except the three
current skill files, which are the migration *inputs*.

## Real vs. Designed
| Area | Status |
|---|---|
| `SKILL_REGISTRY` / any skill graph | Not implemented |
| `ResourceIntent` / `DeploymentPlan` models | Not implemented |
| Deployment profiles (`aws-kubernetes-static-web`, ...) | Not implemented |
| Provider-namespaced `skills/aws/`, `skills/azure/`, `skills/gcp/`, `skills/kubernetes/` | Not implemented — today's `skills/` has exactly three flat entries (`provision-infra`, `security-review-checklist`, `sdlc-diagram-compliance-check`) |
| OpenTofu renderer (`ResourceIntent` → reviewed template → `.tf`) | Not implemented |
| `infra/kubernetes-allowed-resources.json` | Not implemented — decided this session (see APPLICATION_PROVISIONING.md's resolved Q1) |
| `skills/provision-infra/SKILL.md` as entry point | Real file, wrong content — CDK/CCAPI+HCP-shaped, predates this design; **also carries the known `allowed-tools` YAML-list schema bug (`AGENTS.md` Conventions) that must be fixed before any skill-loading mechanism is wired to it** |

## The core idea — units composed by topology, not by an LLM
Skills are broken into small reusable units, and a **deterministic
composition layer** — not a free LLM decision — assembles them per
deployment topology. The LLM may help *select or explain* a profile;
deterministic code validates the final composition. This is
`PROVISION_WORKFLOW.md`'s template-first rule (Level 1/2/3) applied at
a finer grain: the same "runtime renders reviewed artifacts, never
generates arbitrary IaC" invariant, with the reviewed artifact now
being a *profile + unit templates* instead of one monolithic template.

```
User request
  -> intake graph (exists today)
  -> deployment-profile selection
  -> skill graph registry           SKILL_REGISTRY["aws.s3.private_bucket"] ...
  -> composed DeploymentPlan        typed IR, NOT Terraform
  -> deterministic validation       unit contracts + allow-lists + scope
  -> OpenTofu renderer              reviewed templates only
  -> tofu plan -> approval -> apply (PROVISION_WORKFLOW.md, unchanged)
```

## Four unit categories
| Category | Examples | Nature |
|---|---|---|
| Command | `opentofu.init/validate/plan/apply/state_read`, `record_evidence` | One bounded command or check |
| Infrastructure capability | `aws.s3.private_bucket`, `aws.cloudfront.oac_distribution`, `kubernetes.deployment` | Declares inputs, resources it may create, dependencies, required permissions, outputs, verification checks |
| Policy & safety | `validate_scope`, `validate_allowed_resources`, `detect_destructive_changes`, `approval_gate` | Deterministic gating — maps onto the existing security-review/approval mechanics, not new authority |
| Verification | `verify_s3_private`, `verify_kubernetes_rollout`, `verify_application_health` | Post-apply, independent of OpenTofu exit codes |

## Repository shape (target)
Provider-namespaced domains at the top of `skills/`, because AWS,
Azure, and GCP genuinely differ in APIs, IAM, networking, and
Kubernetes integration — a shared *contract*, never shared *internal
logic* (the same one-adapter-per-provider reasoning
`EXECUTION_CREDENTIALS.md`'s `CloudAccessAdapter` section already
states for credentials, applied to provisioning units):

```
skills/
  provision-infra/          # KEPT as the single entry point / router
    SKILL.md                # rewritten around the real workflow:
                            # select profile -> select template ->
                            # render -> plan -> security review ->
                            # approval -> apply -> verify
    profiles/
      aws-kubernetes-static-web/
        SKILL.md
        topology.yaml
        variables.schema.json
  aws/
    s3/          # private_bucket, bucket_policy, artifact_upload
    vpc/         # vpc, subnets, nat_gateway, security_groups
    eks/         # cluster, managed_node_group, access_entry, addons
    cloudfront/  # origin_access_control, distribution
    acm/  route53/  ecr/
  azure/
    storage_account/  virtual_network/  aks/  front_door/  container_registry/
  gcp/
    cloud_storage/  vpc/  gke/  cloud_cdn/  cloud_dns/  artifact_registry/
  kubernetes/    # namespace, service_account, deployment, service,
                 # ingress, hpa -- the shared layer, see below
  opentofu/      # init, validate, plan, apply, state_read
  security-review-checklist/   # existing skill, gains an
                               # opentofu_local/Kubernetes section
```
Each capability unit:
```
skills/aws/s3/private_bucket/
  SKILL.md              # the procedure, human/LLM-readable
  template/             # reviewed OpenTofu module -- the ONLY thing
                        # the renderer may emit from
  inputs.schema.json
  outputs.schema.json
  verify.py
```
**Decided: no second top-level provisioning entry point.**
`skills/provision-infra/SKILL.md` remains the catalog trigger and
compatibility entry point — rewritten, not replaced or duplicated.
`APPLICATION_PROVISIONING.md`'s earlier `provision-application` tree
sketch is superseded by this shape (corrected there in place).

### Terminology note — two meanings of "skill," reconciled
`AGENTS.md`/`CLAUDE.md` define a Skill as a `SKILL.md`-anchored folder
routed by progressive disclosure (description-matched, LLM-facing).
The units above keep that: each unit's `SKILL.md` is real procedural
memory (`MEMORY_ARCHITECTURE.md`'s "skills are procedural memory" —
"skill says how, policy says whether"). What's *new* is that the
runtime composition path doesn't rely on description-matching at all:
`SKILL_REGISTRY` is a code-level dict from provider-qualified ID to
graph builder, and profiles name unit IDs explicitly. Progressive
disclosure remains how a *human or LLM* finds and reads the procedure;
the registry is how the *workflow* executes it. One folder serves both
readers.

## The registry and the shared contract
```python
SKILL_REGISTRY = {
    "aws.s3.private_bucket":        AwsS3BucketGraph,
    "azure.storage.private_container": AzureStorageGraph,
    "gcp.storage.private_bucket":   GcpStorageGraph,
    "aws.eks.cluster":              AwsEksGraph,
    "kubernetes.deployment":        KubernetesDeploymentGraph,
}

class ProvisionSkill(Protocol):
    name: str
    provider: str
    def validate_inputs(self, inputs: dict) -> ValidationResult: ...
    def plan(self, inputs: dict) -> list[ResourceIntent]: ...
    def render(self, inputs: dict) -> IaCArtifacts: ...
    def verify(self, outputs: dict) -> VerificationResult: ...
```
The contract is shared; the implementation is not. `aws.s3.private_bucket`
internally means bucket + policy + public-access block + encryption;
`azure.storage.private_container` means storage account + private
endpoint + container + network rules; `gcp.storage.private_bucket`
means bucket + IAM binding + uniform bucket-level access. The IR does
not pretend these are the same resource.

## The intermediate representation — typed plan, never direct Terraform
Skill graphs return **`ResourceIntent`, not Terraform**. The renderer
maps intents to reviewed templates deterministically:

```python
class ResourceIntent(BaseModel):
    provider: Literal["aws", "azure", "gcp", "kubernetes"]
    kind: str
    logical_name: str
    inputs: dict            # provider-specific fields live HERE,
                            # not in pretend-common top-level fields
    dependencies: list[str]
    allowed_actions: list[str]
    verification_checks: list[str]

class DeploymentPlan(BaseModel):
    profile: str
    resources: list[ResourceIntent]
    dependency_order: list[str]
    policy_snapshot: str
    template_version: str
```
The IR exists **only for orchestration**: dependency ordering, scope
validation, plan-risk calculation, approval summaries, evidence. It is
not a cloud-abstraction layer.

**Runtime LLM→Terraform generation stays forbidden.** Direct Terraform
generation is acceptable in exactly one place — *authoring* a new unit:
LLM proposes a module → PR → human code review → merged into
`skills/<provider>/<domain>/<unit>/template/` → available to the
registry. This is literally `PROVISION_WORKFLOW.md`'s Level 2, unit-
sized; nothing new, restated so the registry doesn't get read as a
loophole.

## Deployment profiles — reviewed composition, parameterized request
A profile is a **reviewed artifact in the template library**, not
runtime configuration the user (or LLM) assembles:

```yaml
name: aws-kubernetes-static-web
provider: aws
requires:                      # prerequisite check -> clear failure,
  - existing: eks.cluster      # never implicit creation
  - existing: route53.hosted_zone
  - existing: opentofu.state_backend
compose:
  - aws.s3.private_bucket
  - aws.cloudfront.origin_access_control
  - aws.cloudfront.distribution
  - aws.acm.cloudfront_certificate
  - aws.route53.alias
  - kubernetes.namespace
  - kubernetes.service_account
  - kubernetes.deployment
  - kubernetes.service
  - kubernetes.ingress
  - kubernetes.hpa
```
The request supplies parameters (project/workspace/region/domain/
image digest/artifact URI); the profile supplies the approved topology.
A future `aws-new-eks-platform` profile composes `vpc.* + eks.* +
ecr.repository` — same machinery, different (bootstrap-side) allow-list,
preserving `BOOTSTRAP_WORKFLOW.md`'s disjointness rule at the profile
level: an application profile can never name identity/cluster units,
and vice versa.

Dependency order comes from the units' declared `dependencies`:
```
s3 -> cloudfront.oac -> cloudfront.distribution -> route53.alias
namespace -> service_account -> deployment -> service -> ingress -> ALB address -> route53.alias
```
Independent branches plan together; dependencies order creation. One
complete OpenTofu plan is rendered from the whole composition —
security checks validate the **final plan**, not just individual units.

## Kubernetes is a shared layer; cluster access is not
`kubernetes.namespace/deployment/service/ingress/hpa` are genuinely
provider-agnostic (they speak the Kubernetes API). Cluster *access* is
provider-specific and stays in the provider namespaces:

```
AWS:   STS credentials -> aws eks get-token          -> Kubernetes API
Azure: Azure token     -> AKS authentication         -> Kubernetes API
GCP:   SA token        -> gke-gcloud-auth-plugin     -> Kubernetes API
```
For AWS specifically (verified this session, both sources):
- The OpenTofu Kubernetes provider's **exec block** is the documented
  mechanism for short-lived tokens — the provider docs state it near-
  verbatim: cloud providers have short-lived tokens, so "an exec-based
  plugin can be used to fetch a new token before each Terraform
  operation," with `aws eks get-token` as their own example
  (`api_version = "client.authentication.k8s.io/v1"`). The `aws`
  process inherits the short-lived STS credentials from its
  environment; **no Kubernetes bearer token is ever written to
  variables, state, plan artifacts, or LangGraph state** — extending
  `EXECUTION_CREDENTIALS.md`'s no-secrets rules to the Kubernetes
  credential path with no new mechanism needed. The provider docs also
  warn against mixing `exec` with static `token`/client-cert
  attributes (undefined precedence) — the rendered provider block must
  carry `exec` only.
- The execution role's *authorization* into the cluster is an **EKS
  access entry** (verified: AWS's stated "best way to grant users
  access to the Kubernetes API," the successor to the `aws-auth`
  ConfigMap), associating the IAM role with namespace-scoped
  Kubernetes permissions or a Kubernetes group. **Creating the access
  entry + namespace-scoped RBAC is bootstrap's job**
  (`BOOTSTRAP_WORKFLOW.md` Level 2 output, alongside the execution
  role itself); the application workflow only *consumes* that access
  and never creates cluster-wide bindings dynamically.

## What units must never do
A unit may say "create a Kubernetes Deployment with these bounded
fields." It must not: choose or assume an IAM role, acquire
credentials, create cluster-admin bindings, deploy arbitrary
user-provided YAML, modify the plan after approval, or bypass the
approval gate. Composition, policy checks, credential acquisition,
plan generation, approval, execution, and evidence belong to the
top-level provision graph and the policy layer — exactly the existing
`EXECUTION_CREDENTIALS.md` executor/credential isolation, restated at
unit granularity so "many small skills" never drifts into "many small
autonomous agents."

## Execution flow (per provider, same spine)
1. Choose cloud/provider profile
2. Resolve provider-qualified unit IDs against `SKILL_REGISTRY`
3. Run each unit's `validate_inputs`
4. Compose + validate the dependency graph
5. Generate `ResourceIntent`s → `DeploymentPlan`
6. Render OpenTofu from reviewed templates only
7. Provider-specific plan checks (AWS: S3 public access blocked, OAC
   in use, IAM actions allowed; Azure: public access disabled, role
   assignments allow-listed, private endpoint; GCP: uniform
   bucket-level access, IAM roles allow-listed, no public principals)
8. Shared security checks (`security-review-checklist`)
9. Approval (existing gate, six-input digest — `DeploymentPlan.
   template_version`/`policy_snapshot` land in the digest's existing
   inputs, no formula change)
10. Provider-specific short-lived credentials (`CloudAccessAdapter`)
11. `tofu apply`
12. Provider-specific verification (units' `verify`)
13. Normalized evidence

## Build order note
This is a target shape, not a first-slice instruction.
`APPLICATION_PROVISIONING.md`'s 12-step implementation order still
governs what gets built first — one profile
(`aws-kubernetes-static-web`), its units inlined as plain modules
inside `workflows/provision/` if that's faster, split into registry
units **only when something is independently reused**
(`MEMORY_ARCHITECTURE.md`'s anti-build list still applies: no
speculative `executors/` package, no uniform unit scaffolding ahead of
a second consumer). The registry earns its existence with the second
profile, not the first.

## Sources
- [Kubernetes provider docs (hashicorp/terraform-provider-kubernetes)](https://registry.terraform.io/providers/hashicorp/kubernetes/latest/docs) — verified 2026-08-14 via the provider repo's `docs/index.md`: exec-based credential plugin for short-lived cloud tokens, `aws eks get-token` example, `client.authentication.k8s.io/v1`, warning against mixing exec with static credential attributes
- [AWS: EKS access entries](https://docs.aws.amazon.com/eks/latest/userguide/access-entries.html) — verified 2026-08-14: "the best way to grant users access to the Kubernetes API," IAM role ↔ Kubernetes permissions/groups association, `aws-auth` ConfigMap successor

## How this relates to the existing docs
Refines [APPLICATION_PROVISIONING.md](APPLICATION_PROVISIONING.md)
(whose three open questions were resolved alongside this doc — see its
updated Open Questions section; its `provision-application` skill-tree
sketch is superseded by this doc's repository shape). Applies
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md)'s Level 1/2/3
template-first rule at unit granularity — no change to that rule.
Extends [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s
no-secrets and executor-isolation rules to the Kubernetes credential
path (exec plugin) and unit boundary, and reuses its
one-adapter-per-provider reasoning for unit namespacing. Adds two
bootstrap outputs to [BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md)'s
Level 2 (EKS access entry + namespace-scoped RBAC for the execution
role) — flagged here, that doc not yet edited.
[MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)'s skills-as-
procedural-memory framing is preserved and its anti-build list still
binds the build order. `AGENTS.md`'s known `allowed-tools` bug in
`provision-infra/SKILL.md` must be fixed as part of that file's
rewrite. Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
