"""The provision_stack workflow (renamed from "drafting" -- see
docs/composable_foundation_blueprints.md Parts G/M): LangGraph
replacement for agents/*.py's ADK graph and gateway/plan_request.py's
execution internals.

NOT YET CUT OVER. gateway/plan_request.py still runs on agents/*.py's
ADK implementation until openspec/changes/migrate-to-langgraph/tasks.md
section 6 (Cutover) completes. This package is built and tested
alongside the existing implementation, not in place of it -- see that
change's design.md "Parallel-build" decision.

This is one workflow among several planned (provision_stack -- named
"drafting" when that taxonomy doc was written -- plus approval,
dispatch, audit, discovery -- see
docs/request_intent_taxonomy_and_workflow_routing.md), named
`workflows/provision_stack/` rather than a framework-generic name so the
module path matches its future WORKFLOW_REGISTRY key exactly.
"""
