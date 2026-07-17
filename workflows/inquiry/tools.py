"""select_resource_type -- classify_resource_type's structured signal
tool, mirroring workflows/drafting/security_tools.py's
record_security_decision pattern: a real bound tool whose CALL is the
meaningful event, harvested from the model response directly (no
ToolNode execution loop here -- classify_resource_type calls the model
once, not via create_react_agent). Enforced by prompt instruction
(candidates listed in the prompt, call exactly once), not API-level
forced tool_choice -- same convention record_security_decision already
uses.
"""
from typing import Optional

from langchain_core.tools import tool


@tool
def select_resource_type(
    resource_type: Optional[str] = None, clarifying_question: Optional[str] = None
) -> str:
    """Resolve a free-text resource-type description to exactly one of
    the allowed resource types given in the prompt. Set resource_type to
    one of those exact strings if confident, or set clarifying_question
    instead if none fit -- never invent a type outside the given list.
    """
    return f"resource_type={resource_type} clarifying_question={clarifying_question}"
