# build-resource-scope-bootstrap

Durable PlatformOps Resource Scope hierarchy, deny-by-default scope access,
registry-controlled Cloud Resource Container bindings, and non-mutating
provision preflight.

## Verification

Run the deterministic unit suite without a database, cloud credential, model,
IdP, or network service:

```sh
uv run pytest \
  tests/gateway/test_resource_scope_registry.py \
  tests/gateway/test_resource_scope_access.py \
  tests/gateway/test_resource_scope_bindings.py \
  tests/gateway/test_resolved_resource_scope.py \
  tests/gateway/test_resource_scope_legacy.py \
  tests/workflows/provision/test_resource_scope_preflight.py
```

Run the persistence coverage only against the explicitly configured local
PlatformOps PostgreSQL database:

```sh
PLATFORMOPS_DATABASE_URL='postgresql://platformops:platformops-local-test@localhost:5432/platformops_dev' \
  uv run pytest \
    tests/gateway/test_postgres_resource_scope_registry.py \
    tests/gateway/test_postgres_resource_scope_bindings.py
```

Then validate the OpenSpec change and whitespace:

```sh
openspec validate build-resource-scope-bootstrap --strict
git diff --check
```

The tests use in-memory or local PostgreSQL registries and fake principals.
They do not call a cloud provider, an IdP, an LLM, or a live email service.

## Explicit boundaries

This change implements logical Resource Scope registration, authorization,
binding selection, and a non-mutating provision preflight only. It does not
implement user registration, organization claiming, a frontend, cloud inquiry,
attaching an existing Cloud Resource Container, or creating a provider
container. Those workflows remain separately authorized changes. An existing
organization Provider Service connection is not a scope binding and cannot
route this preflight without one.
