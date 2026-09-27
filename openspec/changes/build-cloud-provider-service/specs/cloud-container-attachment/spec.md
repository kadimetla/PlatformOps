# Spec Delta

## Purpose

Attach an existing cloud container to a Resource Scope only through explicit,
reviewed control-plane authorization.

## ADDED Requirements

### Requirement: Attachment is explicit and reviewed
The system SHALL require authorized review before an existing container becomes
an active Resource Scope binding. Inquiry output alone SHALL NOT attach it.

#### Scenario: Candidate remains unattached after inquiry
- **WHEN** inquiry returns a GCP project candidate
- **THEN** it is unavailable for provisioning until an approved attachment succeeds
