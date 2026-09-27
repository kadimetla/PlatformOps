"""No-LLM graph for passwordless initiation; confirmation stays at the gateway."""
from langgraph.graph import END, StateGraph

from gateway.auth.registration import RegistrationService
from workflows.login_registration.state import LoginRegistrationState


def build_login_registration_graph(service: RegistrationService):
    def request_verification(state: LoginRegistrationState) -> dict:
        return {"result": service.request_registration(state["email"])}

    builder = StateGraph(LoginRegistrationState)
    builder.add_node("request_verification", request_verification)
    builder.set_entry_point("request_verification")
    builder.add_edge("request_verification", END)
    return builder
