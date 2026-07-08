# Flow Step 1: Request Intake & Normalization

## Owning code
Not built yet — would be a new `harness/channel_adapters/` module, one
adapter per channel (`slack`, `webhook`, `cli`, `copilotkit`). See
`docs/HARNESS_DESIGN.md`'s "Input layer (channels)" and
`docs/ui_and_multitenancy_deep_dive.md` for the CopilotKit-specific case.

## Input contract
Raw channel payload — shape varies per channel (a Slack event, CLI
args, a webhook body, an AG-UI event stream). No shared schema; this
step's whole job is producing one.

## Output contract
`RequestEnvelope` (`harness/schemas.py:14`) — `request_id`, `org_id`,
`bu_id`, `channel`, `channel_user_id`, `workspace_id`, `raw_payload`,
`metadata`. `org_id`/`bu_id` are not yet resolved from the raw payload
alone for channel-binding cases — see Step 2.

## Scenarios

## Scenario: Slack message in a bound channel
Given a Slack message posted in a channel matching a binding in `config/bindings.yaml`
When the Slack channel adapter normalizes it
Then a `RequestEnvelope` is produced with `channel="slack"` and `channel_user_id` set to the Slack user ID

## Scenario: Webhook from an unbound source
Given a webhook payload from a repo with no matching entry in `config/bindings.yaml`
When the webhook adapter processes it
Then intake FAILS with reason "no binding matches this source" — never falls through to a default route (per `docs/HARNESS_DESIGN.md`'s binding validation rule: "a default route is allowed only in a single-BU sandbox deployment")

## Scenario: CopilotKit UI request, identity via session not binding
Given an authenticated CopilotKit UI session with `org_id`/`bu_id` already established at login
When the `copilotkit` channel adapter normalizes the request
Then `org_id`/`bu_id` are taken directly from the session, not resolved via a binding-table lookup — this is the one channel where identity resolution genuinely differs (`docs/end_to_end_flow_example.md` step 1)

## Scenario: DM without a thread-specific binding
Given a direct message to the bot with no channel/thread-scoped binding matching it
When the adapter attempts to normalize it
Then intake FAILS — a bare account/DM fallback is never accepted, per the binding-specificity rule already required for both org/BU routing (`docs/HARNESS_DESIGN.md`) and session routing (`docs/session_memory_design.md`)

## Status
Design only. No channel adapter code exists in this repo.
