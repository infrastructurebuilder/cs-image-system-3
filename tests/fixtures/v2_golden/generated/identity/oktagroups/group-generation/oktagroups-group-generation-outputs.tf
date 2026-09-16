# Outputs of the identity root oktagroups (DESIGN N7).
# GIDs are never literals: the oktapam provider exposes no group gid, so this
# root asks the system's own CLI (read-only, credentials from the environment)
# and publishes the answer as an output for terraform_remote_state consumers.
# gid shim: {group: gid} for every managed group
data "external" "group_gids" {
    provider = external.oktagroups
    program = [
        "cs-image-system",
        "identity",
        "export-gids",
    ]
    query = {
        identity_type = "okta",
        org           = "noaa",
        team          = "nos-coastal-modeling-cloud-sandbox",
        api_host      = "https://noaa.pam.okta.com",
        groups        = "basic,coops,secofs,stofs,tcmet",
    }
}
output "group_gids" {
    value = { for g, gid in data.external.group_gids.result : g => tonumber(gid) }
    description = "Group name -> unix gid, queried from OPA; consume by reference only"
}
output "groups" {
    value = {
        basic  = {
            user_group_id     = module.group_basic.user_group_id,
            admin_group_id    = module.group_basic.admin_group_id,
            resource_group_id = module.group_basic.resource_group_id,
            user_group_name   = module.group_basic.user_group_name,
        },
        coops  = {
            user_group_id     = module.group_coops.user_group_id,
            admin_group_id    = module.group_coops.admin_group_id,
            resource_group_id = module.group_coops.resource_group_id,
            user_group_name   = module.group_coops.user_group_name,
        },
        secofs = {
            user_group_id     = module.group_secofs.user_group_id,
            admin_group_id    = module.group_secofs.admin_group_id,
            resource_group_id = module.group_secofs.resource_group_id,
            user_group_name   = module.group_secofs.user_group_name,
        },
        stofs  = {
            user_group_id     = module.group_stofs.user_group_id,
            admin_group_id    = module.group_stofs.admin_group_id,
            resource_group_id = module.group_stofs.resource_group_id,
            user_group_name   = module.group_stofs.user_group_name,
        },
        tcmet  = {
            user_group_id     = module.group_tcmet.user_group_id,
            admin_group_id    = module.group_tcmet.admin_group_id,
            resource_group_id = module.group_tcmet.resource_group_id,
            user_group_name   = module.group_tcmet.user_group_name,
        },
    }
    description = "Managed OPA groups and their object ids"
}
output "group_enrollment_tokens" {
    value = {
        basic  = module.group_basic.enrollment_token,
        coops  = module.group_coops.enrollment_token,
        secofs = module.group_secofs.enrollment_token,
        stofs  = module.group_stofs.enrollment_token,
        tcmet  = module.group_tcmet.enrollment_token,
    }
    description = "Group -> launch enrollment token (IaC-owned, PLAN.md); consume by reference only"
    sensitive = true
}