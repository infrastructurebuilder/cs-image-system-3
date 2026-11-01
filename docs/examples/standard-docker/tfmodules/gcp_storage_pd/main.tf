# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

resource "google_compute_disk" "this" {
  name     = var.name
  zone     = var.zone
  size     = var.size
  type     = var.disk_type
  labels   = var.labels
  snapshot = var.snapshot != "" ? var.snapshot : null

  # The source snapshot is a creation-time fact: once the disk exists (and
  # the snapshot is deleted after a restore) a later plan must not replace it.
  lifecycle {
    ignore_changes = [snapshot]
  }
}
