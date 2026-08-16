## Status
Designed target with the first non-mutating foundation implemented
2026-08-14. A basic `TopologySpec` loader and structural DAG validator now
exist in `workflows/provision/topology.py`; no unit registry, topology
compiler, renderer, or IaC execution code exists. This doc
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
Most of this remains the *target* shape for `workflows/provision/` and a
`skills/` reorganization. The real provision handler stops after deterministic
scope resolution, reviewed-profile selection, and typed static-web request
extraction; the reviewed profile registry/`topology.yaml` loader and basic
structural validator exist but are not invoked by that handler. See
`PROVISION_IMPLEMENTATION_PLAN.md`. **2026-08-15**: added
the free-composition planner section (LangGraph-native `create_agent`/
`ToolNode`, after evaluating and rejecting a Pi/Node sidecar and Pydantic
AI Harness — both verified against their own current docs, not assumed),
the progressive-disclosure section, and the Kubernetes-skill-neutrality
split rule (`kubernetes.*` stays provider-neutral; cluster access/identity/
registry integration lives in `aws.eks.*`/`azure.aks.*`/`gcp.gke.*`).

## Real vs. Designed
| Area | Status |
|---|---|
| Per-run tenant context / `resolve_scope` | First slice implemented 2026-08-14: `ScopeHint` remains outside `ActorSession`, `gateway/scope.py` resolves exact targets against known workspaces plus execution grants, the harness preserves the hint across clarification, and CLI parses `--scope`; durable `RunContext` and a real workspace registry remain unbuilt |
| `workflows/provision/` request-preparation graph | Implemented through `resolve_scope -> select_profile -> extract_profile_request -> END`; registered through the deterministic dispatcher but returns only a non-executable `ProvisionDraft` |
| `TopologySpec` loader / structural DAG validation | Basic foundation implemented in `workflows/provision/topology.py`; exact unit contracts, binding/allow-list policy validation, compilation, and execution remain unbuilt |
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
  -> intake graph                   classify intent only
  -> resolve scope                  structured/canonical target -> registry
  -> calculate effective access    requires the resolved scope
  -> planner LLM tool call          select one reviewed profile
  -> resolve profile registration  request model + topology path
  -> profile request extraction     use that profile's typed schema + HITL
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
FIXED: resolve scope/workspace -> calculate access -> validate prerequisites
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

### Step 1 — define fixed parent state and revision-local topology state
Do not generate a new state schema from every model proposal. The parent
stores one replaceable candidate, while every topology invocation starts
fresh child state and writes unit results under instance IDs into one
reducer-backed map:

```python
from typing import Annotated, TypedDict

# Closed union of the reviewed-unit TopologySpec and the enabled provider-
# resource topology models; never BaseModel, Any, or a bare dict.
TopologyDefinition = ...

def merge_unit_results(left: dict, right: dict) -> dict:
    merged = dict(left)
    for unit_id, result in right.items():
        if unit_id in merged and merged[unit_id] != result:
            raise ValueError(f"conflicting result for unit {unit_id!r}")
        merged[unit_id] = result
    return merged

class TopologyRevision(BaseModel):
    revision_id: str
    parent_revision_id: str | None
    spec: TopologyDefinition  # reviewed unit DAG or provider-resource topology
    topology_digest: str
    created_by: Literal["profile", "planner", "repair_agent", "user"]
    change_reason: str

class CandidateArtifacts(BaseModel):
    revision_id: str
    unit_results: dict[str, UnitResult]
    rendered_artifact: RenderedArtifact | None = None
    plan_result: LocalPlanResult | None = None
    policy_result: PolicyResult | None = None

class TopologyRunState(TypedDict):
    revision_id: str
    scope: Scope
    auth_context: WorkflowAuthContext
    workspace: WorkspaceContext
    application_request: ApplicationProvisionRequest
    unit_results: Annotated[dict[str, UnitResult], merge_unit_results]

class ProvisionState(TypedDict):
    raw_text: str
    run_context: RunContext
    scope: Scope | None
    auth_context: WorkflowAuthContext
    workspace: WorkspaceContext
    profile_id: str | None
    application_request: ApplicationProvisionRequest | None
    topology_revision: TopologyRevision | None
    candidate_artifacts: CandidateArtifacts | None
    deployment_plan: DeploymentPlan | None
    approval: ApprovalRecord | None
    execution_result: ExecutionResult | None
    verification: VerificationResult | None
```

`scope`, `auth_context`, `workspace`, and the profile-specific
`application_request` are produced before the dynamic subgraph. Unit
nodes may read them but cannot update them. Credentials never appear in
this state.

**Refined 2026-08-16 for fluid composition:** the reducer-backed
`TopologyRunState.unit_results` is scratch state for exactly one topology-
subgraph invocation. It must not survive into a revised topology. Slices
13/14 therefore invoke each validated revision with fresh child state and
return one replacement candidate bundle to the parent.

The parent stores the current `TopologyRevision` and its whole
`CandidateArtifacts`; it does not merge results across revision IDs. A
removed unit must disappear, a changed unit may reuse the same instance ID
without conflicting with its predecessor revision, and every downstream
artifact is attributable to exactly one topology digest. The existing
`merge_unit_results` conflict check remains useful *within* one parallel
invocation, where any second write to an instance ID is an error even if
the value happens to be identical.

Scope resolution is not performed by today's `IntakeDecision`: the real
schema carries intent/routing fields only. Active tenant is also **not a
mutable `ActorSession` field**. A user may have simultaneous threads in
different tenants, so session-level selection would let one tab change
another tab's target. The harness instead supplies per-thread/run context:

```python
class TenantRef(BaseModel):
    org: str
    bu: str

    @property
    def org_bu(self) -> str:
        return f"{self.org}:{self.bu}"

class ScopeHint(BaseModel):
    tenant: TenantRef
    project: str | None = None
    workspace: str | None = None

class RunContext(BaseModel):
    thread_id: str
    actor_id: str
    scope_hint: ScopeHint
```

The first provision slice adds a fixed `resolve_scope` node before access
calculation. It accepts the structured hint from a TUI/UI selector or CLI
`--scope aiq:it/invoices/dev`, resolves it against the workspace registry,
and validates it against the actor's current execution grants. The actor
session is supplied as runtime context, not copied into checkpointed graph
state. Missing or ambiguous mutation scope produces return-and-reinvoke
clarification; unknown and unauthorized targets use the same external
response. Neither org/BU nor project/workspace is accepted from an
unconstrained LLM guess. The resulting complete `Scope` is the input to
effective-access calculation.

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

### Step 4 — select a reviewed profile, then extract its request
Do not bind every unit or mutation-capable operation to the model. Bind
one tool whose arguments select a profile from the catalog. Application
parameters are produced afterward by a separate typed request-extraction
node, not copied into arbitrary per-unit input maps by the planner:

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
async def select_profile(state: ProvisionState, model):
    planner = model.bind_tools(
        [select_deployment_profile],
        tool_choice="select_deployment_profile",
    )
    response = await planner.ainvoke(build_planner_messages(state))
    call = require_exactly_one_tool_call(response)
    selection = ProfileSelection.model_validate(call["args"]["selection"])
    return {"profile_id": selection.profile_id}
```

This call only selects a reviewed graph-as-data artifact. It does not
accept edges, unit IDs, or unit values from the model; resolve credentials,
compile a graph, run OpenTofu, or invoke provider APIs. Session identity,
workspace target, account, region, cluster, namespace, state key, and
execution identity remain hidden runtime context; they are never tool
arguments the LLM chooses.

If more than one reviewed profile matches the request, profile selection
returns a clarification rather than guessing. Scope clarification and
profile clarification use the same bounded return-and-reinvoke HITL
pattern as intake; neither reaches the mutation approval checkpoint.

Profile selection happens before parameter extraction because profiles
have different contracts. The first profile requires only frontend
fields:

```python
class AwsStaticWebProvisionRequest(BaseModel):
    profile_id: Literal["aws-static-web"]
    scope: Scope
    frontend_artifact_uri: str
    frontend_hostname: str
```

`resolve_profile_registration` resolves the selected ID to trusted
metadata containing its request model, topology path, and profile
version. `extract_profile_request` uses that registered schema, extracts
and validates its fields, and emits bounded HITL
clarification for missing values. A later
`aws-kubernetes-static-web` profile uses a different registered request
model containing image, replica, CPU, and memory fields. Those fields do
not become optional members of one flat universal model.

Only after extraction succeeds does deterministic `load_topology` read
and validate the reviewed YAML:

```python
def load_topology(state: ProvisionState):
    registration = PROFILE_REGISTRY.resolve(state["profile_id"])
    spec = load_reviewed_topology(registration.topology_path)
    return {
        "topology_revision": make_topology_revision(
            spec=spec,
            parent=None,
            created_by="profile",
            change_reason="selected reviewed profile",
        )
    }
```

### Step 5 — validate the reviewed topology before compilation
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
    builder = StateGraph(TopologyRunState)

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
    revision = state["topology_revision"]
    validated = validate_topology(
        revision.spec,
        workspace=state["workspace"],
        registry=TOPOLOGY_UNIT_REGISTRY,
    )
    topology = compile_topology(validated, TOPOLOGY_UNIT_REGISTRY)
    result = await topology.ainvoke({
        "revision_id": revision.revision_id,
        "scope": state["scope"],
        "auth_context": state["auth_context"],
        "workspace": state["workspace"],
        "application_request": state["application_request"],
        "unit_results": {},
    })
    return {
        "candidate_artifacts": CandidateArtifacts(
            revision_id=revision.revision_id,
            unit_results=result["unit_results"],
        )
    }
```

The fixed parent graph is compiled once at application startup:

```text
resolve_scope -> resolve_context -> select_profile
  -> resolve_profile_registration -> extract_profile_request
  -> load_topology_revision -> run_topology -> compose_plan
  -> render_opentofu -> tofu_plan -> validate_plan -> approval_interrupt
  -> revalidate -> tofu_apply -> verify -> evidence -> END
```

`approval_interrupt`, credential acquisition, and `tofu_apply` are not
registered topology units and cannot appear in `TopologySpec`.

### Step 8 — merge unit results into a deployment plan
`compose_plan` verifies that `candidate_artifacts.revision_id` matches the
current revision and that every expected unit produced exactly one typed
result, resolves output wiring, and creates the orchestration IR:

```python
class DeploymentPlan(BaseModel):
    revision_id: str
    topology_digest: str
    profile_id: str
    scope: Scope
    resources: list[ResourceIntent]
    dependency_order: list[str]
    template_digests: dict[str, str]
```

**Corrected 2026-08-16 after tracing every handoff:** this is the one
canonical `DeploymentPlan`. An earlier version of this section used
`units: list[ResolvedUnit]`, while the later IR section independently
defined the same class name with `resources: list[ResourceIntent]` and a
`policy_snapshot` but no `scope`. Unit results belong to
`CandidateArtifacts`; `compose_plan` deterministically converts them into
the `ResourceIntent` list above. Plan-policy evaluation has not happened at
this point, so its snapshot/result belongs to the later `PolicyResult`, not
this pre-render IR. `revision_id` and `scope` remain explicit so every
artifact can be checked against the current revision and target.

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

### Step 9 — render reviewed IaC modules
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

The renderer cannot emit a raw `resource` block from model text. The same
reviewed HCL artifact may feed `opentofu_local`, `terraform_local`, or the
HCP upload path, but the workspace registry—not the renderer or model—selects
the toolchain. Direct LLM-generated Terraform/OpenTofu remains an authoring-
time PR path only.

### Step 10 — validate the real local-engine plan
For the MVP, `tofu show -json plan.bin` is the authoritative diff; the
`terraform_local` adapter uses `terraform show -json plan.bin` through the
same `LocalPlanResult` contract. The plan validator
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
identity, allow-list version, and resolved toolchain-identity digest. The
topology digest already covers all unit and template versions. On resume it rechecks
all of them, obtains a fresh apply credential, and runs only
the same sealed local engine identity/version's `apply plan.bin`. It cannot
apply a Terraform plan with OpenTofu or an OpenTofu plan with Terraform, and
the model cannot regenerate or modify anything between approval and apply.

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
    eks/         # cluster, managed_node_group, access, workload_identity,
                 # load_balancer, ecr_auth -- see "Kubernetes is a shared
                 # layer" below for why cluster access lives here, not
                 # under kubernetes/
    cloudfront/  # origin_access_control, distribution
    acm/  route53/  ecr/
  azure/
    storage_account/  virtual_network/
    aks/         # cluster, access, workload_identity, ingress, acr_auth
    front_door/  container_registry/
  gcp/
    cloud_storage/  vpc/
    gke/         # cluster, access, workload_identity, ingress,
                 # artifact_registry_auth
    cloud_cdn/  cloud_dns/  artifact_registry/
  kubernetes/    # namespace, service_account, deployment, service,
                 # ingress, hpa -- provider-NEUTRAL, see below
  local-iac/     # fixed lifecycle adapters: opentofu_local first,
                 # terraform_local second; not topology units
  security-review-checklist/   # existing skill, gains an
                               # local-IaC/Kubernetes section
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

## Progressive disclosure — context, not authority
LangGraph has no built-in `load_skill()` primitive — every graph in
this codebase, including this one, is explicit `add_node`/`add_edge`
calls (confirmed hands-on across this whole design set; there is
nothing else to import). Progressive disclosure here is an
**application pattern built from ordinary nodes and state**, narrowing
what context the model sees at each step rather than a framework
feature:

```
classify_intent
  -> discover_skill_summaries   catalog of profile IDs + one-line
                                descriptions, not full contracts
  -> select_profile             LLM picks one ID (Step 4, above);
                                today's catalog has exactly one entry
  -> load_skill_contracts       resolve_profile_registration + the
                                registered request model (Step 4)
  -> validate_composition       load_topology + validate_topology
                                (Steps 4-5)
  -> provision_workflow         everything from Step 6 onward
```

This is the same five real steps already designed above, named as a
disclosure sequence rather than repeated: the catalog step exists
today only as a `Literal["aws-static-web"]` on `ProfileSelection`
(`workflows/provision/schemas.py`) — a real `discover_skill_summaries`
node becomes necessary once a second profile exists, not before
(`MEMORY_ARCHITECTURE.md`'s anti-build discipline again).

**The boundary that matters**: progressive disclosure controls
*context*, never *authority*. Loading `skills/aws/s3/private_bucket/`
can explain how to shape an S3 unit; it cannot grant AWS access,
choose a credential, or bypass approval — those stay fixed
parent-graph stages regardless of what's loaded (verified: LangChain
documents a tool as "callable functions with well-defined inputs and
outputs... executed through `ToolNode`" — the model decides *when* to
call one, never what the call is permitted to do). A skill loader
therefore returns only trusted, already-registered content:

```python
def load_skill(skill_id: str) -> SkillContract:
    registration = registry.get(skill_id)
    if registration is None:
        raise UnknownSkill(skill_id)
    return registration.load()
```

Never an arbitrary filesystem path, Python import string, or graph
node/edge — the same "the LLM selects an ID, trusted code resolves it"
shape `select_deployment_profile`/`TOPOLOGY_UNIT_REGISTRY` already use
throughout this doc, restated at the loader level so a future
`discover_skill_summaries`/`load_skill_contracts` pair doesn't
reintroduce a path-injection surface this design has otherwise closed
everywhere else.

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
class AwsS3PrivateBucketIntent(BaseModel):
    kind: Literal["aws.s3.private_bucket"]
    logical_name: str
    config: AwsS3PrivateBucketConfig
    dependencies: list[str]
    allowed_actions: list[str]
    verification_checks: list[str]

# The other two first-profile members follow the same exact shape with
# AwsCloudFrontDistributionConfig and AwsCloudFrontOacPolicyConfig.
ResourceIntent = Annotated[
    AwsS3PrivateBucketIntent
    | AwsCloudFrontDistributionIntent
    | AwsCloudFrontOacPolicyIntent,
    Field(discriminator="kind"),
]
```

**Corrected 2026-08-16:** the earlier sketch stored `inputs: dict` after
validation. That still leaves an untyped persisted boundary and conflicts
with the exact unit contracts required by Step 5. The first implementation
uses only the three-member discriminated union above; later providers extend
the closed union deliberately rather than widening it to a generic bag.

The canonical `DeploymentPlan` is defined once in Step 8 above. The policy
snapshot digest is produced when the real OpenTofu plan is checked and is
carried by `PolicyResult`/the sealed approval inputs; it is not guessed or
pre-populated while composing resource intents.
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

### The split rule, stated once
**Decided 2026-08-15:** `kubernetes.*` units stay provider-neutral by
default; do not fork `kubernetes/deployment` into per-cloud copies. A
Deployment/Service/ConfigMap/HPA manifest is materially the same shape
on EKS, AKS, and GKE — forking it three ways to handle differences that
live elsewhere would mean maintaining three near-identical copies of
every workload unit forever. The actual per-cloud divergence is cluster
*access and integration*, which already has its own namespace
(`aws.eks.*`/`azure.aks.*`/`gcp.gke.*`, per the repository shape above):

```
kubernetes skill = the workload resource (provider-neutral)
cloud skill      = cluster, identity, registry, networking, and
                    provider integration (provider-specific)
profile          = the approved composition of both
```

A provider-specific *Kubernetes* skill is warranted only when the
manifest content itself genuinely differs, not just the surrounding
cloud plumbing — concretely: AWS Load Balancer Controller vs. Azure
Application Gateway vs. GKE Ingress/Gateway annotations on the same
`Ingress` object, and IRSA vs. Azure Workload Identity vs. GKE
Workload Identity service-account annotations on the same
`ServiceAccount` object. Those stay `aws.eks.load_balancer`/
`aws.eks.workload_identity` (and Azure/GCP equivalents) — annotation
*producers* the profile composes alongside the neutral
`kubernetes.ingress`/`kubernetes.service_account` units, not forks of
those units themselves.

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
1. Classify intent; today's intake does not resolve scope.
2. Resolve and validate scope, then load the workspace and calculate
   effective access.
3. Have the LLM select an approved profile ID.
4. Resolve its trusted registration and extract/clarify parameters
   against the registered request model.
5. Load and validate that registration's reviewed `TopologySpec`.
6. Resolve provider-qualified unit IDs against
   `TOPOLOGY_UNIT_REGISTRY`.
7. Validate unit inputs, output references, profile membership, and the
   dependency DAG.
8. Compile and invoke the stateless topology subgraph.
9. Generate `ResourceIntent`s → `DeploymentPlan`.
10. Render engine-neutral reviewed HCL modules only; resolve the workspace's
    trusted toolchain (`ccapi`, `hcp_terraform`, `opentofu_local`, or
    `terraform_local`) outside the topology registry.
11. Provider-specific plan checks (AWS: S3 public access blocked, OAC
   in use, IAM actions allowed; Azure: public access disabled, role
   assignments allow-listed, private endpoint; GCP: uniform
   bucket-level access, IAM roles allow-listed, no public principals)
12. Shared security checks (`security-review-checklist`).
13. Approval (existing gate; `DeploymentPlan.topology_digest` is the
    artifact-provenance input and covers profile, unit, and template
    versions)
14. Provider-specific short-lived credentials (`CloudAccessAdapter`).
15. Apply through the selected executor; local runs use the exact same sealed
    engine identity/version that produced the saved plan.
16. Provider-specific verification (registered unit verifiers).
17. Normalized evidence.

## Free-composition planner — LangGraph-native, deferred, not enabled
This is the mechanism for "free composition" the core-idea section
above defers to "a later authority expansion with a bounded repair
loop." It plugs in as an *alternative* source for `topology_revision`
alongside `load_topology_revision` (Step 4) — everything from Step 5 onward
(validate → compile → render → plan → approve → apply) is identical
and does not know or care which source produced the spec.

### Rejected: a Node/Pi sidecar
An external coding-agent SDK (`@earendil-works/pi-coding-agent`,
independently maintained by Earendil Inc. — not an Anthropic product,
despite an early web summary asserting otherwise) was evaluated and
rejected, not because its isolation model is unsound but because it
buys nothing this repository needs badly enough to justify a second
language runtime, a supervised subprocess, and a cross-language IPC
protocol. Its `noTools`/`resourceLoader` controls do work as
documented (verified against its own docs) but require two separate
settings to jointly hold for tool isolation, and its default resource
loader walks up from `cwd` for context files — in this repository that
means auto-ingesting this project's own `AGENTS.md` unless explicitly
overridden. All of that complexity is structural cost with no
capability this repo lacks otherwise.

### Rejected: Pydantic AI Harness
Considered as the closest feature-for-feature Python equivalent
(skills, planning, memory, guardrails, tool search, spend limits — see
its own docs). Rejected for three verified reasons: it would run
alongside LangGraph as a second agent/graph runtime rather than
inside it; it uses 0.x versioning with its own docs stating APIs "may
still move between minor releases... renamed parameters, changed
defaults, restructured APIs"; and its Skills capability's declared
restriction fields are non-enforcing — its own docs list `allowed-tools`,
`disallowed-tools`, `disable-model-invocation`, `shell`, `hooks`, and
`tools` together as "accepted for compatibility, but their behavior is
not implemented." That list rules out Harness Skills as a security
boundary broadly, not just on the one field most likely to be reached
for. Separately, `transports/http.py`'s `_build_model()` already
resolves a multi-provider model via `ChatLiteLLM` (a LangChain
`BaseChatModel`) from `PLATFORMOPS_MODEL`/`PLATFORMOPS_LITELLM_API_BASE`
— the provider construction is reusable by a LangChain-native planner,
but the returned model is **not** reusable as-is: the current transport
binds the intake-only `select_intent` tool before returning it. A planner
must receive the unbound provider model and bind only its own read-only
catalog tools. This split is required to prevent intake tool schemas from
leaking into the topology-planning agent. It is not reusable by Harness,
whose `Agent` takes its own model abstraction and would need that
provider selection re-implemented in a second dialect.

### Evaluated: Deep Agents — same runtime, conditional fit
**Evaluated 2026-08-16 against current official docs and PyPI.** Deep
Agents is materially different from the two rejected harnesses above: it
is an opinionated harness over LangChain `create_agent`, returns a compiled
LangGraph state graph, accepts a LangChain `BaseChatModel`, and supports a
Pydantic `response_format`. It therefore would not introduce a second
language or orchestration runtime, and it can consume the same *unbound*
`ChatLiteLLM` provider model required below.

It is not automatically the right runtime planner. Its bare harness normally
adds filesystem middleware, a general-purpose subagent/`task` tool,
summarization, and context-management behavior. Those defaults target long-
horizon work; Slice 13 is a bounded catalog search plus at most two repair
rounds. Removing every unneeded capability leaves something close to plain
`create_agent`, while adding `deepagents` and full `langchain` — neither is a
current dependency (`uv run` checked 2026-08-16; the repo has
`langgraph==1.2.10` and `langchain-core==1.5.3`).

The fit decision is therefore split by use case:

| Use | Decision | Why |
|---|---|---|
| Reviewed profile | No agent | Deterministic loading is already sufficient |
| Slice 13 reviewed-unit composition | Plain `create_agent`/`ToolNode` first | Deep context, files, delegation, and memory add no demonstrated value |
| Slice 14 raw-resource topology authoring | Deep Agents is an A/B candidate | It may earn its cost when catalogs, diagnostics, and provider context become genuinely long-horizon |
| Slice 15 Level 2 module/renderer authoring PR | Strong Deep Agents fit | Sandboxed files, shell, tests, skills, planning, and review subagents are the job rather than capabilities to remove |
| Approval/apply | Never | Remains fixed parent-graph authority |

#### Runtime use — one stripped topology-author node
If the Slice 14 evaluation selects Deep Agents, it occupies only the same
`plan_topology` slot already designed below. At process startup PlatformOps
registers a harness profile for **every model-provider key it supports**;
Deep Agents has no wildcard profile. The exact synthesized key for the
preconfigured `ChatLiteLLM` instance must be verified in the spike rather
than assumed. That profile:

```python
HarnessProfile(
    excluded_tools={
        "ls", "read_file", "write_file", "edit_file", "delete",
        "glob", "grep", "execute", "task", "write_todos",
    },
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
)
```

The call site then uses a fresh, in-state backend only as required harness
scaffolding, with an explicit deny-all filesystem rule as defence in depth:

```python
topology_author = create_deep_agent(
    model=unbound_chat_model,
    tools=[
        search_provisioning_units,
        get_unit_contract,
        search_provider_resources,
        get_resource_contract,
        get_provider_constraints,
        get_previous_diagnostics,
    ],
    system_prompt=TOPOLOGY_PLANNER_PROMPT,
    response_format=TopologyProposal,
    backend=StateBackend(),
    permissions=[
        FilesystemPermission(
            operations=["read", "write"],
            paths=["/**"],
            mode="deny",
        )
    ],
    subagents=[],                # profile also disables the auto-added one
    skills=None,
    memory=None,
    # no sandbox, Store, independent checkpointer, or interrupt_on
)
```

Only the six explicit read-only domain tools are intended to remain model-
visible. The profile exclusion is the visibility boundary; the deny-all
filesystem rule catches an accidental built-in file-tool leak. Deep Agents'
own documentation is explicit that filesystem permissions do not constrain
custom/MCP tools and do not constrain sandbox `execute`, so every domain tool
still enforces scope and the runtime author receives no sandbox at all.

The fixed parent invokes this graph with sanitized requirements and the last
revision's public diagnostics, requires `structured_response`, validates it
again as `TopologyProposal`, and creates the next immutable
`TopologyRevision`. Deep Agents owns none of the revision counter, two-round
cap, registry/allow-list decision, rendering, plan, sealing, approval, or
execution state. Its `StateBackend` files/messages/todos are not copied into
`ProvisionState`; each automatic repair invocation starts fresh, matching the
revision-local state rule in Step 1. Mandatory architecture/security critics
also remain fixed parent nodes — never optional `task` delegation chosen by
the model.

#### Offline use — Slice 15 sandboxed Level 2 authoring
The stronger first adoption candidate is the existing "no reviewed module
matches" authoring path, outside the runtime provision request. It is tracked
as Slice 15, independently from runtime composition Slices 13 and 14:

```text
no reviewed module -> isolated Deep Agent sandbox
  -> inspect trusted provider contracts and authoring skills
  -> create renderer/module + contract tests
  -> run fmt, tofu validate, pytest, deterministic compliance checks
  -> export a patch/PR artifact
  -> normal human code review and merge
  -> only then can runtime registries import it
```

This agent may use sandbox filesystem and `execute` because those capabilities
are useful there, but it receives no cloud credentials, cannot change runtime
registries in the deployed process, cannot approve, merge, push, or apply, and
its output never enters the executor before normal code review. Only trusted,
reviewed skill libraries are mounted; `skills/provision-infra/SKILL.md`'s
known `allowed-tools` schema bug must still be fixed before any loader is
wired, and skill instructions never become policy authority.

#### Acceptance gate — A/B before dependency adoption
Do not add `deepagents` on architectural appeal alone. Pin the evaluated
version (`0.7.6` as of 2026-08-16; PyPI classifies it Beta) in an isolated
spike and run the same cases through plain `create_agent` and the stripped
Deep Agent:

```text
valid static topology; missing TLS/DNS/logging; invalid provider region;
unknown and forbidden resources; cross-resource constraint failure;
repair that adds/removes a node; catalog too large for one prompt
```

Compare valid-topology rate, requirement coverage, forbidden-resource
rejection, repair success within the same two-round cap, deterministic
revision output, tool/model calls, tokens, latency, and the final visible tool
set. Adopt it for runtime only if context/delegation materially improves those
outcomes without exposing any extra capability. Slice 15's offline authoring
decision is separate and may pass even when the runtime comparison does not.

### Recommended now: `create_agent`, or plain `LangGraph` + `ToolNode` if the dependency is unwanted
`langgraph` and `langchain-core` are already dependencies; `langchain`
(which exposes `create_agent`) is not (`import langchain` fails against
this repo's `.venv` — checked directly, not assumed). Two options,
same shape either way:

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

topology_planner = create_agent(
    model=model,                    # unbound ChatLiteLLM from the shared
                                     # provider factory; do not pass the
                                     # intake model already bound to
                                     # select_intent
    tools=[
        search_provisioning_units,      # read-only catalog search
        get_unit_contract,              # read-only: inputs/outputs/
                                        # allowed_resources for one ID
        get_profile_constraints,        # read-only: required/forbidden
                                        # unit categories for a profile
    ],
    system_prompt=TOPOLOGY_PLANNER_PROMPT,
    response_format=ToolStrategy(TopologyProposal),
    middleware=[bounded_model_calls, bounded_tool_calls],
)
```
The transport should therefore expose two deliberate layers rather than
one overloaded factory:

```python
chat_model = build_chat_model()                         # provider only
intake_model = chat_model.bind_tools([select_intent])   # intake contract
planner_model = chat_model.bind_tools(planner_tools)    # planner contract
```

The exact factory names are implementation detail, but the invariant is
not: a workflow owns the tools bound to its model. LangGraph's tool pattern
binds the model to the workflow's tool set before `ToolNode` executes those
calls; a topology planner must never inherit the intake tool binding.

If adding `langchain` is undesirable, the identical shape is a few
dozen lines of plain `StateGraph` + `ToolNode`: `call_model` → tool
calls exist? loop back through a **read-only** `ToolNode`; no tool
calls? → validate structured output → `END`. Either way the planner
gets exactly the same three read-only tools this doc's "What units
must never do" section already forbids extending: no shell, no
filesystem, no credentials, no approval, no apply. `get_profile_constraints`
is advisory context only — it explains a rule in prose; it is never
asked and never allowed to answer whether execution is permitted, the
same restraint `get_policy_guidance` already needed in the rejected
Pi design and which survives the pivot unchanged.

The parent node re-asserts Python authority over whatever the agent
loop produced:

```python
async def plan_topology(state: ProvisionState) -> dict:
    request = PlanningRequest.from_state(state)   # sanitized: no
                                                    # credentials, no
                                                    # approval records,
                                                    # no full ActorSession
    result = await topology_planner.ainvoke(
        {"messages": [{"role": "user", "content": request.model_dump_json()}]}
    )
    structured = result.get("structured_response")
    if structured is None:
        raise TopologyPlanningFailed("agent loop ended without a proposal")

    proposal = TopologyProposal.model_validate(structured)
    validated = validate_topology(
        proposal,
        profile=state["profile_registration"],
        workspace=state["workspace"],
        registry=TOPOLOGY_UNIT_REGISTRY,
    )
    if not validated.ok:
        # bounded repair: return validated.public_errors to the planner,
        # matching harness/core.py's existing _MAX_CLARIFICATION_ROUNDS = 2
        # cap -- not a new number invented for this path
        ...
    return {
        "topology_revision": make_topology_revision(
            spec=validated.spec,
            parent=state["topology_revision"],
            created_by="planner",
            change_reason="free-composition proposal",
        ),
        "candidate_artifacts": None,
        "deployment_plan": None,
        "approval": None,
    }
```
Two things stated explicitly because they're easy to drop silently:
the `structured is None` check exists because `ToolStrategy` does not
guarantee the agent calls its structured-output tool before the loop
ends (e.g., it exhausts `bounded_tool_calls` first) — an unhandled
`model_validate(None)` would otherwise raise inside the node instead of
producing a clean planning-failed outcome. And `bounded_model_calls`/
`bounded_tool_calls` need real numbers before this ships — **not fixed
here**, left as an explicit open parameter rather than an invented
default, the same way this design set treats every other undecided
policy value.

### Migration order, unchanged from the rejected design's own conclusion
1. Reviewed-profile loading and validation, no agent at all — the
   current real slice.
2. The unit registry and compiler (Steps 3, 6-8 above).
3. This planner as an alternative `topology_revision` source.
4. Keep it disabled by policy (`PROFILE_REGISTRY`-gated, same as any
   other profile) until its own tests and acceptance decision land —
   not a code flag, the same reviewed-artifact gate every profile
   already goes through.

## Resource-primitive authoring — the third composition level, designed 2026-08-16, not enabled
The user's stated target goes one level finer than free unit
composition: **provider-specific topology specs assembled on the fly
from raw resource primitives, with a coding agent authoring and
repairing the composition** — for requests no reviewed module covers.
This section pins that shape so it doesn't fork into a parallel
undocumented design. The authority ladder now has three runtime levels
plus the authoring path, each a separate acceptance decision:

```
A. reviewed profile           FOUNDATION -- registry/topology.yaml loader
                                            implemented; handler stops before it
B. free unit composition      DISABLED  -- Slice 13, planner over
                                          registered units
C. resource-primitive         DISABLED  -- Slice 14 (this section),
   authoring                              planner over raw provider
                                          resources, strictest checks
D. Level 2 authoring PR       unchanged -- new reviewed modules land
                                          via normal code review
```

### Provider-specific specs, not one generic schema
Provider topologies are structurally different and stay that way — a
discriminated envelope, the same reasoning the `ResourceIntent` IR
section already states ("not a cloud-abstraction layer"):

```python
class AwsTopologyEnvelope(BaseModel):
    provider: Literal["aws"]
    topology: AwsTopologySpec

class AzureTopologyEnvelope(BaseModel):
    provider: Literal["azure"]
    topology: AzureTopologySpec

class GcpTopologyEnvelope(BaseModel):
    provider: Literal["gcp"]
    topology: GcpTopologySpec

TopologyEnvelope = Annotated[
    AwsTopologyEnvelope | AzureTopologyEnvelope | GcpTopologyEnvelope,
    Field(discriminator="provider"),
]

class AwsS3BucketSpec(BaseModel):
    id: str
    resource_type: Literal["aws_s3_bucket"]
    configuration: S3BucketConfiguration
    depends_on: list[str] = Field(default_factory=list)

class AwsCloudFrontSpec(BaseModel):
    id: str
    resource_type: Literal["aws_cloudfront_distribution"]
    configuration: CloudFrontConfiguration
    depends_on: list[str] = Field(default_factory=list)

class AwsOriginAccessControlSpec(BaseModel):
    id: str
    resource_type: Literal["aws_cloudfront_origin_access_control"]
    configuration: OriginAccessControlConfiguration
    depends_on: list[str] = Field(default_factory=list)

AwsResourceSpec = Annotated[
    AwsS3BucketSpec | AwsCloudFrontSpec | AwsOriginAccessControlSpec,
    Field(discriminator="resource_type"),
]
```

Both levels are discriminated. The provider tag selects the provider
topology, and `resource_type` selects its exact configuration schema. A
parallel `resource_type` field plus an unrelated union-valued
`configuration` field is insufficient: it could pair a CloudFront type
with an S3 configuration unless an additional validator coupled them.
Configuration is never a bare dictionary.

Per-provider resource registries mirror `TOPOLOGY_UNIT_REGISTRY`'s
shape one level down — exact config schema + **reviewed renderer
function** per resource type, explicit imports, unknown types fail:

```python
AWS_RESOURCE_REGISTRY = {
    "aws_s3_bucket": RegisteredResource(
        schema=S3BucketConfiguration,
        renderer=render_s3_bucket,      # reviewed code, not LLM output
    ),
    ...
}
```

### Terminology, reconciled — three layers now
```
resource primitive   aws_s3_bucket                    NEW bottom layer
unit / module        aws.s3.private_bucket            unchanged (this doc)
profile              aws-static-web                   unchanged
```
`ResourceIntent` remains the orchestration IR; the new
`AwsResourceSpec`-style models are *authoring inputs* upstream of it.
The composition preference is fixed: **prefer reviewed modules for
known patterns; assemble raw primitives only when no module fits** —
and raw composition gets strictly more validation, because a full
resource configuration surface (bucket policies, ACLs, distribution
configs) is categorically larger than a purpose-built unit input model
like `{"private": true}`.

### Why this does NOT break the never-unreviewed-IaC rule — and what it DOES change
The executor invariant survives intact: the LLM emits **typed resource
data**, never HCL; HCL comes only from the registry's reviewed renderer
functions fed schema-validated configuration. What genuinely changes is
`PROVISION_WORKFLOW.md`'s no-match behavior: "no template match → stop,
open a Level 2 PR, END" gains an alternative ending when Level C is
enabled — assemble primitives at runtime instead of stopping. That is a
real authority expansion, corrected in `PROVISION_WORKFLOW.md` in place
(dated note there), not silently absorbed here.

### Authority split — the agent is advisory, everywhere
```
coding agent          composes, interprets diagnostics, proposes repairs
Pydantic              structural authority (specs, config schemas)
resource registry     resource authority (what may exist at all)
tofu validate/plan    provider syntax + dependency authority
policy engine         organizational authority (allow-lists, ceilings)
human approval        mutation authority
```

### The bounded repair loop — native tooling as the oracle
New relative to Slice 13's planner: `tofu validate` diagnostics feed
back to the agent as structured errors, max **2 repair attempts**
(reusing `_MAX_CLARIFICATION_ROUNDS`' cap, not a new number), then fail
closed:

```
compose -> Pydantic -> registry -> render -> tofu validate
   ^                                             |
   |          structured diagnostic              | failure
   +---------------------------------------------+   (≤2 rounds)
                                success -> tofu plan -> checks
                                        -> approval -> apply
```
**Verify before build**: the repair loop must run *pre-credential* —
`tofu init -backend=false` should allow `validate` without backend/state
access (provider plugin download needs network, not cloud credentials).
Confirm against current OpenTofu docs before wiring; if validate turns
out to need more, the loop moves after plan-credential acquisition and
the credential-lifetime story in `PROVISION_WORKFLOW.md` gets revisited.

**Failure-origin triage (added 2026-08-16)**: not every `validate`
failure is repair input. The loop must classify before routing:

```
invalid topology/configuration   -> feed diagnostics to the repair agent
renderer implementation defect   -> STOP; internal compiler error --
                                    the agent must never "fix" a trusted
                                    renderer mid-run; that's a code bug
                                    fixed via normal review, not a
                                    runtime repair
environmental/provider failure   -> stop or retry per explicit policy,
                                    never routed to the agent
```
Feeding a renderer bug to the agent would ask it to work around trusted
code — the exact inversion of the authority table above. Schema validity
alone is not a sufficient discriminator: a failure may instead expose a
cross-resource constraint, an invalid combination not captured by one
resource schema, or an incomplete provider-constraint model. Renderers
must emit provenance-tagged blocks and diagnostics must be classified
against renderer contract tests plus the resource/path that failed; an
unclassified failure stops closed rather than being guessed into a repair
category.

### Two graphs, kept conceptually separate
The **LangGraph workflow graph** (compose → validate → repair → render →
plan → policy → approval) stays fixed — same rule as everywhere else in
this doc. The **infrastructure topology graph** (bucket → distribution →
DNS) is runtime data. Executing the latter through a dynamically
compiled subgraph (Step 6) is an implementation choice, not what makes
the infrastructure declarative — the declarative property lives in the
spec, not the executor.

### Fluid topology lifecycle — revise freely, approve one sealed revision
"Fluid" means a sequence of immutable, content-addressed graph revisions,
not in-place mutation of one `TopologySpec`. The coding agent, a human, or
deterministic diagnostics may change nodes, edges, bindings, or resource
configuration by producing a complete successor revision:

```text
r1  bucket -> distribution
     rejected: private-origin control missing

r2  bucket -> origin-access -> distribution
     rejected: requested DNS/TLS absent

r3  bucket -----------+
    origin-access ----+-> distribution -> DNS
    certificate ------+
     plan accepted: seal r3 for approval
```

Each automatic repair returns a complete replacement snapshot. Patch-like
operations may be retained as audit events or UI presentation, but only the
materialized full snapshot crosses the validation boundary. This prevents
partially-applied graph edits and makes every validation result reproducible.

The fixed parent graph contains the revision loop; conditional repair edges
never move into the dynamically compiled topology graph:

```text
author revision -> architecture review -> schema/registry/DAG checks
       ^                                             |
       |                                             v
       +-- change required <- plan reconciliation <- render/validate/plan
                                                        |
                                                        v
                                               seal -> approval -> apply
```

The architecture/coding-agent review checks semantic completeness — every
stated requirement is represented, expected dependencies exist, and the
shape is not needlessly complex — but remains advisory. Pydantic, registry,
allow-list, provider-plan, and policy checks remain authoritative. Automatic
repair is bounded at two rounds for one candidate attempt; an explicit human
change creates a new revision rather than silently extending that model loop.

The lifecycle is monotonic per revision:

| State | Meaning | Shape change |
|---|---|---|
| `draft` | Agent/human is composing graph data | Produce a successor revision |
| `structurally_valid` | Schema, registry, binding, scope, and DAG checks passed | Successor invalidates derived work |
| `materialized` | Planning units produced typed resource intents | Successor invalidates unit results |
| `rendered` / `tool_validated` | Reviewed renderers emitted IaC and native validation passed | Successor invalidates the artifact |
| `planned` / `policy_valid` | A real provider plan and deterministic policy result exist | Successor discards the plan and planning credential |
| `sealed` / `approval_pending` | Exact revision, artifact, plan, policy, identity, state fingerprint, and allow-list version are bound | No in-place change; successor supersedes approval |
| `approved` | Required approvers accepted that exact digest | Immutable; mismatch requires a fresh plan/approval |
| `applied` / `verified` | Exact saved plan ran and evidence was read back | A later change is a new provision request |

Any topology change atomically invalidates its compiled graph, unit results,
rendered artifact, native-validation result, saved plan, policy result, and
pending approval. Compilation may be cached only by the full topology digest.
Transient retries that do not change content may reuse a revision; a repair
always creates a new one.

Sealing happens when a plan/policy-valid candidate is submitted for approval,
not when the first graph or IaC artifact is built. An `ApprovalRequest` names
`revision_id`, `topology_digest`, artifact/plan digests, and the combined
`approval_digest`. A requested change creates `r(n+1)`, marks the old request
`superseded`, and starts render/plan/check again. Old approval records stay
immutable for audit but authorize nothing in the successor revision. Resume
still recomputes every digest and current-state fingerprint before obtaining
fresh apply credentials.

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
- [LangChain: Agents / `create_agent`](https://docs.langchain.com/oss/python/langchain/agents) — verified 2026-08-15: `create_agent` from `langchain.agents`, tool-calling loop, subgraph-embeddable via identifier
- [LangChain: Structured output](https://docs.langchain.com/oss/python/langchain/structured-output) — verified 2026-08-15: `response_format=ToolStrategy(PydanticModel)`, `result["structured_response"]`
- [LangChain: Deep Agents overview](https://docs.langchain.com/oss/python/deepagents/overview) and [customization](https://docs.langchain.com/oss/python/deepagents/customization) — verified 2026-08-16: Deep Agents is an opinionated harness over LangChain using the LangGraph runtime; `create_deep_agent` returns a compiled state graph, accepts `BaseChatModel`, custom tools/state/context, and structured `response_format`; bare stack includes filesystem, default general-purpose subagent, summarization, and context middleware
- [LangChain: Deep Agents profiles](https://docs.langchain.com/oss/python/deepagents/profiles) — verified 2026-08-16: `excluded_tools` filters harness-injected tools; disabling the general-purpose subagent plus passing no synchronous subagents removes `task`; profiles have no wildcard provider key, so every supported provider/model key needs deliberate registration
- [LangChain: Deep Agents permissions](https://docs.langchain.com/oss/python/deepagents/permissions) and [sandboxes](https://docs.langchain.com/oss/python/deepagents/sandboxes) — verified 2026-08-16: unmatched filesystem permission rules allow by default; rules cover built-in filesystem tools only, not custom/MCP tools or sandbox `execute`; sandbox backends expose isolated files plus command execution
- [PyPI: `deepagents`](https://pypi.org/project/deepagents/) — checked 2026-08-16: latest `0.7.6`, Python 3.11+, Beta classifier; project security statement says tool capability is the enforcement boundary
- [Pi SDK docs](https://pi.dev/docs/latest/sdk), [RPC](https://pi.dev/docs/latest/rpc), [extensions](https://pi.dev/docs/latest/extensions), [skills](https://pi.dev/docs/latest/skills) — verified 2026-08-14/15 (evaluated, rejected — see "Free-composition planner" above); `noTools:"builtin"` leaves extension tools enabled, `resourceLoader` controls extensions/skills/prompts/context (not just system prompt) and defaults to walking `cwd` for `AGENTS.md`; extensions "run with your full system permissions," skills "may include executable code the model invokes"
- [Pydantic AI Harness](https://pydantic.dev/docs/ai/harness/) and its [Skills](https://pydantic.dev/docs/ai/harness/skills/) page — verified 2026-08-15 (evaluated, rejected): 0.x version-stability caveat quoted verbatim above; `allowed-tools`/`disallowed-tools`/`disable-model-invocation`/`shell`/`hooks`/`tools` all listed as accepted-but-unenforced
- `npm` registry for `@earendil-works/pi-coding-agent` — checked directly 2026-08-14 to correct a first-pass web summary's "Anthropic's official SDK" misattribution; real maintainers/publisher are Earendil Inc.

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
