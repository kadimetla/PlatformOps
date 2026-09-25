"""Registered PlatformOps Resource Scopes, independent of cloud containers."""
from enum import Enum
from threading import Lock
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _generated_scope_id() -> str:
    return f"scope_{uuid4().hex}"


class ResourceScopeState(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


def _slug(value: str) -> str:
    if not value or len(value) > 63 or value != value.lower():
        raise ValueError("scope path segments must be lowercase slugs")
    if not value[0].isalpha() or any(not (character.isalnum() or character == "-") for character in value):
        raise ValueError("scope path segments must use lowercase letters, digits, and hyphens")
    return value


class Organization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str = Field(min_length=5)
    slug: str
    state: ResourceScopeState = ResourceScopeState.DRAFT

    _validate_slug = field_validator("slug")(_slug)


class BusinessUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit_id: str = Field(min_length=4)
    organization_id: str = Field(min_length=5)
    slug: str
    state: ResourceScopeState = ResourceScopeState.DRAFT

    _validate_slug = field_validator("slug")(_slug)


class Team(BaseModel):
    model_config = ConfigDict(extra="forbid")

    team_id: str = Field(min_length=5)
    business_unit_id: str = Field(min_length=4)
    slug: str
    state: ResourceScopeState = ResourceScopeState.DRAFT

    _validate_slug = field_validator("slug")(_slug)


class PlatformOpsProject(BaseModel):
    """Logical PlatformOps container; not an AWS/GCP/Azure project."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=8)
    team_id: str = Field(min_length=5)
    slug: str
    state: ResourceScopeState = ResourceScopeState.DRAFT

    _validate_slug = field_validator("slug")(_slug)


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: str = Field(min_length=4)
    project_id: str = Field(min_length=8)
    slug: str
    state: ResourceScopeState = ResourceScopeState.DRAFT

    _validate_slug = field_validator("slug")(_slug)


class ResourceScope(BaseModel):
    """One complete logical ownership and authorization context."""

    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(default_factory=_generated_scope_id, min_length=8)
    organization: Organization
    business_unit: BusinessUnit
    team: Team
    project: PlatformOpsProject
    environment: Environment
    state: ResourceScopeState = ResourceScopeState.DRAFT
    version: int = Field(default=1, ge=1)
    canonical_path: str = ""

    @model_validator(mode="after")
    def _validate_hierarchy_and_path(self) -> "ResourceScope":
        if self.business_unit.organization_id != self.organization.organization_id:
            raise ValueError("business unit must belong to organization")
        if self.team.business_unit_id != self.business_unit.business_unit_id:
            raise ValueError("team must belong to business unit")
        if self.project.team_id != self.team.team_id:
            raise ValueError("project must belong to team")
        if self.environment.project_id != self.project.project_id:
            raise ValueError("environment must belong to project")
        self.canonical_path = (
            f"org:{self.organization.slug}:bu:{self.business_unit.slug}:"
            f"team:{self.team.slug}:project:{self.project.slug}:env:{self.environment.slug}"
        )
        return self

    @property
    def is_complete_and_active(self) -> bool:
        return self.state is ResourceScopeState.ACTIVE and all(
            record.state is ResourceScopeState.ACTIVE
            for record in (self.organization, self.business_unit, self.team, self.project, self.environment)
        )


class ReviewedResourceScopeRegistry(Protocol):
    def register_reviewed(self, scope: ResourceScope) -> None: ...

    def resolve_active(self, scope_id: str) -> ResourceScope | None: ...


class LegacyResourceScopeEdgeLookup(Protocol):
    """Temporary lookup surface for the retired org:bu/project/workspace edge."""

    def find_active_by_legacy_segments(
        self, *, organization_slug: str, business_unit_slug: str,
        project_slug: str, environment_slug: str,
    ) -> tuple[ResourceScope, ...]: ...


class DuplicateCanonicalResourceScope(ValueError):
    pass


class InMemoryReviewedResourceScopeRegistry:
    """Test registry for reviewed records; it cannot route to a cloud provider."""

    def __init__(self) -> None:
        self._by_scope_id: dict[str, ResourceScope] = {}
        self._scope_id_by_path: dict[str, str] = {}
        self._lock = Lock()

    def register_reviewed(self, scope: ResourceScope) -> None:
        with self._lock:
            existing_id = self._scope_id_by_path.get(scope.canonical_path)
            if existing_id is not None and existing_id != scope.scope_id:
                raise DuplicateCanonicalResourceScope("canonical Resource Scope path already exists")
            previous = self._by_scope_id.get(scope.scope_id)
            if previous is not None:
                self._scope_id_by_path.pop(previous.canonical_path, None)
            self._by_scope_id[scope.scope_id] = scope
            self._scope_id_by_path[scope.canonical_path] = scope.scope_id

    def resolve_active(self, scope_id: str) -> ResourceScope | None:
        scope = self._by_scope_id.get(scope_id)
        return scope if scope is not None and scope.is_complete_and_active else None

    def find_active_by_legacy_segments(
        self, *, organization_slug: str, business_unit_slug: str,
        project_slug: str, environment_slug: str,
    ) -> tuple[ResourceScope, ...]:
        return tuple(
            scope for scope in self._by_scope_id.values()
            if scope.is_complete_and_active
            and scope.organization.slug == organization_slug
            and scope.business_unit.slug == business_unit_slug
            and scope.project.slug == project_slug
            and scope.environment.slug == environment_slug
        )


def non_routable_resource_scope_fixture(scope: ResourceScope) -> ResourceScope:
    """Return a logical fixture that intentionally cannot route any workflow."""
    return scope.model_copy(update={"state": ResourceScopeState.DRAFT})
