"""FastAPI dependency for authenticated browser control-plane mutations."""
from collections.abc import Callable

from fastapi import HTTPException, Request

from gateway.browser_sessions import BrowserSessionAuthenticationError, BrowserSessionAuthenticator
from gateway.command_router import ValidatedPrincipal


def browser_mutation_principal_dependency(
    authenticator: BrowserSessionAuthenticator, *, cookie_name: str = "platformops_session",
) -> Callable[[Request], ValidatedPrincipal]:
    """Validate cookie, same Origin, and CSRF proof before a route invokes a workflow."""
    async def authenticate(request: Request) -> ValidatedPrincipal:
        token = request.cookies.get(cookie_name)
        try:
            return authenticator.authenticate_mutation(
                token or "", origin=request.headers.get("origin"),
                csrf_proof=request.headers.get("x-csrf-proof"),
            )
        except BrowserSessionAuthenticationError as error:
            raise HTTPException(status_code=401, detail="invalid browser session") from error

    return authenticate
