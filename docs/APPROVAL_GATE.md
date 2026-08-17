## Status
Designed only, with three pieces already real (see the table). This doc
owns the **implementation** of the approval pause: how the gate node is
decomposed, which components persist what, how the pause reaches a
browser and comes back, and the LangGraph re-execution hazard that
dictates the node split. It deliberately does **not** re-derive the
approval *design* — authority model, self-looping quorum node, payload
fields, staleness rules, and digest binding all live in
[EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s "The Approval
Gate" and are linked, not repeated.

One LangGraph behaviour verified empirically against the installed
version (2026-08-14), because it changes the node decomposition — see
"The re-execution hazard".

## Real vs. Designed
| Piece | Status |
|---|---|
| `ApprovalRequest`/`ApprovalRecord`/`ApprovalVerdict` schemas | **Real** — `gateway/approval.py` |
| Topology revision/digest fields and `superseded` request status | Designed only — required by `COMPOSABLE_PROVISIONER.md`'s fluid-topology lifecycle; absent from the real schemas/store |
| Cloud Stack release/version/content/publication provenance | Designed only — folded into `artifact_provenance` by `CLOUD_STACK_CATALOG.md`; absent from the real schemas/store |
| `HITLEventKind.APPROVAL_REQUIRED`, `HITLStatus` | **Real** — `interaction/events.py:52` |
| `hitl_event_to_interrupt` + approval `responseSchema` | **Real** — `interaction/agui.py:45,75`; already emits `{verdict, approval_digest}` |
| Approval gate node (`interrupt()`, quorum loop) | Not implemented — no checkpointed workflow exists to host it |
| `resume_approval` on the harness | Not implemented — `harness/core.py:19` says so explicitly; only `resume_clarification` exists |
| `transports/http.py` approval resume | Not implemented — `_extract_answer` handles the clarification payload only |
| `ApprovalRequestStore` / `ApprovalDecisionStore` / `ApprovalAuthorizationService` / `ApprovalCoordinator` | Not implemented — no persistence of any kind exists yet |
| Approval inbox UI | Not implemented — `frontend/` has the session grid + floating panel only |

## Where the gate sits
Inside the **fixed parent** provision graph, after the real OpenTofu
plan and its deterministic checks. It is never a topology unit and
cannot be expressed in a `TopologySpec` — the topology registry is
structurally planning-only
([COMPOSABLE_PROVISIONER.md](COMPOSABLE_PROVISIONER.md), Step 3).

```
dynamic topology -> render -> tofu plan -> deterministic checks
  -> create_approval_request -> APPROVAL INTERRUPT -> revalidate -> tofu apply
```

## The re-execution hazard — why `create_approval_request` is its own node
**Verified 2026-08-14 against the installed LangGraph.** A node body
re-executes *from the top* on every resume. It is not "may run again":
it runs once per resume, so an N-approval quorum runs the pre-`interrupt`
code **N+1 times**. Probe result for a 2-of-2 quorum with the request
creation inline in the gate node:

```
after 1st pause,   side effects: ['CREATE_APPROVAL_REQUEST']
after 1st approve, side effects: ['CREATE_APPROVAL_REQUEST', 'CREATE_APPROVAL_REQUEST']
after 2nd approve, side effects: ['CREATE_APPROVAL_REQUEST', 'CREATE_APPROVAL_REQUEST', 'CREATE_APPROVAL_REQUEST']
final: {'approvals': 2, 'done': True}
```

Three approval requests for one deployment. If creation notifies
approvers, that is three notifications; if it writes to a store, three
rows unless the write is idempotent.

This interacts directly with the self-looping quorum node
`EXECUTION_CREDENTIALS.md` already designed: the self-loop is *what
causes* the repeat. So the rule is not optional —

```
create_approval_request   separate node, or idempotent on request_id
                          (keyed writes, not appends)
approval_gate             interrupt() + quorum accumulation ONLY;
                          nothing before the interrupt() call that
                          isn't safe to repeat N+1 times
```

Everything after `interrupt()` in the node is also re-run on the next
resume, so quorum state must live in `ApprovalRequest.approvals_so_far`
(the real field) or the decision store — never in a local variable
accumulated across pauses.

## Field names — corrected against the real schemas
A sketch of this design used field names that do not match
`gateway/approval.py`. Corrected here so implementation doesn't inherit
them:

| Sketch | Real (`gateway/approval.py:43`) | Note |
|---|---|---|
| `artifact_provenance=topology_digest` | `approval_digest` | **Conceptual, not cosmetic**: `artifact_provenance` is one of seven inputs to `approval_digest` ([PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md)); for catalog-derived work it canonically includes exact `CloudStackRelease` version/content/publication digests plus the request-local topology digest (`CLOUD_STACK_CATALOG.md`). `toolchain_identity_digest` remains separate. The request carries the combined digest. |
| `summary` | `vibe_diff` | Named for what it is across the whole doc set |
| `expires_at` | `approval_expires_at` | AG-UI's `Interrupt` separately has a native `expires_at` — see below |
| — | `intent`, `capability_required` | Required, and load-bearing for authority evaluation |
| — | `approvals_so_far: list[ApprovalRecord]` | How quorum is tracked across the self-loop |

## Transport wiring — against the adapter that already exists
`hitl_event_to_interrupt` (real) already produces the interrupt shape,
and `_response_schema_for` already emits the approval response schema:

```python
{"type": "object",
 "properties": {"verdict": {"enum": ["approve", "reject"]},
                "approval_digest": {"type": "string"}},
 "required": ["verdict", "approval_digest"],
 "additionalProperties": False}
```

Two corrections to how a sketch described the emitted event:

- **Metadata is namespaced, not flat.** The real adapter emits
  `metadata.platformops.{request_id, status, resume_mode, payload}` —
  not flat camelCase keys like `planDigest`/`approvalsCollected`. An
  inbox UI reads `metadata.platformops.payload.*`. Changing this means
  changing a tested adapter, which is a decision, not a detail.
- **Expiry has a first-class home.** `ag_ui.core.Interrupt` has a real
  `expires_at` field and the adapter already sets it from
  `event.expires_at`. Don't duplicate expiry into metadata.

Verified field lists from the installed package: `Interrupt` is
`(id, reason, message, tool_call_id, response_schema, expires_at,
metadata)`; `RunFinishedEvent` is `(type, timestamp, raw_event,
thread_id, run_id, result, outcome)`, and interrupts nest under
`outcome` (`RunFinishedInterruptOutcome` = `type` + `interrupts`) while
`result` stays top-level for the success case.

**SSE delivers the pause; an HTTP POST returns the decision.** No
WebSocket is required — this is the same single-`POST /runs` convention
`transports/http.py` already uses for clarification resume
([WEB_CHAT_APP.md](WEB_CHAT_APP.md)), extended with an approval branch
in `_extract_answer` and a `resume_approval` on the harness. Neither
exists yet.

## Two surfaces, one authority
```
inline chat panel   requester sees "waiting for 0 of 2 approvals"
approval inbox      approvers see every pending request for their scopes
```
The inbox is the operational interface — approvers do not have the
requester's thread open. A2UI may render the card dynamically; the
buttons still submit the same structured response. **The UI never
determines authority.**

## Server-side validation — the enforcement point
Order matters: cheap identity checks before expensive re-fetches, and
every check before any record is written.

```
1. verify the approver's own PlatformOps session
2. re-fetch current approval grants (never trust the session snapshot)
3. verify authority for THIS scope
4. reject requester self-approval
5. verify the request is pending, unexpired, and still names the current
   sealed topology revision
6. verify the submitted approval_digest matches
7. enforce idempotency -- one approver cannot approve twice
8. persist an immutable ApprovalRecord
```

**Never accept an `approver_id` from the browser.** Derive it from the
authenticated session, the same rule `harness/core.py`'s
`resume_clarification` already enforces for clarification resumes
(it compares `actor.actor.user_id` against the stored `actor_id`
before consuming the pending entry).

Steps 2-4 are the runtime half of `EXECUTION_CREDENTIALS.md`'s
authority model; step 6 is its digest binding; the "approval permission
changed mid-flight" case is that doc's staleness section. Not repeated
here.

## Topology revision supersession
**Extended 2026-08-16:** resource-primitive authoring makes a provision
request fluid before approval, but never makes an approval target mutable.
The future approval-request schema therefore also carries the sealed
`topology_revision_id`, `topology_digest`, and rendered-artifact digest in
addition to its existing `plan_digest`/`approval_digest`. Catalog-derived work
also carries the exact `CloudStackPublicationRef` (publication target/digest,
registry snapshot, and nested stack/version/provider/content reference) whose
canonical digest is already bound
inside `artifact_provenance`; these display/audit fields cannot replace digest
validation. All are designed fields; `gateway/approval.py` does not contain
them yet.

Once an approval request is pending, an agent or human change creates a new
immutable topology revision. `ApprovalRequestStore` atomically marks the old
request `superseded`; it never edits the request's digests or accumulated
decisions. The successor must render, validate, plan, pass policy, seal, and
create a fresh approval request. Old `ApprovalRecord` values remain evidence
but cannot count toward the successor's quorum. An approver submitting to a
superseded request receives the same non-authorizing outcome as any request
that is no longer pending, and resume-time digest revalidation remains the
last backstop.

## Quorum and rejection
```
approval 1 -> persist record -> quorum unmet -> interrupt again ("1 of 2")
approval 2 -> persist record -> quorum met   -> continue to revalidate
rejection  -> terminate the run (fail-closed, current design)
```

## Recommended components
| Component | Owns |
|---|---|
| `ApprovalRequestStore` | Pending requests + current status |
| `ApprovalDecisionStore` | Immutable approver decisions |
| `ApprovalAuthorizationService` | Evaluates *current* approval grants |
| `ApprovalCoordinator` | Records a decision, then resumes the graph |
| Approval inbox UI | Discovery, plan review, approve/reject |
| `approval_gate` node | Pause, consume a validated decision, enforce quorum |

The boundary that keeps this honest:

```
LangGraph interrupt   pauses and resumes EXECUTION
approval service/UI   discovers, reviews, and RECORDS approvals
policy layer          decides WHO MAY approve
```

The checkpoint is execution state. It is not the approval inbox and not
the audit database — `EXECUTION_CREDENTIALS.md` already requires
approval records to be persisted independently of graph state, and the
stores above are that requirement made concrete.

## How this relates to the existing docs
Implements [EXECUTION_CREDENTIALS.md](EXECUTION_CREDENTIALS.md)'s "The
Approval Gate" — that doc owns authority, the self-looping node,
payload fields, staleness, and digest binding; this one owns node
decomposition, persistence components, transport wiring, and the
re-execution hazard. Sits after
[COMPOSABLE_PROVISIONER.md](COMPOSABLE_PROVISIONER.md)'s dynamic
topology slot in the fixed parent chain. Extends
[WEB_CHAT_APP.md](WEB_CHAT_APP.md)'s single-`POST /runs` resume
convention to approvals. Consumes
[PROVISION_WORKFLOW.md](PROVISION_WORKFLOW.md)'s seven-input
`approval_digest`, including artifact-provenance and resolved-toolchain
identity terms; [CLOUD_STACK_CATALOG.md](CLOUD_STACK_CATALOG.md) defines the
release/content/publication digests folded into artifact provenance for a
catalog-derived deployment. Indexed from
[HARNESS_DESIGN.md](HARNESS_DESIGN.md).
