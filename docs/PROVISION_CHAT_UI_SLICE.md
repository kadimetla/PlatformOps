## Status

Implementation slice started 2026-08-20. The local-dev bridge from the
browser chat to the existing non-mutating provision preflight is now
wired and covered by backend transport tests. It is not the final
multi-user scope selector, stack catalog UI, plan renderer, approval
gate, or executor.

## Goal

Allow the browser chat to exercise the existing provision intake path:

```text
user message in UI
  -> AG-UI /runs
  -> trusted local-dev ScopeHint
  -> PlatformOpsHarness.start_run
  -> intake intent = provision
  -> provision preflight
  -> ProvisionDraft result rendered in chat
```

This proves the UI can reach `resolve_scope -> select_profile ->
extract_profile_request` and return the typed provision draft without
cloud credentials or mutation.

## Implementation

The browser sends a target scope through AG-UI `forwardedProps`:

```json
{
  "scope": "aiq:it/invoices/dev"
}
```

The HTTP transport parses this into `ScopeHint` and passes it to
`PlatformOpsHarness.start_run(...)`.

For this slice, the floating chat panel exposes a compact target field
defaulting to:

```text
aiq:it/invoices/dev
```

That matches the current test fixture in `gateway/dispatcher.py`:

```text
KNOWN_WORKSPACES = [aiq:it/invoices/dev]
```

Implemented files:

- `transports/http.py` parses `forwardedProps.scope` or
  `forwardedProps.scopeHint` before opening the SSE stream, so malformed
  target scope returns a clean HTTP 400.
- `frontend/src/lib/agui.ts` sends `forwardedProps.scope` on new user
  turns.
- `frontend/src/FloatingSessionPanel.tsx` exposes a persisted target
  field defaulting to `aiq:it/invoices/dev`.
- `tests/transports/test_http.py` covers the happy path from browser
  scope to provision preflight and the malformed-scope 400 path.

## Test Message

With a session that has an execution grant for `aiq:it/invoices/dev`,
the UI can test:

```text
provision: deploy s3://releases/invoices-ui.tar.gz at invoices.dev.example.com
```

Expected result:

```text
Routed to provision
ready_to_route = true
profile_id = aws-static-web
application_request contains frontend_artifact_uri and frontend_hostname
```

## Boundaries

- No cloud calls.
- No Terraform/OpenTofu rendering.
- No approval or apply.
- No browser OIDC login.
- No final stack variant selector.
- No guest access-request flow.

The scope field is a local-dev stand-in for the future trusted UI scope
selector. Production must resolve visible scopes from the actor session
and registry, not let arbitrary browser text become authority.

## Next Steps

After this bridge works, implement the real provision planning slice:

```text
ProvisionDraft.ready
  -> load reviewed stack/profile topology
  -> validate topology
  -> bind workspace/request inputs
  -> produce non-mutating DeploymentPlan IR
```

That is the first real "provision a cloud stack for a project" plan
milestone.

## How this relates to the existing docs

`PROVISION_WORKFLOW.md` owns provision workflow design.
`PROVISION_IMPLEMENTATION_PLAN.md` owns the deeper provisioning slices.
`WEB_CHAT_APP.md` owns the browser chat transport. This document is the
thin bridge between the current UI and current provision preflight so
the behavior can be tested from chat.
