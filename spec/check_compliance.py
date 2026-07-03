"""Checks a structured infra spec (YAML) against the Given/When/Then rules in
reference_architecture.md. Mechanical, deterministic — no LLM call needed for
this MVP's compliance checks; an agent can call this as a tool.
"""
import os
import sys

import yaml

APPROVED_REGION = os.environ.get("AWS_REGION", "us-east-1")
MAX_COST = float(os.environ.get("MAX_ESTIMATED_MONTHLY_COST_USD", "5"))
NAME_PREFIX = "platformops-demo-"


def check_compliance(spec: dict) -> list[str]:
    """Return a list of failure reasons; empty list means the spec passes."""
    failures = []

    if spec.get("region") != APPROVED_REGION:
        failures.append("resource targets a non-approved region")

    if spec.get("estimated_monthly_usd", 0) > MAX_COST:
        failures.append("spec exceeds approved cost ceiling")

    for resource in spec.get("resources", []):
        name = resource.get("name", "")
        if not name.startswith(NAME_PREFIX):
            failures.append(f"resource name violates naming convention: {name}")

        if resource.get("type") == "s3_bucket" and resource.get("public_write"):
            failures.append(f"public write access is prohibited: {name}")

        if resource.get("type") == "cloudfront_distribution":
            policy = resource.get("viewer_protocol_policy")
            if policy not in ("redirect-to-https", "https-only"):
                failures.append(f"viewer traffic is not forced to HTTPS: {name}")

    return failures


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "spec/example_submission.yaml"
    with open(path) as f:
        spec = yaml.safe_load(f)

    failures = check_compliance(spec)
    if failures:
        print("FAIL")
        for reason in failures:
            print(f"  - {reason}")
        sys.exit(1)
    print("PASS")
