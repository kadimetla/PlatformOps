"""Allow-listed A2UI presentation for deterministic guest chat routes."""
from typing import Any

from gateway.guest_chat_router import GuestChatAction, GuestChatRoute
from interaction.a2ui import A2UI_VERSION, BASIC_CATALOG_ID


def guest_chat_route_to_a2ui_messages(
    route: GuestChatRoute, *, surface_id: str,
) -> list[dict[str, Any]]:
    """Render public guidance only; session and verification material stays server-side."""
    components = _components_for(route)
    return [
        {
            "version": A2UI_VERSION,
            "createSurface": {"surfaceId": surface_id, "catalogId": BASIC_CATALOG_ID},
        },
        {
            "version": A2UI_VERSION,
            "updateComponents": {"surfaceId": surface_id, "components": components},
        },
    ]


def _components_for(route: GuestChatRoute) -> list[dict[str, Any]]:
    title, message = _copy_for(route.action)
    children = ["title", "message"]
    components: list[dict[str, Any]] = [
        {"id": "root", "component": "Column", "children": children},
        {"id": "title", "component": "Text", "text": title},
        {"id": "message", "component": "Text", "text": message},
    ]
    if route.action is GuestChatAction.START_LOGIN:
        children.extend(["email", "submit"])
        components.extend([
            {
                "id": "email",
                "component": "TextField",
                "label": "Email address",
                "variant": "shortText",
                "validationRegexp": r"^[^\s@]+@[^\s@]+\.[^\s@]+$",
            },
            {
                "id": "submit",
                "component": "Button",
                "child": "submit-label",
                "action": {"event": {"name": "guest.login.submit", "context": {}}},
            },
            {"id": "submit-label", "component": "Text", "text": "Send sign-in link"},
        ])
    return components


def _copy_for(action: GuestChatAction) -> tuple[str, str]:
    if action is GuestChatAction.START_LOGIN:
        return "Sign in", "Enter your email address to receive a sign-in link."
    if action is GuestChatAction.START_REGISTRATION:
        return "Create an account", "Start with your email address to create a PlatformOps account."
    if action is GuestChatAction.START_JOIN_ORGANIZATION:
        return "Join an organization", "Use an invitation or your organization's sign-in path."
    if action is GuestChatAction.SHOW_CONTEXTS:
        return "Available contexts", "Login, account registration, organization joining, and help are available."
    if action is GuestChatAction.LOGIN_REQUIRED:
        return "Sign in required", "Use /login before continuing with that request."
    return "How can we help?", "Use /login to sign in or ask about creating or joining an organization."
