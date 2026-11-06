# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

locals {
  share_name = replace(var.name, "-", "_")
}

resource "google_filestore_instance" "this" {
  name     = var.name
  location = var.zone
  tier     = var.tier
  labels   = merge(var.labels, { csis_groups = join("-", var.group_subtrees), csis_public_read = tostring(var.public_read) })

  file_shares {
    capacity_gb = var.capacity_gb
    name        = local.share_name
  }

  networks {
    network = var.network
    modes   = ["MODE_IPV4"]
  }
}
