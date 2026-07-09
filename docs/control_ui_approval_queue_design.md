# Control UI Approval Queue — Design

## Status
Design only — nothing here is built; no Control UI exists yet
(`docs/HARNESS_DESIGN.md`'s own built-vs-designed table). "Control UI"
has been referenced from seven other docs as a shopping list of five
required views, never as a state machine, an update mechanism, or a
concurrency model. This closes that gap, grounded against three real,
comparable products (HCP Terraform's run queue, GitHub's required-
reviewers pattern, the AG-UI protocol) rather than designed from
scratch — see Sources.

## Part A: The queue is a state machine, not a list of screens
```
drafted → under_review → pending_approval → approved → dispatching → executed
                              │                  │
                              ├─ pending_approval:control_ui    (waiting for a UI click)
                              ├─ pending_approval:external_ticket (waiting on CR-XXXX,
                              │                                    docs/external_ticket_approval_integration.md)
                              │
                              └─ rejected / denied (terminal)
```
**The queue view is "everything in a `pending_approval:*` state,"** not
a separate concept from the state machine. This is the unification
point between the two approval paths now designed: an item waiting on a
ServiceNow CR and an item waiting on a Control UI click are the *same*
queue, same underlying record, different sub-state — rendered
differently (a ticket-link card vs. an Approve/Reject card), never two
systems.

## Part B: New rule — self-review prevention
GitHub's environment protection rules have a named option: *"prevent
self-reviews... users who initiate a deployment cannot approve the
deployment job."* No prior doc in this project stated this rule —
`TeamMember.role="approver"` (`docs/skills_and_workspace_design.md`)
says who is *capable* of approving, nothing said a capable approver
can't approve their own request.

**New check**: `ApprovalRecord.human_reviewer` must never equal the
originating `RequestEnvelope.channel_user_id`. Same deny-by-default
shape as every other check in `harness/tool_dispatcher.py` — this
belongs at the same layer, not just as a UI-level disabled button
(a disabled button is guidance; the actual gate has to be code-level,
matching this project's "deterministic checks stay deterministic" rule
in `AGENTS.md`).

## Part C: Multi-approver semantics
Two real systems, same converged default:
- GitHub: *"only one of the required reviewers needs to approve"* —
  any-of-N, up to 6 named reviewers.
- ServiceNow CAB: *"you control whether you need unanimous approval or
  just one person from the group."*

**Design**: `review_policy` (the config family already named in
`docs/HARNESS_DESIGN.md`'s "Borrow: schema-validated, hot-reloadable
config" section, not yet detailed) gains `approval_mode: "any" |
"unanimous"`, per resource type/tier. **A third value, `"automated"`,
added in `docs/personas_and_tool_blueprints.md` Part C**: no human
review at all, gated by hard cost/time limits instead — the default for
sandbox-purpose `CloudAccountBinding`s. Default `"any"` — matches both
researched systems' default; `"unanimous"` is the opt-in for the
highest-stakes tiers (plausibly foundation-tier, consistent with that
tier's existing "always human, no autonomous exception" rule in
`docs/foundation_app_layering_and_iam_tiers.md` Part A).

## Part D: Concurrency — serialize per foundation, not globally
HCP Terraform processes runs through a *per-workspace* queue
specifically so *"only one apply can modify state at a time."* The
equivalent boundary here is **per-`FoundationRecord`** (or per-BU for
app-tier changes with no foundation dependency): two foundation-tier
changes to the same cluster/VPC must not be allowed to apply
concurrently, regardless of how many are independently approved.

**New dispatcher-level rule**, not just a UI ordering concern:
`BrokeredToolDispatcher.evaluate_intent()` should deny (or queue) a
`ToolIntent` targeting a `foundation_id` that already has an
in-flight (`dispatching`, not yet `executed`/`failed`) intent against
it — same shape as the existing `depends_on_foundation_id` check
(`docs/foundation_app_layering_and_iam_tiers.md` Part D), checking
concurrent-dispatch state instead of existence state.

## Part E: Real-time updates — AG-UI's actual mechanism, not polling
Confirmed: AG-UI synchronizes frontend/backend state via *"snapshots
and JSON Patch deltas"* over an SSE stream
(`docs/ui_and_multitenancy_deep_dive.md` named AG-UI as the transport
candidate; this is the concrete update mechanism that doc didn't
specify). The queue view holds a live state snapshot and applies
incremental patches as `PlanRecord`/`ApprovalRecord` state changes —
**including a webhook-driven external-ticket approval landing as a
patch to the same queue item**, not a separate update path or a
poll-triggered refresh.

## Part F: The five views, with the state machine applied
| View | What it shows, concretely |
|---|---|
| **Pending approvals** | All items in any `pending_approval:*` sub-state — plan summary, risk tier, requester, BU, cost, region, resource types, policy findings, and which sub-state (UI-click vs. external-ticket, with ticket link if the latter) |
| **Plan detail** | Raw structured diff, deterministic compliance results, MCP validation results, security-agent recommendation, human comments — plan-step warning diagnostics surfaced inline on this view, per HCP Terraform's pattern, not a separate tab reviewers have to seek out |
| **Audit log** | Immutable timeline including the new self-review-denial events (Part B) and concurrent-dispatch denials (Part D) alongside the existing request/plan/approval/dispatch/verification/failure/rollback events |
| **Config health** | Active registry version, last reload, validation failures, missing policy coverage, stale credentials — plus, per `docs/harness_memory_design.md`'s "Unconfirmed memory" panel design, agent-authored memory entries awaiting batch confirmation |
| **Break-glass panel** | Time-limited manual approval/deny override — **also subject to Part B's self-review check** and should itself write a distinguishable audit event (break-glass overrides shouldn't look identical to a normal approval in the audit trail) |

## Open questions / not yet decided
- Queue ordering within the "Pending approvals" view — oldest-first
  (fairness) vs. risk-tier-pinned (foundation-tier surfaced above
  app-tier regardless of age) is a UX judgment call, not resolved here.
- Whether `approval_mode: "unanimous"` needs a partial-rejection rule
  (does one reviewer's Reject immediately deny, or wait for all N to
  respond?) — ServiceNow's model implies immediate-deny-on-any-reject;
  not confirmed as the intended behavior here.
- Whether the per-foundation concurrency lock (Part D) should block a
  second `ToolIntent` from even being *approved* while one is in
  flight, or only block it at *dispatch* — leaning toward blocking at
  dispatch only (approval can proceed in parallel, dispatch serializes),
  not decided.

## How this relates to the existing docs
- Gives the state machine, concurrency model, and update mechanism that
  `docs/HARNESS_DESIGN.md`'s "Borrow: Control UI" section only ever
  listed as five view names.
- Unifies with `docs/external_ticket_approval_integration.md`'s two
  approval paths into one queue/state-machine, rather than treating
  them as separate systems.
- The self-review-prevention rule (Part B) is a new, previously-missing
  gap in `docs/skills_and_workspace_design.md`'s `TeamMember` design —
  `role` alone was never sufficient.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [UI and VCS-driven run workflow in HCP Terraform — HashiCorp Developer](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/run/ui)
- [Review deployment runs — Terraform Stacks docs](https://developer.hashicorp.com/terraform/cloud-docs/stacks/deploy/runs)
- [Deployments and environments — GitHub Docs](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [Reviewing deployments — GitHub Docs](https://docs.github.com/actions/managing-workflow-runs/reviewing-deployments)
- [AG-UI Protocol — CopilotKit](https://www.copilotkit.ai/ag-ui)
- [State Management — Agent User Interaction Protocol docs](https://docs.ag-ui.com/concepts/state)
