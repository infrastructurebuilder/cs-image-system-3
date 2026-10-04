# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

output "volume_id" {
  value = aws_ebs_volume.this.id
}

output "volume_arn" {
  value = aws_ebs_volume.this.arn
}
