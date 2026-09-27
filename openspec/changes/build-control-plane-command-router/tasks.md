# Tasks

## 1. Router contracts

- [x] 1.1 Add explicit command allow-list and injected handler dispatch tests.
- [x] 1.2 Add validated issuer/subject principal projection and reject
      caller-supplied principal substitution.

## 2. Organization-onboarding integration

- [x] 2.1 Add composition root wiring `/onboard-org` to the PostgreSQL-backed
      deterministic organization-onboarding graph.
- [x] 2.2 Add end-to-end tests proving route → graph → PostgreSQL lifecycle
      and no provider/cloud data from payload.

## 3. Verification

- [x] 3.1 Run focused router, graph, and PostgreSQL tests.
- [x] 3.2 Run `openspec validate build-control-plane-command-router --strict`.
