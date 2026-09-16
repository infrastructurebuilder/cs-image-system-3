# cs-image-system-okta-opa-plugin

The identity plugin for Okta. It registers the group builders and user
builders that turn the system's `groups:` and `users:` collections into
standalone terraform roots: OPA (Okta Privileged Access, provider
`okta/oktapam`) groups, resource groups, login projects, security policies
and enrollment tokens for groups; `okta/okta` user resources or lookups for
users. It also supplies the pieces other lifecycles need from an identity
type: the packages a base image bakes for `identity_types: [okta]`, the
activation an instance image bakes for its owning group, the launch
parameters, and a read-only gid shim that answers `cs-image-system identity
export-gids` from the OPA Attributes API.

## What it registers

Entry point ([pyproject.toml](pyproject.toml)):

```toml
[project.entry-points."cs_image_system.plugins.group"]
okta_opa_plugin = "cs_image_system.okta_opa_plugin.main:initialize"
```

`initialize()` ([main.py](src/cs_image_system/okta_opa_plugin/main.py))
returns an `OktaTypes` metadata object (metadata version `1`, Python
`3.13`). Every class is registered under one service key, `okta-tf`; each
class's own `csis_name()` supplies the `type:` value a YAML entry uses.

| YAML collection | `type:` | Model class | Builder class | Classification (VCT) |
|---|---|---|---|---|
| `group_builders:` | `okta-tf` | `OktaTfGroupBuilderModel` | `OktaTfGroupBuilder` | `GROUP_BUILDER_MODEL` / `GROUP_BUILDER` |
| `group_builders:` | `okta-tf-ro` | `OktaTfGroupRoBuilderModel` | `OktaTfGroupRoBuilder` | `GROUP_BUILDER_MODEL` / `GROUP_BUILDER` |
| `user_builders:` | `okta-tf` | `OktaTfUserBuilderModel` | `OktaTfUserBuilder` | `USER_BUILDER_MODEL` / `USER_BUILDER` |
| `user_builders:` | `okta-tf-ro` | `OktaTfUserRoBuilderModel` | `OktaTfUserRoBuilder` | `USER_BUILDER_MODEL` / `USER_BUILDER` |

The same two `type:` keys serve both collections; the collection a builder
sits in decides whether it is a group builder or a user builder. There are
no aliases for these keys. A `groups:` or `users:` item selects a builder by
the builder's *name* (or one of the builder's `aliases:`), or by `default`
(the builder with `is_default: true`).

Two further registrations come with the group builder:

- The identity type token is `okta` (`OktaTfGroupBuilder.identity_type()`).
  A base image declares `identity_types: [okta]` to receive this plugin's
  prerequisites.
- `OktaTfGroupBuilder.export_gids` is the gid shim behind
  `cs-image-system identity export-gids`.

## Models

All four builder models mix
[`OktaTfWorkspaceModelMixin`](src/cs_image_system/okta_opa_plugin/okta_tf_workspace.py)
into a base builder model. The mixin carries every field that describes the
terraform workspace (org, team, credentials, providers, state backend); the
base model carries the builder identity and, for users, the templates.

### `OktaTfWorkspaceModelMixin`

Defined in
[okta_tf_workspace.py](src/cs_image_system/okta_opa_plugin/okta_tf_workspace.py).
Not a model on its own; every `OktaTf*BuilderModel` below inherits these
fields.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | `str` | required | Okta org name. Fills `api_host` and the `okta` provider's `org_name`. |
| `team` | `str` | required | OPA team name. Names the `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` variables (non-alphanumerics become `_`) and the `oktapam_team` provider argument. |
| `key` | `EncryptedStr` | `default` | OPA API key. Left at `default`, it resolves at finalize to `var.<team>_key`. May be `ENC[age:...]`. |
| `secret` | `EncryptedStr` | `default` | OPA API secret. Same rules as `key`, resolving to `var.<team>_secret`. |
| `api_host` | `str` | `https://{{ this.org }}.pam.okta.com` | OPA API host; also the host the gid shim queries. |
| `okta_base_url` | `str` | `okta.com` | `okta/okta` provider `base_url` (`oktapreview.com` for preview orgs). |
| `default_user_status` | `str` | `STAGED` | `okta_user.status` for enabled managed users. Any `okta_user` status string. |
| `required_providers` | `list[ConfiguredTerraformProvider]` | `[]` | Providers this root declares: entries with `name`, `source`, `version` and optional `config:`. A group root names `oktapam`; a user root or read-only group root names `okta`. |
| `state_configuration` | `str` | `default` | Name of a `state_backends:` entry (foreign key to `STATE_BACKEND_MODEL`). `default` picks the default backend. |

Behaviour attached to these fields:

- `provider_variables()`: the `oktapam` provider gets two sensitive string
  variables, `<team>_key` and `<team>_secret`; the `okta` provider gets
  none.
- `transform_provider()`: for `oktapam` the provider block is built from
  `key`, `secret`, `api_host` and `team` (a declared-encrypted value is
  emitted by reference to its ciphertext, never quoted into HCL). For
  `okta` the YAML `config:` of the provider entry is used as-is, with
  `org_name` and `base_url` filled in only when absent; credentials are
  never written, the provider reads `OKTA_API_*` from the environment.
- `finalize()`: `api_host` defaults from `org`. When `oktapam` is among
  the providers, `key` and `secret` left at `default` must be backed by
  `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` in the environment,
  otherwise finalize fails with an assertion. When `okta` is among the
  providers and none of `OKTA_API_PRIVATE_KEY`, `OKTA_API_TOKEN`,
  `OKTA_ACCESS_TOKEN` is set, finalize only warns; the builder then skips
  `plan` at generation time.

### `OktaGroupBuilderModel`

Defined in [okta_tf_models.py](src/cs_image_system/okta_opa_plugin/okta_tf_models.py).
Extends
[`GroupBuilderModel`](../base/src/cs_image_system/base/models/group_builder.py),
which itself adds nothing to
[`BuilderModel`](../base/src/cs_image_system/base/models/builder_model.py)
(`name`, `type`, `description`, `aliases`, `executable`, `is_default`,
`config`, `gitignore`, `tags`).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `gateway_selector` | `str \| None` | `None` | `gateway_selector` of every group's login project. |
| `account_discovery` | `bool` | `True` | `account_discovery` of every group's login project. |

`effective_gateway_selector` returns `gateway_selector` when set, otherwise
the global `config.okta_gateway_selector` value, otherwise `None` (the
module call then omits the argument).

### `OktaTfGroupBuilderModel` (`okta-tf`)

Defined in
[okta_opa_tf_group_models.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_models.py).
`OktaTfWorkspaceModelMixin` + `OktaGroupBuilderModel`; adds no fields. The
managed group root: it expects `oktapam` in `required_providers`.

### `OktaTfGroupRoBuilderModel` (`okta-tf-ro`)

Same file; extends `OktaTfGroupBuilderModel` and adds no fields. The
read-only group root: it expects `okta` in `required_providers`, because the
`oktapam` provider has no group data source.

### `OktaUserBuilderModel` and `OktaTfUserBuilderModel` (`okta-tf`)

`OktaUserBuilderModel`
([okta_tf_models.py](src/cs_image_system/okta_opa_plugin/okta_tf_models.py))
extends
[`UserBuilderModel`](../base/src/cs_image_system/base/models/user_builder.py)
and adds no fields. `OktaTfUserBuilderModel`
([okta_opa_tf_user_models.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_user_models.py))
mixes in the workspace fields. The base fields that matter here:

| Base field (`UserBuilderModel`) | Default | Use in this plugin |
|---|---|---|
| `default_user_email_template` | `{{ user.name }}` | Renders a user's `email` when the item leaves it at `default`. The email is the value the `okta_user` lookup searches for (`profile.login`). |
| `default_user_description_template` | `User {{ user.name }} / {{ user.email }}` | Renders a user's `description`; not emitted into HCL. |
| `email_as_username` | `True` | When true, `user.name` must equal `user.email` (case-insensitive) or the run aborts; a blank name is set from the email. |

### `OktaTfUserRoBuilderModel` (`okta-tf-ro`)

Same file; extends `OktaTfUserBuilderModel`, adds no fields. Its builder
defaults every user to lookup-only and refuses `managed: true`.

### Base fields this plugin overrides or constrains

- `BuilderModel.executable` must name an `executables:` entry whose
  binary is `tofu`/`terraform` (the fixture uses `open-tofu-1`); every
  emitted command runs it.
- `BuilderModel.parameters` is refused at load (a base-model rule).
- The `type` class attribute on each model is documentation only; the
  registry keys on `csis_name()`.

### How the group and user items are read

The items themselves are the base
[`Group`](../base/src/cs_image_system/base/models/group.py) and
[`User`](../base/src/cs_image_system/base/models/user.py) models; this
plugin adds no item subclasses.

Group fields consumed: `name`, `members`, `admins`, `is_root` (the root
group's admins are merged into every other group's admins),
`include_root_group_in_admins` (opts a group out of that merge),
`unmanaged` (the module call is replaced by a comment and the module is
removed from state, never destroyed), `attributes` (validated against
`unix_gid: int`, `unix_group_name: str`, `windows_group_name: str`; an int
below 1024 is refused). Not consumed: `gid` (never emitted; the gid policy
is `creation-only`, OPA assigns it and the root publishes it by reference),
`description`, `tags`, `config`.

User fields consumed: `name`, `first_name`, `last_name`, `email`,
`is_enabled` (false maps to status `SUSPENDED`), `managed` (per-item
override of the builder's default), `attributes` (validated against
`unix_uid: int`, `unix_gid: int`, `unix_user_name: str`,
`windows_user_name: str`), and every optional `okta_user` argument that is
also a `User` field (`middle_name`, `mobile_phone`, `title`, `department`,
`manager`, ...) when it is set. Not emitted: `public_keys`,
`is_service_account`, `description`.

### Terraform emitters

[okta_tf_models.py](src/cs_image_system/okta_opa_plugin/okta_tf_models.py)
also holds the `TerraformGenerator` classes the builders render through
[hashicorp-utils](../hashicorp-utils/src/cs_image_system/hashicorp_utils/blocks.py):

| Class | Emits |
|---|---|
| `OktaTFUser` | `resource "okta_user" "<label>"` (first/last name, login, email, status, optional profile arguments) and `data "okta_user" "<label>"` with a `search { name = "profile.login" ... }` block, `skip_roles`/`skip_groups` true, and `depends_on` the resource when the user is managed. |
| `OktaTFGroupLookup` | `data "okta_group" "<label>"` by name; no resource. |
| `OktaTFGroup`, `OktaTFUserToGroup`, `OktaTFResourceGroup`, `OktaTFSecurityPolicyV1` | Single-resource emitters for `oktapam_group`, `oktapam_user_group_attachment`, `oktapam_resource_group` + `oktapam_resource_group_project`, and `oktapam_security_policy`. The group builder emits a module call instead of these; they are kept, tested, and usable by other code. |

`<label>` is the item name with every non-alphanumeric character replaced
by `_` (`avery.alpha` becomes `avery_alpha`).

## The builders

All four own a terraform root through
[`TerraformRootMixin`](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py).
Paths below are relative to the run's generation directory
(`generated/identity/` when the identity lifecycle runs). `<ws>` is the
builder's name.

### `OktaTfGroupBuilder` (`okta-tf`)

[okta_opa_tf_group_builder.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py).
Extends
[`GroupBuilderBase`](../base/src/cs_image_system/base/basic/builder_base_group.py).
Every lifecycle hook keys on the `group-generation` phase and is silent in
every other phase.

1. `generate_items_before` writes the workspace scaffolding:
   - `<ws>/group-generation/<ws>-group-generation.tf`: a header comment;
     the `terraform {}` block with `required_providers` from the model plus
     `external = { source = "hashicorp/external" }` (the gid shim's
     provider), and a `backend "s3" {}` stanza when state backends are
     enabled; one `provider` block per provider, each aliased with the
     workspace name; a `data "external" "sensitive"` block plus
     `locals { sensitive = ... }` only when a declared-encrypted credential
     was registered.
   - `<ws>/group-generation/<ws>-group-generation-<ws>-vars.tf`: the two
     sensitive `variable` blocks for the OPA key and secret.
   - `<ws>/group-generation/<ws>-group-generation.tfbackend.hcl`: the
     backend partial configuration (bucket, key, region, encrypt,
     use_lockfile, profile).
2. `get_commands_to_run_before`: nothing.
3. `generate_items_during` writes, per attached group,
   `<ws>-group-generation-group-<group>.tf` holding one `module "group_<label>"`
   call (or a one-line comment when the group is `unmanaged: true`), and
   `<ws>-group-generation-outputs.tf` holding the root's outputs.
4. `get_commands_to_run_during`: nothing.
5. `generate_items_after`: nothing.
6. `get_commands_to_run_after` returns two lists:
   - Generation-time commands (run in-process, a read): `tofu fmt`,
     `tofu init` (`-backend=false` on a dry run; `-reconfigure
     -backend-config=<file>` on a real run), `tofu validate`, and on a real
     run `tofu plan`.
   - Deferred commands (written to `run-identity.sh`): `rm -f tfplan`;
     `tofu init -input=false -reconfigure -backend-config=...`;
     `tofu state rm module.group_<label>` for each group that is
     `unmanaged` now but was recorded as managed before; `tofu plan
     -input=false -out=tfplan`; `cs-image-system gate-plan --planfile
     tfplan --tofu <binary>`; and, only when `config.apply_identity` is
     true, `cs-image-system apply-check --lifecycle identity --root <ws>`
     followed by `tofu apply -input=false tfplan`. When any group or user
     declares `attributes:`, one more deferred command follows:
     `cs-image-system identity-attributes --probe --dry-run-apply`.
7. `pre_finalize_phase` / `post_finalize_phase`: not overridden.

The module call
([`_group_module_call`](src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py))
targets [tfmodules/okta_opa_module](../../tfmodules/okta_opa_module/main.tf):

| Module input | Value |
|---|---|
| `source` | `okta_opa_module` under `config.module_source_base`, made relative to the root directory. |
| `providers` | `{ oktapam = oktapam.<ws> }` (every bound provider except `external`). |
| `group_id` | The group label. The module derives `<label>_user` and `<label>_admin` groups, `<label>_rg` resource group, `<label>_rg_login` project, one server enrollment token, and the `_user`/`_admin` security policies selecting servers labelled `system.os_type=linux` and `sftd.tx.group=<label>`. |
| `members` | The group's `members`, sorted. |
| `admins` | The group's `admins` plus the root group's admins (unless `include_root_group_in_admins: false`), sorted. |
| `delegated_admin_group_ids` | Always `[]`; the module then delegates the resource group to the group's own admin group. |
| `account_discovery` | The model's `account_discovery`. |
| `gateway_selector` | `effective_gateway_selector`, omitted when `None`. |

The outputs file declares `data "external" "group_gids"` (program
`cs-image-system identity export-gids`, query `identity_type`, `org`,
`team`, `api_host`, `groups`) and three outputs: `group_gids` (group name
to numeric gid), `groups` (per group: `user_group_id`, `admin_group_id`,
`resource_group_id`, `user_group_name`) and the sensitive
`group_enrollment_tokens`. Consumers read them through
`data.terraform_remote_state.<ws>.outputs`;
`enrollment_token_reference(group)` returns exactly that expression for
the instance lifecycle.

Hooks other lifecycles call on this builder:

| Hook | What it returns |
|---|---|
| `identity_type()` | `okta`. |
| `gid_policy()` | `creation-only`. |
| `base_image_prerequisites(os_family)` | Shell lines that install `scaleft-server-tools` from the OktaPAM repository (an `apt` path for `debian`/`ubuntu`, an `rpm`/`yum` path otherwise), then `systemctl disable --now sftd` and remove `/var/lib/sftd/enrollment.token`. |
| `verify_commands(os_family)` | Assertions that `sftd` exists, is not enabled, and has no enrollment token. |
| `activation_commands(image, group)` | Writes `Labels:\n  tx.group: <group>` to `/etc/sft/sftd.yaml` and enables `sftd`. |
| `activation_verify_commands(image, group)` | Asserts the label is present and `sftd` is enabled. |
| `launch_parameters(group)` | `{"enrollment": "sftd-token", "server_label": "sftd.tx.group=<group>"}`. |
| `export_gids(query, groups)` | `{group: gid}` read from OPA (`<group>_user`'s `unix_gid` attribute; a group without one is absent, never invented). Credentials come from `TF_VAR_<team>_key`/`_secret` or `OKTAPAM_KEY`/`OKTAPAM_SECRET`. |
| `query_state()` | Per managed group: `present`, `gid`, `local_name`, `members`, `admins`, and whether an IaC-owned enrollment token exists on the login project. Read-only. |
| `validate_attributes`, `query_attributes`, `attribute_conflicts` | OPA attribute validation and read-only reads through [opa_gids.py](src/cs_image_system/okta_opa_plugin/opa_gids.py). |

The OPA API client ([`OpaGidResolver`](src/cs_image_system/okta_opa_plugin/opa_gids.py))
obtains a service token from `POST /v1/teams/{team}/service_token` and
reads `.../groups/{group}/attributes`, `.../groups/{group}/users`,
`.../users/{user}/attributes`, `.../attributes/conflicts` and the resource
group / project / enrollment-token listings. Token values are never fetched
or returned.

### `OktaTfGroupRoBuilder` (`okta-tf-ro`)

[okta_opa_tf_group_ro_builder.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_ro_builder.py).
Extends `OktaTfGroupBuilder`, so the identity-type hooks above are
inherited unchanged. What differs:

- `generate_items_before`: the same scaffolding, but only when at least
  one group is attached.
- `generate_items_during`: one file,
  `<ws>-group-generation-groups-data.tf`, holding a `data "okta_group"`
  lookup per group (sorted by name, `provider = okta.<ws>`). No module
  calls, no resources, no outputs file.
- `get_commands_to_run_after`: generation-time `fmt`, `init`, `validate`;
  `plan` only on a real run with `okta/okta` credentials in the
  environment. No deferred commands, so nothing from this builder reaches
  `run-identity.sh`. Nothing at all when no groups are attached.

### `OktaTfUserBuilder` (`okta-tf`)

[okta_opa_tf_user_builder.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_user_builder.py).
Extends
[`UserBuilderBase`](../base/src/cs_image_system/base/basic/builder_base_user.py).
Every hook keys on the `user-generation` phase and does nothing when no
users are attached.

1. `generate_items_before` registers the workspace, registers every user's
   `first_name`, `last_name`, `email` (and `login`, when it is not the
   email) as sensitive values (a declared-encrypted value becomes a
   `local.sensitive["<key>"]` reference), then writes
   `<ws>/user-generation/<ws>-user-generation.tf` (header, `terraform {}`
   with the `okta` provider and `external` when a decrypting data source is
   needed, the aliased `provider "okta"` block, the `data "external"
   "sensitive"` block and `locals`), a `-<ws>-vars.tf` file only when a
   provider declared variables (the `okta` provider declares none), and
   `<ws>-user-generation.tfbackend.hcl`.
2. `get_commands_to_run_before`: nothing.
3. `generate_items_during`: for each user (sorted by name), a managed user
   (`is_managed`: the item's `managed`, else the builder's
   `default_managed()`, `True` here) gets an `okta_user` resource in
   `<ws>-user-generation-users.tf` and a lookup that depends on it in
   `<ws>-user-generation-users-data.tf`; an unmanaged user gets only an
   eager lookup in the `-users-data.tf` file.
4. `get_commands_to_run_during`: nothing.
5. `generate_items_after`: nothing.
6. `get_commands_to_run_after`: generation-time `fmt`, `init`, `validate`,
   plus `plan` on a real run with `okta/okta` credentials present. No
   deferred commands.
7. `pre_finalize_phase` / `post_finalize_phase`: not overridden.

`validate_attributes` and `query_attributes` cover OPA user attributes.
Group membership is not emitted here: the group root attaches members by
username string.

### `OktaTfUserRoBuilder` (`okta-tf-ro`)

[okta_opa_tf_user_ro_builder.py](src/cs_image_system/okta_opa_plugin/okta_opa_tf_user_ro_builder.py).
Extends `OktaTfUserBuilder` and changes two things: `default_managed()` is
`False`, so every user is a lookup unless the item says otherwise; and
`validate_user` reports an error for any item with `managed: true`. The
emission and commands are the parent's.

## Emission

Real file names from the golden emission under
[tests/fixtures/v2_golden/generated/identity](../../tests/fixtures/v2_golden/generated/identity),
produced by the fixture's `oktagroups` (`okta-tf`) and `okta-tf-users`
(`okta-tf-ro`) builders:

| File | Content |
|---|---|
| [oktagroups/group-generation/oktagroups-group-generation.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tf) | `terraform {}` with `oktapam` and `external`, `backend "s3" {}`, `provider "oktapam"` (key and secret as `var.` references) and `provider "external"`, both `alias = "oktagroups"`. |
| [oktagroups-group-generation-oktagroups-vars.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-oktagroups-vars.tf) | The two sensitive variables. |
| [oktagroups-group-generation-group-basic.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-group-basic.tf), `-coops.tf`, `-secofs.tf`, `-stofs.tf`, `-tcmet.tf` | One `module "group_<label>"` call each. |
| [oktagroups-group-generation-outputs.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-outputs.tf) | The gid shim data source and the three outputs. |
| [oktagroups-group-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tfbackend.hcl) | Backend partial configuration. |
| [okta-tf-users/user-generation/okta-tf-users-user-generation.tf](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tf) | `terraform {}` with `okta` and `external`, `provider "okta"` with `org_name`/`base_url`, the `data "external" "sensitive"` block carrying the ciphertexts, and `locals`. |
| [okta-tf-users-user-generation-users-data.tf](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation-users-data.tf) | One `data "okta_user"` lookup per user. No `-users.tf` file: the builder is read-only, so no resources exist. |
| [okta-tf-users-user-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tfbackend.hcl) | Backend partial configuration. |
| [run-identity.sh](../../tests/fixtures/v2_golden/generated/identity/run-identity.sh) | The deferred commands: only the `oktagroups` root's `rm`, `init`, `plan` and `gate-plan` (the fixture has `apply_identity: false`, so no `apply`). |

The system's identity read-model
([meta-state/identity.yaml](../../tests/fixtures/v2_golden/meta-state/identity.yaml))
records, per group, the `builder`, `identity_type: okta`,
`gid_policy: creation-only`, `managed`, members and admins as this plugin
reports them.

## Example configuration

From
[tests/fixtures/config/cfg/group-builders.yml](../../tests/fixtures/config/cfg/group-builders.yml):

```yaml
group_builders:
  - name: oktagroups
    is_default: true
    type: okta-tf
    executable: open-tofu-1
    org: "noaa"
    team: "nos-coastal-modeling-cloud-sandbox"
    required_providers:
      - name: oktapam
        source: okta/oktapam
        version: '>= 0.6.3'

user_builders:
  - name: okta-tf-users
    is_default: true
    type: okta-tf-ro
    executable: open-tofu-1
    org: "noaa"
    team: "nos-coastal-modeling-cloud-sandbox"
    email_as_username: false
    default_user_email_template: "{{ user.name }}@example.invalid"
    required_providers:
      - name: okta
        source: okta/okta
        version: '>= 6.0'
```

The `gateway_selector` those groups use comes from the global
configuration
([cfg/_config.yml](../../tests/fixtures/config/cfg/_config.yml)):
`config.okta_gateway_selector: "environment=staging"`.

The groups these builders act on live in
[tests/fixtures/config/groups](../../tests/fixtures/config/groups). Member
and admin entries are bare OPA usernames, declared encrypted (`ENC[age:...]`
ciphertexts, shortened here); the golden shows their decrypted values. From
[test-group.yaml](../../tests/fixtures/config/groups/test-group.yaml):

```yaml
groups:
  - name: basic
    is_root: true
    is_default: false
    description: "Root admin group with access to everything"
    admins:
      - ENC[age:...]        # avery.alpha
    tags:
      environment: production
  - name: coops
    is_default: false
    description: "CO-Ops  group"
    members:
      - ENC[age:...]        # avery.alpha
      - ENC[age:...]        # casey.charlie
    admins:
      - ENC[age:...]        # avery.alpha
      - ENC[age:...]        # casey.charlie
    tags:
      environment: test
```

Because `basic` is the root group, its admin `avery.alpha` appears in the
`admins` list of every other group's module call. A user entry from
[users.yaml](../../tests/fixtures/config/groups/users.yaml) has the same
shape: `name`, `first_name`, `last_name` (all required, all declared
encrypted) and an optional `email`; with no `email`, the builder's template
derives `<name>@example.invalid`.

## Related

- Base models extended:
  [group_builder.py](../base/src/cs_image_system/base/models/group_builder.py),
  [user_builder.py](../base/src/cs_image_system/base/models/user_builder.py),
  [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py);
  items read:
  [group.py](../base/src/cs_image_system/base/models/group.py),
  [user.py](../base/src/cs_image_system/base/models/user.py).
- Base builder classes:
  [builder_base_group.py](../base/src/cs_image_system/base/basic/builder_base_group.py),
  [builder_base_user.py](../base/src/cs_image_system/base/basic/builder_base_user.py).
- Library:
  [hashicorp-utils](../hashicorp-utils) --
  [collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py)
  (providers, variables, backends, sensitive references),
  [blocks.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/blocks.py)
  (HCL rendering),
  [roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py)
  (`TerraformRootMixin`).
- Terraform module called:
  [tfmodules/okta_opa_module](../../tfmodules/okta_opa_module)
  ([main.tf](../../tfmodules/okta_opa_module/main.tf),
  [variables.tf](../../tfmodules/okta_opa_module/variables.tf),
  [outputs.tf](../../tfmodules/okta_opa_module/outputs.tf)).
- Tests: [tests/](tests) -- the module call, the workspace mixin, the
  resource emitters, the four builder roots, and the gid shim.
