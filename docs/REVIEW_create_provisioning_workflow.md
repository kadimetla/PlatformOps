# Code Review: `feature/create-provisioning-workflow`

## Overview
This branch introduces a massive set of capabilities centered around building the **deterministic control plane**, establishing secure **passwordless registration**, creating strict **organization onboarding workflows**, and introducing the **Resource Scope governance model**.

The overarching design principle successfully implemented here is **deny-by-default** with strictly audited, immutable state transitions.

## Key Subsystems & Implementations

### 1. Passwordless User Registration (`gateway/auth/registration.py`)
- **Token Security:** Employs industry-standard practices by never storing plain-text verification tokens. Instead, it generates a secure HMAC digest using `hashlib.sha256` and a configured `hmac_key`.
- **Identity Decoupling:** Elegantly separates `UserAccount` (PlatformOps identity) from `VerifiedEmailContact`. Emails are robustly canonicalized via IDNA (`.encode("idna")`), preventing spoofing or edge cases with internationalized domains.
- **Resilience & Privacy:** Rate limiters (`RegistrationRateLimiter`) are built-in, and delivery failures gracefully redact the sensitive tokens to prevent accidental log leakage (`redact_registration_secret`).

### 2. Organization Onboarding (`gateway/organization_onboarding.py`)
- **Explicit Lifecycle:** Organizations start as `OrganizationOnboardingRequest` in a `PENDING` state and require a separate, authenticated `OrganizationOnboardingApproval` to transition into an `ActiveOrganization`.
- **Deterministic Identity Verification:** The `IdentityBoundaryVerifier` requires verifiable proof (`IdentityBoundaryVerificationEvidence`) matching the requested domain/IdP before activation can occur. 
- **Immutable Proofs:** A digest (`onboarding_digest`) of the requested onboarding properties is sealed during approval. Any mutation to the request invalidates the approval, ensuring a high-trust workflow.

### 3. Resource Scope Governance (`gateway/resolved_resource_scope.py`)
- **Context Sealing:** The `ResolvedResourceScopeContext.seal()` method is a standout implementation. It takes the requested `ResourceScope`, the `ResourceScopeAuthorizationDecision`, and `ResourceScopeGovernanceDecision`, and effectively freezes them into a digest. 
- **Execution Safety:** This ensures that downstream provision execution operates *only* on the exact binding identities and versions approved at the moment of evaluation. If bindings drift, `requires_fresh_resolution` catches it.

## Architectural Alignment with `AGENTS.md`
The code heavily complies with the rules set in `AGENTS.md`:
- **Deterministic Checks:** No LLM judgment calls exist in the core domain logic; validation is explicitly handled by strictly configured Pydantic models.
- **Deny by Default:** Methods like `verify_pending` and `resolve_routable_organization` fail closed (returning `None` or raising structured errors rather than proceeding optimistically).
- **Timezone Awareness:** Enforces UTC timezone-aware dates everywhere (`_utc_now()`), rejecting naive datetime objects outright.

## Suggestions & Observations
1. **In-Memory to Persistence:** While `InMemoryUserRegistrationStore` and `InMemoryOrganizationOnboardingStore` are well-structured for testing/local-dev, ensure the Postgres implementations (e.g., `postgres.py` added in commit `91990cd3`) strictly enforce the same transactional locks as the `Lock()` used in memory.
2. **Token TTL:** In `RegistrationService`, the default `token_ttl_seconds` is 900 (15 minutes). Consider making this configurable via the environment if email delivery times fluctuate for specific organizations.
3. **Pydantic Validation:** The use of `@model_validator(mode="after")` to enforce cross-field invariants (like checking `consumed_at` vs `invalidated_at`) is very clean and readable.

## Summary
The branch effectively translates the spec designs into robust, production-ready Python models. The separation of concerns between storage, delivery, authorization, and execution is strictly maintained.
