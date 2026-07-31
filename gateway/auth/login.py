"""Authentik/OIDC device-code login primitives.

Network I/O is injected through small callables so tests stay offline
and the TUI/CLI layer can decide how to perform HTTP requests.
"""
from typing import Callable

from pydantic import BaseModel, Field

from gateway.auth.claims import OIDCClaims, parse_id_token

DEVICE_CODE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


class OIDCDeviceClientConfig(BaseModel):
    issuer: str
    client_id: str
    audience: str
    scopes: tuple[str, ...] = ("openid", "email", "profile", "groups")


class OIDCProviderMetadata(BaseModel):
    issuer: str
    token_endpoint: str
    jwks_uri: str
    device_authorization_endpoint: str | None = None


class DeviceAuthorization(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int
    interval: int = 5


class TokenSet(BaseModel):
    access_token: str
    id_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None


class DeviceAuthorizationPending(Exception):
    pass


class DeviceAuthorizationSlowDown(Exception):
    pass


class DeviceAuthorizationDenied(Exception):
    pass


class DeviceAuthorizationExpired(Exception):
    pass


FetchJson = Callable[[str], dict]
PostForm = Callable[[str, dict[str, str]], dict]


def discover_oidc_metadata(issuer: str, fetch_json: FetchJson) -> OIDCProviderMetadata:
    base = issuer.rstrip("/")
    data = fetch_json(f"{base}/.well-known/openid-configuration")
    return OIDCProviderMetadata(
        issuer=data["issuer"],
        token_endpoint=data["token_endpoint"],
        jwks_uri=data["jwks_uri"],
        device_authorization_endpoint=data.get("device_authorization_endpoint"),
    )


def authentik_device_endpoint(issuer: str) -> str:
    """Authentik documents `/application/o/device/` for RFC 8628
    initiation. Prefer metadata when it advertises an endpoint; use
    this helper when it does not.
    """
    return f"{issuer.rstrip('/')}/application/o/device/"


def authentik_token_endpoint(issuer: str) -> str:
    return f"{issuer.rstrip('/')}/application/o/token/"


def begin_device_authorization(
    config: OIDCDeviceClientConfig,
    post_form: PostForm,
    metadata: OIDCProviderMetadata | None = None,
) -> DeviceAuthorization:
    endpoint = (
        metadata.device_authorization_endpoint
        if metadata and metadata.device_authorization_endpoint
        else authentik_device_endpoint(config.issuer)
    )
    data = post_form(
        endpoint,
        {"client_id": config.client_id, "scope": " ".join(config.scopes)},
    )
    return DeviceAuthorization(**data)


def poll_device_token(
    config: OIDCDeviceClientConfig,
    device_code: str,
    post_form: PostForm,
    metadata: OIDCProviderMetadata | None = None,
) -> TokenSet:
    endpoint = metadata.token_endpoint if metadata else authentik_token_endpoint(config.issuer)
    data = post_form(
        endpoint,
        {
            "grant_type": DEVICE_CODE_GRANT,
            "client_id": config.client_id,
            "device_code": device_code,
        },
    )

    error = data.get("error")
    if error == "authorization_pending":
        raise DeviceAuthorizationPending()
    if error == "slow_down":
        raise DeviceAuthorizationSlowDown()
    if error == "access_denied":
        raise DeviceAuthorizationDenied()
    if error == "expired_token":
        raise DeviceAuthorizationExpired()
    if error:
        raise ValueError(f"device token request failed: {error}")

    return TokenSet(**data)


def parse_device_id_token(
    token_set: TokenSet,
    jwks: dict,
    config: OIDCDeviceClientConfig,
) -> OIDCClaims:
    return parse_id_token(
        token_set.id_token,
        jwks,
        issuer=config.issuer.rstrip("/"),
        audience=config.audience,
    )
