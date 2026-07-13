# UI Channel & Team-Member Tenancy — Deep Dive

## Status
Analysis only — nothing in this document is built. Captured before any
implementation, per this project's habit of analyzing before building (see
`docs/HARNESS_DESIGN.md`'s "Document map"). If you're picking this up
later: none of the CopilotKit/A2UI pieces below exist in code yet, and
`RequestEnvelope`/`WorkspaceBundle`/`PlanRecord`/`ApprovalRecord`/
`ToolIntent` (which this design reuses) are the only parts already real —
see `gateway/schemas.py`.

## Terminology, disambiguated
These four get conflated constantly; they're layers, not alternatives:

| Layer | What it actually is |
|---|---|
| **MCP** | Agent ↔ tools. Already our main paradigm (`aws-iac-mcp-server`, `ccapi-mcp-server`, HashiCorp's Terraform MCP Server). |
| **A2A** | Agent ↔ agent, across trust boundaries. Not used in this project yet. |
| **AG-UI** (CopilotKit) | Agent runtime ↔ frontend **transport** — event-based, bi-directional state sync. The wire, not the picture on the screen. |
| **A2UI** (Google, public since Dec 2025, Apache 2.0, v0.8) | The **UI-rendering data format** riding on top of AG-UI (or A2A): agents send declarative JSON describing a component tree from a pre-approved catalog (Button, Card, TextField, ...) — never executable code. Client renders natively (web/Flutter/Angular/React/Lit). |

## Why this fits the existing design, not just "a nicer UI"
A2UI's core security philosophy — *"agents can only use pre-approved
components from your catalog, no UI injection attacks"* — is the same
deny-by-default, allow-list-everything principle already used throughout
this project (`infra/allowed-resource-types.json`, the dispatcher's
approval gate in `gateway/tool_dispatcher.py`). It's also a concrete
implementation candidate for the "Control UI" that
`docs/HARNESS_DESIGN.md` only sketched conceptually — a Vibe Diff or
approval request becomes an interactive Card with Approve/Reject buttons,
not a text blob a human has to parse.

## Org → Business Unit → Team member: what maps to what
`https://docs.openclaw.ai/concepts/agent-workspace` confirms something
specific and previously unstated in this project's docs: the workspace
(`AGENTS.md`, `SOUL.md`, `USER.md`, memory files) is **one persona per
`agent_id`** — *"the agent's home... persistent memory."* `USER.md` is
singular ("who *the* user is"), and OpenClaw's own docs explicitly don't
address multiple people sharing one workspace with separate identities.
Sessions live *separately* from the workspace, keyed as
`agent:<agentId>:<mainKey>` — that `mainKey` is where per-requester
distinction actually lives, not the workspace.

So, concretely:
- **Org** — our config-layer construct (unchanged from `docs/HARNESS_DESIGN.md`).
- **Business Unit** — one `agent_id`, one workspace: shared instructions,
  persona, credentials, allow-list, cost ceiling. **Not** per-person.
- **Team member** — distinguished at the **session/request level**, not
  the workspace level. `gateway/schemas.py`'s `RequestEnvelope` already
  has a `channel_user_id` field for exactly this — built in before we
  understood precisely why it was the right shape.

### The audit gap this surfaces
`gateway/tool_dispatcher.py`'s `audit_logs` table currently records
`plan_id`, `org_id`, `bu_id`, `resource_type`, `operation`, `decision`,
`reason`, `payload` — **no `channel_user_id`**. That was fine when "which
BU did this" was the only granularity that mattered. Once individual
actions (e.g., clicking Approve in a UI) matter, "which BU" isn't enough —
"which person" is. This should be fixed regardless of the UI decision
below; it's a gap in the schema/table, not something the UI choice causes
or fixes.

## Step-by-step input flow, with a CopilotKit channel added
This walks the same request lifecycle already described in
`docs/HARNESS_DESIGN.md`'s "How the flow works," with a new channel type
substituted at the front and A2UI substituted for plain text at the
review step:

1. **Team member opens the CopilotKit web UI**, authenticates (org
   SSO — a new trust question, see risks below).
2. **Describes the desired infra** in the embedded Copilot chat/sidebar —
   natural language, e.g. "deploy a static site for the payments team."
3. **AG-UI transport** streams this to a new `copilotkit` channel adapter
   on the Gateway (alongside `slack`/`webhook`/`cli`), which normalizes it
   into a `RequestEnvelope`: `channel="copilotkit"`,
   `channel_user_id=<member>`, `org_id`/`bu_id` resolved from the
   authenticated session.
4. **Gateway resolves the binding** → workspace bundle — unchanged by the
   UI choice.
5. **Deterministic preflight** (`spec/check_compliance.py`) — unchanged.
6. **ADK agent graph runs `plan_request(envelope)`** (still the one
   required build item from `docs/planned_implementation.md` Phase 3) —
   drafts the plan, Vibe Diff, and `ToolIntent`(s) via the non-executing
   `propose_tool_intent` tool.
7. **The Gateway renders the result as an A2UI message** instead of plain
   text — a Card component showing the resource diff, region, and cost,
   with Approve/Reject buttons from a pre-approved catalog — streamed
   back over AG-UI to the same UI.
8. **If the review policy requires a human**, the same card surface
   handles it: clicking Approve/Reject sends a structured AG-UI event
   back (not free text), which the Gateway turns into an `ApprovalRecord`
   (`human_approved`, `human_reviewer=channel_user_id`).
9. **Gateway calls `BrokeredToolDispatcher.evaluate_intent()`**; only
   `True` reaches the real CCAPI/Terraform MCP call — unchanged.
10. **Result streams back as another A2UI component** — a success card
    with the resulting URL, or a denial card with the specific reason.

## Open risks / not yet designed
- **A2UI is very new** (public since Dec 2025, v0.8) — same
  "verify against current docs, don't assume stability" caution that
  applies to other fast-moving integrations in this project (e.g., the
  AWS/Terraform MCP servers).
- **The component catalog is itself a security boundary.** Deciding
  exactly which components (Card, DiffView, CostBreakdown,
  ApproveButton, ...) are pre-approved is a real design task, not a
  footnote — it bounds what an agent can ever render, the same way
  `infra/allowed-resource-types.json` bounds what it can ever provision.
- **CopilotKit UI needs its own auth story.** Slack/webhook bindings rely
  on channel-account identity (see `docs/HARNESS_DESIGN.md`'s "Routing is
  binding-based" section); a web UI needs SSO/org-login to establish
  trust before `org_id`/`bu_id`/`channel_user_id` can be resolved at all.
  Not yet designed.
- **The `channel_user_id` audit gap** noted above should be fixed in
  `gateway/tool_dispatcher.py` independent of whether CopilotKit ships.

## How this relates to the existing docs
- Extends `docs/HARNESS_DESIGN.md`'s multi-tenancy section with the
  team-member layer it didn't previously make explicit.
- Proposes `copilotkit` as a new channel type alongside
  `slack`/`webhook`/`cli` in the harness layer design — additive, doesn't
  change the Gateway/dispatcher design already in place.
- Doesn't change the required next step (`plan_request(envelope)` in
  `docs/planned_implementation.md` Phase 3) — this UI work is layered on
  top of that, not a substitute for it.
