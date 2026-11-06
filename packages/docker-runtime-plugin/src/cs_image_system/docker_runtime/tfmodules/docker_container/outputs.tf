# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "instance_id" {
  value = docker_container.this.id
}

output "name" {
  value = docker_container.this.name
}

output "hostname" {
  value = var.hostname
}

output "image" {
  value = local.image
}

output "internal_ip" {
  value = try(docker_container.this.network_data[0].ip_address, "")
}
