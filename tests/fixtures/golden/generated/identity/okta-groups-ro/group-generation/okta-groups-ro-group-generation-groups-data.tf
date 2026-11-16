# Lookup of Okta group readers by name
data "okta_group" "readers" {
    provider = okta.okta_groups_ro
    name = "readers"
}