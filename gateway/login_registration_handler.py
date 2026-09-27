"""Gateway composition for public `/login` initiation."""
from pydantic import BaseModel, ConfigDict, Field

from gateway.auth.registration import RegistrationService
from gateway.command_router import CommandInvocation
from workflows.login_registration.graph import build_login_registration_graph


class LoginCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=320)


def build_login_registration_handler(service: RegistrationService):
    graph = build_login_registration_graph(service).compile()

    async def handle(invocation: CommandInvocation):
        command = LoginCommand.model_validate(invocation.payload)
        state = await graph.ainvoke({"email": command.email, "result": None})
        return state["result"]

    return handle
