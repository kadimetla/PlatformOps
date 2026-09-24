# Tasks

## 1. Contracts and PostgreSQL persistence

- [ ] 1.1 Add typed membership, invitation, source, role-reference, and
      lifecycle contracts; test incomplete records and duplicates.
- [ ] 1.2 Add PostgreSQL migration and repository for memberships and
      single-use invitations; test active-organization and invitation checks.

## 2. Deterministic member-onboarding workflow

- [ ] 2.1 Add authenticated `/join-org` gateway routing to a deterministic
      LangGraph workflow; no LLM node or free-text membership mutation.
- [ ] 2.2 Add invitation-validation and membership-activation nodes; verify
      tokens and credentials are absent from graph state and diagnostics.
- [ ] 2.3 Test pending organization, expired/consumed invitation, duplicate
      relationship, revoked membership, and multi-organization membership.

## 3. Authorization handoff

- [ ] 3.1 Add active-membership lookup as deterministic input to later scope
      authorization; verify it creates no grant, binding, or cloud access.
- [ ] 3.2 Verify revoked membership denies a newly started provision request.

## 4. Verification

- [ ] 4.1 Run focused tests without live IdP, SCIM, cloud, model credential,
      or frontend.
- [ ] 4.2 Run `openspec validate build-organization-member-onboarding --strict`.
