# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "workload_identity_provider" {
  value       = local.provider_name
  description = "the provider's full resource name: the GCP_WORKLOAD_IDENTITY_PROVIDER secret"
}

output "read_service_account" {
  value       = local.read_email
  description = "the READ-ONLY service account's address: the GCP_SERVICE_ACCOUNT secret"
}

output "write_service_account" {
  value       = var.want_write ? local.write_email : local.read_email
  description = "the address CI may write as: the WRITE account's, or the READ-ONLY one's when CI performs on no GCE runtime (CI_SETUP.md 3.4 step 4)"
}
