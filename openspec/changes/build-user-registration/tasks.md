# Tasks

## 1. User and verification-attempt contracts

- [x] 1.1 Add typed UserAccount, verified-email contact, and verification-attempt contracts with a PlatformOps issuer, generated stable subject, canonical email-domain handling, expiry, and consumption state; verify focused unit tests preserve local parts, canonicalize domains only, and reject invalid/incomplete records.
- [x] 1.2 Add an in-memory development/test persistence boundary that looks up a verified contact without using it as the user primary key and atomically creates or recovers one user account; verify tests create one active user for a first verification and recover the same subject for a returning verified email.
- [x] 1.3 Add protected verification-token storage using only an HMAC digest and attempt metadata, with invalidation of prior unconsumed attempts for the same canonical email; verify tests assert plaintext tokens and complete verification URLs are absent from stored records. Token/log redaction is verified by task 2.3.
- [x] 1.4 Add PostgreSQL migrations and repository operations for user accounts, verified-email contacts, and verification attempts; verify PostgreSQL integration tests enforce canonical-email uniqueness, invalidation of previous attempts, and atomic single-use consumption with create-or-recover user behavior.

## 2. Registration initiation and email delivery boundary

- [x] 2.1 Add a server-side registration initiation boundary that creates a cryptographically secure opaque verification token and calls an injectable email-delivery interface; verify fake-delivery tests receive a verification message without requiring a live provider.
- [x] 2.2 Return one generic verification-pending response for new and existing users and enforce server-side delivery/rate controls without disclosing which condition occurred; verify enumeration and rate-limit tests receive the identical public response shape.
- [x] 2.3 Add centralized redaction for token-bearing URLs and token fields at registration, delivery, and error/log boundaries; verify diagnostics tests cannot find a raw token or complete verification URL.

## 3. Scanner-safe verification and narrow session issuance

- [x] 3.1 Add a verification-intent endpoint or handler that validates an unexpired unused token without consuming it; verify a simulated link-scanner GET leaves the attempt usable.
- [x] 3.2 Add same-origin confirmation handling that atomically consumes a valid token and rejects expired, consumed, mismatched, or racing attempts; verify focused tests permit exactly one successful consumption and no second session.
- [x] 3.3 Issue the existing authenticated-session representation only after successful confirmation with the PlatformOps user subject and no organization, approval, execution, cloud, or provider-binding grants; verify session tests assert the active unassociated state.
- [x] 3.4 Add a deterministic no-LLM `workflows/login_registration` graph for
      `/login` initiation; keep raw tokens and confirmation outside graph state
      in the gateway security boundary.
- [x] 3.5 Add scanner-safe gateway confirmation handling: intent inspection
      leaves a link usable and same-origin confirmation issues at most one
      unassociated session without exposing the token to graph state.

## 4. Post-login organization-domain discovery

- [x] 4.1 Add deterministic lookup of an active organization’s verified canonical domain and return only a next-journey result; verify tests exclude pending/unverified domains and create no membership, tenant-admin, provider-binding, or cloud grant.
- [x] 4.2 Return personal-organization creation and business-claim request as the only unknown-domain journeys; verify unknown-domain tests do not infer organization ownership or a cloud provider.
- [ ] 4.3 Direct a matching organization member journey to its configured IdP boundary rather than treating the email-link session as corporate authentication; verify fake-configuration tests return the configured IdP journey and no membership resolution.

## 5. Verification and boundaries

- [ ] 5.1 Run focused registration, verification, session, and domain-discovery tests with fake delivery and no real model credentials or email provider; record the commands in developer documentation.
- [ ] 5.2 Verify this change does not implement personal-organization creation, business claims, membership/invites, SCIM, customer IdP setup, cloud-provider connection, password storage, or a frontend; record any newly required behavior as a separate OpenSpec change before coding it.
- [ ] 5.3 Run `openspec validate build-user-registration --strict` and update the change status only after all implementation tasks and their verifications are complete.
