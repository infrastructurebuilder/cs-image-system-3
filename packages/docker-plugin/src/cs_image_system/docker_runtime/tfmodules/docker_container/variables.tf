# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

variable "name" {
  description = "Container name (the instance's declared name; unique on the daemon)"
  type        = string
}

variable "hostname" {
  description = "The machine's canonical name (<name>-NNN): the container is created with it"
  type        = string
}

variable "image" {
  description = "Concrete image id (the pinned build, sha256:...); empty = the newest image under image_tag"
  type        = string
  default     = ""
}

variable "image_tag" {
  description = "The series' floating tag (<repository>:<prefix>) used when image is empty (deferred provider-specific images)"
  type        = string
  default     = ""
}

variable "network" {
  description = "The daemon network the container joins, by name; referenced, never created"
  type        = string
  default     = "bridge"
}

variable "cpus" {
  description = "CPU limit as the daemon spells it back (\"1.0\", \"0.5\"); empty = unlimited"
  type        = string
  default     = ""
}

variable "memory" {
  description = "Memory limit in MB; 0 = unlimited"
  type        = number
  default     = 0
}

variable "restart" {
  description = "Restart policy: a stopped container stays stopped (the power state is the operator's), a daemon restart brings a running one back"
  type        = string
  default     = "unless-stopped"
}

variable "command" {
  description = "The container's command; empty = the image's own (the baked keepalive)"
  type        = list(string)
  default     = []
}

variable "labels" {
  description = "Labels fixed at creation: the configuration id, the instance, the generation; csis_build is added from the image"
  type        = map(string)
  default     = {}
}

variable "volumes" {
  description = "Per-instance volume mounts (N16): storage name -> { volume_name, container_path }; the daemon mounts them before the first command"
  type = map(object({
    volume_name    = string
    container_path = string
  }))
  default = {}
}

variable "launch_script" {
  description = "Launch parameters (DESIGN N26): the generated script, uploaded at creation to /var/lib/csis/launch.sh and run by the system through the session after the apply; immutable after launch"
  type        = string
  default     = ""
}

variable "destroy_grace_seconds" {
  description = "Seconds a destroy waits for the container to stop before killing it"
  type        = number
  default     = 15
}
