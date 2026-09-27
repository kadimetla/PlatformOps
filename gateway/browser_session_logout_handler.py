"""Gateway-only logout boundary for browser sessions."""
from dataclasses import dataclass

from gateway.browser_sessions import BrowserSessionAuthenticator, BrowserSessionClearCookie


@dataclass(frozen=True)
class BrowserSessionLogout:
    clear_cookie: BrowserSessionClearCookie


class BrowserSessionLogoutHandler:
    def __init__(self, *, authenticator: BrowserSessionAuthenticator, cookie_name: str = "platformops_session") -> None:
        if not cookie_name:
            raise ValueError("browser session cookie name is required")
        self._authenticator = authenticator
        self._cookie_name = cookie_name

    def logout(self, token: str) -> BrowserSessionLogout:
        self._authenticator.logout(token)
        return BrowserSessionLogout(clear_cookie=BrowserSessionClearCookie(name=self._cookie_name))
