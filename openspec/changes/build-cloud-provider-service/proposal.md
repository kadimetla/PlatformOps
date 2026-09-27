# Proposal

## Why

PlatformOps needs a provider-neutral service boundary for connecting an active
organization to AWS, GCP, or Azure without mixing cloud control, discovery, or
container creation into user registration, organization claiming, or ordinary
provisioning.

## What Changes

- Add a Cloud Provider Service that owns verified organization-to-provider
  connections and provider-specific adapters behind a narrow control-plane
  boundary.
- Add read-only Cloud Resource Container inquiry for existing AWS accounts,
  GCP projects, and Azure subscriptions within an already verified connection.
- Add reviewed attachment of an existing Cloud Resource Container to a
  PlatformOps Resource Scope; inquiry never creates access or attachment.
- Add a separately privileged provider-container bootstrap path for creating a
  new provider account, project, or subscription. It is not ordinary app
  provisioning and requires explicit organization policy and approval.
- Keep organization claiming/domain activation, user registration, Resource
  Scope authorization, and normal resource provisioning in their existing or
  separate changes.

## Capabilities

### New Capabilities

- `provider-connection`: register, verify, activate, suspend, and audit an
  organization-owned provider control boundary and read-only discovery identity.
- `cloud-container-inquiry`: return read-only candidate cloud containers only
  within an authorized verified provider connection.
- `cloud-container-attachment`: review and explicitly attach an existing
  Cloud Resource Container to an authorized PlatformOps Resource Scope.
- `provider-container-bootstrap`: create a new provider account, project, or
  subscription through a separately authorized, approval-controlled workflow.

### Modified Capabilities

(none — no archived OpenSpec capability owns this service boundary.)

## Impact

- `build-org-onboarding` will relinquish cloud-root verification and retain
  business organization claim, verified-domain activation, and initial tenant
  administration.
- `build-resource-scope-bootstrap` consumes reviewed provider connections and
  explicit Cloud Resource Container bindings; it does not discover, attach, or
  create provider containers.
- Later implementation adds provider adapter contracts, control-plane records,
  review/approval integration, fake-adapter tests, and current-doc provider
  verification before any live adapter is enabled.
