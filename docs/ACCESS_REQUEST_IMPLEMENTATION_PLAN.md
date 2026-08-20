## Status

Implementation plan captured 2026-08-20. No code exists yet for
`access_request` intent routing, guest route policy, requestable-access
catalog, access-request workflow, midPoint backend, or status lookup.
The current harness dispatch path is still provision-specific:
`harness/core.py` builds `ProvisionInvocation` directly and calls
`ROUTE_REGISTRY["provision"]`. Generic route dispatch is therefore an
explicit prerequisite, not an assumed foundation.

This document breaks the guest/chat permission-request design into
buildable slices. `GUEST_ACCESS_REQUEST_CHAT.md` owns the product flow.
This document owns the implementation order and contracts.

## Goal

Enable a user who is authenticated but has no PlatformOps operational
grants to request project/workspace permissions from chat.

The MVP must:

- allow only a limited `access_request` route for authenticated guests;
- collect org/BU/project/workspace, role/capability, duration, and
  justification;
- resolve the request against reviewed requestable-access catalog data;
- avoid target/role enumeration leaks;
- create a governed request through a backend;
- return request id/status/next action;
- leave grant activation to normal login/session refresh.

The MVP must not:

- grant access directly from chat;
- let the model choose raw IdP group names or entitlement IDs;
- patch the current session with newly approved access;
- expose project/workspace inventory to guests;
- implement provisioning, inquiry, or approval bypass for guests.

## Workflow Set

The access-request feature needs these pieces:

```text
auth/session pipeline
  deterministic; builds ActorSession and identifies guest vs authorized

intake route update
  adds ACCESS_REQUEST first; ACCESS_REQUEST_STATUS lands with its
  own route/status workflow later

access_request workflow
  LangGraph preflight: collect fields, resolve requestable role,
  run checks, submit request

requestable access catalog
  deterministic policy data for requestable roles/capabilities

eligibility checks
  fail-closed checks for requester, target, role, duration, disclosure

access request backend
  adapter protocol; manual/no-op first, midPoint second

access_request_status workflow
  own-request status only

backend sync/reconciliation
  optional poll/webhook path for midPoint/internal backend state

evidence/audit store
  records request, backend refs, decisions, and status transitions
```

Internal approval and Authentik group mutation are needed only if
PlatformOps chooses the internal IGA backend. If midPoint is used,
midPoint owns approval, assignment implementation, expiry, revocation,
and access review.

## Slice 0 — Generic Dispatch and Actor Route Gate

The first slice is not `ACCESS_REQUEST`. The first slice is making the
existing dispatcher actually pluggable.

Current reality:

```text
intake classifies intent and route generically
  -> harness checks tenant policy
  -> harness always builds ProvisionInvocation
  -> harness always calls ROUTE_REGISTRY["provision"]
```

Target shape:

```text
intake classifies intent and resolves route
  -> tenant route gate
  -> actor route gate
  -> route registration builds the route-specific invocation
  -> route registration handler runs
```

Define a route registration contract:

```python
class RouteRegistration(BaseModel):
    route_id: str
    intent: Intent
    build_invocation: Callable[..., object]
    handler: Callable[..., Awaitable[object]]
    map_result_to_event: Callable[..., HITLEvent | PlatformOpsEvent]
```

Provision becomes one route registration:

```text
route_id: provision
intent: provision
build_invocation: ProvisionInvocation(raw_text, scope_hint)
handler: prepare_provision_request
```

Access request later becomes another:

```text
route_id: access_request
intent: access_request
build_invocation: AccessRequestInvocation(raw_text, actor_ref, scope_hint)
handler: prepare_access_request
```

Do not add dynamic import paths or model-selected handlers. The route
registry remains trusted code/config.

Add an explicit actor gate beside `check_tenant_policy`:

```python
class ActorAccessState(str, Enum):
    ANONYMOUS = "anonymous"
    AUTHENTICATED_GUEST = "authenticated_guest"
    AUTHORIZED = "authorized"


def check_actor_route_access(
    actor: ActorSession | None,
    intent: Intent,
    scope_hint: ScopeHint | None,
) -> ActorRouteDecision:
    ...
```

Evaluation rule:

- anonymous means no authenticated actor session;
- authenticated guest means authenticated actor, but no matching
  execution grant for the requested scope;
- authorized means authenticated actor with a matching grant for the
  requested scope or a route that does not require one.

When a request names a project/workspace, guest-vs-authorized is
scope-specific. A user may be authorized for `aiq:it/invoices/dev` and
still be a guest for `aiq:it/billing/prod`. Do not classify the whole
actor as globally authorized just because any grant exists.

Route policy after Slice 0:

```text
provision
  requires authenticated actor and target-scope authorization

access_request
  not added yet

compliance_check
  preserves existing resolved-route/no-handler behavior until its real
  handler exists
```

Tests:

- existing provision route still reaches `prepare_provision_request`;
- compliance_check route still resolves without being invoked;
- no route can be invoked by a model-emitted module path;
- an unknown route id fails closed;
- actor gate distinguishes anonymous, authenticated guest for the
  requested scope, and authorized for the requested scope;
- the harness dispatches through the route registration instead of
  hardcoding `_dispatch_provision`.

## Slice 1 — Access Request Intent and Route Gate

Extend the real `Intent` enum with only the route that becomes
reachable in this slice. Do not replace the enum and do not add
reserved values.

```python
class Intent(str, Enum):
    PROVISION = "provision"
    INQUIRY = "inquiry"
    COMPLIANCE_CHECK = "compliance_check"
    ACCESS_REQUEST = "access_request"
```

`ACCESS_REQUEST_STATUS` is intentionally not added here. The enum's
real docstring forbids reserved, unreachable values. Add
`ACCESS_REQUEST_STATUS` in Slice 6, when its handler and route gate
land.

Route behavior:

```text
anonymous
  -> login / account request only

authenticated guest
  -> access_request
  -> access_request_status for own requests

authorized user
  -> provision / inquiry / access_request according to policy
```

Implementation notes:

- Keep auth outside LangGraph.
- Do not treat "no execution grants" as unauthenticated.
- Use `check_actor_route_access` from Slice 0. Guests may route only to
  `access_request`; provision/inquiry remain scope-authorized routes.
- Return uniform denial for unsupported operational routes.

Tests:

- anonymous cannot route to `access_request` without login;
- authenticated guest can route to `access_request`;
- authenticated guest cannot route to `provision`;
- authorized user keeps existing route behavior.

## Slice 2 — Access Request Schemas

Add shared schemas, likely under `workflows/access_request/schemas.py`
or `gateway/access_request.py` if needed across gateway/backend.

Initial shape:

```python
class AccessRequestStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IMPLEMENTED = "implemented"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


class AccessRequestDraft(BaseModel):
    requester: ActorRef
    target_scope: Scope | None = None
    requested_role: str | None = None
    requested_capability: Capability | None = None
    duration: str | None = None
    justification: str | None = None
    clarification_questions: list[ClarificationQuestion] = []
    unavailable_reason: str | None = None


class AccessRequestRecord(BaseModel):
    request_id: str
    requester: ActorRef
    target_scope: Scope
    requested_role: str
    requested_capability: Capability
    duration: str
    justification: str
    backend: str
    external_request_ref: str | None
    status: AccessRequestStatus
```

Keep `ActorSession` out of persisted request records. Store `ActorRef`
and evidence fields, not tokens or grants.

Tests:

- records require requester, target scope, role, duration,
  justification;
- invalid empty role/justification fails;
- no token/session secret fields exist.

## Slice 3 — Requestable Access Catalog

Add reviewed catalog data for requestable roles. Start in versioned
YAML or Python fixture data; keep it deterministic.

Example:

```yaml
items:
  - item_id: platformops-invoices-dev-operator
    display_name: Invoices Dev Operator
    scope:
      org: aiq
      bu: it
      project: invoices
      workspace: dev
    capability: apply_limited
    backend: midpoint
    backend_ref: midpoint-role-oid-123
    max_duration: 30d
    disclosure: named_target_only
```

Rules:

- Catalog lookup accepts a named target and requested role/capability.
- Guests cannot list all catalog items.
- Unknown and unauthorized target/role outcomes collapse to a uniform
  public response.
- Raw backend refs are not exposed to the model.

Tests:

- exact known item resolves;
- unknown item fails closed;
- guest list operation is unavailable;
- max duration is enforced.

## Slice 4 — Access Request LangGraph Preflight

Create `workflows/access_request/`.

Initial graph:

```text
resolve_requester
  -> collect_target_scope
  -> collect_requested_access
  -> collect_duration_justification
  -> resolve_requestable_item
  -> eligibility_checks
  -> create_access_request
  -> END
```

LLM involvement:

- may extract target, role wording, duration, justification;
- may ask clarification;
- may suggest role wording;
- may not choose backend refs, IdP groups, approval policy, or grant
  outcome.

Deterministic nodes:

- requester classification;
- target parsing;
- catalog lookup;
- eligibility checks;
- backend submission.

Tests:

- complete request submits through fake backend;
- missing duration asks clarification;
- missing justification asks clarification;
- malformed tool output returns clarification, not exception;
- unknown target returns uniform unavailable response;
- model-supplied group/backend ref is ignored.

## Slice 5 — Manual Backend

Add a first backend that records the request locally but mutates
nothing.

Protocol:

```python
class AccessRequestBackend(Protocol):
    def create_request(self, request: AccessRequestRecord) -> BackendResult: ...
    def get_status(self, request_id: str, requester: ActorRef) -> BackendStatus: ...
```

Manual backend result:

```yaml
backend: manual
external_request_ref: null
status: submitted
next_action: platform admin must process this request manually
```

This lets the chat flow become real before midPoint integration.

Tests:

- create request records evidence;
- status lookup limited to requester;
- no IdP/cloud mutation call exists.

## Slice 6 — Status Lookup

Add the second intent only when this slice is implemented:

```python
class Intent(str, Enum):
    ...
    ACCESS_REQUEST_STATUS = "access_request_status"
```

Add `access_request_status`.

Rules:

- requester can see their own requests;
- approver/admin status views are separate future work;
- unknown request id and unauthorized request id should use the same
  public response for non-admin users.

Tests:

- requester sees own submitted request;
- another user cannot see it;
- unknown and unauthorized responses are uniform.

## Slice 7 — midPoint Backend Spike

Add a backend behind the same protocol.

Two MVP modes:

```text
deep_link
  resolve role, return midPoint URL/context, user finishes in midPoint

api_create
  call midPoint REST API to create access request, return external ref
```

Prefer deep link first if the REST request shape or authentication
model is not yet verified enough. Prefer API create once the connector
contract is validated.

Needed config:

```yaml
midpoint:
  base_url: https://midpoint.example.com
  mode: deep_link | api_create
  role_ref_mapping_source: requestable_access_catalog
```

Security rules:

- no user-supplied midPoint role OID;
- no model-supplied URL;
- service credentials are not in graph state;
- backend call logs redact credentials and sensitive payloads.

Tests:

- fake midPoint client receives canonical request;
- backend ref comes from catalog;
- failed midPoint call returns retryable/unavailable result;
- no credentials are serialized in workflow state.

## Pluggable IGA Backend Contract

The backend contract should be narrow enough that an organization can
bring its own IGA or service-management tool without changing the chat
workflow.

Supported backend families:

```text
manual
platformops_internal
midpoint
saviynt
servicenow
jira
custom_http
```

The chat workflow always emits the same canonical request. The backend
adapter translates it:

```python
class AccessRequestBackend(Protocol):
    backend_id: str

    def create_request(
        self,
        request: AccessRequestRecord,
        catalog_item: RequestableAccessItem,
    ) -> BackendResult:
        ...

    def get_status(
        self,
        request_id: str,
        requester: ActorRef,
    ) -> BackendStatus:
        ...

    def cancel_request(
        self,
        request_id: str,
        requester: ActorRef,
    ) -> BackendStatus:
        ...
```

Org/BU policy chooses the backend:

```yaml
org_bu: aiq:it
access_request_backend:
  type: midpoint
  config_ref: midpoint_aiq_it
  mode: api_create
```

Catalog items carry backend references:

```yaml
item_id: platformops-invoices-dev-operator
backend: midpoint
backend_ref: midpoint-role-oid-123
```

For another org:

```yaml
item_id: platformops-claims-dev-operator
backend: servicenow
backend_ref: catalog-item-sys-id
```

The LLM never selects `backend`, `backend_ref`, URLs, credentials,
group names, or entitlement IDs. Those are reviewed catalog/config
values.

Backend invariants:

- backend plugins create governed requests; they do not bypass route
  policy or eligibility checks;
- only the explicitly selected internal backend may mutate Authentik
  groups, and only after its approval gate;
- external IGA backends own approval and entitlement implementation;
- PlatformOps waits for login/session refresh before treating access as
  active;
- every backend result is normalized into PlatformOps evidence.

## Slice 8 — Backend Sync or Callback

Once midPoint creates real requests, PlatformOps needs status
freshness.

Options:

```text
polling
  scheduled job reads midPoint request state by external_request_ref

callback/webhook
  midPoint calls PlatformOps status endpoint if supported/configured

on-demand read
  status route fetches current state live from midPoint
```

MVP can use on-demand read or polling. Callback can come later.

Status mapping:

```text
midPoint requested/open       -> submitted / pending_approval
midPoint approved             -> approved
midPoint assignment complete  -> implemented
midPoint rejected             -> rejected
midPoint expired/revoked      -> expired / cancelled
```

PlatformOps must still not grant access from status alone. The user
refreshes/relogs in and normal discovery must see the resulting grant.

## Slice 9 — Internal IGA Backend Only If Needed

Build this only if midPoint/OpenIAM/Saviynt-style integration is
rejected or deferred.

Graph:

```text
create_request
  -> approval_gate
  -> apply_idp_group_change
  -> evidence
  -> expiry_reconciliation
```

Extra responsibilities PlatformOps would own:

- approver routing;
- self-approval prevention;
- duplicate approval prevention;
- time-bound access;
- Authentik group mutation;
- expiry/revocation job;
- reconciliation;
- access review/certification if required.

This is intentionally a later option, not the default first build.

## Slice 10 — Evidence and Reporting Foundation

Record:

- request id;
- requester;
- target scope;
- requested role and capability;
- duration and justification;
- catalog item id and version;
- backend and external request ref;
- status transitions;
- approver references if known;
- timestamps;
- final implementation/rejection reason safe to disclose.

Reporting is not required for the first chat flow, but evidence must be
captured from the start so later reporting and audits have source data.

## First Milestone

The first useful milestone is:

```text
authenticated guest
  -> chat says "I need deploy access to invoices dev"
  -> workflow collects duration and justification
  -> deterministic catalog resolves Invoices Dev Operator
  -> manual backend records request
  -> user receives request id and next action
  -> provision remains denied until grants exist in a future session
```

This proves the route boundary, guest UX, non-enumeration behavior,
schemas, catalog lookup, and request evidence without taking on
midPoint or IdP mutation risk immediately.

## How this relates to the existing docs

`GUEST_ACCESS_REQUEST_CHAT.md` owns the product flow. `OPS_IAM_FLOW.md`
owns the larger IAM lifecycle. `MIDPOINT_IGA_DEEP_DIVE.md` owns the
midPoint user/request path. This document turns those decisions into an
implementation sequence.
