# Design

## Ownership map

| Concern | Owning OpenSpec change |
|---|---|
| browser cookie/session and CSRF boundary | `build-browser-session-auth` |
| browser AG-UI transport migration | `unify-browser-agui-control-plane` |
| guest routing and active chat context | `build-chat-workflow-context` |
| durable conversations | `build-chat-conversations` |
| V2 React shell and workflow surfaces | `build-workflow-chat-ui` |
| durable role-aware Work Items | `build-work-items` |
| personal preferences and governance Settings | `build-context-and-settings` |

This change coordinates integration only. Referenced changes remain the
authoritative owner of their data model, authorization rules, and task detail.

## Delivery sequence

```text
1. browser session transport
   -> 2. guest login and safe identity refresh
      -> 3. durable conversations
         -> 4. V2 Chat shell
            -> 5. context and resumable runs
               -> 6. Work Item projection and Work UI
                  -> 7. preferences and Settings
```

Steps must not be collapsed by placing authority or persistence temporarily in
the browser. A later UI slice may use fixtures for layout tests, but it cannot
be called functional until its server-owned projection and authorization
boundary exist.

## First vertical slice

The first end-to-end browser slice is:

```text
Guest opens Chat
  -> /login renders a safe typed email surface
  -> passwordless confirmation issues an HttpOnly browser cookie
  -> browser receives only the CSRF proof needed for same-origin mutation
  -> safe identity/context projection refreshes
  -> user creates or returns to an owner-private durable conversation
  -> V2 Chat shell sends and resumes AG-UI runs
```

This slice uses no cloud provider credential, binding, target decision, Work
Item, or governed-setting mutation. A guest never sees an authorized context
or Work queue. The browser never receives a JWT.

## Later slice boundaries

Work starts only after a server-owned Work Item registry can return
authorization-filtered rows/counts and workflow actions can re-check live
eligibility. Settings starts with personal preferences and read-only effective
governance projections; governed setting mutations wait for their separate
workflow, revision, audit, and approval boundaries.
