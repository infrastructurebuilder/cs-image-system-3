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

# The mount targets and the group that reaches them (stage 19). The ingress is
# group-to-group: the clients' own security groups are named as the source, so
# nothing is opened to a CIDR and no existing group is modified.
resource "aws_security_group" "mount_targets" {
  count       = length(var.mount_target_subnet_ids) > 0 && var.vpc_id != "" ? 1 : 0
  name_prefix = "csis-efs-${var.name}-"
  description = "NFS to EFS ${var.name} from the declared client security groups"
  vpc_id      = var.vpc_id
  tags        = merge({ Name = "csis-efs-${var.name}" }, var.tags)

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group_rule" "mount_target_nfs" {
  count                    = length(aws_security_group.mount_targets) > 0 ? length(var.client_security_group_ids) : 0
  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = aws_security_group.mount_targets[0].id
  source_security_group_id = var.client_security_group_ids[count.index]
  description              = "NFS from a declared client security group"
}

resource "aws_efs_mount_target" "this" {
  count           = length(aws_security_group.mount_targets) > 0 ? length(var.mount_target_subnet_ids) : 0
  file_system_id  = local.file_system_id
  subnet_id       = var.mount_target_subnet_ids[count.index]
  security_groups = [aws_security_group.mount_targets[0].id]
}
