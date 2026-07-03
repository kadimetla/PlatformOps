---
name: sdlc-diagram-compliance-check
description: >
  Procedure for checking a submitted infrastructure spec against the
  company's reference architecture rules. Trigger when the user uploads or
  describes an architecture/diagram and asks whether it's compliant.
version: 0.1.0
allowed-tools:
  - check_compliance
---

# SDLC Diagram Compliance Check

## When to use this skill
The user asks "does this architecture comply with our standards?" or submits
a spec/diagram before requesting provisioning.

## Procedure

1. **Get a structured spec.** For this MVP, input is a YAML spec in the shape
   of `spec/example_submission.yaml` (see `spec/reference_architecture.md`
   for the rules it's checked against). If the user only has a diagram image,
   say explicitly that image parsing isn't implemented yet and ask for a
   structured spec instead — don't guess at the diagram's contents.
2. **Call `check_compliance`** with the spec.
3. **Report results plainly**: PASS, or FAIL with the specific list of
   violated rules — each one should map back to a named scenario in
   `spec/reference_architecture.md` so the user knows exactly what to fix.
4. **Do not auto-fix** the spec. Compliance checking and provisioning are
   separate steps — report violations and let the user (or
   provisioning_agent, on a corrected spec) act on them.
