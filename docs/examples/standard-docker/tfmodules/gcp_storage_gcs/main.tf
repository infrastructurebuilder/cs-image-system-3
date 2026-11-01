# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

resource "google_storage_bucket" "this" {
  name                        = var.bucket_name
  location                    = var.location
  labels                      = var.labels
  uniform_bucket_level_access = true
  force_destroy               = false
}

resource "google_storage_bucket_object" "group_prefix" {
  for_each = toset(var.group_prefixes)
  name     = "${each.value}/"
  content  = " "
  bucket   = google_storage_bucket.this.name
}
