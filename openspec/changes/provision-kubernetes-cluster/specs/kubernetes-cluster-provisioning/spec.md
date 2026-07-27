## ADDED Requirements

### Requirement: A cluster-creation request is denied before resolution unless the requester has stack scope
The system SHALL check `TeamMember.scope` for the requesting
`channel_user_id` before any skill or MCP tool resolution runs for a
Kubernetes cluster-creation request, and SHALL deny the request
immediately if `scope` is `"app"` only.

#### Scenario: An app-scoped requester is denied before provisioning starts
- **WHEN** a `channel_user_id` with `TeamMember.scope="app"` submits a
  request to create an EKS/GKE/AKS cluster
- **THEN** the request is denied at the scope check, and no provisioning
  agent or MCP client is constructed

#### Scenario: A stack-scoped requester passes the scope check
- **WHEN** a `channel_user_id` with `TeamMember.scope="stack"` (or
  `"both"`) submits a request to create a cluster
- **THEN** the request proceeds to template generation

### Requirement: Template generation is non-mutating and does not require approval
The system SHALL allow cluster template/manifest generation to run
without a prior approval record, and SHALL record the generation step
in the audit trail without treating it as a gated mutation.

#### Scenario: Generation runs without an approval record
- **WHEN** a stack-scoped request reaches the generation step with
  no `ApprovalRecord` yet present for the plan
- **THEN** the generation call still succeeds and its result is recorded

### Requirement: The actual cluster-creation call always requires both agent and human approval
The system SHALL require `BrokeredToolDispatcher.evaluate_intent()` to
return `True` — meaning both `agent_approved` and `human_approved` are
`True` — before calling the mutating cluster-creation MCP tool for any
cloud, with no autonomous-approval path for this capability.

#### Scenario: A cluster-creation intent without human approval is denied
- **WHEN** a `ToolIntent` for cluster creation has `agent_approved=True`
  but `human_approved=False`
- **THEN** `dispatch_and_execute_cluster()` does not call any mutating
  MCP tool, and the outcome is recorded as `"denied"`

### Requirement: The same flow executes correctly across AWS, GCP, and Azure
The system SHALL provide one shared `dispatch_and_execute_cluster()`
entry point that accepts `cloud_provider` and routes to the correct
provider-specific adapter, without duplicating the approval-gate, audit,
or `ResourceRecord`-write logic per provider.

#### Scenario: An AWS request calls the EKS adapter
- **WHEN** `dispatch_and_execute_cluster()` is called with
  `cloud_provider="aws"` and an approved `ToolIntent`
- **THEN** it calls `eks-mcp-server`'s cluster-creation tool, not any
  other provider's

#### Scenario: A GCP request calls the GKE adapter
- **WHEN** `dispatch_and_execute_cluster()` is called with
  `cloud_provider="gcp"` and an approved `ToolIntent`
- **THEN** it calls `gke-mcp`'s cluster-creation tool, not any other
  provider's

#### Scenario: An Azure request calls the AKS adapter
- **WHEN** `dispatch_and_execute_cluster()` is called with
  `cloud_provider="azure"` and an approved `ToolIntent`
- **THEN** it calls `aks-mcp`'s cluster-creation tool, not any other
  provider's

### Requirement: A successful cluster creation writes a `ResourceRecord` tagged with the Kubernetes compute paradigm
The system SHALL write a `ResourceRecord` with `status="active"`,
`compute_paradigm="kubernetes"`, and the created cluster's
`resource_identifier` upon a successful cluster-creation execution, for
any of the three supported clouds.

#### Scenario: ResourceRecord reflects the actual created cluster and its paradigm
- **WHEN** a cluster-creation `ToolIntent` executes successfully
- **THEN** a `ResourceRecord` is written with `cloud_provider` matching
  the request, `compute_paradigm="kubernetes"`, `layer="compute"`,
  `status="active"`, and `approved_plan_id` set to the originating plan

### Requirement: A denied or failed cluster-creation attempt never writes a ResourceRecord
The system SHALL NOT write a `ResourceRecord` for any cluster-creation
attempt that was denied by the dispatcher or that failed during
execution.

#### Scenario: A denied intent leaves no ResourceRecord
- **WHEN** `evaluate_intent()` denies a cluster-creation `ToolIntent`
- **THEN** no `ResourceRecord` is written for that attempt

### Requirement: Every ResourceRecord belongs to a Stack, never null
The system SHALL set `stack_id` on every `ResourceRecord` it writes,
using the caller-supplied value when one is given, and SHALL NOT write
a `ResourceRecord` with a null or missing `stack_id` under any
circumstance (`docs/composable_foundation_blueprints.md` Part H's
"never dangling" rule).

#### Scenario: A caller-supplied stack_id is preserved, not overridden
- **WHEN** `dispatch_and_execute_cluster()` is called with an explicit
  `stack_id` and the execution succeeds
- **THEN** the resulting `ResourceRecord.stack_id` equals the supplied
  value, unchanged

#### Scenario: No stack_id supplied still produces a non-null one
- **WHEN** `dispatch_and_execute_cluster()` is called with no `stack_id`
  and the execution succeeds
- **THEN** the resulting `ResourceRecord.stack_id` is a real, non-null
  value (a fresh, standalone Stack — the real binding mechanism from
  `docs/composable_foundation_blueprints.md` Part H remains undesigned;
  this is a stand-in, not a resolution of that question)
