# Flow Step 2: Binding & Context Resolution

## Owning code
`gateway/config_engine.py` — `ConfigLoader.load_and_validate()`.

## Input contract
A `RequestEnvelope`'s channel-match fields (`channel`, plus
channel-specific match criteria like `workspace_id`/`channel_id`), and
the loaded `config/bindings.yaml` + `config/workspace_bundles/*.yaml`.

## Output contract
Resolved `org_id`, `bu_id`, `agent_id`, and a `WorkspaceBundle`
(`gateway/schemas.py:25`) — or a fail-closed error if resolution can't
complete.

## Scenarios

## Scenario: A binding resolves to org, BU, agent, and bundle
Given `config/bindings.yaml`'s entry for `channel: slack, workspace_id: T123, channel_id: C-platform-payments`
When the config loader resolves it
Then `org_id="acme"`, `bu_id="payments"`, `agent_id="acme-payments"`, `workspace_bundle_ref="acme-payments"` (`config/bindings.yaml:5-12`)

## Scenario: A binding references a missing workspace bundle
Given a binding whose `workspace_bundle_ref` does not match any loaded `WorkspaceBundle.bundle_id`
When `_validate_referential_integrity()` runs
Then config loading FAILS with a `ValueError` naming the missing bundle — fails closed, no partial/default config is promoted (`gateway/config_engine.py:51-58`)

## Scenario: One agent_id bound to two different BUs
Given two bindings with the same `agent_id` but different `(org_id, bu_id)` pairs
When `_validate_uniqueness()` runs
Then config loading FAILS — `agent_id` must map to exactly one BU, never shared, since OpenClaw-style isolation depends on this (`gateway/config_engine.py:60-75`)

## Scenario: One agent_id reachable via two channels — allowed
Given two bindings with the same `agent_id` and the same `(org_id, bu_id)` pair, but different channels (e.g. Slack and a GitHub webhook)
When `_validate_uniqueness()` runs
Then config loading PASSES — one BU reachable via multiple channels is explicitly fine (`gateway/config_engine.py:61-64`'s docstring)

## Status
**Real, tested.** `gateway/config_engine.py` implements exactly this;
see `tests/test_gateway.py` for proof. This is one of the two most-built
steps in the whole flow, alongside Step 7.
