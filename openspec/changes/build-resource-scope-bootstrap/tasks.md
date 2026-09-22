# Tasks

## 1. Resource Scope registry contracts

- [ ] 1.1 Add typed Organization, Business Unit, Team, PlatformOps Project, Environment, and Resource Scope contracts with immutable `scope_id`, canonical-path validation, and lifecycle state; verify focused unit tests cover valid paths, incomplete hierarchies, duplicate canonical paths, and stable IDs after a permitted rename.
- [ ] 1.2 Add an administrator-owned reviewed registry interface that resolves only active complete Resource Scopes by `scope_id`; verify tests reject missing, inactive, malformed, sibling, parent, and provider-default fallback resolution.
- [ ] 1.3 Add non-routable registry fixtures for dependent workflow tests without creating user, organization-claiming, provider-connection, or cloud-mutation behavior; verify the fixtures contain no cloud credentials or live provider calls.

## 2. Principal grants and governance evaluation

- [ ] 2.1 Add typed user, identity-group, and service-principal references plus role-binding contracts for principal, action set, Resource Scope or ancestor, explicit inheritance, and conditions; verify unit tests distinguish `bu` ownership records from identity groups.
- [ ] 2.2 Implement deterministic deny-by-default scope authorization using exact bindings and explicitly inheriting ancestor bindings only; verify focused tests cover no grant, exact grant, non-inheriting parent grant, inheriting parent grant, and revoked group access.
- [ ] 2.3 Implement restrictive governance-guardrail evaluation across Organization, BU, Team, Project, and Environment; verify tests show a child can narrow but cannot widen a parent provider restriction and an applicable deny overrides an allow.
- [ ] 2.4 Require scope authorization to be evaluated for every requested action rather than trusted from a saved selection; verify a previously listed or selected scope is denied after its applicable binding is revoked.

## 3. Cloud Resource Container binding resolution

- [ ] 3.1 Add typed, versioned Cloud Resource Container binding contracts containing `binding_id`, `scope_id`, provider, container type/reference, execution-identity reference, optional provider workspace, and lifecycle state; verify unit tests distinguish AWS account, GCP project, and Azure subscription references from PlatformOps Project identifiers.
- [ ] 3.2 Add registry loading and resolution for zero or more active bindings per Resource Scope; verify tests show an Organization provider connection alone cannot route an unbound scope.
- [ ] 3.3 Implement deterministic profile/provider binding selection after scope authorization; verify tests select exactly one eligible binding and return non-routable outcomes for no eligible or ambiguous bindings.
- [ ] 3.4 Ensure request, token, and model routing hints cannot override the resolved provider, container, execution identity, or workspace; verify tests demonstrate that conflicting client-supplied values never change the resolved binding.

## 4. Provision handoff and audit context

- [ ] 4.1 Define an immutable resolved Resource Scope context containing the authorized `scope_id`, canonical path, matched binding IDs, matched grant/guardrail identifiers, and scope/binding registry versions or digests; verify mutation attempts or changed registry versions require a fresh resolution.
- [ ] 4.2 Integrate the resolved context at the provision preflight boundary while preserving its non-mutating behavior; verify an end-to-end fake-registry test reaches preflight only for an active, authorized scope with exactly one resolved binding.
- [ ] 4.3 Add edge migration from the legacy `org:bu:project:workspace` hint to the canonical `env`/`scope_id` lookup without persisting `workspace`; verify compatibility tests normalize only at the boundary and reject ambiguous or incomplete legacy input.

## 5. Verification and documented boundaries

- [ ] 5.1 Add focused unit and integration test commands to the developer documentation and run the Resource Scope registry, authorization, binding-resolution, and provision-preflight tests without real model credentials or cloud access.
- [ ] 5.2 Verify that inquiry, attaching an existing Cloud Resource Container, creating a provider container, user registration, organization claiming, and frontend work remain absent from this implementation; record any newly required behavior as a separate OpenSpec change before coding it.
- [ ] 5.3 Run `openspec validate build-resource-scope-bootstrap --strict` and update the change status only after all implementation tasks and their verifications are complete.
