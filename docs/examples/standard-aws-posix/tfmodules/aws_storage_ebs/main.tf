# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

data "aws_subnet" "this" {
  count = var.availability_zone == "" && var.subnet_id != "" ? 1 : 0
  id    = var.subnet_id
}

locals {
  availability_zone = var.availability_zone != "" ? var.availability_zone : data.aws_subnet.this[0].availability_zone
}

data "aws_ebs_snapshot" "archive" {
  count       = var.snapshot_name != "" ? 1 : 0
  most_recent = true
  owners      = ["self"]
  filter {
    name   = "tag:Name"
    values = [var.snapshot_name]
  }
}

resource "aws_ebs_volume" "this" {
  availability_zone = local.availability_zone
  size              = var.size
  type              = var.volume_type
  encrypted         = var.encrypted
  snapshot_id       = var.snapshot_name != "" ? data.aws_ebs_snapshot.archive[0].id : null
  tags              = merge({ Name = var.name }, var.tags)
  lifecycle {
    ignore_changes = [snapshot_id]
  }
}
