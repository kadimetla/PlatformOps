# Proposal

## Why

Users need a clear way to see their authorized operating context and manage
personal preferences. Administrators need scoped governance settings without
turning browser-visible roles, settings, or context selection into authority.

## What Changes

- Add safe context navigation across authorized Organization, Business Unit,
  Team, PlatformOps Project, and Environment records.
- Define personal preferences separately from governed configuration.
- Define inherited governance settings with an explicit source and effective
  value, where lower scopes may tighten but cannot weaken inherited guardrails.
- Define a role-filtered Settings experience for membership, governance, cloud
  services, notifications, and audit views.

## Non-Goals

This change does not implement a general policy language, grant access through
a context switch, expose provider credentials, or make a browser UI the policy
enforcement point. It does not replace `build-chat-workflow-context`; that
change remains responsible for active conversational context and workflow-run
selection.
