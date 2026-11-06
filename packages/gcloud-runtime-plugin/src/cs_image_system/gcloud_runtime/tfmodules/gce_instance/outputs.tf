# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "instance_id" {
  value = google_compute_instance.this.id
}

output "internal_ip" {
  value = google_compute_instance.this.network_interface[0].network_ip
}

output "image" {
  value = local.image
}
