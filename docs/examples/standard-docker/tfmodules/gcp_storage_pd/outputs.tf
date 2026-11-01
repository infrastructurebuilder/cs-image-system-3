# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "disk_id" {
  value = google_compute_disk.this.id
}

output "self_link" {
  value = google_compute_disk.this.self_link
}

output "name" {
  value = google_compute_disk.this.name
}
