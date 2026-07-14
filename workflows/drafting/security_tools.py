"""record_security_decision -- the structured signal security_review_node
uses to approve or reject a drafted plan, mirroring propose_tool_intent's
own pattern (tools.py): a real bound tool whose CALL is the meaningful
event, harvested by plan_request() afterward.

DESIGN NOTE, stated explicitly rather than silently decided: unlike
ADK's event-stream capture (which never executes propose_tool_intent
calls, only observes them), LangGraph's ToolNode genuinely executes
bound tools as part of the ReAct loop. So provisioning nodes' proposed
intents already exist in the message history by the time
security_review_node runs -- structurally preventing their harvest
isn't possible the way "the security node runs first" would suggest.
Instead, plan_request()'s harvest step (task 4.3) checks whether this
tool was called with approved=True before including ANY ToolIntent in
its return -- rejection (or the tool never being called at all) means
zero ToolIntents, regardless of what propose_tool_intent calls exist in
the message history. This is where "review before dispatch" actually
gets enforced in this workflow, not by graph structure alone.
"""
from langchain_core.tools import tool


@tool
def record_security_decision(approved: bool, reason: str) -> str:
    """Record security_review_node's approve/reject decision for the
    plan drafted so far. MUST be called exactly once, after reviewing
    every propose_tool_intent call already made in this conversation.
    Reject with a specific, actionable reason -- never approve silently
    per security-review-checklist skill's rule.
    """
    return f"Security decision recorded: approved={approved} ({reason})"
