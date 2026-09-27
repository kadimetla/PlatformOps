# Proposal

## Why

The current browser frontend proves AG-UI/A2UI transport but is not yet a
usable workspace for multiple PlatformOps workflows.

## What Changes

- Build a centered conversation workspace with a compact navigation rail and
  persistent bottom composer.
- Present workflow context, identity state, and workflow-owned typed surfaces.
- Add a role-aware Work entry point and an architecture-review presentation
  path without creating a second approval mechanism.
- Present server-projected work queues while reserving durable work-item
  storage and workflow authorization for `build-work-items`.

## Non-Goals

No cloud execution, client-side authorization, raw workflow JSON, browser JWT
access, generic workflow renderer that can invoke arbitrary actions, or a new
approval mechanism.
