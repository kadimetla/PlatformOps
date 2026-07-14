"""Graph state for the drafting workflow."""
from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from gateway.schemas import WorkspaceBundle


class DraftingState(TypedDict):
    messages: Annotated[list[Any], add_messages]
    spec: dict
    bundle: WorkspaceBundle
    toolchain: str
