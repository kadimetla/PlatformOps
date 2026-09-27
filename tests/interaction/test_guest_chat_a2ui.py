from gateway.guest_chat_router import GuestChatAction, GuestChatRoute
from interaction.guest_chat_a2ui import guest_chat_route_to_a2ui_messages


def _flatten(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten(item)


def test_login_route_renders_an_email_entry_surface_with_no_sensitive_control_plane_data():
    messages = guest_chat_route_to_a2ui_messages(
        GuestChatRoute(action=GuestChatAction.START_LOGIN), surface_id="guest-login",
    )

    assert messages[0]["createSurface"]["surfaceId"] == "guest-login"
    components = messages[1]["updateComponents"]["components"]
    assert any(component["component"] == "TextField" for component in components)
    assert any(
        component.get("action", {}).get("event", {}).get("name") == "guest.login.submit"
        for component in components
    )
    rendered_keys = set(_flatten(messages))
    assert not {
        "jwt", "cookie", "csrf_proof", "token", "magic_link", "organization",
        "target", "provider", "role", "grant", "credential", "binding",
    } & rendered_keys


def test_login_required_surface_contains_guidance_but_not_an_email_or_authority_payload():
    messages = guest_chat_route_to_a2ui_messages(
        GuestChatRoute(action=GuestChatAction.LOGIN_REQUIRED), surface_id="guest-required",
    )

    components = messages[1]["updateComponents"]["components"]
    assert not any(component["component"] == "TextField" for component in components)
    assert "Use /login before continuing" in str(messages)
