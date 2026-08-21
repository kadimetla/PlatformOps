## Status

Design captured and first implementation slice started 2026-08-20.

This document defines how PlatformOps should generate workflow-specific
UI on the fly without letting an LLM emit arbitrary HTML.

## Decision

Do not accept raw HTML, JSX, CSS, or JavaScript from an LLM.

Instead, use this pipeline:

```text
workflow or LLM identifies missing user input
  -> returns a small typed DynamicUISpec
  -> server validates the spec
  -> server compiles it to allowed A2UI basic-catalog components
  -> frontend renders the A2UI surface in a generic host
```

The LLM may help choose wording, examples, labels, and options. It does
not choose arbitrary DOM nodes, scripts, styles, event handlers, or data
bindings.

## Why not HTML from the LLM

Raw generated HTML creates problems that are not worth taking on:

- XSS and unsafe markup.
- Inconsistent app styling.
- Hard-to-audit event handlers and hidden inputs.
- No reliable mapping from UI answer back to workflow state.
- No deterministic allow-list boundary.

The safe unit of generation is a validated UI intent, not browser DOM.

## First Spec Shape

The initial implemented shape is `DynamicCardSpec` in
`interaction/dynamic_ui.py`.

It supports:

- `title`
- `message`
- `help_texts`
- optional choices
- one response field for choice buttons

It compiles only to these A2UI basic-catalog components:

- `Card`
- `Column`
- `Text`
- `Button`

This is deliberately small. `TextField`, `ChoicePicker`, and richer
data-bound forms should be added only when the answer/resume contract is
implemented end-to-end.

## Static-web Example

For a user asking to provision a static web app, the workflow may need
details that a layman does not recognize as `frontend_artifact_uri` or
`frontend_hostname`.

The workflow should surface a generated card like:

```text
Input needed

To prepare this static website, provide two details:
1) where the built frontend package is, for example
   s3://releases/invoices-ui.tar.gz
2) the website address users should open, for example
   invoices.dev.example.com

Need help with these details?

Built frontend package: where your compiled website files are stored.
Website address: the domain users should open.
If you do not have a custom domain yet, say:
use the generated CloudFront URL for now.
If you only have source code, say where it is.
```

The browser should not contain a React component named
`StaticWebProvisionQuestion`. It should only host the generated A2UI
surface.

## Frontend Layout

Frontend React code should be mostly global shell and renderer hosting:

```text
frontend/src/
  App.tsx                         session grid / app shell
  FloatingSessionPanel.tsx        current local-dev session chrome
  components/
    a2ui/
      ActiveSurfaceSlot.tsx       centered host for active A2UI surfaces
  lib/
    agui.ts                       AG-UI client, event processing, thread state
    threadManager.ts              local thread registry
    sessionPresentation.ts        status/label helpers
    storage.ts                    localStorage helpers
```

Future cleanup can move `FloatingSessionPanel.tsx` under
`components/session/`, but this slice avoids broad file moves while the
UI is still changing quickly.

Workflow-specific UI should normally live server-side as spec builders:

```text
workflows/provision/
  ui.py        provision-specific DynamicUISpec builders, later
```

Shared UI compilers/adapters live in:

```text
interaction/
  dynamic_ui.py   typed UI specs and A2UI compiler
  a2ui.py         event-to-surface adapter
```

## LLM Generation Boundary

When LLM-generated UI is introduced, the LLM output must be parsed into
a Pydantic model like `DynamicCardSpec`.

Rules:

- If validation fails, fall back to a deterministic generic clarification
  card.
- The LLM cannot name component types directly.
- The LLM cannot provide CSS, HTML, scripts, URLs to remote JS, or event
  handler code.
- The server chooses the A2UI compiler.
- The server chooses action names and resume payload keys.
- The frontend never trusts LLM content as DOM.

## Current Implementation

The current slice implements:

- `interaction/dynamic_ui.py`
  - `DynamicCardSpec`
  - `DynamicChoice`
  - `compile_dynamic_card(...)`
- `interaction/a2ui.py`
  - HITL events now build a `DynamicCardSpec` and compile it to an A2UI
    `Card`
- `frontend/src/components/a2ui/ActiveSurfaceSlot.tsx`
  - generic centered host for the active generated surface

This proves the direction without adding a free-form UI-generation LLM
step yet.

## Next Steps

1. Add a workflow-level UI builder for provision:
   `workflows/provision/ui.py`.
2. Add a richer form spec only after resume can carry structured field
   values, not just chat text or choice buttons.
3. Allow an LLM to draft `DynamicCardSpec` content behind deterministic
   validation and fallback.
4. Move more session chrome under `frontend/src/components/session/`
   once the interaction model stabilizes.
