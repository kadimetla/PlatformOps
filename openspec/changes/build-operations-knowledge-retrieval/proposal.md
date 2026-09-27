# Proposal

## Why

Operators need current, cited guidance in chat without allowing retrieved text
to grant permissions, approve work, or select cloud routing.

## What Changes

- Add a curated operations-knowledge catalog and advisory retrieval boundary.
- Add a separate architecture-review workflow for submitted diagrams and
  designs, producing findings rather than implementation or approval actions.

## Capabilities

### New Capabilities

- `operations-knowledge-retrieval`: cited advisory retrieval.
- `architecture-review`: deterministic and advisory architecture/diagram review.

## Impact

PostgreSQL metadata, object-backed source documents, a retrieval service, and
chat presentation only. Authorization, policy, provider binding, approval, and
execution remain owned by their existing deterministic boundaries.
