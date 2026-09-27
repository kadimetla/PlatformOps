# Tasks

## 1. Catalog and ingestion

- [ ] 1.1 Define strict source, version, classification, lifecycle, and citation schemas.
- [ ] 1.2 Add PostgreSQL metadata migrations and object-storage source interface.
- [ ] 1.3 Implement curator-only ingestion, validation, expiry, and revocation.

## 2. Advisory retrieval

- [ ] 2.1 Implement authorization-filtered keyword retrieval with citations.
- [ ] 2.2 Add embeddings/vector retrieval only after keyword baseline evaluation.
- [ ] 2.3 Add chat presentation that labels results as guidance and preserves citations.

## 3. Architecture review workflow

- [ ] 3.1 Define submitted-diagram/spec and non-mutating finding contracts.
- [ ] 3.2 Reuse deterministic reference-architecture/diagram checks.
- [ ] 3.3 Add optional advisory retrieval and reviewer-Inbox integration without approval authority.
- [ ] 3.4 Add tests proving no retrieval or review result changes authorization, routing, or execution.

## 4. Verification

- [ ] 4.1 Run focused tests, security review, and `openspec validate build-operations-knowledge-retrieval --strict`.
