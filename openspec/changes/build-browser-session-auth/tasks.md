# Tasks

## 1. Session contracts and server-side state

- [x] 1.1 Add typed browser-session, signing-key-provider, session repository,
      and CSRF contracts. Ensure public workflow contracts contain neither raw
      JWTs nor cookies.
- [x] 1.2 Add in-memory test doubles that enforce short expiry, session/user
      matching, revocation, and CSRF-proof verification.
- [x] 1.3 Add PostgreSQL migration and repository operations for create,
      validate, revoke, expire, and CSRF-protect browser sessions. Persist only
      protected CSRF material and no signing key or plaintext session token.

## 2. Cookie issuance and validation

- [x] 2.1 Add a gateway session issuer that signs only `iss`, `sub`, `sid`,
      `aud`, `iat`, and `exp`, then emits it exclusively through an `HttpOnly`,
      `Secure`, `SameSite=Lax`, host-scoped cookie with bounded lifetime.
- [x] 2.2 Adapt successful passwordless confirmation to call the session issuer
      after atomic user verification; preserve scanner-safe link handling and
      never return the token to the browser body, URL, logs, or workflow state.
- [x] 2.3 Add gateway session validation that verifies signature, issuer,
      audience, issued-at/expiry, and live PostgreSQL session state before it
      derives `ValidatedPrincipal` for a protected route.

## 3. Browser request protection and lifecycle

- [x] 3.1 Add same-origin and per-session CSRF validation before each
      cookie-authenticated state-changing command is routed.
- [x] 3.2 Add logout/revocation handling that revokes the server-side session
      and clears the cookie. Reject expired, unknown, and revoked sessions.
- [x] 3.3 Define the deployment signing-key provider contract, current/previous
      verification-key rotation behavior, and non-production local-secret
      loading without committing a key.

## 4. Verification and boundaries

- [x] 4.1 Add focused unit tests proving the token contains exactly the
      permitted identity/session claims and never authorization, provider, or
      cloud data.
- [x] 4.2 Add gateway tests proving JavaScript-readable/browser-storage token
      delivery is absent; valid cookies work; malformed, expired, wrong-
      audience, revoked, and substituted-user tokens fail before routing.
- [x] 4.3 Add CSRF/origin and logout tests, including proof replay/mismatch and
      cross-site mutation rejection.
- [x] 4.4 Run focused registration, session, command-router, and PostgreSQL
      tests without a real email provider, IdP, cloud credential, or signing
      secret committed to the repository.
- [x] 4.5 Run `openspec validate build-browser-session-auth --strict` and
      record the verification command/results before marking the change ready.
