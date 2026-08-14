"""platformops -- the local-command-execution transport. See
docs/TRANSPORTS.md: a transport moves bytes for the same gateway
contract every other transport uses -- it must never classify intent,
compute grants, approve policy, or run workflow logic itself. This
one wires together what already exists (gateway.auth.cli's
device-code login, session read/write, interaction/tui.py's
rendering) rather than inventing new architecture. `run` is shaped but
fails clearly: intake requires a caller-provided model and this
project hasn't chosen a provider yet (see
workflows/intake/graph.py's build_intake_graph docstring) -- guessing
one here would declare that decision by accident.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable

from gateway.auth.cli import DEFAULT_SESSION_PATH, load_grant_mapping, login_once
from gateway.auth.login import OIDCDeviceClientConfig
from gateway.auth.sessions import ActorSession, read_session
from gateway.scope import parse_scope_hint
from interaction.tui import render_session_detail, render_session_summary


def _session_path_default() -> Path:
    return Path(os.environ.get("PLATFORMOPS_SESSION_PATH", DEFAULT_SESSION_PATH))


def _handle_login(args: argparse.Namespace) -> int:
    if not args.issuer:
        print("error: --issuer or PLATFORMOPS_OIDC_ISSUER is required", file=sys.stderr)
        return 2
    if not args.client_id:
        print("error: --client-id or PLATFORMOPS_OIDC_CLIENT_ID is required", file=sys.stderr)
        return 2

    config = OIDCDeviceClientConfig(
        issuer=args.issuer.rstrip("/"),
        client_id=args.client_id,
        audience=args.audience or args.client_id,
    )
    mapping = load_grant_mapping(args.grant_mapping)
    login_once(config, mapping, session_path=args.session_path)
    return 0


def _print_session(path: Path, render: Callable[[ActorSession], str]) -> int:
    if not path.exists():
        print(f"error: no session at {path} -- run 'platformops login' first", file=sys.stderr)
        return 1
    print(render(read_session(path)))
    return 0


def _handle_whoami(args: argparse.Namespace) -> int:
    return _print_session(args.session_path, render_session_summary)


def _handle_session_show(args: argparse.Namespace) -> int:
    return _print_session(args.session_path, render_session_detail)


def _handle_run(args: argparse.Namespace) -> int:
    print(
        "error: no model provider configured; intake requires a bound "
        "model (see workflows/intake/graph.py's build_intake_graph "
        "docstring) -- not guessed here.",
        file=sys.stderr,
    )
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="platformops")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="Log in via Authentik device-code flow")
    login.add_argument("--issuer", default=os.environ.get("PLATFORMOPS_OIDC_ISSUER"))
    login.add_argument("--client-id", default=os.environ.get("PLATFORMOPS_OIDC_CLIENT_ID"))
    login.add_argument("--audience", default=os.environ.get("PLATFORMOPS_OIDC_AUDIENCE"))
    login.add_argument(
        "--grant-mapping",
        type=Path,
        default=os.environ.get("PLATFORMOPS_GRANT_MAPPING"),
    )
    login.add_argument("--session-path", type=Path, default=_session_path_default())
    login.set_defaults(handler=_handle_login)

    whoami = subparsers.add_parser("whoami", help="Show the logged-in actor")
    whoami.add_argument("--session-path", type=Path, default=_session_path_default())
    whoami.set_defaults(handler=_handle_whoami)

    session = subparsers.add_parser("session", help="Session commands")
    session_subparsers = session.add_subparsers(dest="session_command", required=True)
    session_show = session_subparsers.add_parser("show", help="Show full session detail")
    session_show.add_argument("--session-path", type=Path, default=_session_path_default())
    session_show.set_defaults(handler=_handle_session_show)

    run = subparsers.add_parser("run", help="Run a request (not wired up yet)")
    run.add_argument("request", help="Freeform request text")
    run.add_argument(
        "--scope",
        type=parse_scope_hint,
        help="Structured target in org:bu/project/workspace form",
    )
    run.set_defaults(handler=_handle_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
