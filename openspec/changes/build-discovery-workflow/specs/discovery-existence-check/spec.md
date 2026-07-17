## ADDED Requirements

### Requirement: `discover_request()` answers existence against stored inventory only
The system SHALL provide `discover_request(query: DiscoveryQuery, store: InfraInventoryStore) -> DiscoveryResult`
querying `InfraInventoryStore.lookup()` only, and SHALL NOT call any
live cloud provider API.

#### Scenario: A previously discovered resource is found
- **WHEN** `InfraInventoryStore` has a record matching `query.org_id`,
  `query.bu_id`, the resolved `resource_type`, and `query.resource_identifier`
- **THEN** `discover_request()` returns a `DiscoveryResult` with
  `found=True` and `record` set to that record

#### Scenario: A resource with no matching record is not found
- **WHEN** no record in `InfraInventoryStore` matches the resolved
  lookup key
- **THEN** `discover_request()` returns `found=False` and `record=None`,
  without raising

#### Scenario: A record scoped to a different BU is invisible
- **WHEN** `InfraInventoryStore` holds a record for the same
  `resource_type`/`resource_identifier` but a different `bu_id` than
  `query.bu_id`
- **THEN** `discover_request()` returns `found=False` — a query never
  sees another BU's inventory, matching `InfraInventoryStore.lookup()`'s
  own org/BU-scoped primary key

### Requirement: `resource_type` is resolved via bounded classification, never free-form
The system SHALL resolve `DiscoveryQuery.resource_type` either directly
(already given) or, when only `resource_type_description` free text is
given, via a `select_resource_type` tool call forced to choose from
`WorkspaceBundle.allowed_resource_types` or return a clarifying
question. The system SHALL NOT accept an LLM-generated resource type
string that isn't a member of that candidate list.

#### Scenario: An already-known resource type skips classification
- **WHEN** `DiscoveryQuery.resource_type` is already set (e.g. supplied
  by a structured UI action or a text-prefix-routed request)
- **THEN** `discover_request()` performs no LLM call and proceeds
  directly to the existence check

#### Scenario: A free-text description resolves to one allowed type
- **WHEN** `DiscoveryQuery.resource_type` is `None` and
  `resource_type_description` is a free-text phrase (e.g. "S3 bucket")
  that maps unambiguously onto one entry in
  `WorkspaceBundle.allowed_resource_types`
- **THEN** `classify_resource_type` resolves it to that entry and the
  existence check proceeds using it

#### Scenario: An unresolvable description produces a clarifying question, not a guess
- **WHEN** `resource_type_description` doesn't map clearly onto any
  entry in `WorkspaceBundle.allowed_resource_types`, or the candidate
  list is empty
- **THEN** `discover_request()` returns a `DiscoveryResult` with
  `clarifying_question` set and no existence check is performed

### Requirement: The result shows interpretation and answer together, with no confirmation gate
The system SHALL return `DiscoveryResult.resource_type` populated with
the resolved type (whether given directly or classified) alongside
`found`/`record` in the same response, and SHALL NOT pause or wait for
explicit user confirmation before returning an existence-check result —
discovery is read-only and reversible, unlike drafting's mutation path.

#### Scenario: A classified request shows what was understood alongside the answer
- **WHEN** `resource_type` was resolved from a free-text description
- **THEN** the returned `DiscoveryResult.resource_type` reflects the
  resolved value so a caller can display "interpreted as X" together
  with `found`/`record`, in one response, with no separate approval
  step

### Requirement: `org_id`/`bu_id` are accepted as given, never parsed from text by this workflow
The system SHALL treat `DiscoveryQuery.org_id` and `DiscoveryQuery.bu_id`
as already-resolved inputs and SHALL NOT attempt to extract or infer
either field from `resource_type_description` or any other free-text
field.

#### Scenario: Org/BU scoping comes from the query object, not text parsing
- **WHEN** `discover_request()` is called with a `DiscoveryQuery` whose
  `org_id`/`bu_id` were set by the caller from an authenticated session
- **THEN** the existence check uses those values directly, and no node
  in `workflows/discovery/` inspects free text for org/BU identifiers
