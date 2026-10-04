# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

locals {
  user_group  = "${var.group_id}_user"
  admin_group = "${var.group_id}_admin"

  # Root group: delegated admins are passed in; the root group itself passes
  # nothing and delegates to its own admin group.
  rg_delegated_admins = length(var.delegated_admin_group_ids) > 0 ? var.delegated_admin_group_ids : [oktapam_group.admin.id]

  server_labels = merge(
    {
      "system.os_type" = "linux"
      "sftd.tx.group"  = var.group_id
    },
    var.server_labels,
  )
}

resource "oktapam_group" "user" {
  name = local.user_group
}

resource "oktapam_group" "admin" {
  name = local.admin_group
}

resource "oktapam_user_group_attachment" "members" {
  for_each = toset(var.members)
  group    = oktapam_group.user.name
  username = each.value
}

resource "oktapam_user_group_attachment" "admins" {
  for_each = toset(var.admins)
  group    = oktapam_group.admin.name
  username = each.value
}

resource "oktapam_resource_group" "rg" {
  name                            = "${var.group_id}_rg"
  description                     = "Resource group for Okta group ${var.group_id}"
  delegated_resource_admin_groups = local.rg_delegated_admins
}

resource "oktapam_resource_group_project" "rg_login" {
  name              = "${var.group_id}_rg_login"
  resource_group    = oktapam_resource_group.rg.id
  account_discovery = var.account_discovery
  gateway_selector  = var.gateway_selector != "" ? var.gateway_selector : null
}

# One launch-enrollment token per project, IaC-owned (PLAN.md "IaC-managed
# server enrollment tokens"): created with the project, destroyed with it.
# An out-of-band deletion is recreated (with a NEW value) on the next apply.
resource "oktapam_resource_group_server_enrollment_token" "login" {
  resource_group = oktapam_resource_group.rg.id
  project        = oktapam_resource_group_project.rg_login.id
  description    = "cs-image-system launch enrollment for ${var.group_id} (IaC-owned; do not delete by hand)"
}

resource "oktapam_security_policy" "user" {
  name           = "${var.group_id}_v1_security_policy_user"
  description    = "Security policy for Okta group ${local.user_group}"
  active         = true
  resource_group = oktapam_resource_group.rg.id

  principals {
    groups = [oktapam_group.user.id]
  }

  rule {
    name = "allow_login_${var.group_id}"

    conditions {
      gateway {
        traffic_forwarding = true
        session_recording  = false
      }
    }

    privileges {
      principal_account_ssh {
        enabled                 = true
        admin_level_permissions = false
      }
    }

    resources {
      servers {
        label_selectors {
          server_labels = local.server_labels
        }
      }
    }
  }
}

resource "oktapam_security_policy" "admin" {
  name           = "${var.group_id}_v1_security_policy_admin"
  description    = "Security policy for Okta group ${local.admin_group}"
  active         = true
  resource_group = oktapam_resource_group.rg.id

  principals {
    groups = [oktapam_group.admin.id]
  }

  rule {
    name = "allow_login_${var.group_id}"

    conditions {
      gateway {
        traffic_forwarding = true
        session_recording  = false
      }
    }

    privileges {
      principal_account_ssh {
        enabled                 = true
        admin_level_permissions = true
      }
    }

    resources {
      servers {
        label_selectors {
          server_labels = local.server_labels
        }
      }
    }
  }
}
