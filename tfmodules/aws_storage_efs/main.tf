# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

resource "aws_efs_file_system" "this" {
  count            = var.existing_file_system_id == "" ? 1 : 0
  creation_token   = var.name
  performance_mode = var.performance_mode
  encrypted        = var.encrypted
  tags             = merge({ Name = var.name }, var.tags)
  dynamic "lifecycle_policy" {
    for_each = var.transition_to_ia != "" ? [var.transition_to_ia] : []
    content {
      transition_to_ia = lifecycle_policy.value
    }
  }
  dynamic "lifecycle_policy" {
    for_each = var.transition_to_archive != "" ? [var.transition_to_archive] : []
    content {
      transition_to_archive = lifecycle_policy.value
    }
  }
}

data "aws_efs_file_system" "existing" {
  count          = var.existing_file_system_id != "" ? 1 : 0
  file_system_id = var.existing_file_system_id
}

locals {
  file_system_id = var.existing_file_system_id != "" ? data.aws_efs_file_system.existing[0].id : aws_efs_file_system.this[0].id
}

resource "aws_efs_access_point" "group" {
  for_each       = var.access_points
  file_system_id = local.file_system_id

  posix_user {
    gid = each.value.gid
    uid = 0
  }

  root_directory {
    path = each.value.path
    creation_info {
      owner_gid   = each.value.gid
      owner_uid   = 0
      permissions = each.value.permissions
    }
  }

  tags = merge({ Name = "${var.name}-${each.key}", "csis:group" = each.key }, var.tags)
}

resource "aws_efs_access_point" "public_read" {
  count          = var.public_read ? 1 : 0
  file_system_id = local.file_system_id

  root_directory {
    path = "/"
  }

  tags = merge({ Name = "${var.name}-public-read" }, var.tags)
}
