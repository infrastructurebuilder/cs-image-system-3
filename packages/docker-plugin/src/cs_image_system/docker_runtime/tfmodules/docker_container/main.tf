# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

# The newest image under the series' floating tag, when no build is pinned
# (a deferred provider-specific image: the bake moves the tag).
data "docker_image" "floating" {
  count = var.image == "" ? 1 : 0
  name  = var.image_tag
}

locals {
  image  = var.image != "" ? var.image : data.docker_image.floating[0].id
  labels = merge(var.labels, { csis_build = local.image })
}

resource "docker_container" "this" {
  name     = var.name
  hostname = var.hostname
  image    = local.image

  # No init system: the image's keepalive runs
  # under --init, and the launch work arrives by exec after the apply.
  init    = true
  command = length(var.command) > 0 ? var.command : null

  # The power state is the operator's: a container the operator
  # stopped is left stopped by the next apply (must_run = false, proved
  # against the provider before anything else), and comes back
  # with the daemon only if it was running (unless-stopped).
  must_run = false
  start    = true
  restart  = var.restart

  network_mode = var.network
  cpus         = var.cpus != "" ? var.cpus : null
  memory       = var.memory > 0 ? var.memory : null

  destroy_grace_seconds = var.destroy_grace_seconds

  dynamic "labels" {
    for_each = local.labels
    content {
      label = labels.key
      value = labels.value
    }
  }

  dynamic "volumes" {
    for_each = var.volumes
    content {
      volume_name    = volumes.value.volume_name
      container_path = volumes.value.container_path
    }
  }

  dynamic "upload" {
    for_each = var.launch_script != "" ? [1] : []
    content {
      content    = var.launch_script
      file       = "/var/lib/csis/launch.sh"
      executable = true
    }
  }

  # Upgrades are intentional (DESIGN §3F5): a standing container keeps its
  # ORIGINAL image until deliberately replaced (plan -replace). Labels and
  # the uploaded script are fixed when the container is created (a change
  # would re-create it: relabel reports, an upgrade re-creates), and the
  # daemon computes memory_swap from memory.
  lifecycle {
    ignore_changes = [image, labels, upload, memory_swap]
  }
}
