import pytest

from gateway.auth.login import (
    DEVICE_CODE_GRANT,
    DeviceAuthorizationDenied,
    DeviceAuthorizationExpired,
    DeviceAuthorizationPending,
    DeviceAuthorizationSlowDown,
    OIDCDeviceClientConfig,
    TokenSet,
    authentik_device_endpoint,
    authentik_token_endpoint,
    begin_device_authorization,
    discover_oidc_metadata,
    parse_device_id_token,
    poll_device_token,
)


ISSUER = "https://authentik.example.com"


def test_authentik_endpoint_helpers_match_documented_paths():
    assert authentik_device_endpoint(ISSUER) == (
        "https://authentik.example.com/application/o/device/"
    )
    assert authentik_token_endpoint(ISSUER) == (
        "https://authentik.example.com/application/o/token/"
    )


def test_discover_oidc_metadata_uses_well_known_configuration():
    seen = []

    def fetch_json(url):
        seen.append(url)
        return {
            "issuer": ISSUER,
            "token_endpoint": f"{ISSUER}/application/o/token/",
            "jwks_uri": f"{ISSUER}/application/o/platformops/jwks/",
            "device_authorization_endpoint": f"{ISSUER}/application/o/device/",
        }

    metadata = discover_oidc_metadata(ISSUER, fetch_json)

    assert seen == [f"{ISSUER}/.well-known/openid-configuration"]
    assert metadata.issuer == ISSUER
    assert metadata.device_authorization_endpoint.endswith("/application/o/device/")


def test_parse_device_id_token_uses_discovered_canonical_issuer(monkeypatch):
    seen = {}

    def fake_parse_id_token(token, jwks, issuer, audience):
        seen.update(issuer=issuer, audience=audience)
        return "claims"

    monkeypatch.setattr("gateway.auth.login.parse_id_token", fake_parse_id_token)
    config = OIDCDeviceClientConfig(
        issuer="http://localhost:9000/application/o/platformops",
        client_id="platformops",
        audience="platformops",
    )

    result = parse_device_id_token(
        TokenSet(access_token="access", id_token="id", token_type="Bearer"),
        {"keys": []},
        config,
        issuer="http://localhost:9000/application/o/platformops/",
    )

    assert result == "claims"
    assert seen == {
        "issuer": "http://localhost:9000/application/o/platformops/",
        "audience": "platformops",
    }


def test_begin_device_authorization_posts_client_and_scope():
    calls = []

    def post_form(url, data):
        calls.append((url, data))
        return {
            "device_code": "device-1",
            "user_code": "ABCD-EFGH",
            "verification_uri": f"{ISSUER}/activate",
            "verification_uri_complete": f"{ISSUER}/activate?user_code=ABCD-EFGH",
            "expires_in": 600,
            "interval": 5,
        }

    config = OIDCDeviceClientConfig(
        issuer=ISSUER, client_id="platformops", audience="platformops"
    )
    result = begin_device_authorization(config, post_form)

    assert calls == [
        (
            f"{ISSUER}/application/o/device/",
            {"client_id": "platformops", "scope": "openid email profile"},
        )
    ]
    assert result.user_code == "ABCD-EFGH"


def test_poll_device_token_posts_rfc8628_grant():
    calls = []

    def post_form(url, data):
        calls.append((url, data))
        return {
            "access_token": "access",
            "id_token": "id",
            "token_type": "Bearer",
            "expires_in": 300,
        }

    config = OIDCDeviceClientConfig(
        issuer=ISSUER, client_id="platformops", audience="platformops"
    )
    result = poll_device_token(config, "device-1", post_form)

    assert calls == [
        (
            f"{ISSUER}/application/o/token/",
            {
                "grant_type": DEVICE_CODE_GRANT,
                "client_id": "platformops",
                "device_code": "device-1",
            },
        )
    ]
    assert result.access_token == "access"


@pytest.mark.parametrize(
    ("error", "exc"),
    [
        ("authorization_pending", DeviceAuthorizationPending),
        ("slow_down", DeviceAuthorizationSlowDown),
        ("access_denied", DeviceAuthorizationDenied),
        ("expired_token", DeviceAuthorizationExpired),
    ],
)
def test_poll_device_token_maps_oauth_errors(error, exc):
    def post_form(url, data):
        return {"error": error}

    config = OIDCDeviceClientConfig(
        issuer=ISSUER, client_id="platformops", audience="platformops"
    )

    with pytest.raises(exc):
        poll_device_token(config, "device-1", post_form)
