from gateway.auth.registration import (
    InMemoryUserRegistrationStore,
    InMemoryVerificationAttemptStore,
    RegistrationService,
)
from gateway.browser_sessions import (
    BrowserSessionIssuer,
    BrowserSessionSigningKey,
    InMemoryBrowserSessionRepository,
    StaticBrowserSessionSigningKeyProvider,
)
from gateway.login_confirmation_handler import LoginConfirmationHandler


class FakeDelivery:
    def __init__(self) -> None:
        self.token: str | None = None

    def send_verification(self, *, email: str, token: str) -> None:
        self.token = token


def test_intent_does_not_consume_and_confirmation_issues_one_unassociated_session():
    delivery = FakeDelivery()
    service = RegistrationService(
        attempts=InMemoryVerificationAttemptStore(),
        users=InMemoryUserRegistrationStore(),
        delivery=delivery,
        token_hmac_key=b"test-key",
    )
    service.request_registration("alice@example.com")
    handler = LoginConfirmationHandler(
        service,
        browser_sessions=BrowserSessionIssuer(
            repository=InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key"),
            signing_keys=StaticBrowserSessionSigningKeyProvider(
                BrowserSessionSigningKey(
                    key_id="test-key", secret=b"test-signing-key-that-is-at-least-32-bytes"
                )
            ),
            csrf_hmac_key=b"test-csrf-key",
        ),
    )

    assert delivery.token is not None
    assert handler.inspect_intent(delivery.token).valid is True
    confirmation = handler.confirm(delivery.token)

    assert confirmation is not None
    assert confirmation.body.subject.startswith("usr_")
    assert confirmation.body.csrf_proof
    assert "HttpOnly" in confirmation.set_cookie.as_header()
    assert "Secure" in confirmation.set_cookie.as_header()
    assert "SameSite=Lax" in confirmation.set_cookie.as_header()
    assert confirmation.set_cookie._token not in confirmation.body.model_dump_json()
    assert confirmation.set_cookie._token not in repr(confirmation)
    assert handler.confirm(delivery.token) is None
