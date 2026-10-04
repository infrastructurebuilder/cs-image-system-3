# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "ip_address" {
  value = google_filestore_instance.this.networks[0].ip_addresses[0]
}

output "share_name" {
  value = local.share_name
}

output "instance_id" {
  value = google_filestore_instance.this.id
}
