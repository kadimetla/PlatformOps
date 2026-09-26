# Tasks

## 1. Conversation contracts and persistence

- [ ] 1.1 Define strict conversation, message, title-source, archive, and safe
  list-projection schemas; verify authority-bearing fields are rejected.
- [ ] 1.2 Add PostgreSQL tables and owner-scoped repository operations; verify
  a user cannot read or alter another user's conversation or messages.

## 2. Conversation lifecycle

- [ ] 2.1 Add create, generated-title, rename, archive, list, and read
  boundaries; verify titles are never used as authorization or scope input.
- [ ] 2.2 Link safe workflow-run summaries by immutable IDs; verify raw
  checkpoint state and authorization data are absent.

## 3. Chat navigation

- [ ] 3.1 Add an A2UI/React conversation drawer with generated/user-edited
  titles, active state, archive view, and safe filters.
- [ ] 3.2 Verify no shared conversation visibility exists in v1 and run focused
  gateway, persistence, transport, and frontend tests.
- [ ] 3.3 Run `openspec validate build-chat-conversations --strict`.
