"""intake_request() -- the intake workflow's external boundary, same
call shape as plan_request()/inquiry_request(): a caller-constructed
request object in, a result object out. org_id/bu_id on IntakeRequest
are assumed already resolved from the authenticated session
(docs/intent_routing_and_staged_confirmation.md Part A) -- this
function never parses them from text. Not yet wired to any channel
adapter or dispatch step (proposal.md's stated non-goals, same
precedent as plan_request()/discover_request() themselves).
"""
from workflows.intake.graph import build_intake_graph
from workflows.intake.state import IntakeRequest, IntakeResult


async def intake_request(request: IntakeRequest) -> IntakeResult:
    builder = build_intake_graph()
    graph = builder.compile()
    result = await graph.ainvoke({"request": request, "result": None})
    return result["result"]
