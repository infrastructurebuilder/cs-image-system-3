# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "bucket" {
  value = google_storage_bucket.this.name
}

output "url" {
  value = google_storage_bucket.this.url
}

output "group_prefixes" {
  value = var.group_prefixes
}
