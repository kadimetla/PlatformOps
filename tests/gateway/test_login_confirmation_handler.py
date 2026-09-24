from gateway.auth.registration import (
    InMemoryUserRegistrationStore,
    InMemoryVerificationAttemptStore,
    RegistrationService,
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
    handler = LoginConfirmationHandler(service)

    assert delivery.token is not None
    assert handler.inspect_intent(delivery.token).valid is True
    session = handler.confirm(delivery.token)

    assert session is not None
    assert session.actor.user_id.startswith("usr_")
    assert session.actor.execution_grants == []
    assert session.actor.approval_grants == []
    assert handler.confirm(delivery.token) is None
