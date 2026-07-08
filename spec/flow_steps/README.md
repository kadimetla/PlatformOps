# Flow-Step Specs

One spec per harness pipeline stage, in execution order. See
`docs/flow_step_spec_decomposition.md` for why this layer exists and
how it differs from `spec/reference_architecture.md` (that file checks
a submitted resource spec's *content*; these check the *pipeline
stages* a request moves through).

| # | File | Step |
|---|---|---|
| 1 | `01_request_intake.md` | Request intake & normalization |
| 2 | `02_binding_resolution.md` | Binding & context resolution |
| 3 | `03_deterministic_preflight.md` | Deterministic preflight |
| 4 | `04_plan_drafting.md` | Plan drafting |
| 5 | `05_security_review.md` | Security review |
| 6 | `06_human_approval_gate.md` | Human approval gate (conditional) |
| 7 | `07_tool_intent_dispatch.md` | `ToolIntent` dispatch |
| 8 | `08_execution_and_audit.md` | Execution + audit |
