# External Ticket (ServiceNow/Jira) Approval Integration

## Status
Design only. Confirmed by search: no code in this repo references
ServiceNow or Jira anywhere — only unelaborated "future channel"
mentions in `docs/HARNESS_DESIGN.md`. `ApprovalRecord`
(`gateway/schemas.py:50-59`) has no ticket-related fields. This is that
design, grounded in real, current ServiceNow/Jira MCP tooling rather
than assumed capability (see Sources).

## Part A: What actually exists to integrate with
- **ServiceNow**: real MCP servers exist, including ServiceNow's own
  official "MCP Server Console." A `change_coordinator` tool package
  manages the change-request lifecycle (create, route, query). **Hard
  limitation, confirmed directly**: *"Flows with approval steps, wait
  conditions, or other async logic are not eligible for standard MCP
  tool usage regardless of ACL configuration."* The MCP surface can
  create/route/query a Change Request; it cannot drive the actual CAB
  approval gate synchronously.
- **Jira**: the official Atlassian Rovo MCP Server (GA Feb 2026) has
  `transition_issue`/`get_transition_id` — moves an issue through
  workflow states. **Confirmed limitation**: *"no webhook or
  change-event surface"* through the MCP interface — webhook-driven
  notifications need the separate REST API, configured once by an
  admin, not something the agent sets up per-request. Jira does support
  attaching a webhook as a workflow post-function on transition; it's
  just outside the MCP tool boundary.

### The architectural consequence
Neither system's MCP surface supports "call a tool, get an approval
result back synchronously." Approval-via-ticket has to be **push-based**
(a webhook fired by the ticketing system on approval, received by the
Gateway) or **poll-based** — the same shape as this project's existing
`webhook` channel concept
(`docs/HARNESS_DESIGN.md`'s input channels), repurposed as an
*approval-completion* signal rather than a request-intake one. This
isn't a new channel type to design from scratch; it's a new *purpose*
for one already sketched.

## Part B: Two modes, different safety treatment

### Mode A — the harness creates the ticket (push)
For resource types whose policy requires a formal change record:
1. Plan drafted, requires human approval.
2. Harness creates a ServiceNow CR or Jira issue via the relevant MCP
   tool, embedding `plan_hash` in a **structured field** (a custom
   field, not prose) — this is what makes the eventual approval
   verifiable, not just "a ticket exists somewhere."
3. CAB/approval progression happens natively in ServiceNow/Jira,
   outside the MCP surface (per Part A's limitation).
4. A webhook (ServiceNow Business Rule / Jira post-function) fires to
   the Gateway on approval.
5. Gateway verifies the embedded `plan_hash` matches the `PlanRecord`
   being gated **before** setting `ApprovalRecord.human_approved=True`
   — the same tamper-evidence principle
   `gateway/tool_dispatcher.py:89-91` already applies to plan-hash
   verification for internally-recorded approvals.

### Mode B — the requester references an already-approved ticket (pull)
For change management that happened before the harness was involved:
1. Requester supplies a ticket ID (in `RequestEnvelope.metadata` or
   stated in chat).
2. Harness queries it read-only via the same MCP tools, confirms an
   approved/scheduled state.
3. **Scope verification** — the hard part: does the ticket actually
   cover *this* change, not just *a* change? See Part C.

## Part C: The central rule — scope must be verified structurally, never inferred
A ticket's existence or "approved" status is **not sufficient** on its
own. Its approved scope has to be programmatically verified against the
actual plan — never inferred from free text by an LLM. This is the same
class of risk this project has refused everywhere else:
- `SkillProposal`s require human review before trust
  (`docs/skills_and_workspace_design.md` Part C) — an agent's own
  unverified judgment isn't sufficient to trust a new pattern.
- `iam:PassRole` must be ARN-scoped, not wildcarded
  (`docs/infra_discovery_and_platform_app_split.md` Part B).
- Memory is "context, never authority"
  (`docs/harness_memory_design.md`).

A loosely-matched ticket is the same shape of escalation vector: approve
a trivial CR, dispatch an unrelated dangerous change against it. **The
rule**: `ticket_scope_verified` is only ever set `True` by matching a
structured field the harness itself wrote or checks against (e.g., the
embedded `plan_hash`, or a resource-type list) — never by semantic/LLM
judgment as the actual gate. Matches `AGENTS.md`'s existing hard rule,
"deterministic checks stay deterministic."

## Part D: `ApprovalRecord` schema addition
```python
class ApprovalRecord(BaseModel):
    # ... existing fields unchanged (approval_id, plan_id, plan_hash,
    # agent_approved, agent_reasoning, human_approved, human_reviewer,
    # approval_timestamp, is_valid) ...
    external_ticket_system: Optional[str] = None  # "servicenow" | "jira" | None
    external_ticket_id: Optional[str] = None
    external_ticket_url: Optional[str] = None
    ticket_scope_verified: bool = Field(
        default=False,
        description=(
            "True only if a structured field on the ticket (e.g. an "
            "embedded plan_hash) was programmatically matched against "
            "this plan -- never set from free-text/LLM judgment alone."
        ),
    )
```

## Part E: Dispatcher check addition
`BrokeredToolDispatcher.evaluate_intent()` gains one more deny-by-default
check, same shape as its existing resource-type/region/plan-hash checks
(`gateway/tool_dispatcher.py:50-105`): if the resource type's
`review_policy` requires an external ticket, deny unless
`external_ticket_id` is set **and** `ticket_scope_verified=True`.

## Part F: Policy default — foundation-tier requires a ticket
Extends the `review_policies/*.yaml` config family already named in
`docs/HARNESS_DESIGN.md`'s "Borrow: schema-validated, hot-reloadable
config" section with a third dimension, alongside auto-approve/human-
approve/always-deny: **which resource types require an external ticket
specifically**, not just any human approval. Natural default:
foundation-tier resources — already mandatory-human-approval per
`docs/foundation_app_layering_and_iam_tiers.md` Part A — also require a
formal external CR by default, matching what a real enterprise would
expect for that risk tier. App-tier changes stay on the lighter Control
UI approval path unless a specific resource type's policy overrides
that.

## Open questions / not yet decided
- Polling vs. webhook-only for detecting ticket approval — webhook is
  lower-latency but requires the Gateway to expose a reachable
  endpoint; polling is simpler to deploy but slower and noisier. Not
  decided.
- Which structured field convention to standardize on per system (a
  dedicated ServiceNow custom field vs. a Jira custom field vs. parsing
  a conventionally-formatted description block) — not decided, needs a
  concrete pilot integration to settle.
- Whether Mode B's scope-verification failure should be a hard deny or
  route to a human for manual scope confirmation — leaning hard deny
  (fail closed, consistent with everything else), not decided as a
  final rule.
- Whether `ticket_scope_verified` needs its own audit-log entry
  distinct from the approval decision itself, for compliance auditors
  who care specifically about ticket-scope match history — not decided.
- **Scope gap, confirmed by re-reading this doc (2026-07-14): this
  design covers only the `PlanRecord`/`ApprovalRecord` dispatch-time
  human-approval gate — it says nothing about, and provides no path
  for, the two separate human-review gates in the skill-proposal
  lifecycle** (`docs/skills_and_workspace_design.md` Part C's admission
  review, and `docs/skill_promotion_thresholds.md` Gate 3's BU→org
  promotion review). Both of those are still "a `TeamMember` with
  `role="approver"`/`"admin"` reviews it directly" with no
  ServiceNow/Jira option designed. If an org wants skill admission or
  promotion to also route through an external ticket instead of a
  direct human review, that's new scope, not something this design
  already covers by extension — not decided whether it's even wanted,
  just named as a real gap rather than silently assumed covered.

## How this relates to the existing docs
- Gives concrete design to the "Jira/ServiceNow" and "ticket comment"
  mentions already present but unelaborated in
  `docs/HARNESS_DESIGN.md`'s input-channel and notification-sink lists.
- Reuses the `webhook` channel concept for a new purpose
  (approval-completion signal) rather than designing a new channel
  type.
- Reuses the plan-hash tamper-evidence principle already in
  `gateway/tool_dispatcher.py`, applied to ticket-embedded scope
  verification instead of internal `ApprovalRecord` matching.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).
- **Explicitly does NOT cover** `docs/skills_and_workspace_design.md`
  Part C's skill-admission review or `docs/skill_promotion_thresholds.md`
  Gate 3's BU→org promotion review — both cross-linked back to this
  doc's Open Questions with that gap named plainly (2026-07-14).

## Sources
- [echelon-ai-labs/servicenow-mcp — GitHub](https://github.com/echelon-ai-labs/servicenow-mcp)
- [What's New in MCP Server Console: From Skills to Full Platform — ServiceNow Community](https://www.servicenow.com/community/now-assist-articles/what-s-new-in-mcp-server-console-from-skills-to-full-platform/ta-p/3541621)
- [atlassian/atlassian-mcp-server — GitHub](https://github.com/atlassian/atlassian-mcp-server)
- [Jira MCP Server Guide (2026): Official vs Community Setup — MCP.Directory](https://mcp.directory/blog/jira-mcp-complete-guide-2026)
- [Change Advisory Board (CAB) workbench — ServiceNow docs](https://www.servicenow.com/docs/r/it-service-management/change-management/cab-workbench.html)
