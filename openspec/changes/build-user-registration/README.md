# build-user-registration

Passwordless user registration and post-login organization-domain discovery, preceding business organization claiming and cloud-provider connection.

## Verification

Run the deterministic registration, scanner-safe confirmation, unassociated
browser-session, and domain-discovery suite without a live email provider,
IdP, model credential, cloud provider, or frontend:

```sh
uv run pytest \
  tests/gateway/auth/test_registration.py \
  tests/gateway/auth/test_domain_discovery.py \
  tests/gateway/test_login_confirmation_handler.py \
  tests/gateway/test_browser_sessions.py \
  tests/workflows/login_registration/test_graph.py
```

Run persistence coverage only against the explicitly configured local
PlatformOps PostgreSQL database:

```sh
PLATFORMOPS_DATABASE_URL='postgresql://platformops:platformops-local-test@localhost:5432/platformops_dev' \
  uv run pytest \
    tests/gateway/auth/test_postgres_registration.py \
    tests/gateway/test_postgres_browser_sessions.py

openspec validate build-user-registration --strict
git diff --check
```

## Explicit boundaries

This change registers and verifies a PlatformOps user and returns only the
next organization journey. It does not create personal organizations, claim
business organizations, create memberships or invitations, synchronize SCIM,
configure a customer IdP, connect a cloud provider, store passwords, or build
a frontend. Each is a separate OpenSpec change.
