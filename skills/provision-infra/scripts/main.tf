# Terraform template for provision-infra's deterministic zero-LLM path
# (workflows/drafting/skill_fill.py's run_deterministic_skill_fill()).
# Scoped to the one case metadata.resource_types declares: a single S3
# bucket, matching spec/example_submission.yaml's shape and
# spec/check_compliance.py's rules (platformops-demo- name prefix, no
# public write access).

variable "bucket_name" {
  type = string
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
