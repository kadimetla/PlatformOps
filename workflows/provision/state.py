from typing import TypedDict

from gateway.schemas import Scope
from workflows.provision.schemas import ProvisionDraft, ProvisionInvocation


class ProvisionState(TypedDict):
    invocation: ProvisionInvocation
    scope: Scope | None
    profile_id: str | None
    result: ProvisionDraft
