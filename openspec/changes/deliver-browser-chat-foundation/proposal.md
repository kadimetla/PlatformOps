# Proposal

## Why

The browser product has approved but separately owned session, conversation,
context, chat UI, Work, and Settings changes. Contributors need one explicit
delivery sequence that produces a useful end-to-end experience without
accidentally bypassing the existing security and workflow boundaries.

## What Changes

- Define the implementation order and integration acceptance criteria for the
  browser-chat foundation.
- Establish the first shippable vertical slice: guest login through a
  browser-cookie session into a durable conversation and V2 Chat shell.
- Make Work and Settings later dependent slices rather than frontend-only
  mock features.

## Non-Goals

This coordination change does not replace the requirements, designs, or tasks
owned by its referenced changes. It does not add cloud execution, a new
authorization path, or a generic workflow/task engine.
