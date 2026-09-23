# Tasks

## 1. Provider connection contracts

- [ ] 1.1 Add typed provider-connection records with organization ownership, provider, boundary reference, discovery-identity reference, lifecycle state, and version; verify unit tests reject inactive/unverified use and credential material.
- [ ] 1.2 Add deterministic fake provider-adapter contracts for verification and read-only inquiry; verify tests require explicit adapter selection by trusted connection data.

## 2. Read-only container inquiry

- [ ] 2.1 Implement authorized inquiry through an active verified connection using a fake read-only adapter; verify candidate results create no binding, grant, or provider mutation.
- [ ] 2.2 Add tests constraining inquiry candidates to the configured provider boundary and excluding secret credential values.

## 3. Reviewed container attachment

- [ ] 3.1 Add attachment request and review records binding a candidate, connection, and Resource Scope; verify tests reject candidates outside the connection boundary.
- [ ] 3.2 Create an active versioned Cloud Resource Container binding only after approved attachment; verify ordinary provisioning cannot use an unreviewed candidate.

## 4. Provider-container bootstrap

- [ ] 4.1 Add a separately authorized provider-container bootstrap request with policy and approval checks; verify ordinary provisioning receives setup-required rather than creating a container.
- [ ] 4.2 Add fake-adapter tests proving a created container returns as a candidate and still requires reviewed attachment.

## 5. Live-adapter readiness and verification

- [ ] 5.1 Verify the exact AWS provider API/MCP contract, minimum permissions, and resource support against current official documentation before implementing a live adapter; record sources and tests.
- [ ] 5.2 Run fake-adapter tests and `openspec validate build-cloud-provider-service --strict`; do not enable a live provider adapter by default.
