"""Scanner-safe passwordless confirmation boundary.

This is intentionally a gateway handler rather than a LangGraph node: raw
magic-link tokens are request-local security material and must not enter graph
state, checkpoints, events, or diagnostics.
"""
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from gateway.auth.registration import RegistrationService
from gateway.browser_sessions import BrowserSessionIssuer, BrowserSessionSetCookie


class VerificationIntentResponse(BaseModel):
    valid: bool


class BrowserLoginConfirmationResponse(BaseModel):
    """JSON-safe confirmation result; browser session token is not included."""

    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=5)
    csrf_proof: str = Field(min_length=1)


@dataclass(frozen=True)
class BrowserLoginConfirmation:
    """Gateway-only HTTP adaptation material following successful confirmation."""

    body: BrowserLoginConfirmationResponse
    set_cookie: BrowserSessionSetCookie


class LoginConfirmationHandler:
    def __init__(self, service: RegistrationService, *, browser_sessions: BrowserSessionIssuer) -> None:
        self._service = service
        self._browser_sessions = browser_sessions

    def inspect_intent(self, token: str) -> VerificationIntentResponse:
        """Safe GET-equivalent check; it does not consume the token."""
        return VerificationIntentResponse(valid=self._service.verification_intent(token))

    def confirm(self, token: str) -> BrowserLoginConfirmation | None:
        """Same-origin POST-equivalent operation; consumes once and sets a cookie."""
        actor_session = self._service.confirm_and_issue_session(token)
        if actor_session is None:
            return None
        issued = self._browser_sessions.issue(subject=actor_session.actor.user_id)
        return BrowserLoginConfirmation(
            body=BrowserLoginConfirmationResponse(
                subject=actor_session.actor.user_id, csrf_proof=issued.csrf_proof
            ),
            set_cookie=issued.set_cookie,
        )
