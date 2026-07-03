#!/usr/bin/env bash
# Destroys all demo resources created by the platformops agent.
# Run this immediately after recording the demo video.
set -euo pipefail

PREFIX="platformops-demo-"
REGION="${AWS_REGION:-us-east-1}"

echo "Looking for S3 buckets matching ${PREFIX}*..."
for bucket in $(aws s3api list-buckets --query "Buckets[?starts_with(Name, '${PREFIX}')].Name" --output text); do
  echo "Emptying and deleting bucket: ${bucket}"
  aws s3 rm "s3://${bucket}" --recursive
  aws s3api delete-bucket --bucket "${bucket}" --region "${REGION}"
done

echo "Looking for CloudFront distributions tagged for this demo..."
for dist_id in $(aws cloudfront list-distributions \
    --query "DistributionList.Items[?starts_with(Comment, 'platformops demo')].Id" \
    --output text); do
  echo "Disabling distribution ${dist_id} (must be disabled before deletion; may need a re-run once disabled)"
  etag=$(aws cloudfront get-distribution-config --id "${dist_id}" --query ETag --output text)
  config=$(aws cloudfront get-distribution-config --id "${dist_id}" --query DistributionConfig)
  echo "${config}" | jq '.Enabled = false' > /tmp/dist-config.json
  aws cloudfront update-distribution --id "${dist_id}" --if-match "${etag}" \
    --distribution-config file:///tmp/dist-config.json
  echo "Distribution ${dist_id} disabled — wait for deployment, then delete manually with:"
  echo "  aws cloudfront delete-distribution --id ${dist_id} --if-match <new-etag>"
done

echo "Teardown pass complete. Re-run after CloudFront distributions finish disabling to delete them."
