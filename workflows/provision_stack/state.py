"""Graph state for the provision_stack workflow."""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from gateway.schemas import WorkspaceBundle


class ProvisionStackState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    spec: dict
    bundle: WorkspaceBundle
    toolchain: str
