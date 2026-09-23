# Spec Delta

## Purpose

Create provider accounts, projects, or subscriptions through a privileged,
approval-controlled bootstrap path rather than normal provisioning.

## ADDED Requirements

### Requirement: Provider container creation is separately authorized
The system SHALL require explicit organization policy and recorded approval
before creating a provider account, project, or subscription. Ordinary app
provisioning requests SHALL NOT create provider containers.

#### Scenario: App provisioning cannot create an account
- **WHEN** an ordinary provisioning request lacks an existing container binding
- **THEN** it returns a setup-required outcome and creates no provider container
