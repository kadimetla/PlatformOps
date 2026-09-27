from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from gateway.browser_sessions import (
    BrowserSessionAuthenticator, BrowserSessionIssuer, BrowserSessionSigningKey,
    InMemoryBrowserSessionRepository, StaticBrowserSessionSigningKeyProvider,
)
from gateway.command_router import ValidatedPrincipal
from transports.browser_auth import browser_mutation_principal_dependency


def _client():
    now = datetime.now(timezone.utc)
    repository = InMemoryBrowserSessionRepository(csrf_hmac_key=b"test-csrf-key")
    keys = StaticBrowserSessionSigningKeyProvider(BrowserSessionSigningKey(
        key_id="test-key", secret=b"test-signing-key-that-is-at-least-32-bytes",
    ))
    issued = BrowserSessionIssuer(
        repository=repository, signing_keys=keys, csrf_hmac_key=b"test-csrf-key",
    ).issue(subject="usr_alice", now=now)
    authenticator = BrowserSessionAuthenticator(
        repository=repository, signing_keys=keys, expected_origin="https://platformops.example",
    )
    app = FastAPI()

    @app.post("/runs")
    async def runs(principal: ValidatedPrincipal = Depends(
        browser_mutation_principal_dependency(authenticator)
    )):
        return {"subject": principal.subject}

    client = TestClient(app)
    client.cookies.set("platformops_session", issued.set_cookie._token)
    return client, issued


def test_browser_mutation_dependency_derives_principal_before_route_execution():
    client, issued = _client()

    response = client.post("/runs", headers={
        "origin": "https://platformops.example", "x-csrf-proof": issued.csrf_proof,
    })

    assert response.status_code == 200
    assert response.json() == {"subject": "usr_alice"}


def test_browser_mutation_dependency_rejects_missing_invalid_or_cross_origin_session_proofs():
    client, issued = _client()

    assert client.post("/runs").status_code == 401
    assert client.post("/runs", headers={
        "origin": "https://evil.example", "x-csrf-proof": issued.csrf_proof,
    }).status_code == 401
    assert client.post("/runs", headers={
        "origin": "https://platformops.example", "x-csrf-proof": "wrong",
    }).status_code == 401
