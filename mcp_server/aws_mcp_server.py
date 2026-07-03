"""Minimal MCP server exposing a narrow AWS surface: static-site provisioning only.

Every tool re-checks the IAM allow-list and cost ceiling itself — the security
agent's approval is a gate upstream, this is defense-in-depth downstream.

NOTE: the CloudFront DistributionConfig below is simplified for scaffolding.
Verify required fields against the current boto3 CloudFront API before
running this against a real account.
"""
import json
import os

import boto3
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("aws-platformops")

REGION = os.environ.get("AWS_REGION", "us-east-1")
MAX_COST = float(os.environ.get("MAX_ESTIMATED_MONTHLY_COST_USD", "5"))
NAME_PREFIX = "platformops-demo-"
IAM_POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "infra", "iam-policy.json")


def _allowlisted_actions() -> set[str]:
    with open(IAM_POLICY_PATH) as f:
        policy = json.load(f)
    actions: set[str] = set()
    for stmt in policy.get("Statement", []):
        actions.update(stmt.get("Action", []))
    return actions


@mcp.tool()
def estimate_cost(app_name: str, traffic_tier: str = "low") -> dict:
    """Estimate monthly USD cost for an S3 + CloudFront static site at a given traffic tier."""
    tier_cost = {"low": 1.0, "medium": 3.5, "high": 9.0}
    cost = tier_cost.get(traffic_tier, tier_cost["low"])
    return {
        "app_name": app_name,
        "estimated_monthly_usd": cost,
        "within_ceiling": cost <= MAX_COST,
    }


@mcp.tool()
def create_static_site(app_name: str, traffic_tier: str = "low", approved: bool = False) -> dict:
    """Create an S3 bucket + CloudFront distribution for a static site.

    Requires approved=True, set only after the security_agent has reviewed
    the plan via the security-review-checklist skill.
    """
    if not approved:
        return {"status": "rejected", "reason": "security_agent approval required before execution"}

    required_actions = {"s3:CreateBucket", "s3:PutBucketWebsite", "cloudfront:CreateDistribution"}
    missing = required_actions - _allowlisted_actions()
    if missing:
        return {"status": "rejected", "reason": f"actions not allow-listed: {sorted(missing)}"}

    est = estimate_cost(app_name, traffic_tier)
    if not est["within_ceiling"]:
        return {
            "status": "rejected",
            "reason": f"estimated cost {est['estimated_monthly_usd']} exceeds ceiling {MAX_COST}",
        }

    bucket_name = f"{NAME_PREFIX}{app_name}".lower()

    s3 = boto3.client("s3", region_name=REGION)
    s3.create_bucket(Bucket=bucket_name)
    s3.put_bucket_website(Bucket=bucket_name, WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"}})

    cloudfront = boto3.client("cloudfront")
    distribution = cloudfront.create_distribution(
        DistributionConfig={
            "CallerReference": bucket_name,
            "Origins": {
                "Quantity": 1,
                "Items": [
                    {
                        "Id": bucket_name,
                        "DomainName": f"{bucket_name}.s3-website-{REGION}.amazonaws.com",
                        "CustomOriginConfig": {
                            "HTTPPort": 80,
                            "HTTPSPort": 443,
                            "OriginProtocolPolicy": "http-only",
                        },
                    }
                ],
            },
            "DefaultCacheBehavior": {
                "TargetOriginId": bucket_name,
                "ViewerProtocolPolicy": "redirect-to-https",
                "TrustedSigners": {"Enabled": False, "Quantity": 0},
                "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
                "MinTTL": 0,
            },
            "Enabled": True,
            "Comment": f"platformops demo site for {app_name}",
        }
    )
    return {
        "status": "created",
        "bucket": bucket_name,
        "distribution_id": distribution["Distribution"]["Id"],
        "domain_name": distribution["Distribution"]["DomainName"],
    }


@mcp.tool()
def get_deployment_status(distribution_id: str) -> dict:
    """Check the deployment status of a CloudFront distribution."""
    cloudfront = boto3.client("cloudfront")
    resp = cloudfront.get_distribution(Id=distribution_id)
    return {
        "status": resp["Distribution"]["Status"],
        "domain_name": resp["Distribution"]["DomainName"],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
