"""The drafting workflow: LangGraph replacement for agents/*.py's ADK
graph and gateway/plan_request.py's execution internals.

NOT YET CUT OVER. gateway/plan_request.py still runs on agents/*.py's
ADK implementation until openspec/changes/migrate-to-langgraph/tasks.md
section 6 (Cutover) completes. This package is built and tested
alongside the existing implementation, not in place of it -- see that
change's design.md "Parallel-build" decision.

This is one workflow among several planned (drafting, approval,
dispatch, audit, discovery -- see
docs/request_intent_taxonomy_and_workflow_routing.md), named
`workflows/drafting/` rather than a framework-generic name so the
module path matches its future WORKFLOW_REGISTRY key exactly.
"""
