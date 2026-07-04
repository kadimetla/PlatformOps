# Next Steps to Revisit

A checkpoint of outstanding work, split by branch, so nothing gets lost
between sessions. Not a design doc — see `docs/HARNESS_DESIGN.md` for the
actual architecture decisions and reasoning.

## On this branch (`design/harness-architecture`)

### Required (blocks the spike from being "done")
Exactly one item — see `docs/planned_implementation.md` Phase 3 for the
concrete mechanism (not just "wrap the agent graph," but specifically: pull
`ccapi-mcp-server`'s mutating tools off `cdk_provisioning_agent` entirely,
replace with a non-executing `propose_tool_intent(...)` function tool, and
have the Gateway — not the agent — call the real MCP tool only after
`BrokeredToolDispatcher.evaluate_intent()` returns `True`):

1. **Wrap the existing ADK graph behind `plan_request(envelope) -> PlanRecord`**
   in `agents/orchestrator.py`, and move the actual mutating MCP calls out
   of the agent's tool list into the Gateway/dispatcher layer. Needs the
   ADK Runner invocation API verified against the installed `google-adk`
   version first (untested from this environment).

**Small, separate, verifiable bug found while tracing a request through
the system** (see `docs/current_architecture.md` Section 4's worked
example): `README.md`'s "Run the agent" step says
`python -m agents.orchestrator`, but `agents/orchestrator.py` only
defines `root_agent = Agent(...)` — there's no `Runner`/`Session`
construction or `if __name__ == "__main__":` block anywhere in this
codebase, so that command constructs the Agent objects and exits without
processing any input. The likely correct command is ADK's own CLI
(`adk web agents/` or `adk run agents/`, which auto-discovers
`root_agent`) — needs verifying against the installed `google-adk`
version, then fixing in `README.md`.

### Already done (for reference, not action items)
1. ~~Define `RequestEnvelope`, `WorkspaceBundle`, `PlanRecord`,
   `ApprovalRecord`, `ToolIntent` schemas.~~ **Done** — `harness/schemas.py`.
2. ~~Add config validation for bindings and workspace bundles.~~ **Done** —
   `harness/config_engine.py`, fail-closed on bad config, tested.
3. ~~Move mutating MCP calls behind a local dispatcher function.~~ **Done**
   standalone — `harness/tool_dispatcher.py`'s `BrokeredToolDispatcher`,
   deny-by-default, tested. Not yet wired to intercept the real
   CCAPI/Terraform MCP tool calls — that wiring is the Required item above.
4. ~~Add a file-backed or SQLite audit log.~~ **Done** —
   `harness/tool_dispatcher.py`'s `audit_logs`/`approvals` tables, proven
   by the 8 passing tests in `tests/test_harness.py`.

### Optional / longer-horizon (not required to close out this spike)
- Org registry + onboarding automation (mint a fresh `agent_id`/BU scope,
  register it, wire its workspace config bundle) — currently manual steps.
- Control UI (approval queue, plan detail, audit log, config health,
  break-glass panel) — comes after the schemas/dispatcher above, not before.
  See `docs/ui_and_multitenancy_deep_dive.md` for an analyzed-not-built
  candidate: CopilotKit/AG-UI transport + A2UI (Google's declarative,
  pre-approved-component-catalog UI format) for both the input channel
  and the approval-card rendering.
- **Small, cheap fix worth doing regardless of the UI decision**: add
  `channel_user_id` to `harness/tool_dispatcher.py`'s `audit_logs` table —
  currently only `org_id`/`bu_id` are recorded, so "which person approved
  this" isn't in the audit trail, only "which BU." Identified while
  analyzing the team-member layer underneath Org/BU.
- Revisit the declined "register PlatformOps as an MCP tool source on a
  real OpenClaw Gateway" path if the custom Gateway build proves heavier
  than expected (see "Superseded" section in the design doc for why it was
  declined, not ruled out permanently).
- Model-agnosticism beyond Gemini (`agents/model_config.py` currently
  returns a raw string, not a provider-neutral handle).

## On `kaggle-submission` (frozen hackathon entry, separate from the above)

Nothing here has been run end-to-end yet — this is the gap between
"designed/committed" and "demoed."

### Required to submit
1. Run the actual build: install `google-adk`, `mcp`, `pyyaml`; verify the
   `google-adk` import paths in `agents/*.py` against whatever version gets
   installed (flagged as unverified in code comments).
2. Set up the AWS sandbox account + billing alarm per `README.md` Setup.
3. Test the CDK path live: `uvx awslabs.aws-iac-mcp-server@latest` and
   `uvx awslabs.ccapi-mcp-server@latest` have not been run against a real
   account from here.
4. Capture real demo footage per `VIDEO_SCRIPT.md`'s recording checklist:
   golden path (CDK) and one rejected case (e.g. public-write S3 spec) —
   the two beats the rubric actually grades.
5. Fill in the `WRITEUP.md` placeholders with what actually happens in that
   footage (Demo Walkthrough, Challenges, video URL, cover image) — do not
   submit with placeholders still in.
6. Recount `WRITEUP.md`'s word count after edits (was ~2,189 of the 2,500
   cap as of the last check).
7. Submit before the stated deadline (Monday, July 6, 2026, 11:59 PM PT).

### Optional, strengthens the submission but not blocking
- Create an HCP Terraform account, get a `TFE_TOKEN`, and verify the exact
  HashiCorp Terraform MCP Server install/launch command
  (`mcp_server/external_servers.py` flags this as unverified) — needed
  only to demo the Terraform path live, not the CDK path.
- Also capture the same request re-run with "using Terraform" in the demo
  footage, to show the router actually switching paths — nice-to-have on
  top of the required CDK golden-path + rejected-case footage.
- Trim `VIDEO_SCRIPT.md` narration if needed — currently ~609 words
  (~4:20 at natural pace), under the 5-minute cap but tighter than the
  original draft.

## Branch map, for orientation
- `main` / `dev` / `kaggle-submission` — multi-tool CDK+Terraform
  provisioning work, frozen for submission purposes on `kaggle-submission`.
- `design/harness-architecture` — the forward-looking Gateway/model design,
  intentionally kept separate; merge into `dev` when ready, not into
  `kaggle-submission`.
