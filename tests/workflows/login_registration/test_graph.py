import asyncio

from gateway.auth.registration import (
    InMemoryRegistrationRateLimiter,
    InMemoryVerificationAttemptStore,
    RegistrationService,
)
from gateway.command_router import ControlPlaneCommandRouter
from gateway.login_registration_handler import build_login_registration_handler


class FakeDelivery:
    def __init__(self):
        self.messages = []

    def send_verification(self, *, email, token):
        self.messages.append((email, token))


def test_public_login_command_starts_deterministic_passwordless_workflow():
    delivery = FakeDelivery()
    service = RegistrationService(
        attempts=InMemoryVerificationAttemptStore(), delivery=delivery, token_hmac_key=b"test-key"
    )
    router = ControlPlaneCommandRouter(
        {"login_registration": build_login_registration_handler(service)}
    )

    result = asyncio.run(router.dispatch("/login", {"email": "alice@example.com"}, principal=None))

    assert "verification message" in result.message
    assert delivery.messages[0][0] == "alice@example.com"


def test_public_login_threads_internal_source_to_registration_rate_limiting():
    delivery = FakeDelivery()
    service = RegistrationService(
        attempts=InMemoryVerificationAttemptStore(),
        delivery=delivery,
        token_hmac_key=b"test-key",
        rate_limiter=InMemoryRegistrationRateLimiter(max_per_email=5, max_per_source=1),
    )
    router = ControlPlaneCommandRouter(
        {"login_registration": build_login_registration_handler(service)}
    )

    first = asyncio.run(router.dispatch(
        "/login", {"email": "alice@example.com"}, principal=None, source="198.51.100.7",
    ))
    second = asyncio.run(router.dispatch(
        "/login", {"email": "bob@example.com"}, principal=None, source="198.51.100.7",
    ))

    assert first == second
    assert [email for email, _token in delivery.messages] == ["alice@example.com"]
