"""A2UI adapter for PlatformOps interaction events -- dynamic UI
surfaces for the browser transport (transports/http.py), carried over
AG-UI's Custom event as {"type": "CUSTOM", "name": "a2ui.<messageType>",
"value": <this module's message dict>}.

Builds on interaction/agui.py's HITLEvent -> Interrupt mapping rather
than re-deriving message text/choices from IntakeDecision/ApprovalRequest
a second time -- same "each adapter builds on the previous one, not on
raw internal types twice" discipline agui.py already follows relative
to interaction/events.py.

Wire shape verified directly against the installed @a2ui/web_core npm
package's own Zod schemas and example fixtures (not assumed from docs
alone) 2026-08-07: createSurface/updateComponents messages carry a
sibling "version" field, not a "type" field; components compose via
Column's `children: [id, ...]` referencing sibling components by id,
not inline nesting; Button has no `text` prop -- it references a
label Text component via `child: <id>`, and its click-report shape is
`action.event.{name,context}`, not a bare `action.{name,context}`.

Renders using @a2ui/react's built-in basicCatalog only (Column, Text,
Button) -- no custom catalog registration needed on the frontend.
"""
from typing import Any

from interaction.agui import hitl_event_to_interrupt
from interaction.events import HITLEvent, HITLEventKind, PlatformOpsEvent

A2UI_VERSION = "v0.9"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json"

# The exact keys harness/core.py's _classify builds into a PlatformOpsEvent
# payload today. Explicit allow-list, not event.payload.items() -- a
# future payload key (evidence, IAM detail, anything else) has to be
# added here deliberately before it can ever reach the browser, rather
# than auto-rendering by virtue of existing in the dict.
_ROUTE_RESULT_FIELDS = (
    "intent",
    "route",
    "ready_to_route",
    "mutation_requested",
    "approval_required",
    "unsupported_reason",
)


def _create_surface(surface_id: str) -> dict[str, Any]:
    return {
        "version": A2UI_VERSION,
        "createSurface": {"surfaceId": surface_id, "catalogId": BASIC_CATALOG_ID},
    }


def _update_components(surface_id: str, components: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": A2UI_VERSION,
        "updateComponents": {"surfaceId": surface_id, "components": components},
    }


def _choice_field_and_enum(interrupt: dict[str, Any]) -> tuple[str, list[str]] | None:
    """responseSchema's selected_choice enum, for clarification only --
    see hitl_event_to_a2ui_messages for why APPROVAL_REQUIRED's verdict
    enum is deliberately not read here even though agui.py computes one.
    """
    properties = interrupt.get("responseSchema", {}).get("properties", {})
    schema = properties.get("selected_choice")
    if schema and schema.get("enum"):
        return "selected_choice", schema["enum"]
    return None


def hitl_event_to_a2ui_messages(event: HITLEvent) -> list[dict[str, Any]]:
    """A createSurface + updateComponents pair: a root Column holding a
    message Text plus, for CLARIFICATION_REQUIRED only, one Button
    (labeled via a child Text component) per choice.

    APPROVAL_REQUIRED renders message-only, no buttons -- harness/core.py
    has no resume_approval path (its own docstring: approval resume
    "needs a real LangGraph checkpointer behind a provision/inquiry
    workflow, neither of which exists"), so a Button here would be an
    affordance the system can never honor. Revisit once a real
    approval-gate workflow exists to resume into.

    No buttons for clarification either if agui.py's responseSchema
    carries no selected_choice enum -- a free-text answer would need a
    TextField component, not reachable today since classify_workflow's
    clarifying_question always carries the full Intent enum as choices
    (workflows/intake/nodes.py's _clarification()).
    """
    interrupt = hitl_event_to_interrupt(event)
    surface_id = event.event_id

    message_component = {"id": "message", "component": "Text", "text": interrupt["message"]}
    root_children = ["message"]
    components: list[dict[str, Any]] = [message_component]

    choice_field_and_enum = (
        _choice_field_and_enum(interrupt)
        if event.kind == HITLEventKind.CLARIFICATION_REQUIRED
        else None
    )
    if choice_field_and_enum is not None:
        field, choices = choice_field_and_enum
        for choice in choices:
            label_id = f"choice-{choice}-label"
            button_id = f"choice-{choice}"
            components.append({"id": label_id, "component": "Text", "text": choice})
            components.append(
                {
                    "id": button_id,
                    "component": "Button",
                    "child": label_id,
                    "action": {"event": {"name": surface_id, "context": {field: choice}}},
                }
            )
            root_children.append(button_id)

    root = {"id": "root", "component": "Column", "children": root_children}
    return [
        _create_surface(surface_id),
        _update_components(surface_id, [root, *components]),
    ]


def platformops_event_to_a2ui_messages(event: PlatformOpsEvent) -> list[dict[str, Any]]:
    """A createSurface + updateComponents pair: a root Column of Text
    fields rendering a resolved (or unsupported) route. Reads
    event.payload directly -- it's already the plain dict
    harness/core.py's _classify built from IntakeDecision, not a second
    model to parse. Only _ROUTE_RESULT_FIELDS render, in that fixed
    order -- an explicit view-model projection, not event.payload.items()
    -- so a future payload key doesn't automatically reach the browser
    without a deliberate decision to add it above. None-valued fields
    (e.g. route on an unsupported intent) are omitted rather than
    rendered as "route: None".
    """
    surface_id = event.event_id
    field_components = [
        {"id": f"field-{key}", "component": "Text", "text": f"{key}: {event.payload[key]}"}
        for key in _ROUTE_RESULT_FIELDS
        if event.payload.get(key) is not None
    ]
    root = {
        "id": "root",
        "component": "Column",
        "children": [component["id"] for component in field_components],
    }
    return [
        _create_surface(surface_id),
        _update_components(surface_id, [root, *field_components]),
    ]
