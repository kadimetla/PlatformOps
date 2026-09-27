# build-provision-flow

Authenticated provision handoff, deterministic Resource Scope preflight, sealed
plan/policy approval, checkpointed reviewer separation, and an injected final
execution gate.

## Verification

Run the focused suite without cloud credentials, a live provider, an IdP, or
model credentials:

```sh
uv run pytest \
  tests/gateway/test_provision_handler.py \
  tests/gateway/test_provision_plan.py \
  tests/gateway/test_provision_execution.py \
  tests/gateway/test_resolved_resource_scope.py \
  tests/gateway/test_resource_scope_access.py \
  tests/gateway/test_resource_scope_bindings.py \
  tests/workflows/provision/test_prepare_request.py \
  tests/workflows/provision/test_resource_scope_preflight.py \
  tests/workflows/provision/test_approval_graph.py

openspec validate build-provision-flow --strict
git diff --check
```

The execution test uses an injected fake executor. No cloud adapter or
credential is provided by this change.
