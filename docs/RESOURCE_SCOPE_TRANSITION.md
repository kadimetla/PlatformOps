# Resource Scope transition

## Removed temporary flow

The branch previously contained a compatibility-only runtime edge for an old
request shape:

```text
org:bu / project / workspace
```

For example, a caller could provide an organization/business-unit pair plus
`project=checkout` and `workspace=prod`. The temporary normalizer searched the
registry for a single matching active scope and translated that hint into a
`scope_id`.

That edge is removed. PlatformOps has not been deployed, so retaining two
target-selection models would create ambiguity without providing a migration
benefit. The removed components were `gateway/resource_scope_legacy.py`, the
legacy registry lookup protocol, and its PostgreSQL implementation.

## Replacement flow

The current provisioning boundary uses one authoritative target identifier:

```text
authenticated principal
  -> requested scope_id
  -> active Resource Scope registry record
  -> canonical org:bu:team:project:env path
  -> authorized provider binding
  -> sealed provision context
```

`scope_id` is immutable. The canonical path is descriptive and is derived from
the registered hierarchy; it is not permission or cloud-routing authority.
The server resolves the provider binding after authorization. Clients do not
supply provider, account, workspace, execution identity, group membership, or
any fallback target segments.

## Terminology

| Old term | Current term |
|---|---|
| `workspace` | `environment` (`env`) in a PlatformOps Resource Scope |
| `org:bu/project/workspace` hint | `scope_id` targeting an `org:bu:team:project:env` Resource Scope |
| target normalizer | reviewed Resource Scope registry resolution |

`provider_workspace` remains an internal optional field of a provider binding.
It is a provider-specific execution reference, not a PlatformOps Resource
Scope environment and never client-selected.

## Schema upgrade note

The PostgreSQL migration retains a one-time backfill for the
`organization_slug` column. This is schema safety for databases created by an
earlier branch revision, not a runtime request compatibility flow. It recovers
the slug from the persisted canonical path and does not accept old request
shapes.
