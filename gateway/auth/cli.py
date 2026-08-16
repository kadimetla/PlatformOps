"""CLI entry point for Authentik/OIDC device-code login.

This is intentionally small and synchronous: it exists to exercise a
real IdP early without introducing a web server or TUI framework. It
stores only the normalized ActorSession, never OIDC tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from gateway.auth.grants import GrantMappingConfig, resolve_group_grants
from gateway.auth.login import (
    DeviceAuthorizationPending,
    DeviceAuthorizationSlowDown,
    OIDCDeviceClientConfig,
    begin_device_authorization,
    discover_oidc_metadata,
    parse_device_id_token,
    poll_device_token,
)
from gateway.auth.sessions import ActorSession, build_actor_session


DEFAULT_SESSION_PATH = Path(".platformops/session.json")


def fetch_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def load_grant_mapping(path: Path | None) -> GrantMappingConfig:
    if path is None:
        return GrantMappingConfig()
    data = yaml.safe_load(path.read_text()) or {}
    return GrantMappingConfig.model_validate(data)


def write_session(session: ActorSession, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session.model_dump_json(indent=2) + "\n")
    path.chmod(0o600)


def login_once(
    config: OIDCDeviceClientConfig,
    mapping: GrantMappingConfig,
    *,
    session_path: Path,
) -> ActorSession:
    metadata = discover_oidc_metadata(config.issuer, fetch_json)
    authorization = begin_device_authorization(config, post_form, metadata)

    verification_url = (
        authorization.verification_uri_complete or authorization.verification_uri
    )
    print("Open this URL to authenticate:")
    print(verification_url)
    print(f"User code: {authorization.user_code}")

    deadline = time.monotonic() + authorization.expires_in
    interval = authorization.interval
    while True:
        if time.monotonic() >= deadline:
            raise TimeoutError("device authorization expired before login completed")

        try:
            token_set = poll_device_token(
                config, authorization.device_code, post_form, metadata
            )
            break
        except DeviceAuthorizationPending:
            time.sleep(interval)
        except DeviceAuthorizationSlowDown:
            interval += 5
            time.sleep(interval)

    jwks = fetch_json(metadata.jwks_uri)
    claims = parse_device_id_token(token_set, jwks, config, issuer=metadata.issuer)
    grants = resolve_group_grants(claims.groups, mapping)
    session = build_actor_session(
        claims, grants.execution_grants, grants.approval_grants
    )
    write_session(session, session_path)

    print(f"Logged in as {session.actor.email}")
    print(f"Session written to {session_path}")
    print(f"Execution grants: {len(session.actor.execution_grants)}")
    print(f"Approval grants: {len(session.actor.approval_grants)}")
    return session


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Login to PlatformOps via Authentik")
    parser.add_argument(
        "--issuer",
        default=os.environ.get("PLATFORMOPS_OIDC_ISSUER"),
        help="OIDC issuer URL, e.g. https://authentik.example.com",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("PLATFORMOPS_OIDC_CLIENT_ID"),
        help="OIDC client id",
    )
    parser.add_argument(
        "--audience",
        default=os.environ.get("PLATFORMOPS_OIDC_AUDIENCE"),
        help="Expected ID-token audience. Defaults to --client-id.",
    )
    parser.add_argument(
        "--grant-mapping",
        type=Path,
        default=os.environ.get("PLATFORMOPS_GRANT_MAPPING"),
        help="Optional YAML mapping of IdP groups to PlatformOps grants",
    )
    parser.add_argument(
        "--session-path",
        type=Path,
        default=Path(os.environ.get("PLATFORMOPS_SESSION_PATH", DEFAULT_SESSION_PATH)),
        help=f"Where to write the token-free session JSON. Default: {DEFAULT_SESSION_PATH}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.issuer:
        parser.error("--issuer or PLATFORMOPS_OIDC_ISSUER is required")
    if not args.client_id:
        parser.error("--client-id or PLATFORMOPS_OIDC_CLIENT_ID is required")

    config = OIDCDeviceClientConfig(
        issuer=args.issuer.rstrip("/"),
        client_id=args.client_id,
        audience=args.audience or args.client_id,
    )
    mapping = load_grant_mapping(args.grant_mapping)
    login_once(config, mapping, session_path=args.session_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
