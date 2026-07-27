"""openspec/changes/provision-kubernetes-cluster/tasks.md task 2.4.
scope value renamed "foundation" -> "stack" (docs/composable_foundation_blueprints.md
Parts G/M).
"""
from gateway.schemas import TeamMember, WorkspaceBundle
from gateway.scope_gate import requester_has_stack_scope


def _bundle_with_members(*members: TeamMember) -> WorkspaceBundle:
    return WorkspaceBundle(
        bundle_id="acme-payments",
        allowed_resource_types=["AWS::S3::Bucket"],
        members=list(members),
    )


def test_app_scoped_requester_is_denied():
    bundle = _bundle_with_members(
        TeamMember(channel_user_id="alice", display_name="Alice", role="requester", scope="app")
    )
    assert requester_has_stack_scope(bundle, "alice") is False


def test_stack_scoped_requester_passes():
    bundle = _bundle_with_members(
        TeamMember(channel_user_id="bob", display_name="Bob", role="admin", scope="stack")
    )
    assert requester_has_stack_scope(bundle, "bob") is True


def test_both_scoped_requester_passes():
    bundle = _bundle_with_members(
        TeamMember(channel_user_id="carol", display_name="Carol", role="admin", scope="both")
    )
    assert requester_has_stack_scope(bundle, "carol") is True


def test_unknown_requester_is_denied():
    bundle = _bundle_with_members(
        TeamMember(channel_user_id="bob", display_name="Bob", role="admin", scope="stack")
    )
    assert requester_has_stack_scope(bundle, "mallory") is False
