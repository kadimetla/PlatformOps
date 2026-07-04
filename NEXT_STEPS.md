# Next Steps to Revisit

A checkpoint of outstanding work, split by branch, so nothing gets lost
between sessions. Not a design doc — see `docs/HARNESS_DESIGN.md` for the
actual architecture decisions and reasoning.

## On this branch (`design/harness-architecture`)

Detailed phase-by-phase plan lives in `docs/planned_implementation.md`;
this is just the status summary:

1. ~~Define `RequestEnvelope`, `WorkspaceBundle`, `PlanRecord`,
   `ApprovalRecord`, `ToolIntent` schemas.~~ **Done** — `harness/schemas.py`.
2. ~~Add config validation for bindings and workspace bundles.~~ **Done** —
   `harness/config_engine.py`, fail-closed on bad config, tested.
3. **Not done — the actual next step**: wrap the existing ADK graph
   (`agents/orchestrator.py`) behind a `plan_request(envelope)` call — the
   Gateway calls this, it doesn't own mutation dispatch itself.
4. ~~Move mutating MCP calls behind a local dispatcher function.~~ **Done**
   standalone — `harness/tool_dispatcher.py`'s `BrokeredToolDispatcher`,
   deny-by-default, tested. Not yet wired to intercept the real
   CCAPI/Terraform MCP tool calls the agents make — that's part of step 3.
5. ~~Add a file-backed or SQLite audit log.~~ **Done** —
   `harness/tool_dispatcher.py`'s `audit_logs`/`approvals` tables, proven
   by the 8 passing tests in `tests/test_harness.py`.

Longer-horizon, not urgent:
- Org registry + onboarding automation (mint a fresh `agent_id`/BU scope,
  register it, wire its workspace config bundle) — currently manual steps.
- Control UI (approval queue, plan detail, audit log, config health,
  break-glass panel) — comes after the schemas/dispatcher above, not before.
- Revisit the declined "register PlatformOps as an MCP tool source on a
  real OpenClaw Gateway" path if the custom Gateway build proves heavier
  than expected (see "Superseded" section in the design doc for why it was
  declined, not ruled out permanently).
- Model-agnosticism beyond Gemini (`agents/model_config.py` currently
  returns a raw string, not a provider-neutral handle).

## On `kaggle-submission` (frozen hackathon entry, separate from the above)

Nothing here has been run end-to-end yet — this is the gap between
"designed/committed" and "demoed":
1. Run the actual build: install `google-adk`, `mcp`, `pyyaml`; verify the
   `google-adk` import paths in `agents/*.py` against whatever version gets
   installed (flagged as unverified in code comments).
2. Set up the AWS sandbox account + billing alarm per `README.md` Setup.
3. Test the CDK path live: `uvx awslabs.aws-iac-mcp-server@latest` and
   `uvx awslabs.ccapi-mcp-server@latest` have not been run against a real
   account from here.
4. (Optional, Terraform path) Create an HCP Terraform account, get a
   `TFE_TOKEN`, and verify the exact HashiCorp Terraform MCP Server
   install/launch command — `mcp_server/external_servers.py` flags this as
   unverified.
5. Capture real demo footage per `VIDEO_SCRIPT.md`'s recording checklist:
   golden path (CDK), the same request re-run with "using Terraform" to
   show the router actually switching, and one rejected case (e.g.
   public-write S3 spec).
6. Fill in the `WRITEUP.md` placeholders with what actually happens in that
   footage (Demo Walkthrough, Challenges, video URL, cover image) — do not
   submit with placeholders still in.
7. Trim `VIDEO_SCRIPT.md` narration if needed — currently ~609 words
   (~4:20 at natural pace), under the 5-minute cap but tighter than the
   original draft.
8. Recount `WRITEUP.md`'s word count after edits (was ~2,189 of the 2,500
   cap as of the last check).
9. Submit before the stated deadline (Monday, July 6, 2026, 11:59 PM PT).

## Branch map, for orientation
- `main` / `dev` / `kaggle-submission` — multi-tool CDK+Terraform
  provisioning work, frozen for submission purposes on `kaggle-submission`.
- `design/harness-architecture` — the forward-looking Gateway/model design,
  intentionally kept separate; merge into `dev` when ready, not into
  `kaggle-submission`.
