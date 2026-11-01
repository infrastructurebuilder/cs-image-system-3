# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

data "aws_ami" "this" {
  count       = var.ami_id == "" ? 1 : 0
  most_recent = true
  owners      = ["self"]

  filter {
    name   = "name"
    values = [var.ami_name_pattern]
  }
}

locals {
  ami_id = var.ami_id != "" ? var.ami_id : data.aws_ami.this[0].id
}

resource "aws_instance" "this" {
  ami                         = local.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id != "" ? var.subnet_id : null
  associate_public_ip_address = var.associate_public_ip_address
  vpc_security_group_ids      = length(var.vpc_security_group_ids) > 0 ? var.vpc_security_group_ids : null
  iam_instance_profile        = var.iam_instance_profile != "" ? var.iam_instance_profile : null
  user_data                   = var.user_data != "" ? var.user_data : null
  tags                        = merge({ Name = var.name }, var.tags)

  # Upgrades are intentional (DESIGN §3F5): a running instance keeps its
  # ORIGINAL image until deliberately replaced. Even an erroneous
  # regeneration with a newer AMI must not replace it via apply; only an
  # explicit upgrade (plan -replace) moves an instance.
  lifecycle {
    ignore_changes = [ami, user_data]
  }
}

resource "aws_volume_attachment" "this" {
  for_each    = var.ebs_volumes
  device_name = each.value.device_name
  volume_id   = each.value.volume_id
  instance_id = aws_instance.this.id
}

