# Tasks

## 1. Shell and navigation

- [ ] 1.1 Inspect current React/AG-UI/A2UI components and define typed view models.
- [ ] 1.2 Build responsive navigation rail, centered transcript, header, and persistent composer.
- [ ] 1.3 Add accessible loading, error, empty, and disconnected states.

## 2. Conversations and contexts

- [ ] 2.1 Connect server-owned conversation list/create/rename/archive projections.
- [ ] 2.2 Render safe identity/organization/context header projections and context switching.
- [ ] 2.3 Preserve conversation and active context across workflow navigation.

## 3. Typed workflow surfaces

- [ ] 3.1 Render validated status, form, selector, and review-card A2UI surfaces.
- [ ] 3.2 Implement guest/login return-to-conversation without exposing browser credentials.
- [ ] 3.3 Add workflow progress/context side panel and safe failure recovery.

## 4. Work and architecture review

- [ ] 4.1 Add Work navigation and server-projected queues for My requests,
  Needs my review, Needs my action, Architecture reviews, and Completed;
  delegate actions to workflow-owned handlers.
- [ ] 4.2 Render architecture-review findings, citations, and request-change actions as non-mutating surfaces.

## 5. Verification

- [ ] 5.1 Add component and browser-flow tests for guest, authenticated, context, form, and review states.
- [ ] 5.2 Verify accessibility, responsive behavior, safe rendering, and AG-UI/A2UI event contracts.
- [ ] 5.3 Run frontend build, focused tests, and `openspec validate build-workflow-chat-ui --strict`.
