# Design

## Context

`build-org-onboarding` already owns the deterministic request, proof, review,
and activation lifecycle. Browser sessions already establish a minimal user
identity, while the existing reviewer authorizer decides who may review. See
the proposal and new capability specification for the behavioral boundary.

## Goals / Non-Goals

**Goals:**

- Provide an authenticated reviewer-facing request detail and review action.
- Reuse the existing server-side review graph and PostgreSQL records.
- Keep browser state non-authoritative and free of credentials/provider routing.

**Non-Goals:**

- This does not redesign organization claiming, identity proof, reviewer
  policy, tenant administration, provider connection, resource-scope
  bootstrap, or cloud execution.
- This does not make generic chat input an approval path.

## Decisions

### Browser is a projection and command client

The wizard reads a safe pending-request projection and invokes a narrow,
authenticated review command. Server code reloads the pending request and
proof, authorizes the reviewer, derives the digest, and performs activation.
The rejected alternative is sending full lifecycle state or a browser-derived
approval digest back to the server; that would let stale UI data become
authority.

### Review is a dedicated route, not a provision action

The wizard is routed independently from `/provision` and has no provider
fields. This keeps organization activation distinct from cloud setup and
ordinary provisioning.

### Safe projections are explicit

The API response is an allow-listed projection of request status, organization
name, identity-boundary reference, proof status, and lifecycle outcome. Raw
verification tokens, delivery URLs, session tokens, and credentials are never
rendered.

## Risks / Trade-offs

- [Risk] A stale wizard view is submitted after request activation → Mitigation:
  server reloads the pending record and retains exactly-once activation checks.
- [Risk] Frontend action data attempts to add authority → Mitigation: strict
  payload schema accepts only the action; browser identity is validated by the
  gateway and authorization is repeated server-side.

## Migration Plan

1. Add safe projection and authenticated review API contracts with fake-backed
   tests.
2. Build the browser wizard against those contracts and verify browser-session
   and reviewer denial paths.
3. Keep the existing server review command available until the wizard is
   proven; no data migration is required.
