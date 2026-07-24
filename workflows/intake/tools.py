"""select_workflow -- classify_workflow's Tier 3 structured signal
tool, mirroring workflows/inquiry/tools.py's select_resource_type
pattern: a real bound tool whose CALL is the meaningful event, harvested
from the model response directly (no ToolNode execution loop -- this is
a single-shot classification call, not a create_react_agent loop).
Enforced by prompt instruction (candidates listed in the prompt, call
exactly once), not API-level forced tool_choice -- same convention
select_resource_type/record_security_decision already use.
"""
from typing import Optional

from langchain_core.tools import tool

# The two real workflow package names -- not an abstract category.
# Resolves docs/intent_routing_and_staged_confirmation.md's open
# question ("assumed yes [workflow_hint equals] the WORKFLOW_REGISTRY
# keys, not confirmed"). Plain tuple, extended by hand as new workflows
# are built -- no registry before a third workflow exists to need one
# (design.md's Decisions).
WORKFLOW_CANDIDATES = ("drafting", "inquiry")


@tool
def select_workflow(
    workflow_name: Optional[str] = None, clarifying_question: Optional[str] = None
) -> str:
    """Resolve free-text raw_text to exactly one of the candidate
    workflow names given in the prompt. Set workflow_name to one of
    those exact strings if confident, or set clarifying_question
    instead if neither fits -- never invent a workflow name outside the
    given list.
    """
    return f"workflow_name={workflow_name} clarifying_question={clarifying_question}"
