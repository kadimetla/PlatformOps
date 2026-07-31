from datetime import datetime, timezone
from pathlib import Path

from gateway.auth.claims import OIDCClaims
from gateway.auth.cli import load_grant_mapping, write_session
from gateway.auth.sessions import build_actor_session


def test_load_grant_mapping_from_yaml(tmp_path):
    path = tmp_path / "grants.yaml"
    path.write_text(
        """
mappings:
  - group: aiq-it-prod-approvers
    grant_type: approval
    capability: apply_limited
    scope:
      org: aiq
      bu: it
      project: "*"
      workspace: prod
"""
    )

    mapping = load_grant_mapping(path)

    assert len(mapping.mappings) == 1
    assert mapping.mappings[0].grant_type == "approval"


def test_write_session_persists_no_tokens_and_restricts_permissions(tmp_path):
    session = build_actor_session(
        OIDCClaims(
            sub="user-1",
            email="alice@example.com",
            groups=["aiq-it-invoices-dev-operator"],
        ),
        [],
        [],
        now=datetime(2026, 7, 30, tzinfo=timezone.utc),
    )
    path = tmp_path / "session.json"

    write_session(session, path)

    text = path.read_text()
    assert "alice@example.com" in text
    assert "id_token" not in text
    assert "access_token" not in text
    assert oct(path.stat().st_mode & 0o777) == "0o600"
