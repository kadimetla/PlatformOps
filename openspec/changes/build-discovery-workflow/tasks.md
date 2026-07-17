## 1. State and models

- [x] 1.1 Create `workflows/discovery/__init__.py`. **Done.**
- [x] 1.2 Create `workflows/discovery/state.py`: `DiscoveryQuery`,
      `DiscoveryResult` (Pydantic models, per `design.md`'s Decisions),
      and `DiscoveryState` (TypedDict). **Done, with one deviation from
      this task's original text**: `store` is NOT a `DiscoveryState`
      field — injected via `functools.partial` into `existence_check`
      instead, mirroring `workflows/drafting/graph.py`'s own
      `mcp_client` injection (avoids putting a non-serializable object
      in graph state). `DiscoveryState` ended up
      `{query, bundle, resolved_resource_type, clarifying_question, result}`
      — `bundle` added because `classify_resource_type` needs
      `WorkspaceBundle.allowed_resource_types` as its candidate list.

## 2. Bounded resource-type classification

- [x] 2.1 Add a `select_resource_type` bound tool. **Done, with one
      deviation**: enforcement is prompt-based (candidates listed in
      the system message, "call exactly once" instruction), not an
      API-level forced `tool_choice` — matches
      `record_security_decision`'s own existing convention, which also
      doesn't force `tool_choice`; `ChatLiteLLM`'s forced-tool-choice
      behavior isn't verified against the installed version, so this
      avoids relying on an unverified API shape.
- [x] 2.2 Implement `classify_resource_type` node in `workflows/discovery/nodes.py`.
      **Done** — skips the model call entirely when
      `DiscoveryQuery.resource_type` is already set.
- [x] 2.3 Handle an empty candidate list as an automatic
      clarifying-question case. **Done**, checked before the model call.

## 3. Existence check

- [x] 3.1 Implement `existence_check` node in `workflows/discovery/nodes.py`.
      **Done.**
- [x] 3.2 Ensure a not-found lookup returns `found=False` cleanly, no
      exception. **Done** — `InfraInventoryStore.lookup()` already
      returns `None` on no match, not an exception.

## 4. Graph and entry function

- [x] 4.1 Create `workflows/discovery/graph.py`: `build_discovery_graph()`
      wiring `classify_resource_type -> existence_check` as a fixed
      two-node sequence (no router, per design.md). **Done.**
- [x] 4.2 Create `workflows/discovery/discover_request.py`:
      `discover_request(query, bundle, store) -> DiscoveryResult`.
      **Done, with one signature deviation**: takes `bundle` as a third
      parameter (not just `query`/`store`) — needed to reach
      `classify_resource_type`'s candidate list, same reason `store`
      moved out of `DiscoveryState` above.

## 5. Tests

- [x] 5.1 Write `tests/test_workflows_discovery.py` with fixture rows
      written directly to `InfraInventoryStore`. **Done**, 7 tests.
- [x] 5.2 Cover: found; not-found; wrong-BU-scoped-out. **Done.**
- [x] 5.3 Cover: `resource_type` already given skips classification.
      **Done** — `get_model` monkeypatched to raise if called.
- [x] 5.4 Cover: free-text `resource_type_description` resolves via
      `select_resource_type`. **Done**, scripted fake chat model.
- [x] 5.5 Cover: unresolvable description (or empty candidate list)
      returns a `clarifying_question`, no existence check performed.
      **Done**, two separate tests (unresolvable description; empty
      candidate list also asserts no model call).
- [x] 5.6 Cover: `DiscoveryResult.resource_type` is populated on the
      classified path. **Done.**

## 6. Verification

- [x] 6.1 Run `uv run python -m pytest tests/ -q` to confirm no
      regressions. **Done** — 54 passed (47 pre-existing + 7 new), no
      failures, no regressions to `workflows/drafting/` or
      `gateway/infra_inventory_store.py`.
- [x] 6.2 Run `openspec validate build-discovery-workflow --type change`
      to confirm the change now passes. **Done** — see below.
