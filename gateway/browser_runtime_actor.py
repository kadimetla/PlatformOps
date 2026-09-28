"""Server-owned runtime actor lookup for browser AG-UI transport.

Browser sessions identify a principal only. This boundary supplies the narrow
runtime projection still required by the legacy harness without reading the
CLI session file or accepting browser-provided grants.
"""
from datetime import datetime, timezone
from typing import Protocol

from gateway.auth.schemas import Actor, ApprovalGrant, ExecutionGrant
from gateway.command_router import ValidatedPrincipal


class BrowserRuntimeActorResolutionError(PermissionError):
    """The authenticated principal has no active server-owned actor projection."""


class BrowserRuntimeActorResolver(Protocol):
    def resolve(self, *, principal: ValidatedPrincipal) -> Actor: ...


class BrowserRuntimeActorStore(Protocol):
    def get_active_actor(self, *, issuer: str, subject: str) -> Actor | None: ...


class StoredBrowserRuntimeActorResolver:
    """Resolve a browser principal from an injected authoritative store."""

    def __init__(self, store: BrowserRuntimeActorStore) -> None:
        self._store = store

    def resolve(self, *, principal: ValidatedPrincipal) -> Actor:
        actor = self._store.get_active_actor(
            issuer=principal.issuer, subject=principal.subject
        )
        if actor is None or actor.user_id != principal.subject:
            raise BrowserRuntimeActorResolutionError("browser runtime actor unavailable")
        return actor


class InMemoryBrowserRuntimeActorStore:
    """Focused test double; browser input never mutates this store."""

    def __init__(self, actors: tuple[Actor, ...] = ()) -> None:
        self._actors = {actor.user_id: actor for actor in actors}

    def get_active_actor(self, *, issuer: str, subject: str) -> Actor | None:
        if issuer != "platformops":
            return None
        return self._actors.get(subject)


def browser_runtime_actor(
    *, subject: str, email: str, execution_grants: list[ExecutionGrant] | None = None,
    approval_grants: list[ApprovalGrant] | None = None,
) -> Actor:
    """Build an explicit server fixture; production code uses a store."""
    return Actor(
        user_id=subject,
        email=email,
        execution_grants=execution_grants or [],
        approval_grants=approval_grants or [],
        resolved_at=datetime.now(timezone.utc),
    )
