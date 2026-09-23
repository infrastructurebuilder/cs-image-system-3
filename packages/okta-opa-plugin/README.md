# cs-image-system-okta-opa-plugin

The identity plugin for Okta. It registers the group builders and user
builders that turn the system's `groups:` and `users:` collections into
standalone terraform roots: OPA (Okta Privileged Access, provider
`okta/oktapam`) groups, resource groups, login projects, security policies
and enrollment tokens for groups; `okta/okta` user resources or lookups for
users. It also supplies the pieces other lifecycles need from an identity
type: the packages a base image bakes for `identity_types: [okta]`, the
activation an instance image bakes for its owning group, the launch
parameters, a read-only gid shim that answers `cs-image-system identity
export-gids` from the OPA Attributes API, the OPA server registry the
instance lifecycle reads and retires, and the CI login policy the identity
lifecycle keeps beside each group's user policy through the OPA API.

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
| `api_host` | `str` | `https://{{ this.org }}.pam.okta.com` | OPA API host; also the host the gid shim, the state query and every other OPA API call use. |
| `okta_base_url` | `str` | `okta.com` | `okta/okta` provider `base_url` (`oktapreview.com` for preview orgs). |
| `default_user_status` | `str` | `STAGED` | `okta_user.status` for enabled managed users. Not checked against the `okta_user` status set; the provider refuses an unknown one at plan. |
| `required_providers` | `list[ConfiguredTerraformProvider]` | `[]` | Providers this root declares: entries with `name`, `source`, `version` and optional `config:`. A group root names `oktapam`; a user root or read-only group root names `okta`. |
| `state_configuration` | `str` | `default` | Name of a `state_backends:` entry (foreign key to `STATE_BACKEND_MODEL`). `default` picks the default backend; the identity roots have no runtime, so there is no runtime rung in between. |

Behaviour attached to these fields:

- `provider_variables()`: the `oktapam` provider gets two sensitive string
  variables, `<team>_key` and `<team>_secret`; the `okta` provider gets
  none.
- `transform_provider()`: for `oktapam` the provider block is built from
  `key`, `secret`, `api_host` and `team` (a declared-encrypted value is
  emitted by reference to its ciphertext, never quoted into HCL). For
  `okta` the YAML `config:` of the provider entry is used as-is, with
  `org_name` and `base_url` filled in only when absent; credentials are
  never written, the provider reads `OKTA_API_*` from the environment. Any
  other provider name is passed through with a warning.
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
| `workload_connection` | `str \| None` | `None` | The name of the team's OPA workload connection, made by hand once ([WORKLOAD_CONNECTION.md](../../WORKLOAD_CONNECTION.md)). Read only together with `workload_role`. |
| `workload_role` | `str \| None` | `None` | The name of the team's one workload role. With both names set, the builder keeps one CI login policy per managed group (`<group>_v1_security_policy_ci`) through the OPA API and reports it in the state query. |

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
| `email_domain` | `None` | The organisation half of a derived address; folded into the template where it says `{{ builder.email_domain }}`. Declared encrypted, one marker serves every derived address (stage 51). |
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
`description`, `tags`, `config`, `in_both` (the base model applies it
before the builder sees the sets).

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
| `OktaTFGroupLookup` | `data "okta_group" "<label>"` by name; no resource. The okta provider's name search is prefix-based, so exact group names are the contract. |
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
     provider), and a `backend "<type>" {}` stanza naming the bound
     backend's type (`local` in the fixture, `s3` in the live tree) when
     `config.use_state_backends` is true; one `provider` block per
     provider, each aliased with the workspace name; a `data "external"
     "sensitive"` block plus `locals { sensitive = ... }` only when a
     declared-encrypted credential was registered.
   - `<ws>/group-generation/<ws>-group-generation-<ws>-vars.tf`: the two
     sensitive `variable` blocks for the OPA key and secret.
   - `<ws>/group-generation/<ws>-group-generation.tfbackend.hcl`: the
     backend partial configuration the bound backend renders (`path` for
     `local`; `bucket`, `key`, `region`, `encrypt`, `use_lockfile`,
     `profile` for `s3`); absent when backends are off.
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
     -backend-config=<file>` on a real run), `tofu validate`, and on a
     real run only, `cs-image-system materialize .` followed by `tofu
     init` and `tofu plan -refresh=false` in the private mirror
     (`_private/identity/<ws>/group-generation` under the configuration
     root), because the committed emission carries ciphertext and the
     plan reads plaintext. The plan is a preview: `-refresh=false` keeps
     the provider from refreshing an attachment whose membership is gone
     (it errors instead of planning the destroy).
   - Deferred commands (written to `run-identity.sh`, each run inside the
     private mirror of the root): `rm -f tfplan`; `tofu init -input=false
     -reconfigure [-backend-config=...]`; when a group is `unmanaged` now
     but was recorded as managed before, `cs-image-system state-migration
     backup` (the state pulled to
     `_private/state-backups/<ws>.backup-<run>.tfstate`) then `tofu state
     rm module.group_<label>` per such group; `cs-image-system
     prune-attachments --builder <ws> --tofu <binary> --run <run>` (stage
     61 item 3, below); `tofu plan -input=false -out=tfplan`;
     `cs-image-system gate-plan --planfile tfplan --tofu <binary>`; and,
     only when `config.apply_identity` allows this root,
     `cs-image-system apply-check --lifecycle identity --root <ws>`
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
| `delegated_admin_group_ids` | Always `[]`; the module then delegates the resource group to the group's own admin group. The root group's admin group is never a delegated admin of another resource group; its admins reach other groups as usernames in `admins`. |
| `account_discovery` | The model's `account_discovery`. |
| `gateway_selector` | `effective_gateway_selector`, omitted when `None`. |

The outputs file declares `data "external" "group_gids"` (program
`cs-image-system identity export-gids`, query `identity_type`, `org`,
`team`, `api_host`, `groups`) and three outputs: `group_gids` (group name
to numeric gid), `groups` (per group: `user_group_id`, `admin_group_id`,
`resource_group_id`, `user_group_name`) and the sensitive
`group_enrollment_tokens`. With no managed group the file holds only an
empty `group_gids` output. Consumers read them through
`data.terraform_remote_state.<ws>.outputs`;
`enrollment_token_reference(group)` returns exactly that expression for
the instance lifecycle.

Hooks other lifecycles call on this builder:

| Hook | What it returns |
|---|---|
| `identity_type()` | `okta`. |
| `gid_policy()` | `creation-only`. |
| `base_image_prerequisites(os_family)` | Shell lines that install `scaleft-server-tools` from the OktaPAM repository (an `apt` path for `debian`/`ubuntu`, first installing `curl` and `gnupg` when absent; an `rpm`/`yum` path otherwise), then `systemctl disable --now sftd` and remove `/var/lib/sftd/enrollment.token`. |
| `verify_commands(os_family)` | Assertions that `sftd` exists, is not enabled, and has no enrollment token. |
| `activation_commands(image, group)` | Writes `Labels:\n  tx.group: <group>` to `/etc/sft/sftd.yaml` and enables `sftd`. |
| `activation_verify_commands(image, group)` | Asserts the label is present and `sftd` is enabled. |
| `launch_parameters(group)` | `{"enrollment": "sftd-token", "server_label": "sftd.tx.group=<group>"}`. |
| `export_gids(query, groups)` | `{group: gid}` read from OPA (`<group>_user`'s `unix_gid` attribute, then the bare name; a group without one is absent, never invented). Credentials come from `TF_VAR_<team>_key`/`_secret` or `OKTAPAM_KEY`/`OKTAPAM_SECRET`. |
| `query_state()` | Per managed group: `present`, `gid`, `local_name`, `members`, `admins` (when OPA answers), whether an IaC-owned enrollment token exists on the login project (`enrollment_token`), and, when the workload fields are set, `workload` (role, policy, connection). A call that failed is `{present: false, error: ...}`; a 404 is `{present: false}`. Read-only. |
| `can_query_servers()`, `registered_servers(group)`, `retire_servers_named(group, hostname)` | The OPA server registry of `<group>_rg_login` (stage 55): every enrolled server as `{id, hostname, address, canonical_name, alt_names, instance_id}`, or `None` when OPA could not be asked; retirement `DELETE`s every registration of a hostname and returns the ids, raising when the registry cannot be read. |
| `can_manage_workload_access()`, `workload_access_expected(group)`, `workload_access_state(group)`, `ensure_workload_access(group)` | The CI login policy (stage 56): true only with both `workload_connection` and `workload_role` set; what the configuration expects; what OPA holds; and the reconcile that creates, updates or leaves the `<group>_v1_security_policy_ci` policy as a copy of `<group>_v1_security_policy_user` with the role as its only principal and admin-level permissions forced off. |
| `prune_stale_attachments(tofu, run, cwd)` | The runner step (stage 61 item 3): lists tofu state, keeps every `oktapam_user_group_attachment` the declaration still has, asks OPA about each dropped one and removes from state, after a backup, only those OPA no longer holds. |
| `validate_attributes`, `query_attributes`, `attribute_conflicts` | OPA attribute validation and read-only reads through [opa_attributes.py](src/cs_image_system/okta_opa_plugin/opa_attributes.py) and [opa_gids.py](src/cs_image_system/okta_opa_plugin/opa_gids.py). |

The OPA API client ([`OpaGidResolver`](src/cs_image_system/okta_opa_plugin/opa_gids.py))
obtains a service token from `POST /v1/teams/{team}/service_token` and
reads `.../groups/{group}/attributes`, `.../groups/{group}/users`,
`.../users/{user}/attributes`, `.../attributes/conflicts`, the resource
group / project / enrollment-token / server listings under
`/v1/teams/{team}/resource_groups/...`, `.../security_policy`,
`.../workload-roles` (a hyphen) and `.../connections/workloads`. It writes
only through `DELETE .../servers/{id}`, `POST .../security_policy` and `PUT
.../security_policy/{id}`. Token values are never fetched or returned. A
listing longer than one page is read as its first page. The policy
derivation is pure code in
[workload_policy.py](src/cs_image_system/okta_opa_plugin/workload_policy.py).

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
  `plan` (in the private mirror) only on a real run with `okta/okta`
  credentials in the environment. No deferred commands, so nothing from
  this builder reaches `run-identity.sh`. Nothing at all when no groups
  are attached.

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
   plus `materialize` and `plan` in the private mirror on a real run with
   `okta/okta` credentials present. No deferred commands.
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
(`okta-tf-ro`) builders, both bound to the fixture's `local-dev` state
backend:

| File | Content |
|---|---|
| [oktagroups/group-generation/oktagroups-group-generation.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tf) | `terraform {}` with `oktapam` and `external`, `backend "local" {}`, `provider "oktapam"` (key and secret as `var.` references) and `provider "external"`, both `alias = "oktagroups"`. |
| [oktagroups-group-generation-oktagroups-vars.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-oktagroups-vars.tf) | The two sensitive variables. |
| [oktagroups-group-generation-group-basic.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-group-basic.tf), `-coops.tf`, `-secofs.tf`, `-stofs.tf`, `-tcmet.tf` | One `module "group_<label>"` call each. |
| [oktagroups-group-generation-outputs.tf](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation-outputs.tf) | The gid shim data source and the three outputs. |
| [oktagroups-group-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tfbackend.hcl) | Backend partial configuration (`path = ...` for the local backend). |
| [okta-tf-users/user-generation/okta-tf-users-user-generation.tf](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tf) | `terraform {}` with `okta` and `external`, `backend "local" {}`, `provider "okta"` with `org_name`/`base_url`, the `data "external" "sensitive"` block carrying the ciphertexts (a derived address as `<name>@ENC[age:...]`), and `locals`. |
| [okta-tf-users-user-generation-users-data.tf](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation-users-data.tf) | One `data "okta_user"` lookup per user. No `-users.tf` file: the builder is read-only, so no resources exist. |
| [okta-tf-users-user-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tfbackend.hcl) | Backend partial configuration. |
| [run-identity.sh](../../tests/fixtures/v2_golden/generated/identity/run-identity.sh) | The deferred commands: only the `oktagroups` root's `rm`, `init`, `prune-attachments`, `plan` and `gate-plan`, each entered through `cs-image-system materialize` (the fixture has `apply_identity: false`, so no `apply-check` or `apply`). |

The system's identity read-model
([meta-state/identity.yaml](../../tests/fixtures/v2_golden/meta-state/identity.yaml))
records, per group, the `builder`, `identity_type: okta`,
`gid_policy: creation-only`, `managed`, `is_root`, members and admins as
this plugin reports them, plus a `workload` record (the expected
connection, role and policy names, and after a real apply the reconcile's
`action`, `id`, `role_id` and `run`) when the builder names the workload
objects.

## Example configuration

From
[tests/fixtures/config/cfg/group-builders.yml](../../tests/fixtures/config/cfg/group-builders.yml):

```yaml
group_builders:
  - name: oktagroups
    is_default: true
    type: okta-tf
    executable: open-tofu-1
    state_configuration: local-dev
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
    state_configuration: local-dev
    org: "noaa"
    team: "nos-coastal-modeling-cloud-sandbox"
    email_as_username: false
    email_domain: ENC[age:...]            # example.invalid
    default_user_email_template: "{{ user.name }}@{{ builder.email_domain }}"
    required_providers:
      - name: okta
        source: okta/okta
        version: '>= 6.0'
```

The live tree adds `workload_connection: "github-cs-image-system"` and
`workload_role: "cs-image-system-ci"` to the group builder and binds both
roots to the default (S3) backend.

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

## Prerequisites and integration

Everything below exists outside the system. Where the plugin finds each
item is named next to it; the general rules are in
[docs/OPERATIONS.md](../../docs/OPERATIONS.md) ("Credentials contract")
and [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) (section 14,
environment variables).

**An Okta org and an OPA team.** The org name goes in `org`, the team
name in `team`. The OPA API is reached at `api_host` (default
`https://<org>.pam.okta.com`); the Okta org itself at
`<org>.<okta_base_url>` through the `okta/okta` provider. Both are HTTPS
from wherever the configuration loads, plans or is queried: the load itself
makes no network call, but a real run's generation-time plan, every
deferred command, the gid shim, the state query and `verify login` do.

**An OPA API service key pair for the team**, with its `resource_admin`
role. The oktapam terraform provider reads it through two sensitive
variables, `var.<team>_key` and `var.<team>_secret`, filled from the
environment variables `TF_VAR_<team>_key` and `TF_VAR_<team>_secret` (the
team name with every non-alphanumeric character replaced by `_`; the
live team is `nos_coastal_modeling_cloud_sandbox`). `key:` and `secret:`
left at `default` on the builder resolve to those variables at finalize
and the load asserts the environment variables exist whenever `oktapam`
is among `required_providers`. A literal (or `ENC[age:...]`) `key:` and
`secret:` bypass the variables. The plugin's own API client
(`credentials_from_env` in [opa_gids.py](src/cs_image_system/okta_opa_plugin/opa_gids.py))
takes the same `TF_VAR_<team>_*` pair, or `OKTAPAM_KEY` / `OKTAPAM_SECRET`
as a generic fallback; it never reads `key:`/`secret:` from the builder.
What the pair must be able to do, all under `/v1/teams/<team>/`: mint a
service token; read group and user attributes and attribute conflicts;
list group users; list resource groups, their projects, the projects'
enrollment tokens and servers (servers answer only under the resource
group path, `.../resource_groups/<rg>/projects/<prj>/servers`; the
team-level `/projects/...` path answers `401 Missing capability`); delete a
server registration; list, create and update security policies; list
workload roles and workload connections. The pair lives only in the two
checkouts' `.envrc` files and in the repository secrets `TF_VAR_NOS_KEY` /
`TF_VAR_NOS_SECRET` (exported under the team-specific names by CI).

**An Okta API services app** for the `okta/okta` provider (user lookups,
read-only group lookups). The provider reads `OKTA_API_CLIENT_ID`,
`OKTA_API_SCOPES`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID` (or
`OKTA_API_TOKEN` for SSWS) from the environment itself; nothing about
them enters the configuration or the emission. The load checks only that
one of `OKTA_API_PRIVATE_KEY`, `OKTA_API_TOKEN`, `OKTA_ACCESS_TOKEN` is
set when `okta` is among the providers, warns otherwise, and the builder
then skips its generation-time `plan`. The scopes stay at
`okta.users.read okta.groups.read` (the lookups pass `skip_roles` and
`skip_groups`); DPoP stays off (the provider does not support it); the
`*.manage` scopes stay ungranted. Any provider argument the app needs
(`client_id`, `scopes`, `private_key_id`, ...) may also be written under
the provider entry's `config:` and passes through untouched.

**A terraform binary.** `executable:` names a `cfg/executables.yml` entry
whose binary is `tofu` or `terraform`; the version floor is that entry's
requirement, checked at `validate` and before every run (stage 48). The
providers `okta/oktapam` (`>= 0.6.3` in the fixture and the live tree;
0.7.1 is the version the code's behaviour is written against),
`okta/okta` (`>= 6.0`) and `hashicorp/external` (unpinned, added by the
builder) are fetched by `tofu init` from the public registry.

**The terraform module** `okta_opa_module`, found at
`config.module_source_base` (default `../tfmodules`, relative to the
configuration root). The system repository carries it under
[tfmodules/](../../tfmodules/okta_opa_module); a configuration checkout
needs it beside it.

**A state backend.** `state_configuration` names a `state_backends:`
entry, or `default` picks the default one. The `s3` backend needs an AWS
session for the profile it names (the live tree); the `local` backend
(the fixture) needs nothing. Backend blocks and the `.tfbackend.hcl` file
are emitted only when `config.use_state_backends` is true. The instance
roots read the identity root's outputs through `terraform_remote_state`,
so the instance lifecycle needs read access to the same location.

**The `cs-image-system` CLI on `PATH`** of whoever runs terraform: the
generated roots call `cs-image-system decrypt --json` (the sensitive
values) and `cs-image-system identity export-gids` (the gid shim) as
`data "external"` programs, and the deferred script calls `materialize`,
`prune-attachments`, `state-migration`, `gate-plan` and `apply-check`.
`just` and `uv run` provide it; a hand `tofu plan` inside a generated root
needs it too, together with `CSIS_CONFIG_IDENTITY`.

**The age identity** in `CSIS_CONFIG_IDENTITY`: the rosters (`name`,
`first_name`, `last_name`, `members`, `admins`, `email_domain`) are
`ENC[age:...]` values in the live tree, every load decrypts them, and
terraform decrypts the emitted ciphertexts at plan time through the same
identity. Without it the load refuses.

**The machines.** Base images that declare `identity_types: [okta]` reach
`https://dist.scaleft.com` during the bake (the OktaPAM package
repository), and Debian vendor images get `curl` and `gnupg` installed
first. An instance enrolls with `sftd` at launch using the token the
identity root minted (read by the instance root as a sensitive
remote-state reference; `TF_VAR_sft_enrollment_token` is the explicit
override), advertises its private address, and must be reachable through
an OPA gateway matching `gateway_selector` (the live value is
`environment=staging`, from `config.okta_gateway_selector`) that wears the
gateway's security group.

**The workload connection and role**, only when CI is to log in: made by
hand once in the OPA admin console following
[WORKLOAD_CONNECTION.md](../../WORKLOAD_CONNECTION.md), then named on
the `okta-tf` group builder as `workload_connection` and `workload_role`.
The system reads both by name and never writes them. `verify login` and
`just ci-login-proof` additionally need Okta's `sft` client on the machine
that runs them (and `OPA_TOKEN` to log in as the workload).

**Global keys read** from `cfg/_config.yml`: `apply_identity` (the apply
gate for the group root and for the CI policy reconcile),
`okta_gateway_selector` (the `gateway_selector` fallback),
`module_source_base`, `use_state_backends`.

## Configuration reference

The field-by-field contract. Types are the Python annotations; a default
of `required` means the load refuses without it.

### Every `okta-tf` / `okta-tf-ro` builder (the workspace mixin)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `org` | `str` | required | Okta org name; `api_host` and the `okta` provider's `org_name` derive from it. |
| `team` | `str` | required | OPA team; names the credential variables and the `oktapam_team` provider argument; the API client's `/v1/teams/<team>/` path. |
| `key` | `EncryptedStr` | `default` | OPA API key for the `oktapam` provider block. `default` becomes `var.<team>_key` (backed by `TF_VAR_<team>_key`); a literal is quoted into HCL; an `ENC[age:...]` value is emitted as `local.sensitive["oktapam_key"]`. Read only when `oktapam` is a declared provider. |
| `secret` | `EncryptedStr` | `default` | As `key`, for the secret. |
| `api_host` | `str` | `https://{{ this.org }}.pam.okta.com` | OPA API host for the provider block, the gid shim query, the state query and every API call. |
| `okta_base_url` | `str` | `okta.com` | The `okta` provider's `base_url` when the provider entry's `config:` does not set one. Accepted, not read on a builder without an `okta` provider. |
| `default_user_status` | `str` | `STAGED` | `okta_user.status` for enabled managed users. Read only by a user builder emitting a managed user; accepted, not read on group builders and on `okta-tf-ro` user builders with no `managed: true` item. Not validated by the plugin. |
| `required_providers` | list | `[]` | Provider entries (below). Nothing checks that a group root names `oktapam` or a user root names `okta`; a root with no provider emits no provider block and the plugin logs a warning about the missing `okta` binding when it emits data sources. |
| `state_configuration` | `str` | `default` | Foreign key to a `state_backends:` entry; `default` binds the default backend. |

A `required_providers` entry:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | required | `oktapam`, `okta`, or another provider (passed through with a warning). |
| `source` | `str` | required | e.g. `okta/oktapam`. |
| `version` | `str` | required | The constraint written into `terraform { required_providers }`. |
| `config` | mapping | `{}` | Provider arguments. For `okta` used as-is plus `org_name`/`base_url` defaults; for `oktapam` ignored (the block is built from the fields above). |

### Group builders (`okta-tf`, `okta-tf-ro`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `gateway_selector` | `str \| None` | `None` | The login project's `gateway_selector` in every module call; `None` falls back to `config.okta_gateway_selector`, and with neither the argument is omitted. Accepted, not read by `okta-tf-ro` (no module call). |
| `account_discovery` | `bool` | `True` | The login project's `account_discovery`. Accepted, not read by `okta-tf-ro`. |
| `workload_connection` | `str \| None` | `None` | The team's workload connection, by name. Read only when `workload_role` is set too. |
| `workload_role` | `str \| None` | `None` | The team's workload role, by name. With both set the builder manages one CI login policy per managed group and reports the three objects in the state query. |

### User builders (`okta-tf`, `okta-tf-ro`)

The base `UserBuilderModel` fields, all read here:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `default_user_email_template` | `str` | `{{ user.name }}` | Renders `email` for a user that declares none; `{{ builder.email_domain }}` inside it is replaced by `email_domain` before rendering. |
| `default_user_description_template` | `str` | `User {{ user.name }} / {{ user.email }}` | Renders `description`; never emitted. |
| `email_domain` | `str \| None` | `None` | The domain half of a derived address; may be `ENC[age:...]`, in which case every derived address carries that ciphertext in the emission. |
| `email_as_username` | `bool` | `True` | `name` must equal `email` case-insensitively (a blank name is set from the email); a mismatch aborts the load. |

### Common builder fields (`BuilderModel`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | `str` | required | The workspace name: the root directory, the provider alias, the state key, the module call's `providers` binding. |
| `type` | `str` | required | `okta-tf` or `okta-tf-ro`. |
| `executable` | `str \| None` | `None` | The `executables:` entry to run; required in practice (a missing one fails the first command with `Executable '...' not found`). |
| `is_default` | `bool` | `False` | The builder an item's `type: default` selects (loader). |
| `aliases` | `set[str]` | `{}` | Other names an item may select this builder by (loader). |
| `description`, `config`, `gitignore`, `tags` | | | Accepted, not read by this plugin. |
| `parameters` | | | Refused at load. |

### Items

Group (`groups:`) fields the plugin reads: `name`, `members`, `admins`,
`is_root`, `include_root_group_in_admins`, `unmanaged`, `attributes`.
Accepted, not read by the plugin: `gid`, `description`, `tags`, `config`,
`in_both`, `is_default`, `aliases`.

User (`users:`) fields the plugin reads: `name`, `first_name`,
`last_name`, `email`, `is_enabled`, `managed`, `attributes`, and the
`okta_user` profile arguments (`middle_name`, `mobile_phone`,
`honorific_prefix`, `honorific_suffix`, `title`, `display_name`,
`nick_name`, `profile_url`, `second_email`, `primary_phone`,
`street_address`, `city`, `state`, `zip_code`, `country_code`,
`postal_address`, `preferred_language`, `locale`, `timezone`,
`user_type`, `employee_number`, `cost_center`, `organization`,
`division`, `department`, `manager_id`, `manager`) when set and truthy.
Accepted, not read: `description` (rendered by the base, never emitted),
`is_service_account`, `public_keys`, `tags`, `config`.

Attribute declarations (`attributes:`) accept exactly: on a group
`unix_gid` (int), `unix_group_name` (str), `windows_group_name` (str); on
a user `unix_uid` (int), `unix_gid` (int), `unix_user_name` (str),
`windows_user_name` (str). An int must be at least 1024 and not a bool; a
str must not be blank. They are planned and probed, never written.

### Variations

- **`okta-tf` versus `okta-tf-ro` as a group builder.** `okta-tf` emits one
  module call per group, the outputs file, the vars file, and the deferred
  plan-gate-apply sequence, and always scaffolds its root even with no
  group. `okta-tf-ro` emits only `data "okta_group"` lookups, no outputs
  and no deferred commands, and emits nothing at all with no group; it
  needs the `okta` provider instead of `oktapam`, so no `TF_VAR_<team>_*`
  assertion fires for it. Every identity-type hook (prerequisites,
  activation, launch parameters, `query_state`, the registry, the CI
  policy) is inherited unchanged, so a group on an `okta-tf-ro` builder is
  still recorded as `identity_type: okta`, `gid_policy: creation-only` and
  managed, and the state query asks OPA about its `<group>_user` group.
- **`okta-tf` versus `okta-tf-ro` as a user builder.** The emission is one
  code path chosen per item by `managed`: `okta-tf` defaults to managed (an
  `okta_user` resource plus a lookup that `depends_on` it); `okta-tf-ro`
  defaults to lookup-only (an eager lookup that must resolve at plan) and
  refuses `managed: true` at `validate`.
- **`managed: true|false|null` on a user.** `null` takes the builder's
  default; an explicit value overrides it. A managed user's status is
  `default_user_status`, or `SUSPENDED` when `is_enabled: false`.
- **`unmanaged: true` on a group.** The module call becomes a one-line
  comment, the group leaves the outputs, and, when the identity read-model
  last recorded it as managed, the runner backs the state up and runs
  `tofu state rm module.group_<label>` before its plan. Nothing is
  destroyed. The CI policy reconcile and `query_state` skip it.
- **`include_root_group_in_admins: false`.** The root group's admin
  usernames are not merged into this group's `admins`, in the module call
  and in what `prune_stale_attachments` treats as declared. The state
  query still expects the merge (a base rule), so such a group shows
  `admins` drift.
- **`is_root: true`.** That group's `admins` are merged into every other
  group's admins. The root group's own module call is a normal one.
- **`key`/`secret` at `default`, literal, or `ENC[age:...]`.** `default`:
  `var.<team>_*` in the provider block, two variables in the vars file,
  and the load asserts the `TF_VAR_<team>_*` variables exist. A literal:
  quoted into the provider block (a secret in the emission; do not). An
  `ENC[age:...]` value: emitted as `local.sensitive["oktapam_key"]` /
  `["oktapam_secret"]` fed by the root's `data "external" "sensitive"`
  block, and no assertion fires. The API client ignores all three and
  reads the environment.
- **Encrypted versus clear roster values.** A `first_name`, `last_name`,
  `email` (or a bare-name `login`) that was declared encrypted is emitted
  as `local.sensitive["<key>_<label>"]` and its ciphertext goes into the
  root's decrypting data source; a clear value is emitted as a literal. A
  derived address inherits the encryption of `email_domain`
  (`<name>@ENC[age:...]`). Usernames in `members`/`admins` are always
  emitted in clear (a public join key by decision).
- **`gateway_selector` set, unset with a global, unset without.** The
  module argument is the builder's value, else `config.okta_gateway_selector`,
  else omitted (the module passes `null` and OPA assigns no gateway).
- **`oktapam` versus `okta` in `required_providers`.** `oktapam`: two
  sensitive variables, the credentials in the provider block by variable,
  the `TF_VAR` assertion at load. `okta`: no variables, `org_name` and
  `base_url` in the block, a warning at load without `OKTA_API_*`
  credentials, and `plan` skipped at generation while they are absent.
- **Dry run versus real run** (the `--dry-run` default versus
  `--no-dry-run`). Dry: `init -backend=false`, no generation-time plan,
  no state touched, no mirror; the deferred script is still written in
  full. Real: `init -reconfigure -backend-config=...`, then
  `materialize` and a plan in the private mirror (`-refresh=false` for the
  group root); the deferred script executes afterwards in-process, and
  the after-apply hooks run.
- **`apply_identity` off, on, or a list.** Off: the runner ends at
  `gate-plan`, the CI policy reconcile does not run, and the read-model's
  `workload` record stays at what is expected. On (`true`, or a list
  naming this builder): `apply-check` and `apply` follow the gate, and
  after the runner every managed group's CI policy is created, updated or
  left alone, the outcome written under the group in `identity.yaml`.
  `apply-check` re-reads the flag at execution and refuses (exit 3) when
  it is off by then.
- **Workload fields set versus unset.** Unset: `can_manage_workload_access()`
  is false, the read-model carries no `workload` key, the state query
  reports nothing about policies, and `verify login` skips every instance
  of the group ("names no workload connection and role"). Set: the
  reconcile runs after a real apply, the state query reads policies, roles
  and connections, and `verify login` proves the login.
- **`attributes:` declared on any group or user versus none.** Declared:
  the load validates names and types, the identity lifecycle writes
  `generated/identity/attributes-plan.json`, and the runner ends with
  `identity-attributes --probe --dry-run-apply` (a read-only probe; a write
  exits 4 by design). None: no plan file, no probe.
- **`os_family` `debian`/`ubuntu` versus anything else.** The base-image
  prerequisites use the apt repository path (with a `curl`/`gnupg`
  bootstrap) or the rpm/yum path.
- **`use_state_backends` true versus false.** True: a `backend "<type>" {}`
  stanza and the `.tfbackend.hcl` file; the runner's `init` carries
  `-backend-config=`. False: neither; `init` runs bare and the state is
  local to the root.
- **`--migrate-state <ws>` on a real run.** The runner sequence begins with
  `state-migration begin`, inits with `-migrate-state -force-copy`, plans
  with `-detailed-exitcode` and records the move after the gate (a base
  mechanism the identity roots share).

## What it tests and verifies

**At load (model construction and finalize).** Pydantic refuses a wrong
type or a missing `org`/`team`; the base model refuses `parameters`.
`UserBuilderBase.add_user_to_builder` raises `ValueError` when
`email_as_username` is true and `name` differs from `email`. The
workspace's `finalize()` asserts `TF_VAR_<team>_key` and
`TF_VAR_<team>_secret` exist when `oktapam` is declared and `key`/`secret`
are at `default` (an `AssertionError` that fails every configuration load,
`validate` included), and logs a warning when `okta` is declared and no
`OKTA_API_*` credential is set. Verdicts: an exception with the message
below, or a log line `Okta builder <name>: no okta/okta credentials in the
environment (...); 'plan' will be skipped for this workspace`.

**At `validate` (and before every run).** The plugin's item checks run
through the base's `validate_identity_items`
([identity_attributes.py](../base/src/cs_image_system/base/identity_attributes.py)):
`OktaTfUserRoBuilder.validate_user` refuses `managed: true`;
`validate_attributes` refuses unknown names, wrong types, ids below 1024
and blank strings on groups and users. Around them the base checks that a
group the read-model recorded as managed is still declared
([v2_validation.py](../base/src/cs_image_system/base/v2_validation.py)),
that every base image's `identity_types` names a registered plugin, that
an instance image's group resolves to an identity type its base declares,
and, when the instance-image lifecycle is requested with `apply_instances`
on, that no declared instance's canonical hostname is already registered
in its group's OPA registry (`registered_servers`; an unreadable registry
is a refusal, not a free name). Verdict: `validate` prints one `- <error>`
line per rule and exits 1; a run refuses before generating.

**At generation.** Every root runs `tofu fmt`, `tofu init` and `tofu
validate` in-process, so an emission the provider rejects fails the run
there. On a real run the group root plans with `-refresh=false` and the
user and read-only group roots plan, all in the private mirror with the
credentials of the environment; a lookup that finds no user, or a
provider that cannot authenticate, fails the plan and the run. The
builders log a warning when they emit a data source or resource with no
`okta` provider bound. After the identity lifecycle generates, the base
writes `meta-state/identity.yaml` from this plugin's answers and
`generated/identity/attributes-plan.json` when attributes are declared.

**At apply (the deferred runner).** `prune-attachments` lists the state
the root is bound to; when an attachment in state is no longer declared it
asks OPA (`group_users`) and removes only those OPA no longer holds, after
`state-migration backup` pulled the state to
`_private/state-backups/<ws>.backup-<run>.tfstate`; a failed list, backup
or removal exits non-zero and the runner stops before its plan; a silent
OPA removes nothing. The run log names every attachment and why (`... was
dropped from group ... and OPA no longer holds it; its attachment leaves
tofu state before the plan: state rm ...`, or `... OPA still holds it; the
plan will show the destroy`). Then `plan -out=tfplan`, `gate-plan` (exit 3
on any destroy not whitelisted, a stale or missing plan file) and, with the
flag on, `apply-check` (exit 3 when the flag is off now) and `apply`. When
attributes are declared, `identity-attributes --probe --dry-run-apply`
reads every planned item's live attributes and the team's conflict report
and prints `would set: ...` lines; it never writes.

**After apply.** With `apply_identity` on and the workload fields set, the
base's [workload_access.py](../base/src/cs_image_system/base/workload_access.py)
calls `ensure_workload_access` for every managed group and records
`{action: created|updated|unchanged|failed, policy, id, role_id, run}`
under the group's `workload` key in `meta-state/identity.yaml`; a failure
is an `ERROR` log line (`Group <g>: its CI login policy was NOT reconciled
(...); the CI login proof for this group fails until it is`), never fatal
to the apply that already happened. When an instance is decommissioned,
the base's [launch_params.py](../base/src/cs_image_system/base/launch_params.py)
calls `retire_servers_named` for its recorded hostname and logs the
retirement or an `ERROR` naming the stale server.

**In the state query** (`state query [--strict]`, every run's first step;
[state_query.py](../base/src/cs_image_system/base/state_query.py)).
`query_state` reads every managed group's `<group>_user` attributes,
members, the `<group>_admin` members, the login project's enrollment
tokens and, with the workload fields set, the policies, roles and
connections. The base turns it into: `missing [HARD]` when OPA answered
404 for the group; `missing` (not hard) when the group has no gid;
`missing [HARD]` when no IaC-owned enrollment token stands on the
project; `changed` when members or admins differ from the read-model;
`missing` when the workload role is unknown to OPA or the CI policy is
absent, `changed` when the CI policy no longer mirrors the user policy
(with the differing leaves named); a `note:` when the connection is
absent, still a `DRAFT`, or of unknown status; and `unavailable:
groups/<g>: <error>` when the call failed (a 401, no network, no
credentials), which is never drift. Verdicts land in
`generated/state-report.json` and on the console; `--strict` exits 1 on
any drift but `stale` and on any `unavailable:` line; a plain run refuses
only on `[HARD]` drift.

**In the login proof** (`verify login`, `just ci-login-proof`, the `sft`
leg of `cloud-verify`; [login_proof.py](../base/src/cs_image_system/base/commands/login_proof.py)).
For each standing instance of a group whose builder names the workload
objects: the machine is running, exactly one registration answers to its
hostname (`registered_servers`), `sft resolve` succeeds, `id` runs over
`sft ssh`. Verdicts go to `meta-state/login-proofs.yaml`; a failure exits 1.

**In the images.** `verify_commands` (sftd present, disabled, no token)
become in-bake assertions of every base image declaring `okta`, and
`activation_verify_commands` (the `tx.group` label, sftd enabled) of every
instance image, through the base's
[image_tests.py](../base/src/cs_image_system/base/image_tests.py); a
failing line fails the bake.

**In the gid shim.** `identity export-gids` answers terraform's `data
"external"` query from the OPA Attributes API; a requested group with no
`unix_gid` makes the command exit 1 with `export-gids: identity plugin
'okta' reported no gid for groups [...]`, which fails the plan or apply
that asked. Nothing is ever invented.

## When it fails

Failures that have happened, oldest first. Each names the symptom as the
operator saw it, what it meant, where to look and what to do; the dated
record is in [docs/OPERATIONS.md](../../docs/OPERATIONS.md),
[docs/history/LEDGER.md](../../docs/history/LEDGER.md),
[WORKLOAD_CONNECTION.md](../../WORKLOAD_CONNECTION.md) and
[tests/test_v2_hygiene_five.py](../../tests/test_v2_hygiene_five.py).

- **Memberships that already existed in OPA (stage 1, 2026-08-31 to
  2026-09-02).** The first identity plan wanted to *create*
  `oktapam_user_group_attachment` resources that stood in OPA already, and
  the provider would have errored on apply. Repair: `tofu import` each
  live attachment first; the import id is `<group>|<username>` (a `/`
  separator is rejected). Six imports, zero OPA writes, then a plan
  reading "No changes". Rule since: never let a plan create an attachment
  that already exists (OPERATIONS "Adopt out-of-band group membership").

- **An enrollment token deleted out of band (finding 32, 2026-09-02).**
  The identity plan ERRORS at refresh (oktapam 0.7.1 cannot plan the
  recreate); the state query shows `groups/<g>: missing ... IaC-owned
  launch enrollment token missing from the identity provider ... [HARD]`
  and every run refuses. Repair: `tofu state rm` the token resource in the
  group's module, then a gated identity apply mints a new one (a new
  value; instances launched before it keep the old token and are not
  affected). The state query's `enrollment_token` probe is the only
  witness.

- **A stale plan file passed the gate (finding 33, 2026-09-02).** A failed
  plan left an older `tfplan` that `gate-plan` accepted. Since then the
  runner starts every root with `rm -f tfplan` and `gate-plan` refuses a
  plan file older than the root's newest `*.tf` (exit 3, `STALE
  PLANFILE`).

- **`Okta builder oktagroups is missing a key value. Expected to find
  environment variable TF_VAR_nos_coastal_modeling_cloud_sandbox_key ...`
  (finding 87, 2026-09-15).** Every configuration load finalizes the
  workspace and asserts the pair; CI had been red for 245 runs because
  three tests inherited the developer's `.envrc` locally and had nothing
  in CI. Any command that loads the tree (`validate`, `run`, `state
  query`, `verify`) dies with this `AssertionError`. Repair: `source
  .envrc` (or export the two variables); in CI the secrets
  `TF_VAR_NOS_KEY`/`TF_VAR_NOS_SECRET`.

- **A secret that exists but is empty (2026-09-16).** Three green `live`
  runs ran nothing because `OKTA_API_PRIVATE_KEY` had been set to the
  empty string from a checkout missing `.envrc`; the finalize warning
  `no okta/okta credentials in the environment` is exactly what an empty
  value produces. Since then the CI gate names every missing or empty
  secret and fails, and `preflight` exits 2 on any credential-shaped
  variable (`OKTA_*`, `TF_VAR_*`, ...) that is set but empty. A job's
  conclusion is never proof its steps ran.

- **Five standing groups read as deleted (2026-09-21, stage 61 item 1
  landed 2026-09-23).** With an unsourced `.envrc` the API answered 401
  and `query_state` reported every group `present: false`, so the state
  query printed five `missing ... [HARD]` lines and refused the run.
  Since stage 61 a failed call is `{present: false, error: "HTTP 401
  Unauthorized"}` and the report says `unavailable: groups/<g>: HTTP 401
  Unauthorized`; only an answered 404 is `missing`. A 401 or "no gid"
  means the wrong or lapsed key pair: check which pair the environment
  exports (the last export wins) and rotate in the OPA console if it
  expired.

- **Three registrations of one hostname (stage 55, 2026-09-21).** Every
  relaunch of `coops-model` enrolled another server under the same
  canonical name and `sft ssh coops-model` could not choose. The
  team-level `/v1/teams/<team>/projects/...` path answered `401 Missing
  capability`; servers answer only under
  `/resource_groups/<rg>/projects/<prj>/servers` (`GET` 200, `DELETE`
  204), which the resolver walks from the resource-group and project
  *names* (`<g>_rg`, `<g>_rg_login`) to their ids. Since then a
  decommission or replacement retires the registration (an `ERROR`
  naming the hostname when it cannot: `Instance <n>: its OPA registration
  as '<h>' was NOT retired (...); a stale server will answer to that name
  until it is deregistered by hand`), and a run that can launch refuses a
  claimed or unreadable name (`could not check whether canonical hostname
  ... is already claimed ... refusing to launch on silence`). The two
  duplicates were deleted by hand on 2026-09-21.

- **The first reconcile refused by hard drift (2026-09-22).** The run
  that would create the CI policies was refused because their absence
  was reported as hard drift. Workload drift is now never hard: `missing`
  for an absent role (`workload role '...' named in the configuration is
  not known to OPA; the operator creates it (WORKLOAD_CONNECTION.md
  section 2)`) or an absent policy (`CI login policy '...' is absent; an
  identity run with apply_identity creates it ...`), `changed` for a
  policy that no longer mirrors (`... the next identity apply rewrites it
  -- <leaf>: <standing> != <desired>`). A strict query still fails on
  them; the identity apply is the repair.

- **`GET /v1/teams/<team>/workload_roles` answered 404 (2026-09-22).**
  The path is hyphenated, `workload-roles`, as Okta's PAM SDK carries it;
  the connections path is `connections/workloads`. A 404 from either
  listing surfaces as `unavailable:` in the state query and as `OPA's
  security policies or workload roles could not be read` from the
  reconcile.

- **`HTTP Error 400` and nothing more (2026-09-22).** The first live
  policy write taught nothing because the API's explanation was in the
  response body. `_send` now raises `POST /v1/teams/.../security_policy:
  HTTP 400 Bad Request -- <body>`; and a stored rule carries
  `security_policy_id`, the one field on which a copy differed from its
  original, so the comparison strips OPA's bookkeeping ids at every depth.

- **Every derived lookup failed on a real run (2026-09-22).** After stage
  51 the emission carries `<name>@ENC[age:...]` addresses; the
  generation-time plan ran in `generated/` and searched Okta for the
  ciphertext. The plan (and the runner) now run in the private mirror
  after `cs-image-system materialize .`. A hand `tofu plan` in
  `generated/identity/...` reproduces the failure; plan in
  `_private/identity/...` instead, with `CSIS_CONFIG_IDENTITY` and
  `cs-image-system` on `PATH`.

- **`sft resolve --quiet` exit 126 with no output (2026-09-22).** The
  client wanted a browser: run by hand it means an expired client session
  (`sft login` first); as the workload it means `OPA_TOKEN` is missing or
  was refused. The login proof records `the client has no session ...`.

- **A dropped membership blocked every identity plan (hygiene V item 3,
  2026-09-23).** A user removed from a group's roster after being removed
  in OPA made the provider ERROR on refresh, `user "x" is not present
  within group "g"`, instead of planning the destroy; the plan never ran.
  Three live attempts the same day taught that the read-model written at
  generation outlived the failed runner (it said the membership was
  already gone; only `tofu state list` is a witness), that the CLI's load
  changes directory to the configuration root (a runner step must act in
  the directory it was invoked from; the first backup pulled nothing from
  the wrong directory at 10:15, said "nothing to keep" and let the
  removal run unbacked), and that a pipe to `tail` masked the bar's exit
  code. Since then every identity runner carries `prune-attachments`
  between `init` and `plan`, backing the state up first; proved 10:46
  (backup serial 36 kept, one attachment removed, plan clean). If the
  plan still errors this way, the membership is one OPA still holds:
  either restore the roster entry or remove the member in OPA and rerun.

- **A replacement's old registration claimed the new machine's alias
  (stage 19 step 5, 2026-09-22).** `retire_servers_named` now runs for
  the machine a replacement retires, and the alias pass waits for a
  machine launched in the same run to enroll before writing `AltNames`.

- **Debian vendor images without `curl` or `gnupg` (found live, stage
  1).** The apt path of `base_image_prerequisites` installs them first.
  The rpm path needs nothing beyond `rpm` and `yum`.

Failures the code raises that have not been seen live:

- `OPA credentials for team '<team>' not found in the environment
  (TF_VAR_<team>_key/TF_VAR_<team>_secret or OKTAPAM_KEY/OKTAPAM_SECRET)`
  (`ValueError` from `credentials_from_env`): the gid shim exits 1 with
  it (`export-gids: ...`, failing the plan); the state query reports the
  builder `unavailable`; `registered_servers` answers `None` (a launch
  refuses on it); `prune-attachments` logs `... OPA cannot be asked
  whether it still holds them (...); nothing is removed` and continues.
- `OPA service_token response carried no bearer_token`: the key pair
  authenticated but the response had no token; same surfaces as above.
- `okta gid shim query must carry 'team' and 'api_host'`: a hand-written
  `data "external"` query; the emitted one always carries both.
- `identity plugin 'okta' reported no gid for groups [...]` (exit 1 from
  `export-gids`): the group's `<group>_user` OPA group has no `unix_gid`
  attribute yet, typically before the first apply created it, or the name
  differs. The plan that depends on `data.external.group_gids` fails;
  apply the identity root first, or check the group name in OPA.
- `user '<u>': builder <b> is okta-tf-ro (read-only) and cannot manage
  users; move the user to an okta-tf builder` (validate, exit 1).
- `group '<g>': unknown OPA attribute 'x' (known: [...])`, `... must be
  int, got ...`, `... is below the reserved range (1024)`, `... must not
  be empty` (validate, exit 1); the same forms for `user '<u>'`.
- `identity attributes: the provider reports conflicts; refusing: [...]`
  (exit 3) and `writing identity attributes is disabled (DESIGN Q7 not
  confirmed); N change(s) were NOT applied` (exit 4) from
  `identity-attributes`.
- `workload role '<r>' is not known to OPA; the operator creates it
  (WORKLOAD_CONNECTION.md section 2)`, `workload role '<r>' carries no
  id`, `user policy '<g>_v1_security_policy_user' is absent; the identity
  apply creates it, and the CI policy is a copy of it`, `OPA's security
  policies or workload roles could not be read` (`RuntimeError` from
  `ensure_workload_access`): logged as the `ERROR` above and recorded as
  `action: failed` with the message under the group's `workload` key; the
  next real identity run retries.
- `OPA login project for group '<g>' not found; cannot retire <id>`
  (`ValueError` from `retire_server`) and any non-404 error from the
  `DELETE`: the decommission logs the `NOT retired` error and completes;
  deregister by hand under the resource-group path.
- `OPA could not be asked for group '<g>''s servers; registration of
  '<h>' NOT retired` (`RuntimeError` from `retire_servers_named`): same
  handling.
- `Identity builder <ws>: 'state list' failed in <dir>; nothing is removed
  from state` and `'state rm <addr>' failed; the runner stops here` (exit
  1 from `prune-attachments`, stopping the runner before its plan); the
  backup step's own refusals (not an initialised root, a pull that fails,
  a location holding no state) stop it the same way.
- `prune-attachments: no group builder named '<b>'` (exit 2): the runner
  script names a builder the configuration no longer has; regenerate.
- `Group builder <ws> has no configured 'okta' provider; emitted data
  sources will rely on a default provider configuration that this
  workspace does not generate` (and the user builder's twin, a warning):
  the root will fail `tofu validate`; add the `okta` provider entry.
- `No transform for provider '<p>' on <Model>; passing its config through`
  (warning): a provider other than `oktapam`/`okta` was declared; its
  `config:` is emitted verbatim.
- `Sensitive value '<key>' registered twice with different ciphertexts in
  workspace '<ws>'` (`HclConfigConflictError`): two items produced the
  same sensitive key with different markers (two users whose labels
  collide, `avery.alpha` and `avery_alpha`); rename one.
- `Executable '<e>' not found for builder '<ws>' of type '<t>'`
  (`ValueError`): `executable:` names no `executables:` entry.
- `Builder <b> sets email_as_username, but user name '<n>' != email
  '<e>'` (`ValueError` at load).
- `identity: group '<g>' was managed by the system but is missing from
  the YAML; groups never leave the configuration (keep the entry with
  'unmanaged: true' ...)` (a base rule at validate, exit 1).
- `apply_identity is false NOW in <cfg>/_config.yml for root '<ws>' --
  this runner script was generated when it allowed the apply; not
  applying.` (exit 3 from `apply-check`): the flag changed since
  generation; regenerate or turn it back on.
- `login proof FAILED for <instance>: one registration: '<h>' has 2
  registrations: ...` / `resolves: sft resolve <h>: exit N -- ...` /
  `login: sft ssh <h> --command id: exit N -- ...` (exit 1 from `verify
  login`, the record in `meta-state/login-proofs.yaml`): a duplicate
  hostname, a machine that never enrolled, a deactivated or absent CI
  policy, a role condition the run does not match.

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
- Base code that calls this plugin's hooks:
  [read_models.py](../base/src/cs_image_system/base/read_models.py)
  (the identity read-model),
  [state_query.py](../base/src/cs_image_system/base/state_query.py)
  (drift rules),
  [workload_access.py](../base/src/cs_image_system/base/workload_access.py)
  (the CI policy reconcile),
  [launch_params.py](../base/src/cs_image_system/base/launch_params.py)
  (launch parameters, the enrollment token, the registry),
  [identity_attributes.py](../base/src/cs_image_system/base/identity_attributes.py)
  (attributes),
  [identity_gids.py](../base/src/cs_image_system/base/commands/identity_gids.py)
  (the gid shim command),
  [login_proof.py](../base/src/cs_image_system/base/commands/login_proof.py)
  (`verify login`),
  [state_migration.py](../base/src/cs_image_system/base/commands/state_migration.py)
  (the state backup), and the CLI in
  [cli.py](../system/src/cs_image_system/system/cli.py).
- Library:
  [hashicorp-utils](../hashicorp-utils) --
  [collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py)
  (providers, variables, backends, sensitive references),
  [blocks.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/blocks.py)
  (HCL rendering),
  [roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py)
  (`TerraformRootMixin`, the gated apply sequence).
- Terraform module called:
  [tfmodules/okta_opa_module](../../tfmodules/okta_opa_module)
  ([main.tf](../../tfmodules/okta_opa_module/main.tf),
  [variables.tf](../../tfmodules/okta_opa_module/variables.tf),
  [outputs.tf](../../tfmodules/okta_opa_module/outputs.tf)).
- Manuals: [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md) (section
  9, 11.5, 11.6, 13, 14), [docs/OPERATIONS.md](../../docs/OPERATIONS.md)
  ("CI logs in through the policy the system manages", "The state
  query", "Credentials contract", "The gid shim", "Rules: Identity"),
  [docs/DESIGN.md](../../docs/DESIGN.md) (N1, N7, N19, section D),
  [WORKLOAD_CONNECTION.md](../../WORKLOAD_CONNECTION.md).
- Tests: [tests/](tests) -- the module call, the workspace mixin, the
  resource emitters, the four builder roots, the gid shim, the server
  registry and the workload policy; the stage 61 runner step in
  [tests/test_v2_hygiene_five.py](../../tests/test_v2_hygiene_five.py).
