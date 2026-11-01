# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

resource "docker_volume" "this" {
  name        = var.name
  driver      = var.driver
  driver_opts = var.driver_opts

  dynamic "labels" {
    for_each = var.labels
    content {
      label = labels.key
      value = labels.value
    }
  }

  # A volume's labels are fixed when it is created and a change would
  # REPLACE the volume -- with its data. Relabel reports; nothing re-creates.
  lifecycle {
    ignore_changes = [labels]
  }
}
