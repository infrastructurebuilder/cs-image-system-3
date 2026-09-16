# stage 35 (2026-09-15): the declared addresses this V1 snapshot carried in clear are redacted
# (redacted@example.invalid); derived <username>@<domain> addresses are public by construction.
# stage 36 (2026-09-15): every person here is a synthetic persona and the derived domain is
# example.invalid, the same substitution the frozen fixture received (tests/fixtures/config/README.md).
# Lookup of Okta user dakota.delta by login
data "okta_user" "dakota_delta" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "dakota.delta@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user morganm by login
data "okta_user" "morganm" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user noel by login
data "okta_user" "noel" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user kendall.kilo by login
data "okta_user" "kendall_kilo" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user lennox.lima by login
data "okta_user" "lennox_lima" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "lennox.lima@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user emerson.echo by login
data "okta_user" "emerson_echo" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "emerson.echo@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user finley.foxtrot by login
data "okta_user" "finley_foxtrot" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "finley.foxtrot@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user greer.golf by login
data "okta_user" "greer_golf" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "greer.golf@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user harper.hotel by login
data "okta_user" "harper_hotel" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "harper.hotel@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user avery.alpha by login
data "okta_user" "avery_alpha" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "avery.alpha@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user i.india by login
data "okta_user" "i_india" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user blake.bravo by login
data "okta_user" "blake_bravo" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user jordan.juliett by login
data "okta_user" "jordan_juliett" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "jordan.juliett@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user oakley by login
data "okta_user" "oakley" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "redacted@example.invalid"
        comparison = "eq"
    }
}
# Lookup of Okta user casey.charlie by login
data "okta_user" "casey_charlie" {
    provider = okta.okta_tf_users
    skip_roles = true
    skip_groups = true
    
    search {
        name = "profile.login"
        value = "casey.charlie@example.invalid"
        comparison = "eq"
    }
}