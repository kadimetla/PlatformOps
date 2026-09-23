# Spec Delta

## Purpose

Discover existing cloud containers through a verified read-only connection
without turning inventory visibility into PlatformOps authority.

## ADDED Requirements

### Requirement: Inquiry is read-only and connection-bounded
The system SHALL return candidate AWS accounts, GCP projects, or Azure
subscriptions only through an active verified provider connection and SHALL
not mutate provider or PlatformOps binding state.

#### Scenario: Inquiry returns a candidate only
- **WHEN** an authorized administrator inquires through an active connection
- **THEN** the result contains candidates and creates no scope binding or grant
