# Crossplane vs. Terraform/CDK — What to Borrow, What to Refuse

## Status
Reference/analysis doc, not a build proposal. Grounds Crossplane's
actual mechanics (not assumed from the name) against Terraform/CDK,
then makes a specific, narrow recommendation: borrow its Composition/
Claim *pattern*, refuse its continuous-reconciliation *execution
model*, because that model conflicts directly with this project's
approval-gate design. Nothing here is built; no code changes proposed.

## Part A: What Crossplane actually is
A Kubernetes-native **control plane**, not a CLI tool run periodically.
It extends the Kubernetes API with CRDs representing cloud resources —
an `RDSInstance` or `Bucket` becomes a Kubernetes object, `kubectl
apply`-able like a `Deployment`. Three layers:
1. **Providers** — one per cloud (AWS, GCP, Azure), handling auth and
   API translation. Already confirmed in
   `docs/account_vending_machine_design.md` Part C: these provision
   resources *within* an existing account, not the account itself.
2. **Managed Resources** — CRDs mapping 1:1 to individual cloud
   resources.
3. **Compositions/XRDs/Claims** — the self-service abstraction layer,
   Part C below — the part actually relevant to this project.

## Part B: The fundamental difference — execution model, not syntax
| | Terraform | CDK | Crossplane |
|---|---|---|---|
| Triggered by | CLI command (`plan`/`apply`), on-demand | Synthesizes to CloudFormation; CFN deploys | **Continuously running Kubernetes controllers** |
| State | A state file, external to the resources | CloudFormation's own managed state | **No state file — the Kubernetes API/etcd itself is the state** |
| Drift handling | *"Only detected and fixed when you run `terraform plan`/`apply`"* | CFN drift detection exists, not a background loop by default | *"Continuously watches your live cloud environment... automatically restores infrastructure to its declared state"* |

Concretely: if someone manually deletes a database Terraform created,
nothing happens until the next `apply`. If Crossplane created it, its
controller notices within its reconciliation loop and **recreates it
automatically, unasked**.

## Part C: Compositions, XRDs, Claims — the part worth borrowing
- A **platform team** publishes a `CompositeResourceDefinition` (schema
  of a new internal API, e.g. "give me a production-grade database")
  plus a **Composition** (what that expands into underneath — VPC,
  subnet, security group, the RDS instance, wired together).
- An **application team** submits a lightweight **Claim** in their own
  namespace — a few fields — and Crossplane provisions the full
  Composite Resource and everything it depends on.
- **Multiple Compositions can back one XRD**, selected by environment/
  tier — *"a Composition can act like a class of service with
  different configurations for different environments"* — one abstract
  request, dev gets a small instance, prod gets multi-AZ.

This is functionally the same shape as `docs/iac_based_discovery.md`'s
`IacSourceRef` resolving to an org-level shared Terraform module
(`acme/landing-zone/aws`) — a platform team defines the implementation
once, BUs consume a narrow interface. Crossplane didn't invent this
pattern for this project; it's independent confirmation the pattern is
sound, expressed via Kubernetes CRDs instead of Terraform module
instantiation. Worth treating as validation, not as a reason to switch
tools.

## Part D: The tension that rules out adopting the execution model
Crossplane's core value — automatic, continuous, unattended self-
healing — is in **direct conflict** with this project's core value:
nothing mutates without passing through `BrokeredToolDispatcher.evaluate_intent()`'s
deny-by-default gate with a recorded `ApprovalRecord`
(`harness/tool_dispatcher.py`). If Crossplane silently recreates a
manually-deleted resource, that mutation happens **entirely outside**
the dispatcher — no `PlanRecord`, no `ApprovalRecord`, no audit row.

**This is not a reason to dismiss Crossplane's ideas** — the
Composition/Claim pattern (Part C) is still worth keeping — **it is a
reason to refuse the runtime specifically.** Adopting Crossplane's
execution model wholesale would mean either disabling the exact
behavior that makes it valuable (defeating the point of using it), or
fundamentally rearchitecting the approval-gate philosophy every doc in
this set has been built around. Borrow the pattern (platform-defined
abstraction, app-consumed narrow interface, environment-tiered
implementations); refuse the runtime (continuous reconciliation
bypassing the dispatcher).

## Open questions / not yet decided
- Whether a Crossplane-inspired "Composition" concept should be
  designed as a formal PlatformOps artifact (a schema + resolution
  layer analogous to `IacSourceRef`, but multi-implementation like
  Crossplane's multiple-Compositions-per-XRD) or whether the existing
  `IacSourceRef`/skill-precedence mechanisms already cover this well
  enough — not decided.
- Whether any narrow, specifically-scoped use of actual Crossplane
  (e.g., only for read-only drift *detection*, feeding findings back
  into the dispatcher rather than auto-correcting) could sidestep the
  Part D tension — not designed, flagged as a possible middle ground
  worth a future look.

## How this relates to the existing docs
- Extends `docs/account_vending_machine_design.md` Part C's brief
  Crossplane mention (Provider/`ProviderConfig` separation) into a full
  comparison.
- Validates, doesn't replace, `docs/iac_based_discovery.md`'s
  `IacSourceRef` org→BU precedence design — Crossplane's
  Composition/Claim model is independent confirmation of the same
  shape.
- Explicitly does not change
  `harness/tool_dispatcher.py`'s deny-by-default design — Part D is the
  reasoning for why not.
- Doesn't change the one required next step
  (`plan_request(envelope)`, `docs/planned_implementation.md` Phase 3).

## Sources
- [Providers · Crossplane docs](https://docs.crossplane.io/latest/packages/providers/)
- [Composite Resource Definitions · Crossplane docs](https://docs.crossplane.io/latest/composition/composite-resource-definitions/)
- [Why We Looked Beyond Terraform: Crossplane vs Terraform at Scale — CloudKeeper](https://www.cloudkeeper.com/insights/blog/why-we-looked-beyond-terraform-crossplane-vs-terraform-scale)
- [Terraform vs. Crossplane: a practical comparison — Paolo Salvatori, Medium](https://medium.com/@paolo.salvatori/terraform-vs-crossplane-a-practical-comparison-992dc9745e08)
