# Design

## Decision

Retrieved knowledge is advisory context only. It can explain, cite, and
recommend; it cannot authorize a principal, resolve a provider binding,
approve a plan, or trigger execution.

## Knowledge catalog

Each source has immutable ID, title, source URI, owner, classification,
provider/service tags, applicability tags, review date, expiry date, and a
content checksum. PostgreSQL stores metadata and lifecycle state; object
storage stores source content. A search index stores chunk text and embeddings.
Expired, unreviewed, or unauthorized sources are excluded before ranking.

## Retrieval

The chat/workflow caller submits an advisory query plus trusted actor and
context. Retrieval filters classification and applicability first, then ranks
keyword/vector matches. Results carry source ID, title, URI, review date, and
quoted excerpt limits. The caller must present citations and label the result
as guidance.

## Architecture and diagram review

Architecture review is its own workflow:

```text
submitted diagram/spec
  -> structural parsing and reference-architecture checks
  -> optional advisory knowledge retrieval
  -> findings with source citations and severity
  -> reviewer acknowledgement / change request
```

It has no provider credentials, no mutation tools, and no approval authority.
It may create a reviewer-Inbox task, but acceptance of a diagram never approves
a provision plan. Deterministic diagram rules remain code-level checks; an LLM,
if introduced later, may summarize findings but cannot decide compliance.

## Ingestion lifecycle

An authorized curator submits a source, classification, owner, and expiry.
Validation, malware/content scanning, chunking, indexing, and publication are
separate states. Updates create a new version; revocation immediately removes
the source from retrieval.
