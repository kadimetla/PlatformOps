# Proposal

## Why

Users need to find, name, and continue work across browser sessions without
confusing a chat thread with an organization, PlatformOps Project, target, or
approval record.

## What Changes

- Add owner-private, named conversations with generated initial titles and
  user-controlled rename/archive behavior.
- Link conversations to workflow runs without making the conversation the
  workflow's operational record.
- Add safe list/filter projections for personal conversation navigation.
- Keep shared conversation spaces, folders, and chat-derived authorization out
  of the first version.

## Capabilities

### New Capabilities

- `chat-conversations`: Owner-private named conversations that organize chat
  history and link safely to workflow runs.

### Modified Capabilities

(none)

## Impact

- PostgreSQL conversation/message metadata, chat navigation projections, and
  conversation/workflow-run references.
- No change to PlatformOps Project hierarchy, resource authorization, or
  reviewer approval authority.
