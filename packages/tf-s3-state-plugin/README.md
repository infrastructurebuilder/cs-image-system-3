# cs-image-system-tf-s3-state-plugin

This package is the S3 **state backend** plugin. It registers one model,
`TofuS3StateBuilderModel`, for the entries under `state_backends:` in
`cfg/state-backends*.yml`. At configuration load each entry becomes a
`BackendRegistration` in the run-wide `TerraformCollector`; every terraform
root that names the backend (or the default one) then gets an empty
`backend "s3" {}` block, a partial backend configuration file
`<workspace>.tfbackend.hcl`, an `init -backend-config=<file>` argument, and
`terraform_remote_state` data sources pointing at the other roots' state
files in the same bucket. The plugin itself emits no files and runs no
commands; the consumers do, through the collector.

## What it registers

The entry point, from [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.state"]
tf_s3_state_plugin = "cs_image_system.tf_s3_state_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/tf_s3_state_plugin/main.py)
returns a `TFS3StateTypes` metadata object (plugin metadata version `1`,
Python `3.13`).

| Service name (`type:` of a backend entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `s3` | `TofuS3StateBuilderModel` | `TofuS3StateBuilder` | `STATE_BACKEND_MODEL`, `STATE_BACKEND` |

A backend entry selects this plugin with `type: s3`. The same value is the
terraform backend type written into the consumers' `backend "s3" {}` block.
An entry's `name:` (`s3-east2` in the fixture) is what a consumer's
`state_configuration:` field names; `default` (the field's default) resolves
to the entry with `is_default: true`. The entry's `aliases:` register extra
names.

[tf_s3_state_builder.py](src/cs_image_system/tf_s3_state_plugin/tf_s3_state_builder.py)
also defines a `TofuVersionChecker` (`<binary> --version -json`, reading
`terraform_version`), but `main.py` does not register it; the checker that
serves `type: tofu` executables is the one in the AWS instance plugin.

## Models

### `TofuS3StateBuilderModel` (`s3`)

Source:
[tf_s3_state_models.py](src/cs_image_system/tf_s3_state_plugin/tf_s3_state_models.py).
Extends `StateBuilderModel`
([state_builder.py](../base/src/cs_image_system/base/models/state_builder.py)),
which adds nothing over `BuilderModel`
([builder_model.py](../base/src/cs_image_system/base/models/builder_model.py))
except the classification. Unlike the instance and storage builder models,
a state backend has **no `runtime`** field: it is not a
`RuntimeEnabledBuilderModel`. The model is a pydantic dataclass; unknown
keys are refused at load, and a `parameters:` key is refused with a message
naming `variables:`.

Inherited from the base:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | Backend name; normalized (lowercase, spaces to `_`). `/` and `\` are refused. |
| `type` | str | required | `s3`; also the terraform backend type. |
| `description` | str \| None | None | Free text. |
| `aliases` | set[str] | {} | Extra names the registry resolves to this backend. |
| `is_default` | bool | false | The backend chosen for `state_configuration: default`. More than one default is an error when a consumer resolves it. |
| `config`, `gitignore`, `tags` | | | Not read by this plugin. |

Fields this model adds. The **Emitted** column says whether the value
reaches the generated configuration: only the fields carried by
`BackendRegistration` do. The rest are accepted and validated at load and
are not read anywhere else.

| Field | Type | Default | Meaning | Emitted |
|---|---|---|---|---|
| `bucket` | str | required | The state bucket. | yes |
| `key` | str | required | The key **prefix** under which every workspace's state file lives; see the key rules below. | yes |
| `region` | str | `"us-east-2"` | The bucket's region. | yes |
| `encrypt` | bool | false | Server-side encryption of the state objects. | yes |
| `use_lockfile` | bool | true | S3-native state locking (a `.tflock` object beside the state file). | yes |
| `profile` | str \| None | None | The AWS shared-config profile the backend uses. | yes |
| `executable` | str \| None | `"tofu"` | Present for shape parity with the other tofu builders; this plugin runs no commands. | no |
| `required_plugins` | list[`TFTofuPluginModel`] | [] | Same; not read. | no |
| `allowed_account_ids` | list[str] | [] | | no |
| `forbidden_account_ids` | list[str] | [] | | no |
| `http_proxy` | str \| None | None | | no |
| `https_proxy` | str \| None | None | | no |
| `no_proxy` | list[str] | [] | | no |
| `insecure` | bool | false | | no |
| `max_retries` | int | 5 | | no |
| `access_key` | str \| None | None | Never emitted. Credentials come from the profile or the environment. | no |
| `secret_key` | str \| None | None | Never emitted. | no |
| `shared_config_file` | str \| None | None | | no |
| `shared_credentials_file` | str \| None | None | | no |
| `skips_credentials_validation` | bool | false | | no |
| `skip_region_validation` | bool | false | | no |
| `skip_requesting_account_id` | bool | false | | no |
| `skip_metadata_api_check` | bool | false | | no |
| `skip_s3_checksum` | bool | false | | no |
| `use_dualstack_endpoint` | bool | false | | no |
| `use_fips_endpoint` | bool | false | | no |
| `endpoints` | `StateEndpoints` \| None | None | `name` plus optional `dynamodb`, `s3`, `sts`, `iam`, `sso` endpoint overrides. | no |
| `assume_role` | `AssumeRoleConfig` \| None | None | `name`, `role_arn`, `duration`, `policy`, `policy_arns`, `session_name`, `source_identity`, `tags`, `transitive_tag_keys`. | no |
| `assume_role_with_web_identity` | `AssumeRoleWithWebIdentityConfig` \| None | None | `name`, `role_arn`, `duration`, `policy`, `policy_arns`, `session_name`, `web_identity_token`, `web_identity_token_file`. | no |

The nested types come from
[hashicorp.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/hashicorp.py)
in `hashicorp-utils`.

**Key prefix rules** (`__post_init__`):

- an empty `key` raises `ValueError` ("cannot be empty for 's3' type");
- trailing slashes are stripped and exactly one `/` is appended, so
  `statefiles/csia` and `statefiles/csia/` both become `statefiles/csia/`;
- a workspace's state file is `<key><super_safe_name(workspace)>.tfstate`,
  where `super_safe_name` lowercases and turns `-`, `.`, `:`, `+`, `/`, `\`,
  `@` and spaces into `_`. The workspace `open-tofu` under the prefix
  `statefiles/csia-image-system-test/` has the state file
  `statefiles/csia-image-system-test/open_tofu.tfstate`. `get_state_file_path(builder_name)` returns it.

**`finalize()`** runs at configuration load, before any generation phase. It
converts the model with `to_backend_registration()` and calls
`TerraformCollector().register_backend(...)`, so every consumer in the run
sees the registration. Registering the same name twice with different
values raises `HclConfigConflictError`.

### `BackendRegistration` and the S3 kind

The registration is type-agnostic (stage 47): the frozen dataclass in
[collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py)
carries what every backend has -- `name`, `type`, `is_default` -- plus the
type's own settings as an opaque mapping and the *kind* that renders them.
The collector names no field of any type: it asks the kind for a
workspace's `StateLocation`, for the settings the partial configuration
file needs, and for the settings a consumer's remote-state data source
needs (which differ: a data source has no `encrypt` or `use_lockfile`).

This plugin's kind, `S3BackendKind` in
[tf_s3_state_models.py](src/cs_image_system/tf_s3_state_plugin/tf_s3_state_models.py),
holds the S3 knowledge:

| Settings the model registers | `location(settings, workspace)` | `backend_settings(...)` | `remote_state_settings(...)` |
|---|---|---|---|
| `bucket`, `region`, `key_prefix`, `encrypt`, `use_lockfile`, `profile` | `s3://<bucket>/<key prefix>/<super_safe_name(workspace)>.tfstate`, the key normalised (stage 46) | `bucket`, `key`, `region`, `encrypt`, `use_lockfile`, `profile` when set | `bucket`, `key`, `region`, `profile` when set |

The collector resolves a consumer's `state_configuration` with
`resolve_backend(name)`: `default`, `None` or `""` means the single
registration with `is_default: true` (more than one raises
`HclConfigConflictError`; none yields no backend); any other value is looked
up by name. A workspace with no resolvable backend is simply unbound: no
backend block, no partial configuration file, bare `init`. A registration
without a kind is refused the moment it is asked for a location.

### Adding a backend type

A backend type is a model plus one kind (stage 47.5); the next one is a day:

1. A model under `state_backends:` with the type's fields, `csis_name()`
   returning the terraform backend type (`local`, `gcs`, `azurerm`, ...),
   `csis_classifier()` `STATE_BACKEND_MODEL`, and a `finalize()` that
   registers `BackendRegistration(name, type, settings, kind, is_default)`
   with the collector -- the settings in the type's own vocabulary.
2. A kind with three methods: `location(settings, workspace)` returning a
   `StateLocation` (`<type>://<container>/<key>`, the key normalised; for an
   object store `StateLocation.of(type, bucket, prefix, workspace)`),
   `backend_settings(settings, workspace)` (the `.tfbackend.hcl` keys, in
   order) and `remote_state_settings(settings, workspace)` (the data
   source's `config`).
3. The plugin metadata registers the model and a `StateBuilderBase`
   subclass under the type's name; a fixture entry and one collector test
   per rendering.

Nothing else changes: the collector, the roots mixin, the runner header,
the location record and the migration operation render whatever the kind
returns.

## The builder

`TofuS3StateBuilder` in
[tf_s3_state_builder.py](src/cs_image_system/tf_s3_state_plugin/tf_s3_state_builder.py)
extends `StateBuilderBase`
([builder_base_state.py](../base/src/cs_image_system/base/basic/builder_base_state.py))
and implements no hooks: it generates nothing and defers nothing. It exists
so the registry can pair the model with a builder class. Everything the
backend causes to appear is emitted by the **consumers** (the instance,
storage and identity roots) through the collector:

1. **Binding.** In its `generate_items_before`, a root calls
   `TerraformCollector().set_backend(<workspace>, <state_configuration>)`.
2. **The terraform block.** `generate_terraform_block(workspace)` writes an
   empty `backend "s3" {}` inside `terraform {}` when the workspace resolves
   a backend and `config.use_state_backends` is true. The block is empty by
   design: this is terraform's *partial configuration*, and the settings
   live in the file below.
3. **The partial configuration file.** `generate_backend_config(workspace)`
   returns the `key = value` lines the root writes to
   `<builder>/<phase>/<builder>-<phase>.tfbackend.hcl` (the path is
   `get_path_for_phase(phase, suffix=".tfbackend.hcl")` on the root): a
   comment naming the backend and workspace, then `bucket`, `key` (the
   workspace's state file path), `region`, `encrypt`, `use_lockfile`, and
   `profile` when set. Booleans are written lowercase and unquoted, strings
   quoted. The list is empty, and no file is written, when backends are
   disabled or the workspace is unbound.
4. **How `init` consumes it.** `TerraformRootMixin` in
   [roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py)
   builds the arguments:
   - a **dry run** initializes without the backend:
     `init -backend=false`. Providers are installed and the emission is
     validated, and the remote state is never touched;
   - a **real run** at generation time:
     `init -reconfigure -backend-config=<builder>-<phase>.tfbackend.hcl`
     (the bare file name, because tofu runs inside the phase directory).
     `-reconfigure` is always passed: the state is remote, so there is
     nothing to migrate, and a changed backend argument (for example
     `encrypt`) would otherwise make tofu refuse with "Backend configuration
     changed";
   - the **runner script** (`run-<lifecycle>.sh`) repeats an init of its
     own before every plan, in the real-run form:
     `init -input=false -reconfigure -backend-config=<file>`, so a fresh
     clone with no `.terraform/` can execute it.
5. **Remote state between roots.** A consumer calls
   `reference_remote_state(consumer, producer)`; `generate_remote_state_datasources`
   then writes `data "terraform_remote_state" "<producer label>"` with
   `backend = "s3"` and a `config` of `bucket`, `key` (the producer's state
   file path), `region` and `profile`. The backend used is the producer's
   own binding, else the default. `encrypt` and `use_lockfile` are not part
   of a remote-state `config`. This is how the instance root reads the
   storage roots' `storage_<label>` outputs and the identity root's
   `group_gids`.
6. **The runner-script header.** Each `run-<lifecycle>.sh` starts with one
   `# state: workspace <name> -> s3://<bucket>/<state file path>` line per
   bound workspace of that lifecycle.

The whole mechanism is gated by `config.use_state_backends` in
`cfg/_config.yml`. When it is false, `workspace_backend()` answers None for
every workspace: no backend block, no `.tfbackend.hcl`, no remote-state data
sources, and `init` runs bare.

## Emission

From the frozen golden emission over the test fixture. The fixture binds
its storage roots to `s3-east1` and every other root to `s3-east2`
(stage 46), so there is one partial configuration per root, all with
`encrypt = true` and `use_lockfile = true`:

| Workspace | File |
|---|---|
| `open-tofu` (AWS instances) | [open-tofu-instance-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation.tfbackend.hcl) |
| `tofu-gce` (GCE instances) | [tofu-gce-instance-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation.tfbackend.hcl) |
| `aws-ebs` | [aws-ebs-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/aws-ebs/storage-generation/aws-ebs-storage-generation.tfbackend.hcl) |
| `aws-efs` | [aws-efs-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/aws-efs/storage-generation/aws-efs-storage-generation.tfbackend.hcl) |
| `aws-s3` | [aws-s3-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/aws-s3/storage-generation/aws-s3-storage-generation.tfbackend.hcl) |
| `gcp-pd` | [gcp-pd-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/gcp-pd/storage-generation/gcp-pd-storage-generation.tfbackend.hcl) |
| `gcp-gcs` | [gcp-gcs-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/gcp-gcs/storage-generation/gcp-gcs-storage-generation.tfbackend.hcl) |
| `oktagroups` (identity groups) | [oktagroups-group-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tfbackend.hcl) |
| `okta-tf-users` (identity users) | [okta-tf-users-user-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tfbackend.hcl) |

The `open-tofu` file, in full:

```hcl
# Backend 's3-east2' (s3) partial configuration for workspace open-tofu
bucket = "noaa-ioos-cloud-sandbox-tfstate"
key = "statefiles/csia-image-system-test/open_tofu.tfstate"
region = "us-east-2"
encrypt = true
use_lockfile = true
profile = "noaa"
```

The consumer side, in
[open-tofu-instance-generation.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation.tf):
the empty `backend "s3" {}` inside `terraform {}`, and six
`data "terraform_remote_state"` blocks (`aws_efs`, `aws_ebs`, `aws_s3`,
`gcp_pd`, `gcp_gcs`, `oktagroups`), each with `backend = "s3"` and a
`config` naming the PRODUCER's bucket, its state file under the producer's
prefix, the region and the profile -- the storage roots' in `s3-east1`'s
bucket, the identity root's in `s3-east2`'s.

The runner scripts,
[run-storage.sh](../../tests/fixtures/v2_golden/generated/storage/run-storage.sh)
and
[run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh),
carry the `# state: workspace ... -> s3://...` header lines and, per root,
`tofu init -input=false -reconfigure -backend-config=<file>` before the
plan.

This plugin calls no `tfmodules/` module.

## Example configuration

From the test fixture. The default backend,
[cfg/state-backends-2.yml](../../tests/fixtures/config/cfg/state-backends-2.yml):

```yaml
state_backends:
  - name: s3-east2
    type: s3
    encrypt: true
    is_default: true
    bucket: noaa-ioos-cloud-sandbox-tfstate
    key: statefiles/csia-image-system-test/
    region: us-east-2
    profile: noaa
```

A second, non-default backend,
[cfg/state-backends.yml](../../tests/fixtures/config/cfg/state-backends.yml):

```yaml
state_backends:
  - name: s3-east1
    type: s3
    encrypt: true
    bucket: my-east1-tfstate-bucket
    key: statefiles/csia/
    region: us-east-1
    profile: noaa
```

A consumer naming the backend, from
[cfg/instance-builders.yml](../../tests/fixtures/config/cfg/instance-builders.yml):

```yaml
instance_builders:
  - name: open-tofu
    type: tofu
    is_default: true
    runtime: aws-east2-runtime
    executable: open-tofu-1
    state_configuration: s3-east2
```

A storage builder that omits `state_configuration:` (the fixture's `aws-ebs`)
gets `default`, which resolves to `s3-east2` because it is the only entry
with `is_default: true`.

The gate, in [cfg/_config.yml](../../tests/fixtures/config/cfg/_config.yml):

```yaml
config:
  use_state_backends: true
```

## Related

- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)
  and [cs-image-system-tf-gcp-plugin](../tf-gcp-plugin/README.md): the
  consumers whose `state_configuration:` names a backend.
- [hashicorp-utils collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py):
  `TerraformCollector`, `BackendRegistration`, `RemoteStateReference`, and
  the generators for the terraform block, the partial configuration and the
  remote-state data sources.
- [hashicorp-utils roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py):
  `TerraformRootMixin`, the `init` argument rules and the deferred sequence.
- [hashicorp-utils tests/test_terraform_collector.py](../hashicorp-utils/tests/test_terraform_collector.py)
  and [tests/test_roots.py](../hashicorp-utils/tests/test_roots.py): the unit
  tests that pin the backend block, the partial configuration and the init
  arguments.
- [tests/test_v2_state_encryption.py](../../tests/test_v2_state_encryption.py):
  the test that requires every declared and emitted S3 backend to encrypt.
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md): the operator's view of
  state, dry runs and runner scripts.
