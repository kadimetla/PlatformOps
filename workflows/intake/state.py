from typing import TypedDict

from gateway.schemas import IntakeDecision, IntakeRequest


class IntakeState(TypedDict):
    request: IntakeRequest
    result: IntakeDecision | None
