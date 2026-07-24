"""The foundation-scope gate -- openspec/changes/provision-kubernetes-cluster.
A structural check, not a prompt instruction: denies a cluster-creation
request before any skill/tool resolution runs if the requester's
TeamMember.scope doesn't include "foundation". Matches
docs/foundation_and_app_deploy_flow_example.md's Bob/Alice walkthrough
and AGENTS.md's "deterministic checks stay deterministic" rule.
"""
from .schemas import WorkspaceBundle


def requester_has_foundation_scope(bundle: WorkspaceBundle, channel_user_id: str) -> bool:
    """No TeamMember row for this channel_user_id, or a role with
    scope="app" only, both deny -- fail closed, matching this project's
    deny-by-default convention everywhere else (gateway/tool_dispatcher.py)."""
    for member in bundle.members:
        if member.channel_user_id == channel_user_id:
            return member.scope in ("foundation", "both")
    return False
