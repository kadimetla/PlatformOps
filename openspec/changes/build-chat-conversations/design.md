# Design

## Context

`build-chat-workflow-context` owns a user's active conversational focus and
workflow-run selection. This change supplies durable named threads for finding
that work again. A conversation is personal navigation/history; a workflow run
remains the durable lifecycle record and a PlatformOps Project remains a
governance container.

## Goals / Non-Goals

**Goals:** owner-private conversations, generated safe titles, user rename and
archive, safe list projections, and links to originating workflow runs.

**Non-Goals:** shared/group chat, folders, chat-based grants, automatic cloud
scope selection, or using titles as authoritative request data.

## Decisions

### Conversations are owner-private and distinct from operational objects

Each conversation has an immutable ID, `owner_subject`, title, title source
(`generated` or `user_edited`), optional server-authorized organization
reference, primary context, and archive state. It may reference workflow runs.
Messages belong to one conversation. A conversation never stores roles, grants,
provider data, credentials, approval authority, or raw workflow checkpoints.

### Titles are convenience metadata

The system creates a conservative initial title from the first meaningful
request. The owner may rename it. A title is not used for intent,
authorization, resource selection, audit decisions, or provider routing.

### Workflow and Inbox links are references

A workflow run stores an optional originating `conversation_id`; a conversation
may display a safe run summary. Reviewer tasks may link back to an originating
conversation, but reviewer Inbox filtering and approval authorization are
derived from task records and live authorization, not conversation ownership.

## Migration Plan

1. Define strict schemas and PostgreSQL owner-scoped persistence.
2. Add create/list/rename/archive/read boundaries with ownership tests.
3. Link new chat workflow runs to conversations and render a safe navigation
   drawer.
