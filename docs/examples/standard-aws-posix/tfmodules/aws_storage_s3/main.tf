# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "this" {
  bucket        = var.bucket_name
  force_destroy = var.force_destroy
  tags          = merge({ Name = var.bucket_name }, var.tags)
}

resource "aws_s3_object" "group_prefix" {
  for_each = toset(var.group_prefixes)
  bucket   = aws_s3_bucket.this.id
  key      = "${each.value}/"
  content  = ""
  tags     = { "csis:group" = each.value }
}

data "aws_iam_policy_document" "public_read" {
  count = var.public_read ? 1 : 0

  statement {
    sid       = "AccountWideReadOnly"
    actions   = ["s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:PrincipalAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_s3_bucket_policy" "public_read" {
  count  = var.public_read ? 1 : 0
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.public_read[0].json
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  count  = length(var.lifecycle_rules) > 0 ? 1 : 0
  bucket = aws_s3_bucket.this.id
  dynamic "rule" {
    for_each = var.lifecycle_rules
    content {
      id     = rule.value.id
      status = "Enabled"
      filter {
        prefix = rule.value.prefix
      }
      dynamic "transition" {
        for_each = rule.value.transition_days > 0 ? [1] : []
        content {
          days          = rule.value.transition_days
          storage_class = rule.value.storage_class
        }
      }
      dynamic "expiration" {
        for_each = rule.value.expire_days > 0 ? [1] : []
        content {
          days = rule.value.expire_days
        }
      }
    }
  }
}
