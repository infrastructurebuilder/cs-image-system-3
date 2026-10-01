# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# The AWS section of the bootstrap (cs-image-system stage 70 step 4; CI_SETUP.md 3.3):
# the GitHub OIDC identity provider, the READ-ONLY role and the WRITE role with
# their trust documents and permission policies, and -- only when the account
# lacks them -- the state bucket and the Session Manager instance profile.
# What exists is read (a data source) or adopted (an import block in the root),
# never recreated; the network is never touched.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.81"
    }
  }
}

locals {
  oidc_host = "token.actions.githubusercontent.com"
  owner     = split("/", var.repository)[0]
  name      = split("/", var.repository)[1]

  # the subject forms a token may carry (CI_SETUP.md 3.2 step 4): the plain
  # name form, and the id-bearing form of an organisation that customises it
  plain = "repo:${var.repository}"
  ids   = "repo:${local.owner}@${var.owner_id}/${local.name}@${var.repo_id}"
  forms = var.subject_forms == "both" ? [local.plain, local.ids] : (var.subject_forms == "ids" ? [local.ids] : [local.plain])

  read_subjects  = [for f in local.forms : "${f}:*"]
  write_subjects = [for f in local.forms : "${f}:ref:refs/heads/${var.production_branch}"]

  provider_arn  = var.oidc_provider_exists ? data.aws_iam_openid_connect_provider.github[0].arn : aws_iam_openid_connect_provider.github[0].arn
  instance_role = var.instance_profile_exists ? data.aws_iam_instance_profile.session[0].role_name : aws_iam_role.session[0].name
}

# ------------------------------------------------------- the identity provider
data "aws_iam_openid_connect_provider" "github" {
  count = var.oidc_provider_exists ? 1 : 0
  url   = "https://${local.oidc_host}"
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.oidc_provider_exists ? 0 : 1
  url            = "https://${local.oidc_host}"
  client_id_list = ["sts.amazonaws.com"]
}

# ------------------------------------------------------------ the READ-ONLY role
# Trusted on any ref of the repository: what a load, a dry run and the state
# query read. A dry run never touches remote state, so no state objects.
resource "aws_iam_role" "read" {
  name        = var.read_role_name
  description = "cs-image-system CI, read-only: ${var.repository} on any ref"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "${local.oidc_host}:aud" = "sts.amazonaws.com" }
        StringLike   = { "${local.oidc_host}:sub" = local.read_subjects }
      }
    }]
  })
}

resource "aws_iam_role_policy" "read" {
  name = "cs-image-system-read"
  role = aws_iam_role.read.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "Describe"
        Effect   = "Allow"
        Resource = "*"
        Action   = ["ec2:Describe*", "elasticfilesystem:Describe*", "sts:GetCallerIdentity"]
      },
      {
        Sid      = "StorageReality"
        Effect   = "Allow"
        Resource = "arn:aws:s3:::*"
        Action   = ["s3:GetBucketTagging", "s3:GetLifecycleConfiguration", "s3:GetBucketLocation"]
      },
    ]
  })
}

# ---------------------------------------------------------------- the WRITE role
# Trusted on the production branch alone, so no other branch, tag or pull
# request can hold it: what a bake, a release and retention do.
resource "aws_iam_role" "write" {
  name        = var.write_role_name
  description = "cs-image-system CI, write: ${var.repository} on ${var.production_branch} alone"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "${local.oidc_host}:aud" = "sts.amazonaws.com"
          "${local.oidc_host}:sub" = local.write_subjects
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "write" {
  name = "cs-image-system-write"
  role = aws_iam_role.write.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "BakeAndDescribe"
        Effect   = "Allow"
        Resource = "*"
        Action = [
          "ec2:Describe*", "ec2:RunInstances", "ec2:StopInstances", "ec2:TerminateInstances",
          "ec2:CreateKeyPair", "ec2:DeleteKeyPair",
          "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
          "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress",
          "ec2:CreateImage", "ec2:RegisterImage", "ec2:DeregisterImage", "ec2:CopyImage",
          "ec2:CreateSnapshot", "ec2:DeleteSnapshot", "ec2:CreateTags", "ec2:DeleteTags",
          "ec2:ModifyImageAttribute", "ec2:ModifyInstanceAttribute", "ec2:GetConsoleOutput",
          "elasticfilesystem:Describe*", "sts:GetCallerIdentity",
        ]
      },
      {
        Sid      = "StatePrefix"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = ["arn:aws:s3:::${var.state_bucket}", "arn:aws:s3:::${var.state_bucket}/${var.state_prefix}/*"]
      },
      {
        Sid    = "SessionManagerBake"
        Effect = "Allow"
        Action = "ssm:StartSession"
        Resource = [
          "arn:aws:ec2:${var.region}:${var.account_id}:instance/*",
          "arn:aws:ssm:${var.region}::document/AWS-StartSSHSession",
          "arn:aws:ssm:${var.region}::document/AWS-StartPortForwardingSession",
        ]
      },
      {
        Sid      = "SessionManagerSessions"
        Effect   = "Allow"
        Action   = ["ssm:TerminateSession", "ssm:ResumeSession"]
        Resource = "arn:aws:ssm:${var.region}:${var.account_id}:session/*"
      },
      {
        Sid      = "SessionManagerDescribe"
        Effect   = "Allow"
        Resource = "*"
        Action   = ["ssm:DescribeInstanceInformation", "ssm:GetConnectionStatus", "ssm:DescribeSessions"]
      },
      {
        Sid       = "BakeInstanceProfile"
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = "arn:aws:iam::${var.account_id}:role/${local.instance_role}"
        Condition = { StringEquals = { "iam:PassedToService" = "ec2.amazonaws.com" } }
      },
      {
        Sid      = "BakeInstanceProfileRead"
        Effect   = "Allow"
        Action   = "iam:GetInstanceProfile"
        Resource = "arn:aws:iam::${var.account_id}:instance-profile/${var.instance_profile}"
      },
    ]
  })
}

# ------------------------------------------- the state bucket, when it is absent
resource "aws_s3_bucket" "state" {
  count  = var.state_bucket_exists ? 0 : 1
  bucket = var.state_bucket
}

resource "aws_s3_bucket_versioning" "state" {
  count  = var.state_bucket_exists ? 0 : 1
  bucket = aws_s3_bucket.state[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  count  = var.state_bucket_exists ? 0 : 1
  bucket = aws_s3_bucket.state[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  count                   = var.state_bucket_exists ? 0 : 1
  bucket                  = aws_s3_bucket.state[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ------------------------------- the Session Manager instance profile, when absent
data "aws_iam_instance_profile" "session" {
  count = var.instance_profile_exists ? 1 : 0
  name  = var.instance_profile
}

resource "aws_iam_role" "session" {
  count       = var.instance_profile_exists ? 0 : 1
  name        = var.instance_profile
  description = "cs-image-system: what build and standing instances wear for Session Manager"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "session" {
  count      = var.instance_profile_exists ? 0 : 1
  role       = aws_iam_role.session[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "session" {
  count = var.instance_profile_exists ? 0 : 1
  name  = var.instance_profile
  role  = aws_iam_role.session[0].name
}
