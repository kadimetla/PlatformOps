## Status
Designed only. No `gateway/`, `workflows/`, or LangGraph intake code
exists on this branch yet. This document captures the OpenSpec explore
result for request intake with human-in-the-loop clarification before
workflow routing.

## Real vs. Designed
| Area | Current branch | Designed target |
|---|---|---|
| Intake workflow | Not implemented | `workflows/intake/` LangGraph `StateGraph` classifies requests and resolves routing fields |
| Gateway schemas | Not implemented | `gateway/schemas.py` owns request, decision, route, and clarification models |
| Dispatcher | Not implemented | Deterministic route selection maps known intents to known workflows only |
| HITL clarification | Not implemented | Intake interrupts for bounded clarification when intent or routing fields are ambiguous |
| Mutation approval | Not implemented in intake | Intake can mark approval required, but cannot approve or execute mutation |
| Compliance check | Existing deterministic CLI in `spec/check_compliance.py` | Dispatcher can route compliance requests to a wrapper around the deterministic checker |

## Problem
PlatformOps needs to accept free-form user requests and route them to
the correct workflow engine path:

| Intent | Route target | Examples |
|---|---|---|
| `provision` | future `workflows/provision_stack/` | "Deploy an S3 website", "Create CloudFront for this app" |
| `inquiry` | future `workflows/inquiry/` | "How should we host this?", "Compare Terraform and CDK here" |
| `audit` | future `workflows/audit/` | "Review this Terraform plan", "Check this deployment plan" |
| `security_review` | future `workflows/security_review/` | "Is this IAM policy safe?", "Review this provisioning plan for security" |
| `compliance_check` | `spec/check_compliance.py` wrapper | "Does this architecture comply?" |
| `clarification` | intake interrupt | "Set this up", "Review this" without enough context |
| `unsupported` | terminal response | out-of-scope cloud/action/tooling |

Intake must not execute the request. It produces a typed routing
decision and evidence. Downstream workflows remain responsible for
domain work, deterministic checks, and approval-gated mutation.

## Design
Add the smallest useful foundation:

```text
gateway/
  schemas.py
  dispatcher.py
  policy.py

workflows/
  intake/
    graph.py
    nodes.py
    prompts.py
```

The intake graph:

```text
normalize_request
  -> extract_deterministic_signals
  -> classify_intent
  -> validate_decision
  -> needs_clarification?
       yes -> interrupt_for_human
              -> merge_clarification
              -> classify_intent
       no  -> build_route_decision
```

Use the LLM only to classify and summarize. Keep route selection,
required-field validation, mutation gating, and unsupported-workflow
handling in deterministic code.

## Intake Contract
The output should be a Pydantic model, not prose:

```python
class IntakeDecision(BaseModel):
    intent: Intent | None
    confidence: float
    route: WorkflowRoute | None
    mutation_requested: bool
    approval_required: bool
    missing_fields: list[str]
    clarification_questions: list[ClarificationQuestion]
    ready_to_route: bool
    evidence: list[str]
```

Keep these fields separate:

| Field | Meaning | Authority |
|---|---|---|
| `intent` | What the user appears to want | LLM classification plus deterministic signal checks |
| `route` | Which known workflow should receive the request | deterministic dispatcher |
| `mutation_requested` | Whether the request asks to create, update, delete, import, or execute | deterministic signals plus classifier |
| `approval_required` | Whether downstream mutation needs recorded approval | deterministic policy |
| `ready_to_route` | Whether required fields are present and unambiguous | deterministic validation |

This separation prevents a classifier result from becoming permission
to mutate infrastructure.

## HITL Clarification
Use LangGraph `interrupt`/resume semantics for clarification. This is
different from mutation approval.

| Gate | Purpose | Timing |
|---|---|---|
| Clarification HITL | Understand the request well enough to route it | Intake |
| Approval HITL | Authorize a concrete mutating action | Downstream workflow, after deterministic checks |

Ask clarification when:

- confidence is below the accepted threshold
- multiple intents are plausible
- provisioning is implied but cloud, environment, or resource target is missing
- audit target is unclear: security, compliance, Terraform plan, cost, or deployment readiness
- the request is vague and possibly mutating
- required context or attachments are missing

Bound the clarification loop:

```text
max clarification rounds: 2
still ambiguous + clearly non-mutating -> inquiry
still ambiguous + possibly mutating -> unsupported / clarification_failed
```

Example interrupt payload:

```python
{
    "type": "clarification_required",
    "questions": [
        {
            "field": "target_workflow",
            "question": "Should I treat this as provisioning, inquiry, audit, security review, or compliance checking?",
            "choices": [
                "provision",
                "inquiry",
                "audit",
                "security_review",
                "compliance_check",
            ],
        }
    ],
}
```

## Deterministic Signals
Start with simple local signals before the classifier:

| Signal | Likely effect |
|---|---|
| "deploy", "provision", "create", "destroy", "apply", "import" | `mutation_requested = true`, likely `provision` |
| "plan", "review this plan", Terraform plan JSON/logs | likely `audit` |
| "IAM policy", "permissions", "least privilege", "security" | likely `security_review` |
| "comply", "compliance", Given/When/Then architecture submission | likely `compliance_check` |
| "how", "compare", "recommend", "what should" | likely `inquiry` |

These signals should bias classification and validation, not silently
override clear user intent.

## Routing Policy
Route only to known workflow identifiers:

```text
provision         -> workflows.provision_stack
inquiry           -> workflows.inquiry
audit             -> workflows.audit
security_review   -> workflows.security_review
compliance_check  -> spec.check_compliance wrapper
clarification     -> intake interrupt
unsupported       -> terminal response
```

Rules:

- do not route if `ready_to_route` is false
- do not route a possibly mutating ambiguous request to provisioning
- do not let the LLM emit arbitrary module paths, tool names, or shell commands
- setting `approval_required = true` is not an approval
- provision workflows may produce plans before approval, but may not mutate without allow-list match and recorded approval

## Open Questions
| Question | Current recommendation |
|---|---|
| Should intake call Terraform or AWS MCP tools? | No. Keep intake local and route-oriented first. Downstream workflows can use MCP tools when needed. |
| Should unclear non-mutating requests default to inquiry? | Yes, when no mutation is implied. |
| Should unclear mutating requests default to provision plan-only? | No. Ask clarification or terminate as unsupported after the bounded clarification loop. |
| Should compliance use an LLM? | No. Route to deterministic `spec/check_compliance.py`; LLM can explain results later if needed. |

## How this relates to the existing docs
Extends [HARNESS_DESIGN.md](HARNESS_DESIGN.md)'s document map with the
first intake-routing design for the LangGraph migration named in
`AGENTS.md`. Complements [TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md):
Terraform MCP belongs in downstream inquiry/provision/audit workflows,
not in the initial intake router.
