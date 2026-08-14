## Status
Designed only — no code, no directory restructuring performed. This doc
captures the composable-provisioner shape converged on 2026-08-14 (a
multi-round design discussion that evolved through three iterations —
per-deployment units under `skills/provision-infra/`, then top-level
domain directories, then the final provider-namespaced form below; the
final form is what this doc records, the intermediates are superseded).
Two integration claims verified against current sources this session
(Kubernetes provider exec auth, EKS access entries — see Sources).
Three LangGraph mechanics verified **empirically** against the installed
version, not assumed: `checkpointer=False` is a valid argument
(`Checkpointer = None | bool | BaseCheckpointSaver`), a compiled subgraph
sharing the parent's state schema composes correctly across an approval
interrupt without re-running on resume, and list edges are required for
correct joins (see Step 6).
Everything here is the *target* shape for `workflows/provision/` and a
`skills/` reorganization; nothing below exists yet except the three
current skill files, which are the migration *inputs*.

## Real vs. Designed
| Area | Status |
|---|---|
| `TOPOLOGY_UNIT_REGISTRY` / any unit graph | Not implemented |
| `ResourceIntent` / `DeploymentPlan` models | Not implemented |
| Deployment profiles (`aws-kubernetes-static-web`, ...) | Not implemented |
| Provider-namespaced `skills/aws/`, `skills/azure/`, `skills/gcp/`, `skills/kubernetes/` | Not implemented — today's `skills/` has exactly three flat entries (`provision-infra`, `security-review-checklist`, `sdlc-diagram-compliance-check`) |
| OpenTofu renderer (`ResourceIntent` → reviewed template → `.tf`) | Not implemented |
| `infra/kubernetes-allowed-resources.json` | Not implemented — decided this session (see APPLICATION_PROVISIONING.md's resolved Q1) |
| `skills/provision-infra/SKILL.md` as entry point | Real file, wrong content — CDK/CCAPI+HCP-shaped, predates this design; **also carries the known `allowed-tools` YAML-list schema bug (`AGENTS.md` Conventions) that must be fixed before any skill-loading mechanism is wired to it** |

## The core idea — reviewed topology first, free composition later
Skills are broken into small reusable units. For the first slice, a
planner LLM selects a reviewed deployment profile and extracts typed
application parameters; the profile itself supplies the `TopologySpec`,
unit inputs, and edges. Deterministic code validates the profile's units,
inputs, dependencies, target scope, and policy before any graph is
compiled. This is
`PROVISION_WORKFLOW.md`'s template-first rule (Level 1/2/3) applied at
a finer grain: the same "runtime renders reviewed artifacts, never
generates arbitrary IaC" invariant, with the reviewed artifact now
being a *profile + unit templates* instead of one monolithic template.

**Decided 2026-08-14:** build the compiler so the same schema can support
future LLM-proposed unit DAGs, but do not enable that source in the first
slice. Reviewed units do not make every combination of them reviewed.
Free composition is a later authority expansion with a bounded repair
loop and its own acceptance decision. In either mode, a topology is data
with no execution authority until deterministic validation succeeds.

```
User request
  -> intake graph (exists today)
  -> planner LLM tool call          select reviewed profile + extract params
  -> load topology.yaml             version-controlled TopologySpec
  -> topology policy validator      profile becomes executable only here
  -> topology unit registry         planning units only; no executor entries
  -> topology graph compiler        registered implementations only
  -> composed DeploymentPlan        typed IR, NOT OpenTofu
  -> deterministic validation       unit contracts + allow-lists + scope
  -> OpenTofu renderer              reviewed templates only
  -> tofu plan -> approval -> apply (PROVISION_WORKFLOW.md, unchanged)
```

The dynamic topology graph occupies one bounded slot inside a fixed
provision workflow. Authentication, access calculation, credential
acquisition, plan checks, approval, apply, and evidence are never nodes
the planner may add, remove, or reorder:

```
FIXED: resolve actor/workspace -> calculate access -> validate prerequisites
                                  |
                                  v
DYNAMIC:                 [validated topology subgraph]
                                  |
                                  v
FIXED: render -> plan -> checks -> approval -> revalidate -> apply -> verify
```

## Implementation walkthrough — one request, end to end
This section is the implementation contract. It shows exactly what is
stored, what the LLM sees, what gets compiled, and what runs. The first
worked example is the reviewed `aws-static-web` profile; Kubernetes
units use the same mechanism once the smaller path works.

### Step 1 — define one fixed state for the parent and dynamic subgraphs
Do not generate a new state schema from every model proposal. Every unit
writes its result under its instance ID into one reducer-backed map:

```python
from typing import Annotated, TypedDict

def merge_unit_results(left: dict, right: dict) -> dict:
    merged = dict(left)
    for unit_id, result in right.items():
        if unit_id in merged and merged[unit_id] != result:
            raise ValueError(f"conflicting result for unit {unit_id!r}")
        merged[unit_id] = result
    return merged

class ProvisionState(TypedDict):
    request: ApplicationProvisionRequest
    auth_context: WorkflowAuthContext
    workspace: WorkspaceContext
    topology_spec: TopologySpec | None
    unit_results: Annotated[dict[str, UnitResult], merge_unit_results]
    deployment_plan: DeploymentPlan | None
    artifact_path: str | None
    plan_result: TofuPlanResult | None
    approval: ApprovalRecord | None
    execution_result: ExecutionResult | None
    verification: VerificationResult | None
```

`auth_context` and `workspace` are produced before the dynamic subgraph.
Unit nodes may read them but cannot update them. Credentials never appear
in this state.

### Step 2 — define the graph-as-data schema stored by a profile
The reviewed profile stores data, never Python, HCL, import paths, or
condition expressions. Inputs are bindings from the typed application
request, immutable workspace context, or upstream unit outputs:

```python
class LiteralBinding(BaseModel):
    kind: Literal["literal"]
    value: JsonValue

class RequestBinding(BaseModel):
    kind: Literal["request"]
    field: str

class WorkspaceBinding(BaseModel):
    kind: Literal["workspace"]
    field: str

class UnitOutputRef(BaseModel):
    kind: Literal["unit_output"]
    unit_id: str
    output_name: str

InputValue = Annotated[
    LiteralBinding | RequestBinding | WorkspaceBinding | UnitOutputRef,
    Field(discriminator="kind"),
]

class UnitSpec(BaseModel):
    id: str
    uses: str
    inputs: dict[str, InputValue] = Field(default_factory=dict)

class EdgeSpec(BaseModel):
    source: str = Field(alias="from")
    target: str = Field(alias="to")

class TopologySpec(BaseModel):
    schema_version: Literal["1"]
    name: str
    profile: str
    provider: Literal["aws", "azure", "gcp"]
    units: list[UnitSpec]
    edges: list[EdgeSpec]
```

Example reviewed `topology.yaml`:

```json
{
  "schema_version": "1",
  "name": "aws-static-web",
  "profile": "aws-static-web",
  "provider": "aws",
  "units": [
    {
      "id": "assets",
      "uses": "aws.s3.private_bucket",
      "inputs": {
        "bucket_name": {"kind": "workspace", "field": "asset_bucket_name"}
      }
    },
    {
      "id": "cdn",
      "uses": "aws.cloudfront.s3_distribution",
      "inputs": {
        "bucket_id": {
          "kind": "unit_output",
          "unit_id": "assets",
          "output_name": "bucket_id"
        }
      }
    },
    {
      "id": "origin_policy",
      "uses": "aws.s3.cloudfront_oac_policy",
      "inputs": {
        "bucket_id": {
          "kind": "unit_output",
          "unit_id": "assets",
          "output_name": "bucket_id"
        },
        "distribution_arn": {
          "kind": "unit_output",
          "unit_id": "cdn",
          "output_name": "distribution_arn"
        }
      }
    }
  ],
  "edges": [
    {"from": "assets", "to": "cdn"},
    {"from": "assets", "to": "origin_policy"},
    {"from": "cdn", "to": "origin_policy"}
  ]
}
```

The separate `origin_policy` unit is required: its
`aws_s3_bucket_policy` needs both the bucket and CloudFront distribution
ARN. Putting it inside either upstream unit creates a render-time
reference cycle. The topology DAG orders data availability for module
wiring; OpenTofu computes the actual resource creation order from the
rendered references.

### Step 3 — register trusted implementations at process startup
The registry is a PlatformOps application construct, not a built-in
LangGraph service and not content supplied by the LLM:

```python
@dataclass(frozen=True)
class RegisteredUnit:
    unit_id: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    planner: Runnable
    module_path: Path
    allowed_profiles: frozenset[str]
    allowed_resources: frozenset[AllowedResource]
    verifier: UnitVerifier

TOPOLOGY_UNIT_REGISTRY = UnitRegistry([
    register_aws_s3_private_bucket(),
    register_aws_cloudfront_s3_distribution(),
    register_aws_s3_cloudfront_oac_policy(),
])
```

Registration uses explicit imports from reviewed code. `unit.yaml` may
provide metadata, but it may not provide a Python import path that the
runtime imports blindly. Unknown and duplicate IDs fail startup.

A registered `planner` may be a plain typed function or a compiled
LangGraph. Use a graph only when the unit actually has meaningful
multi-step behavior. Both expose the same `ainvoke(input) -> output`
contract to the topology compiler.

This registry is structurally planning-only. Executor, credential,
approval, and evidence nodes live under `workflows/provision/` and are
never imported into this registry. Metadata such as `phase="topology"`
may remain as a consistency check, but it is not the security boundary.

### Step 4 — let the LLM select a reviewed profile
Do not bind every unit or mutation-capable operation to the model. Bind
one tool whose arguments select a profile from the catalog. Application
parameters are produced by the workflow's typed request-extraction node,
not copied into arbitrary per-unit input maps by the planner:

```python
class ProfileSelection(BaseModel):
    profile_id: Literal["aws-static-web"]

@tool
def select_deployment_profile(selection: ProfileSelection) -> str:
    """Select a reviewed deployment topology for this request."""
    return "profile selection captured"
```

As with the existing intake classifier, the tool call itself is the
structured signal. The planner node binds this tool, invokes the model,
and parses the call arguments into state; it does not execute a
mutation-capable tool:

```python
async def propose_topology(state: ProvisionState, model):
    planner = model.bind_tools(
        [select_deployment_profile],
        tool_choice="select_deployment_profile",
    )
    response = await planner.ainvoke(build_planner_messages(state))
    call = require_exactly_one_tool_call(response)
    selection = ProfileSelection.model_validate(call["args"]["selection"])
    spec = load_reviewed_topology(selection.profile_id)
    return {"topology_spec": spec}
```

This call only selects a reviewed graph-as-data artifact. It does not
accept edges, unit IDs, or unit values from the model; resolve credentials,
compile a graph, run OpenTofu, or invoke provider APIs. Session identity,
workspace target, account, region, cluster, namespace, state key, and
execution identity remain hidden runtime context; they are never tool
arguments the LLM chooses.

### Step 5 — validate the proposal before compilation
`validate_topology()` is deterministic and returns either a
`ValidatedTopology` or a list of precise errors. It checks:

1. Every unit ID is unique and exists in `TOPOLOGY_UNIT_REGISTRY`.
2. Every unit is allowed by the selected composition policy/profile.
3. The requested provider matches the registered workspace.
4. Every binding names an allowed field on the typed request/workspace
   model, and the resolved value passes that unit's Pydantic input model;
   arbitrary object paths are rejected.
5. Every output reference names an existing upstream unit and declared
   output.
6. Every reference has a corresponding dependency edge.
7. The graph is acyclic, all units are reachable, and all units reach a
   terminal leaf.
8. Application profiles contain no bootstrap/IAM/RBAC/cluster units.
9. Resource and action declarations are non-empty and allow-listed.
10. No unit has a mutation/executor phase; the dynamic slot is topology-
    planning only.

An invalid reviewed profile is a repository/configuration defect and
fails closed; the LLM does not repair it at runtime. When free composition
is enabled later, structured validation errors may return to that planner
for at most two rounds, matching the harness's existing clarification cap.
An invalid graph is never partially compiled or "best effort" executed.

### Step 6 — compile the validated unit DAG into a stateless subgraph

**First, whether LangGraph is warranted here at all.** The *parent*
graph unambiguously needs it: the approval gate is an `interrupt()`
across a multi-day pause with checkpointed resume, which is exactly
what LangGraph exists for. The *topology subgraph* is a judgment call
and is recorded as one rather than assumed. It is compiled with
`checkpointer=False`, contains no interrupts, and for the first
profile is three pure functions producing typed intents — a
topological sort plus `asyncio.gather` would cover that in far less
machinery.

```
LangGraph earns the topology slot when:   a plain planner is enough when:
  units run concurrently on real          the DAG is small, every unit is a
    branch fan-out                          pure typed function, and nothing
  the reducer's conflict check is           needs tracing beyond a log line
    load-bearing
  a unit is itself multi-step
    (registered planner is a graph,
    not a function)
  per-node tracing/observability
    matters operationally
```
Decision: use LangGraph, because unit planners are already allowed to
*be* compiled graphs when a unit has real multi-step behavior (Step 3),
and one execution model for both cases beats two. But the compiler
below must stay roughly this size — a few dozen lines wiring registered
builders. **If it grows conditional edges, retries, or per-unit control
flow, that is the signal the topology slot has taken on lifecycle
responsibilities that belong in the fixed parent**, not a reason to
extend the compiler.

The parent graph is already fixed. Its `run_topology` node compiles and
invokes a per-request subgraph:

```python
def compile_topology(spec: ValidatedTopology, registry: UnitRegistry):
    builder = StateGraph(ProvisionState)

    for unit in spec.units:
        registration = registry.resolve(unit.uses)
        builder.add_node(
            unit.id,
            build_unit_wrapper(unit, registration),
        )

    for root_id in spec.root_ids:
        builder.add_edge(START, root_id)
    for target_id, predecessor_ids in spec.predecessors_by_target.items():
        # A list edge is a real join: wait for every predecessor rather
        # than triggering the target once per independently-added edge.
        builder.add_edge(predecessor_ids, target_id)
    for leaf_id in spec.leaf_ids:
        builder.add_edge(leaf_id, END)

    return builder.compile(checkpointer=False)
```

**The list edge is not stylistic — verified empirically 2026-08-14**
against the installed LangGraph. With branches of *unequal depth*
(`a -> join` alongside `b1 -> b2 -> join`), separate `add_edge` calls run
`join` **twice**; a single list edge runs it once:
```
list-edge join   -> join ran 1 time(s); order: ['a', 'b1', 'b2', 'join']
separate edges   -> join ran 2 time(s); order: ['a', 'b1', 'b2', 'join', 'join']
```
Equal-depth branches hide the difference (both run once), so this is easy
to get wrong and not notice. `merge_unit_results`' conflict check is the
second line of defence if it ever regresses.

`build_unit_wrapper()` resolves only typed context references and
already-produced upstream outputs, calls the registered planner, validates
its output model, and writes `{unit.id: result}` to `unit_results`.
Independent roots may run in parallel; the reducer merges their distinct
instance IDs. The dynamic subgraph is stateless because human pauses and
durable execution live in the fixed parent graph.

### Step 7 — invoke the subgraph from the fixed provision graph
LangGraph cannot add nodes to an already-compiled parent. The fixed
parent therefore invokes the newly compiled topology from one node:

```python
async def run_topology(state: ProvisionState):
    validated = validate_topology(
        state["topology_spec"],
        workspace=state["workspace"],
        registry=TOPOLOGY_UNIT_REGISTRY,
    )
    topology = compile_topology(validated, TOPOLOGY_UNIT_REGISTRY)
    result = await topology.ainvoke(state)
    return {"unit_results": result["unit_results"]}
```

The fixed parent graph is compiled once at application startup:

```text
resolve_context -> propose_topology -> run_topology -> compose_plan
  -> render_opentofu -> tofu_plan -> validate_plan -> approval_interrupt
  -> revalidate -> tofu_apply -> verify -> evidence -> END
```

`approval_interrupt`, credential acquisition, and `tofu_apply` are not
registered topology units and cannot appear in `TopologySpec`.

### Step 8 — merge unit results into a deployment plan
`compose_plan` verifies that every expected unit produced exactly one
typed result, resolves output wiring, and creates the orchestration IR:

```python
class DeploymentPlan(BaseModel):
    topology_digest: str
    profile: str
    scope: Scope
    units: list[ResolvedUnit]
    dependency_order: list[str]
    template_digests: dict[str, str]
```

The topology digest covers the normalized `TopologySpec`, profile version,
registry unit versions, and every participating template digest. It
replaces the old single `template_version` approval input for composed
deployments, so changing a node, edge, binding, unit implementation, or
template invalidates approval.

Persist a `TopologyExecutionRecord` independently of the LangGraph
checkpoint before planning. It contains the normalized spec, topology
digest, profile version, unit versions, and template digests. The fixed
parent graph does not need the topology to rebuild on resume because the
dynamic subgraph is invoked inside the already-completed `run_topology`
node, not embedded into the parent at compile time. Independent persistence
is still required for approval revalidation, audit, and recovery if the
checkpoint store is unavailable.

### Step 9 — render reviewed OpenTofu modules
Each unit result identifies a reviewed module already present in its
skill folder. The renderer writes a root module containing only `module`
blocks and typed wiring:

```hcl
module "assets" {
  source      = "./modules/aws_s3_private_bucket"
  bucket_name = "invoices-dev-assets"
}

module "cdn" {
  source    = "./modules/aws_cloudfront_s3_distribution"
  bucket_id = module.assets.bucket_id
}

module "origin_policy" {
  source           = "./modules/aws_s3_cloudfront_oac_policy"
  bucket_id        = module.assets.bucket_id
  distribution_arn = module.cdn.distribution_arn
}
```

The renderer cannot emit a raw `resource` block from model text. Direct
LLM-generated OpenTofu remains an authoring-time PR path only.

### Step 10 — validate the real OpenTofu plan
`tofu show -json plan.bin` is the authoritative diff. The plan validator
maps every resource address back to exactly one unit and checks:

```text
planned resource type is declared by that unit
planned action is allowed (delete denied by default)
provider/account/region match the workspace
Kubernetes resources remain in the registered namespace
no unexplained resource exists
```

Unit-level validation proves the composition is legal; plan-level
validation proves the rendered provider resources actually match it.

### Step 11 — approval and apply remain fixed
The parent graph pauses with an approval payload bound to the saved plan,
topology digest, policy snapshot, current-state fingerprint, execution
identity, and allow-list version. The topology digest already covers all
unit and template versions. On resume it rechecks
all of them, obtains a fresh apply credential, and runs only
`tofu apply plan.bin`. The model cannot regenerate or modify anything
between approval and apply.

### Step 12 — verify units and store evidence
After apply, each registered verifier receives only its declared outputs
and immutable workspace context. Results merge into one evidence record:

```text
request -> topology spec/digest -> unit versions -> rendered artifacts
        -> plan/digest -> approval -> execution identity -> resources
        -> independent verification
```

### What is stored where
| Artifact | Location | Authoritative for |
|---|---|---|
| `SKILL.md` | `skills/<provider>/<domain>/<unit>/` | Human/LLM procedure and discovery |
| Unit registration code | Same unit package, imported by application startup | Executable implementation and typed contract |
| Reviewed OpenTofu module | Unit's `template/` directory | IaC emitted at runtime |
| Approved `topology.yaml` | `skills/provision-infra/profiles/<profile>/` | Reusable fast-path composition |
| `TopologyExecutionRecord` | Evidence store beside the approval record | Normalized topology, profile/unit/template versions, deterministic reconstruction and revalidation |
| Compiled topology graph | Process memory; optionally cached by topology digest | Per-request planning execution |
| Saved OpenTofu plan | Request artifact directory | Exact approved provider diff |
| Checkpoint | Parent provision graph's checkpointer | Approval pause/resume |

Future free composition produces the same `TopologyExecutionRecord` but
starts from an untrusted LLM proposal. To promote one into a reusable
profile, a coder opens a PR adding `topology.yaml`; normal code review is
the promotion boundary. Runtime execution never edits the skill library.

## Four unit categories
| Category | Examples | Nature |
|---|---|---|
| Infrastructure capability | `aws.s3.private_bucket`, `aws.cloudfront.s3_distribution`, `kubernetes.deployment` | The only category admitted to `TOPOLOGY_UNIT_REGISTRY`; declares typed inputs/outputs and bounded resource intents |
| Command | `opentofu.init/validate/plan/apply/state_read`, `record_evidence` | Fixed lifecycle services called by parent workflow nodes, never topology units |
| Policy & safety | `validate_scope`, `validate_allowed_resources`, `detect_destructive_changes`, `approval_gate` | Fixed deterministic gates, structurally unavailable to the topology compiler |
| Verification | `verify_s3_private`, `verify_kubernetes_rollout`, `verify_application_health` | Registered callbacks invoked by the fixed verification stage after apply |

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
`TOPOLOGY_UNIT_REGISTRY` is a code-level registry from provider-qualified ID to
trusted registration, and profiles name unit IDs explicitly. Progressive
disclosure remains how a *human or LLM* finds and reads the procedure;
the registry is how the *workflow* executes it. One folder serves both
readers.

## Earlier conceptual contract, refined by the walkthrough above
The first design pass represented every unit as a four-method object.
The implementation walkthrough refines that into a `RegisteredUnit`
whose planner has one typed `ainvoke` boundary and whose module/verifier/
policy metadata sit on the registration. The old sketch is retained here
in corrected form because it explains the common calling convention:

```python
TOPOLOGY_UNIT_REGISTRY = {
    "aws.s3.private_bucket": AwsS3BucketRegistration,
    "aws.cloudfront.s3_distribution": AwsCloudFrontRegistration,
    "aws.s3.cloudfront_oac_policy": AwsCloudFrontOacPolicyRegistration,
    "azure.storage.private_container": AzureStorageRegistration,
    "gcp.storage.private_bucket": GcpStorageRegistration,
    "aws.eks.cluster": AwsEksRegistration,
    "kubernetes.deployment": KubernetesDeploymentRegistration,
}

class UnitPlanner(Protocol):
    async def ainvoke(self, request: BaseModel) -> BaseModel: ...
```
The contract is shared; the implementation is not. `aws.s3.private_bucket`
internally means bucket + public-access block + encryption (**corrected
2026-08-14**: the first pass said "bucket + policy"; the bucket policy is
deliberately a *separate* unit — see "The bucket-policy unit" below, and
note Step 3's registry example already excludes it from
`allowed_resources`); `azure.storage.private_container` means storage
account + private endpoint + container + network rules;
`gcp.storage.private_bucket` means bucket + IAM binding + uniform
bucket-level access. The IR does not pretend these are the same resource.

### The bucket-policy unit — why it is separate
The OAC pattern needs `aws_s3_bucket_policy` granting
`cloudfront.amazonaws.com` `s3:GetObject` under an
`AWS:SourceArn`-equals-this-distribution condition (verified against AWS's
own example — see `APPLICATION_PROVISIONING.md`'s Sources). That policy
depends on **both** the bucket and the distribution, so it cannot live
inside `aws.s3.private_bucket`: doing so would make the unit DAG cyclic
(bucket needs the distribution ARN, distribution needs the bucket). As a
third unit downstream of both, the DAG stays acyclic:

```
assets (bucket) ---------> cdn (distribution + OAC) ---> cloudfront_oac_policy
      \                                                       ^
       \-----------------------------------------------------/
```
This is the general constraint worth stating once: **topology edges order
render-time data flow, not resource creation** — OpenTofu derives real
creation order from the rendered HCL. Unit boundaries must therefore be
drawn so that no unit needs an output of something downstream of itself.

The worked example and registry use
`aws.s3.cloudfront_oac_policy` for this join unit. Provider-specific
tests must prove its rendered policy grants only
`cloudfront.amazonaws.com` and scopes `AWS:SourceArn` to the selected
distribution.

## The intermediate representation — typed plan, never direct Terraform
Skill graphs return **`ResourceIntent`, not Terraform**. The renderer
maps intents to reviewed templates deterministically:

```python
class ResourceIntent(BaseModel):
    provider: Literal["aws", "azure", "gcp", "kubernetes"]
    kind: str
    logical_name: str
    inputs: dict            # serialized only AFTER the unit-specific
                            # Pydantic model validates provider fields
    dependencies: list[str]
    allowed_actions: list[str]
    verification_checks: list[str]

class DeploymentPlan(BaseModel):
    topology_digest: str
    profile: str
    resources: list[ResourceIntent]
    dependency_order: list[str]
    policy_snapshot: str
    template_digests: dict[str, str]
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
  - existing: kubernetes.namespace
  - existing: route53.hosted_zone
  - existing: opentofu.state_backend
compose:
  - aws.s3.private_bucket
  - aws.cloudfront.s3_distribution
  - aws.s3.cloudfront_oac_policy # depends on bucket AND distribution;
                                 # omitting it means CloudFront gets 403
  - aws.acm.cloudfront_certificate
  - aws.route53.alias
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

Dependency order is stored explicitly in the reviewed topology and
validated against every output reference:
```
assets -> cdn
[assets, cdn] -> cloudfront_oac_policy
cdn -> route53.alias
existing namespace -> service_account -> deployment -> service -> ingress -> ALB address
```
Independent branches plan together; dependencies order creation. One
complete OpenTofu plan is rendered from the whole composition —
security checks validate the **final plan**, not just individual units.

The first slice gives the static frontend a custom Route 53 hostname via
CloudFront and reports the controller-created ALB hostname for the API.
Creating a custom API hostname after the asynchronous Ingress controller
reports its ALB is a later reconciliation unit, not falsely represented
as an input known to the first saved plan.

## Kubernetes is a shared layer; cluster access is not
`kubernetes.deployment/service/ingress/hpa` are genuinely
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
  entry + namespace creation + namespace-scoped RBAC is bootstrap's job**
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
1. Resolve the authenticated workspace and its composition policy.
2. Have the LLM select an approved profile and extract typed application
   parameters; load that profile's reviewed `TopologySpec`.
3. Resolve provider-qualified unit IDs against
   `TOPOLOGY_UNIT_REGISTRY`.
4. Validate unit inputs, output references, profile membership, and the
   dependency DAG.
5. Compile and invoke the stateless topology subgraph.
6. Generate `ResourceIntent`s → `DeploymentPlan`.
7. Render OpenTofu from reviewed templates only.
8. Provider-specific plan checks (AWS: S3 public access blocked, OAC
   in use, IAM actions allowed; Azure: public access disabled, role
   assignments allow-listed, private endpoint; GCP: uniform
   bucket-level access, IAM roles allow-listed, no public principals)
9. Shared security checks (`security-review-checklist`).
10. Approval (existing gate; `DeploymentPlan.topology_digest` is the
    artifact-provenance input and covers profile, unit, and template
    versions)
11. Provider-specific short-lived credentials (`CloudAccessAdapter`).
12. `tofu apply` of the saved plan.
13. Provider-specific verification (registered unit verifiers).
14. Normalized evidence.

## Build order note
**Refined 2026-08-14:** the earlier version deferred the registry until
a second profile reused a unit. The graph-as-data design now makes the
small registry part of the first vertical slice because validation and
compilation require it. This does not authorize scaffolding every cloud:
start with `aws.s3.private_bucket` and
`aws.cloudfront.s3_distribution`,
`aws.s3.cloudfront_oac_policy`, one `aws-static-web` profile, and the 12
walkthrough steps above. Add Kubernetes after that path can render and
validate a real OpenTofu plan; add Azure/GCP registrations only when
their first profiles are implemented.

## Sources
- [LangGraph: Subgraphs](https://docs.langchain.com/oss/python/langgraph/use-subgraphs) — verified 2026-08-14: compiled subgraph as a parent node when state is shared; wrapper invocation when schemas differ; `checkpointer=False` for stateless subgraphs
- [LangChain: Tools](https://docs.langchain.com/oss/python/langchain/tools) — verified 2026-08-14: model-visible name/description/input schema, structured tool calls, and `ToolNode` execution boundary; this design captures the forced tool call as structured proposal data rather than exposing execution authority
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
one-adapter-per-provider reasoning for unit namespacing. The matching
[BOOTSTRAP_WORKFLOW.md](BOOTSTRAP_WORKFLOW.md) Level 2 contract now
creates the registered Namespace, EKS access entry, and namespace-scoped
RBAC before the application profile can route.
[MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)'s skills-as-
procedural-memory framing is preserved and its anti-build list still
binds the build order. `AGENTS.md`'s known `allowed-tools` bug in
`provision-infra/SKILL.md` must be fixed as part of that file's
rewrite. Indexed from [HARNESS_DESIGN.md](HARNESS_DESIGN.md).
