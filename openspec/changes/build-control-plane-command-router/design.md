# Design

## Decisions

The gateway owns command parsing, session validation, and a minimal immutable
principal projection (`issuer`, `subject`). Workflow handlers are injected by
the application composition root; a command string never maps to a module path
or model output. The router may run in the same process as workflows today and
be split later without changing the command contract.

`/login` is public. `/onboard-org`, `/join-org`, and `/provision` require a
validated session. Each target workflow independently loads its current
PostgreSQL authorization context; the router does not cache roles, memberships,
scopes, bindings, tokens, or credentials.

The organization-onboarding handler constructs the PostgreSQL repository and
deterministic LangGraph with the gateway-derived principal. Payload contains
only typed workflow input such as organization name and identity-boundary
reference; it cannot select the applicant.
