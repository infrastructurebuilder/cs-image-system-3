# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

data "google_compute_image" "family" {
  count  = var.image == "" ? 1 : 0
  family = var.image_family
}

locals {
  image = var.image != "" ? var.image : data.google_compute_image.family[0].self_link
}

resource "google_compute_instance" "this" {
  name         = var.name
  zone         = var.zone
  machine_type = var.machine_type
  tags         = var.network_tags
  labels       = var.labels

  boot_disk {
    initialize_params {
      image = local.image
    }
  }

  dynamic "attached_disk" {
    for_each = var.attached_disks
    content {
      source      = attached_disk.value.disk_self_link
      device_name = attached_disk.value.device_name
    }
  }

  network_interface {
    subnetwork = var.subnetwork != "" ? var.subnetwork : null
    dynamic "access_config" {
      for_each = var.public_ip ? [1] : []
      content {}
    }
  }

  metadata = var.startup_script != "" ? { startup-script = var.startup_script } : {}

  # Upgrades are intentional (DESIGN §3F5): a running instance keeps its
  # ORIGINAL image until deliberately replaced (plan -replace).
  lifecycle {
    ignore_changes = [boot_disk[0].initialize_params[0].image, metadata]
  }
}
