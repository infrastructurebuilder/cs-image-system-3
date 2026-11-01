# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Instance name (Name tag)"
  type        = string
}

variable "ami_id" {
  description = "Concrete AMI id; leave empty to resolve via ami_name_pattern"
  type        = string
  default     = ""
}

variable "ami_name_pattern" {
  description = "Most-recent self-owned AMI name pattern, used when ami_id is empty (deferred provider-specific images)"
  type        = string
  default     = ""
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "subnet_id" {
  type    = string
  default = ""
}

variable "associate_public_ip_address" {
  type    = bool
  default = true
}

variable "vpc_security_group_ids" {
  description = "Security groups for the instance; empty = the subnet's default group"
  type        = list(string)
  default     = []
}

variable "iam_instance_profile" {
  description = "Instance profile for the runtime's session mechanism (e.g. SSM); empty = none"
  type        = string
  default     = ""
}

variable "user_data" {
  description = "Launch parameters (DESIGN N26): generated cloud-init script; immutable after launch"
  type        = string
  default     = ""
}

variable "ebs_volumes" {
  description = "Per-instance EBS attachments (N16): storage name -> { volume_id, device_name }"
  type = map(object({
    volume_id   = string
    device_name = string
  }))
  default = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}
