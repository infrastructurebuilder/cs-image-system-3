# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "volume_id" {
  value = docker_volume.this.id
}

output "volume_name" {
  value = docker_volume.this.name
}

output "mountpoint" {
  value = docker_volume.this.mountpoint
}
