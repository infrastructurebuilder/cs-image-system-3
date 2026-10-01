# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "read_role_arn" {
  value       = aws_iam_role.read.arn
  description = "the READ-ONLY role's ARN: the AWS_ROLE_ARN secret"
}

output "write_role_arn" {
  value       = aws_iam_role.write.arn
  description = "the WRITE role's ARN: the AWS_APPLY_ROLE_ARN secret"
}

output "oidc_provider_arn" {
  value       = local.provider_arn
  description = "the GitHub OIDC identity provider"
}

output "state_bucket" {
  value       = var.state_bucket
  description = "the state bucket (made here only when it did not exist)"
}

output "instance_profile_arn" {
  value       = var.instance_profile_exists ? data.aws_iam_instance_profile.session[0].arn : aws_iam_instance_profile.session[0].arn
  description = "the Session Manager instance profile"
}
