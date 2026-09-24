"""Scanner-safe passwordless confirmation boundary.

This is intentionally a gateway handler rather than a LangGraph node: raw
magic-link tokens are request-local security material and must not enter graph
state, checkpoints, events, or diagnostics.
"""
from pydantic import BaseModel

from gateway.auth.registration import RegistrationService
from gateway.auth.sessions import ActorSession


class VerificationIntentResponse(BaseModel):
    valid: bool


class LoginConfirmationHandler:
    def __init__(self, service: RegistrationService) -> None:
        self._service = service

    def inspect_intent(self, token: str) -> VerificationIntentResponse:
        """Safe GET-equivalent check; it does not consume the token."""
        return VerificationIntentResponse(valid=self._service.verification_intent(token))

    def confirm(self, token: str) -> ActorSession | None:
        """Same-origin POST-equivalent operation; consumes exactly once."""
        return self._service.confirm_and_issue_session(token)
