from datetime import datetime, timezone

from gateway.auth.claims import OIDCClaims
from gateway.auth.cli import write_session
from gateway.auth.sessions import build_actor_session
from transports.cli import main


def _write_test_session(path):
    session = build_actor_session(
        OIDCClaims(sub="alice", email="alice@example.com", groups=["aiq-it-prod-approvers"]),
        [],
        [],
        now=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )
    write_session(session, path)
    return session


def test_whoami_without_a_session_fails_clearly(tmp_path, capsys):
    session_path = tmp_path / "session.json"

    exit_code = main(["whoami", "--session-path", str(session_path)])

    assert exit_code == 1
    assert "platformops login" in capsys.readouterr().err


def test_whoami_prints_actor_identity(tmp_path, capsys):
    session_path = tmp_path / "session.json"
    _write_test_session(session_path)

    exit_code = main(["whoami", "--session-path", str(session_path)])

    assert exit_code == 0
    assert "alice@example.com" in capsys.readouterr().out


def test_session_show_prints_grants(tmp_path, capsys):
    session_path = tmp_path / "session.json"
    _write_test_session(session_path)

    exit_code = main(["session", "show", "--session-path", str(session_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "execution_grants:" in out
    assert "approval_grants:" in out


def test_run_fails_clearly_instead_of_guessing_a_model(capsys):
    exit_code = main(["run", "deploy invoices to dev"])

    assert exit_code == 1
    assert "no model provider configured" in capsys.readouterr().err


def test_login_requires_issuer(capsys):
    exit_code = main(["login", "--client-id", "abc"])

    assert exit_code == 2
    assert "--issuer" in capsys.readouterr().err


def test_login_requires_client_id(capsys):
    exit_code = main(["login", "--issuer", "https://authentik.example.com"])

    assert exit_code == 2
    assert "--client-id" in capsys.readouterr().err
