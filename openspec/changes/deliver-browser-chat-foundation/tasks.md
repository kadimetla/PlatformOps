# Tasks

## 1. Browser session and guest entry

- [ ] 1.1 Complete `unify-browser-agui-control-plane` transport task 1.2 and
  client tasks 3.1–3.2: replace browser `/runs` file-session use with validated
  cookie/session and in-memory CSRF handling.
- [ ] 1.2 Complete `build-chat-workflow-context` tasks 3.6–3.8: typed public
  `/login`, passwordless confirmation return, and safe identity/context
  refresh.
- [ ] 1.3 Verify an unauthenticated user reaches only public routes and never
  receives target, provider, Work, or authorization data.

## 2. Durable Chat foundation

- [ ] 2.1 Complete `build-chat-conversations` contract, PostgreSQL, ownership,
  and safe navigation tasks before replacing browser-memory thread ownership.
- [ ] 2.2 Complete `build-workflow-chat-ui` shell/navigation tasks 1.1–1.3
  using safe server projections; implement the V2 responsive states.
- [ ] 2.3 Complete `build-workflow-chat-ui` guest/login and typed-surface tasks
  3.1–3.3 without exposing credentials or authorization inputs.
- [ ] 2.4 Verify guest -> login -> confirmed session -> named conversation ->
  send/resume flow end to end with fake email/model/cloud dependencies.

## 3. Context, Work, and Settings increments

- [ ] 3.1 Complete active-context persistence/switch/resume work before
  rendering a functional context switcher; preserve the project-versus-
  unresolved-environment distinction.
- [ ] 3.2 Complete the Work Item registry/projections and one workflow adapter
  before enabling Work rows/counts/actions in the browser.
- [ ] 3.3 Complete personal preferences and read-only effective-governance
  projections before enabling the Settings destination; defer governed
  mutation UI until its workflow boundary is complete.

## 4. Integration verification

- [ ] 4.1 Add browser-flow coverage for guest, login return, conversation
  ownership, context switch, responsive shell, safe A2UI surfaces, and
  disconnected/error states.
- [ ] 4.2 Validate every referenced OpenSpec change and run frontend build plus
  focused gateway/transport/persistence tests.
- [ ] 4.3 Record the completed first vertical slice and remaining later slices
  in the implementation-status document map.
