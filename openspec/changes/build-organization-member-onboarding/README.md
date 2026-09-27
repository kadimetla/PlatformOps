# build-organization-member-onboarding

Deterministic onboarding of one registered PlatformOps user into one active
organization. A user can hold separate memberships in multiple organizations.

## Verification

Run deterministic membership, `/join-org`, and provision-revocation coverage
without a live IdP, SCIM adapter, cloud provider, model credential, or frontend:

```sh
uv run pytest \
  tests/gateway/test_organization_membership.py \
  tests/workflows/organization_member_onboarding/test_graph.py \
  tests/workflows/provision/test_resource_scope_preflight.py
```

Run PostgreSQL persistence coverage only against the explicitly configured
local PlatformOps database:

```sh
PLATFORMOPS_DATABASE_URL='postgresql://platformops:platformops-local-test@localhost:5432/platformops_dev' \
  uv run pytest tests/gateway/test_postgres_organization_membership.py

openspec validate build-organization-member-onboarding --strict
git diff --check
```
