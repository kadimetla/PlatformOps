# Next Steps to Revisit

A checkpoint of outstanding work, split by branch, so nothing gets lost
between sessions. Not a design doc — see `docs/HARNESS_DESIGN.md` for the
actual architecture decisions and reasoning.

## On this branch (`design/harness-architecture`)

Next spike, per `docs/HARNESS_DESIGN.md`'s "What to implement first":
1. Define `RequestEnvelope`, `WorkspaceBundle`, `PlanRecord`,
   `ApprovalRecord`, and `ToolIntent` schemas.
2. Add config validation for bindings and workspace bundles (fail closed on
   malformed config, per the "Borrow: schema-validated, hot-reloadable
   config" section).
3. Wrap the existing ADK graph (`agents/orchestrator.py`) behind a
   `plan_request(envelope)` call — the Gateway calls this, it doesn't own
   mutation dispatch itself.
4. Move mutating MCP calls (CCAPI, Terraform apply) behind a local
   dispatcher function that checks a `ToolIntent` against an approval
   record before executing — this is the enforcement gap between
   "prompt-level rule" (what exists today) and "runtime-enforced rule."
5. Add a file-backed or SQLite audit log before building any Control UI.

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
