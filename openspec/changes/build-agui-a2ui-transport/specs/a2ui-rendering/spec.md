## ADDED Requirements

### Requirement: A2UI messages carry the verified v0.9 wire envelope
The system SHALL produce A2UI messages as `{"version": "v0.9",
"createSurface": {...}}` or `{"version": "v0.9", "updateComponents":
{...}}` -- a sibling `version` field with the message kind as a key --
not a `{"type": "createSurface", ...}` flat shape. This SHALL match the
real `@a2ui/web_core` package's `CreateSurfaceMessageSchema`/
`UpdateComponentsMessageSchema` exactly.

#### Scenario: createSurface envelope shape
- **WHEN** `hitl_event_to_a2ui_messages` or
  `platformops_event_to_a2ui_messages` produces its first message
- **THEN** the message is `{"version": "v0.9", "createSurface":
  {"surfaceId": <event.event_id>, "catalogId": <basic catalog URL>}}`

### Requirement: Components compose via id references, not inline nesting
The system SHALL emit a flat list of sibling components under
`updateComponents.components`, with a root `Column` component
referencing its children by `id` string in a `children` array -- never
nesting child component objects inline inside a parent.

#### Scenario: Root Column references children by id
- **WHEN** any A2UI message pair is produced
- **THEN** `updateComponents.components` contains a `{"id": "root",
  "component": "Column", "children": [...]}` entry whose `children`
  values are `id`s of other entries in the same list

### Requirement: Clarification renders one Button per choice via a label Text
**Corrected 2026-08-07 (review pass)**: originally this requirement also
covered `APPROVAL_REQUIRED`'s verdict choices; corrected below to
`CLARIFICATION_REQUIRED` only -- `harness/core.py` has no
`resume_approval` path, so an approval Button would be an affordance the
system can never honor (see the new "Approval events render message-only"
requirement below and `design.md`'s dated correction).

The system SHALL render each `ClarificationQuestion` choice as a
`Button` component whose `child` field references a sibling `Text`
component's `id` for the button's label -- `Button` SHALL NOT carry a
`text` property directly, matching the real `ButtonApi` schema (`child:
string`, no `text` field).

#### Scenario: Button references its label via child, not text
- **WHEN** `hitl_event_to_a2ui_messages` renders a `CLARIFICATION_REQUIRED`
  choice
- **THEN** the `Button` component has a `child` field naming another
  component's `id`, and that referenced component is a `Text` whose
  `text` equals the choice value; the `Button` component itself has no
  `text` key

### Requirement: Approval events render message-only, no buttons
**Added 2026-08-07 (review pass)**. The system SHALL NOT render any
`Button` component for a `HITLEvent` whose `kind` is
`HITLEventKind.APPROVAL_REQUIRED` -- only the message `Text`. No resume
path for an approval verdict exists yet (`harness/core.py` has no
`resume_approval`), so rendering a clickable verdict button would present
an action the system cannot complete.

#### Scenario: Approval renders no Button components
- **WHEN** `hitl_event_to_a2ui_messages` renders an event with
  `kind == HITLEventKind.APPROVAL_REQUIRED`
- **THEN** `updateComponents.components` contains no component with
  `"component": "Button"`, and the root `Column`'s `children` is exactly
  `["message"]`

### Requirement: Button actions report via the nested event shape
The system SHALL set each `Button`'s `action` field to
`{"event": {"name": <string>, "context": {<field>: <choice>}}}` -- not a
bare `{"name": ..., "context": ...}` -- matching the real `ButtonApi`
schema's `action.event.{name,context}` shape. `name` SHALL equal the
surface's `id` (the wrapped `HITLEvent`'s `event_id`, which is also the
AG-UI `Interrupt.id` per `interaction/agui.py`), so a client can resolve
which interrupt an action addresses without a separate id-mapping table.

#### Scenario: Action name equals the interrupt id
- **WHEN** `hitl_event_to_a2ui_messages(event)` renders a choice Button
- **THEN** `button["action"]["event"]["name"] == event.event_id`

### Requirement: Route-resolved and unsupported outcomes render as Text fields
**Corrected 2026-08-07 (review pass)**: originally this iterated
`event.payload.items()` directly -- any key present in the payload
would render. Corrected to an explicit allow-list
(`_ROUTE_RESULT_FIELDS`) so a future payload key (evidence, IAM detail,
anything else) cannot reach the browser without a deliberate code change
to add it to that list.

The system SHALL render a `PlatformOpsEvent`'s payload as a `Column` of
`Text` components, one per non-`None` field from a fixed, explicit field
list (`intent`, `route`, `ready_to_route`, `mutation_requested`,
`approval_required`, `unsupported_reason`), formatted as `"<key>:
<value>"`. Fields whose value is `None` (e.g. `route` on an unsupported
intent, or `unsupported_reason` on a resolved route) SHALL be omitted
entirely, not rendered as `"<key>: None"`. Any payload key outside that
fixed list SHALL NOT render, regardless of its value.

#### Scenario: A payload key outside the fixed list never renders
- **WHEN** `event.payload` contains a key not in `_ROUTE_RESULT_FIELDS`
- **THEN** no rendered `Text` component's `text` mentions that key or
  its value

#### Scenario: Resolved route omits unsupported_reason
- **WHEN** `platformops_event_to_a2ui_messages` renders a `compliance_check`
  route-resolved event (`unsupported_reason is None`)
- **THEN** no `Text` component's `text` starts with `"unsupported_reason:"`

#### Scenario: Unsupported intent omits route
- **WHEN** `platformops_event_to_a2ui_messages` renders a `provision`
  event (`route is None`, `unsupported_reason` set)
- **THEN** no `Text` component's `text` starts with `"route:"`, and one
  `Text` component's `text` equals `"unsupported_reason: <the reason>"`

### Requirement: A2UI rendering builds on the existing AG-UI interrupt mapping
The system SHALL derive clarification/approval message text and choice
enums by calling `interaction/agui.py`'s `hitl_event_to_interrupt`
internally, rather than re-deriving them from `IntakeDecision`/
`ApprovalRequest` a second time.

#### Scenario: Message text matches the AG-UI interrupt's message
- **WHEN** `hitl_event_to_a2ui_messages(event)` is called
- **THEN** the rendered `Text` message component's `text` equals
  `hitl_event_to_interrupt(event)["message"]`

### Requirement: A non-interrupt run finish reports success with the result on the event
The system SHALL emit `platformops_event_to_run_finished(event, ...)` as
`{"type": "RUN_FINISHED", "threadId": ..., "runId": ..., "result":
<event.payload>, "outcome": {"type": "success"}}` -- `result` SHALL sit
on the top-level event dict, not nested inside `outcome`, matching the
real `ag_ui.core.RunFinishedEvent`/`RunFinishedSuccessOutcome` schema
(`RunFinishedSuccessOutcome` carries only `type`).

#### Scenario: Success outcome carries no result field
- **WHEN** `platformops_event_to_run_finished` builds a frame
- **THEN** `frame["outcome"] == {"type": "success"}` and
  `frame["result"] == event.payload`
