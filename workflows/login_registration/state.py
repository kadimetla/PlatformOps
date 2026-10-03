from typing import TypedDict

from gateway.auth.registration import RegistrationPendingResponse


class LoginRegistrationState(TypedDict):
    email: str
    source: str | None
    result: RegistrationPendingResponse | None
