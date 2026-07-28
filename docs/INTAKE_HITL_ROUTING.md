## Status
Designed only. No `gateway/`, `workflows/`, or LangGraph intake code
exists on this branch yet. This document captures the OpenSpec explore
result for request intake with human-in-the-loop clarification before
workflow routing.

**Corrected by the 2026-07-27 deep-dive explore** (grounded against
`design/harness-architecture`'s built-and-tested intake:
`workflows/intake/{graph,nodes,state,tools}.py`,
`openspec/changes/build-intake-workflow/design.md`,
`docs/intent_routing_and_staged_confirmation.md` — all on that branch).
Original sections below are preserved; corrections are marked inline.
Summary of what changed and why:

| # | Original claim | Correction | Grounding |
|---|---|---|---|
| C1 | Clarification via in-graph `interrupt`/resume loop | Graph always ends; clarification questions are returned as data and the caller re-invokes (round counter on the request, capped at 2 by caller policy). `interrupt`/`Command` is reserved for downstream mutation approval. | Prior art rejected pause/resume twice: "no pause/resume mechanism" (build-intake-workflow design) and "resolve the ambiguity before the run starts" (staged-confirmation Part B). Interrupt requires checkpointer + host runtime this branch lacks. |
| C2 | `missing_fields` + required-field validation in intake | Dropped from intake. Intent classification (Stage 1) emits a label only; structure extraction and missing-field clarification (Stage 2) live inside each target workflow. | Staged-confirmation Part A: a router that knows every workflow's field shape breaks independent workflow extensibility. |
| C3 | `confidence: float` + accepted threshold | Dropped. One bound-tool call — `select_workflow(workflow_name \| clarifying_question)` — the call itself is the structured signal: valid enum value XOR question. Clarify when the model asks, when deterministic signals disagree with its pick, or when the tool call is malformed. No threshold exists. | Prior art's tool-forced pattern; LLM self-reported confidence is uncalibrated. |
| C4 | Seven-intent taxonomy incl. `audit`, `security_review` | Start at three user-intent labels: `provision`, `inquiry`, `compliance_check`. Only `compliance_check` is routable today (`spec/check_compliance.py` is this branch's only executable target); the rest fail closed to unsupported until their workflows exist. Extend the enum as workflows land, never before. | Prior art's "no registry before a third workflow exists" discipline; it explicitly declined to reserve an `audit:` prefix for a nonexistent workflow. |
| C5 | `clarification`/`unsupported` as members of the intent enum | They're outcomes, not intents. The enum holds only things a user wants; `ready_to_route`, `clarification_questions`, and a new `unsupported_reason` express outcomes. | Prior art's `IntakeResult`: hint XOR question, no outcome-in-enum. |
| C6 | Route target named `workflows/provision_stack/` | This branch names it `workflows/provision/` — intent label and package share the one name, covering all mutation verbs (create/update/destroy). Prior art's `provision_stack` rename solved its own `drafting` naming collision, which this branch doesn't inherit. | Decision this session (2026-07-27 explore). |

Two additions the original omitted entirely:

**(A1) Scope model — decided this session.** Every workflow operates
inside a three-level scope:

```text
<org>:<bu>  ->  project  ->  workspace

org = company identifier: aiq, efx, abc, ...
bu  = business unit: root (default), it, finance, ...
e.g.  aiq:root, aiq:it, efx:finance
```

The BU is not a separate hierarchy level — it rides with the org as
one composite identifier, which is the **policy key** that shapes the
workflow per requesting team. The levels split into two kinds:

| Level | Kind | Source | Rule |
|---|---|---|---|
| `<org>:<bu>` | Identity — who's asking | Authenticated session; static config until an auth layer exists (none on this branch, verified by grep 2026-07-27) | Never parsed from `raw_text` |
| `project`, `workspace` | Target — where work lands | May be stated in request text, or defaulted | Deny by default: a stated target must match the requester's allowed scope, never trusted as parsed |

Shaping by team happens in deterministic code, keyed on the composite:

```text
resolve_route: route = POLICY.get((scope.org_bu, intent))
               no entry -> unsupported, fail closed

  (aiq:root, *)                -> full catalog
  (aiq:it, provision)          -> allowed, approval always required
  (efx:finance, provision)     -> no entry -> unsupported
  (efx:finance, inquiry)       -> allowed
```

The classifier's output never becomes permission — a BU with no policy
entry for an intent cannot reach that workflow regardless of what the
LLM says.

Mapping onto the two provisioning paths — stated as intent, works
until proven otherwise, reshape if issues surface:

| PlatformOps scope | Terraform path (HCP) | CDK/CCAPI path (AWS) |
|---|---|---|
| `<org>:<bu>` | HCP organization | AWS account (+ tag) |
| `project` | HCP project | Name prefix (`platformops-<project>-`; `spec/check_compliance.py` already enforces prefix naming) |
| `workspace` | HCP workspace ([TERRAFORM_MCP_SERVER.md](TERRAFORM_MCP_SERVER.md)'s workspace tools operate at exactly this level) | Stack name + region |

Open sub-question, deferred until the Terraform path goes live:
`<org>:<bu>` → one HCP organization per BU is the clean 1:1 but means
separate HCP orgs (users, billing); the cheaper start is one HCP org
per company with the BU expressed in project naming.

**(A2)** A deterministic text-prefix tier (`"compliance_check: ..."`
etc., exact intent-enum values, case-sensitive) is checked before any
LLM call.

## Real vs. Designed
| Area | Current branch | Designed target |
|---|---|---|
| Intake workflow | Not implemented | `workflows/intake/` LangGraph `StateGraph` classifies requests and resolves routing fields |
| Gateway schemas | Not implemented | `gateway/schemas.py` owns request, decision, route, and clarification models |
| Dispatcher | Not implemented | Deterministic route selection maps known intents to known workflows only |
| HITL clarification | Not implemented | Intake returns clarification questions as data and ends; caller re-invokes, capped at 2 rounds (corrected — C1; was "intake interrupts") |
| Mutation approval | Not implemented in intake | Intake can mark approval required, but cannot approve or execute mutation |
| Compliance check | Existing deterministic CLI in `spec/check_compliance.py` | Dispatcher can route compliance requests to a wrapper around the deterministic checker |

## Problem
PlatformOps needs to accept free-form user requests and route them to
the correct workflow engine path:

(**Corrected — C4/C5/C6**: table kept as the trail; the corrected
intent enum is `provision` | `inquiry` | `compliance_check` — `audit`
and `security_review` classify as unsupported until their workflows
exist, `clarification`/`unsupported` moved from intents to outcomes,
and `provision_stack` is named `workflows/provision/` on this branch.)

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

The intake graph (**corrected — C1/C2**: the original loop below is
superseded; the graph now always ends, with no interrupt node):

```text
# Original (superseded):
normalize_request
  -> extract_deterministic_signals
  -> classify_intent
  -> validate_decision
  -> needs_clarification?
       yes -> interrupt_for_human
              -> merge_clarification
              -> classify_intent
       no  -> build_route_decision

# Corrected:
normalize_request
  -> extract_deterministic_signals   # incl. A2 prefix tier; may skip the LLM
  -> classify_intent                 # one bound-tool call, only if prefix missed
  -> resolve_route                   # deterministic; END
# Decision, clarification questions, or unsupported — the graph
# returns one of these as data every time. Caller re-invokes on
# clarification with the answer appended (round counter on the
# request, caller-enforced cap of 2).
```

Use the LLM only to classify and summarize. Keep route selection,
required-field validation, mutation gating, and unsupported-workflow
handling in deterministic code.

## Intake Contract
The output should be a Pydantic model, not prose (**corrected —
C2/C3/C5 + A1**: `confidence` and `missing_fields` removed,
`unsupported_reason` and scope added; original shape kept for the
trail):

```python
# Original (superseded):
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

# Corrected:
class Scope(BaseModel):
    org: str                         # company: "aiq", "efx", ...  (identity — from
    bu: str = "root"                 # session/config per A1, never from raw_text)
    project: str | None = None      # target; may come from text, validated
    workspace: str | None = None    # target; same

    @property
    def org_bu(self) -> str:
        """The composite identifier used as the policy key, e.g. "aiq:it"."""
        return f"{self.org}:{self.bu}"

class IntakeRequest(BaseModel):
    scope: Scope
    raw_text: str
    clarification_round: int = 0     # caller increments on re-invoke; caps at 2

class IntakeDecision(BaseModel):
    intent: Intent | None            # "provision" | "inquiry" | "compliance_check"
    route: WorkflowRoute | None      # known identifiers only; today: compliance_check
    mutation_requested: bool
    approval_required: bool
    clarification_questions: list[ClarificationQuestion]
    unsupported_reason: str | None
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
**Corrected — C1**: the original sentence below is superseded.
Clarification does not use in-graph `interrupt`/resume — the graph
always ends and returns `clarification_questions` as data; the caller
asks (its channel's way: CLI list, Slack buttons), then re-invokes
with the answer and `clarification_round` incremented. Each round is a
fresh stateless run — no checkpointer, no `thread_id`, no paused
threads. `interrupt`/`Command` is reserved for downstream mutation
approval, where a pause is genuinely stateful (a plan artifact to
hold). The two-gate table below survives unchanged.

Original: Use LangGraph `interrupt`/resume semantics for clarification.
This is different from mutation approval.

| Gate | Purpose | Timing |
|---|---|---|
| Clarification HITL | Understand the request well enough to route it | Intake |
| Approval HITL | Authorize a concrete mutating action | Downstream workflow, after deterministic checks |

Ask clarification when (**corrected — C2/C3**: the original list mixed
in a confidence threshold that no longer exists and Stage-2
missing-field triggers that now belong to the target workflows; the
corrected triggers are all structural/checkable):

- the classifier's tool call carries `clarifying_question` instead of
  a valid intent (the model itself couldn't pick)
- the tool call is missing or malformed (never guess on a bad call)
- deterministic signals disagree with the classifier's pick
- the request is vague and signals say possibly mutating

Original list (superseded): confidence below threshold; multiple
intents plausible; provisioning implied but cloud/environment/resource
target missing; audit target unclear; vague and possibly mutating;
required context or attachments missing.

Bound the clarification loop:

```text
max clarification rounds: 2
still ambiguous + clearly non-mutating -> inquiry
still ambiguous + possibly mutating -> unsupported / clarification_failed
```

**Corrected — C1**: the original example here was an interrupt
payload; superseded by the return-and-re-invoke walkthrough below
(original kept in git history; it carried the same
`field`/`question`/`choices` shape, which survives in
`ClarificationQuestion`).

### Walkthrough: "set this up for the invoices app"

Run 1 — intake can't place it:

```text
extract_signals:   no prefix match; "set this up" -> mutation-ish signal
classify_intent:   model can't pick -> tool call carries clarifying_question
resolve_route:     no intent -> IntakeDecision(
                     intent=None, route=None, ready_to_route=False,
                     mutation_requested=True,
                     clarification_questions=[ClarificationQuestion(
                       field="intent",
                       question="Provision infrastructure for the invoices app,
                                 answer a question about it, or run a
                                 compliance check?",
                       choices=["provision", "inquiry", "compliance_check"])])
```

The caller asks, however its channel does that — the question is
structured data precisely so intake never needs to know the channel.
The graph is done; the only state between rounds is the
`IntakeRequest` the caller holds.

Run 2 — `choices` are the intent enum, so a chosen answer re-enters
through the deterministic prefix tier (A2):

```text
caller:            raw_text = "provision: set this up for the invoices app"
                   clarification_round = 1
extract_signals:   prefix "provision:" -> intent=provision -- LLM SKIPPED
resolve_route:     POLICY[("aiq:it", provision)] -> route=workflows.provision,
                   approval_required=True, ready_to_route=True
```

A chosen answer can't be misclassified and costs zero model calls —
the loop converges by construction. Only a free-text answer goes back
through the classifier, appended as
`raw_text + "\n[clarification] <answer>"`.

Two properties worth keeping:

- **The question is an audit artifact.** "Routed to provision because
  the user explicitly chose it in round 1" is a stronger
  `IntakeDecision.evidence` line than any classifier score.
- **Channel-composable.** A future Slack adapter carries the round
  counter and original text in its thread; the downstream
  interrupt-based approval gate coexists without touching this — the
  two-gate table above, realized.

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
Route only to known workflow identifiers (**corrected — C4/C5/C6**:
original table below kept for the trail; `audit`/`security_review`
wait until their workflows exist, `clarification`/`unsupported` are
outcomes not routes, `provision_stack` renamed, and routes are
resolved per-scope via `POLICY[(org_bu, intent)]`, not a flat map):

```text
# Original (superseded):
provision         -> workflows.provision_stack
inquiry           -> workflows.inquiry
audit             -> workflows.audit
security_review   -> workflows.security_review
compliance_check  -> spec.check_compliance wrapper
clarification     -> intake interrupt
unsupported       -> terminal response

# Corrected:
compliance_check  -> spec.check_compliance wrapper   (REAL today — the only
                                                      executable target on
                                                      this branch)
provision         -> workflows.provision             (future; routable when built)
inquiry           -> workflows.inquiry               (future; routable when built)
# anything else, or no POLICY entry for (org_bu, intent) -> unsupported,
# fail closed. Clarification/unsupported are decision outcomes, not routes.
```

Rules:

- do not route if `ready_to_route` is false
- do not route a possibly mutating ambiguous request to provisioning
- do not let the LLM emit arbitrary module paths, tool names, or shell commands
- setting `approval_required = true` is not an approval
- provision workflows may produce plans before approval, but may not mutate without allow-list match and recorded approval

## Open Questions
All four recommendations below survive the 2026-07-27 corrections
unchanged. One new open question — one HCP organization per BU vs. BU
in project naming — is tracked in the A1 scope block above, deferred
until the Terraform path goes live.

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
