# cs-image-system-tf-s3-state-plugin

This package is the S3 **state backend** plugin. It registers one model,
`TofuS3StateBuilderModel`, for the entries under `state_backends:` in
`cfg/state-backends*.yml`. At configuration load each entry becomes a
`BackendRegistration` in the run-wide `TerraformCollector`; every terraform
root that names the backend (or the default one) then gets an empty
`backend "s3" {}` block, a partial backend configuration file
`<workspace>.tfbackend.hcl`, an `init -backend-config=<file>` argument, and
`terraform_remote_state` data sources pointing at the other roots' state
files wherever those live (the producer's own backend, of whatever type).
The plugin itself emits no files and runs no commands; the consumers do,
through the collector.

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
to the entry with `is_default: true`. The entry's `aliases:` are names it
answers to as well: a `state_configuration:` that names an alias binds to
this backend (stage 63; until 2026-09-25 an alias was refused as "not
declared").

The checker that serves `type: tofu` executables is the one in the AWS
instance plugin; this package registers none (a second copy that was never
registered was removed in stage 63).

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
| `name` | str | required | Backend name; normalized (trimmed, lowercased, spaces and `:` to `_`). `/` and `\` are refused; `default`, `self` and the empty string are refused. |
| `type` | str | required | `s3`; also the terraform backend type. |
| `description` | str \| None | None | Free text. |
| `aliases` | set[str] | {} | Extra names, normalized like `name`, checked for collisions within the class; a `state_configuration:` may name one (stage 63). |
| `is_default` | bool | false | The backend chosen for `state_configuration: default`. A second `is_default: true` in the class is refused at load. |
| `config`, `gitignore`, `tags` | | | Not read by this plugin. |

Fields this model adds. The first six are the core the backend file
always carries; every other one is a terraform s3-backend argument that is
**passed through** (stage 63, decided 2026-09-25): emitted into the
backend file and into every consumer's remote-state `config` when it
differs from its default, and absent otherwise, so a tree that declares
none renders exactly as before.

| Field | Type | Default | Meaning | Emitted |
|---|---|---|---|---|
| `bucket` | str | required | The state bucket. | always |
| `key` | str | required | The key **prefix** under which every workspace's state file lives; see the key rules below. | always |
| `region` | str | `"us-east-2"` | The bucket's region. | always |
| `encrypt` | bool | false | Server-side encryption of the state objects. | always (backend file) |
| `use_lockfile` | bool | true | S3-native state locking (a `.tflock` object beside the state file). | always (backend file) |
| `profile` | str \| None | None | The AWS shared-config profile the backend uses. | when set |
| `executable` | str \| None | None | The `cfg/executables.yml` entry the roots bound here run. When declared it must exist in the executables list (`validate`, `check_state_backend_executables`), where it is version-checked like every entry; unset, nothing is checked. | no |
| `allowed_account_ids`, `forbidden_account_ids` | list[str] | [] | The account guards. | when non-empty |
| `http_proxy`, `https_proxy` | str \| None | None | Proxies for the backend's AWS calls. | when set |
| `no_proxy` | list[str] | [] | Hosts that bypass the proxy; written as the comma-separated string tofu takes. | when non-empty |
| `insecure` | bool | false | Skip TLS verification. | when true |
| `max_retries` | int | 5 | AWS API retries. | when not 5 |
| `shared_config_file`, `shared_credentials_file` | str \| None | None | One file each; written as the lists tofu takes, `shared_config_files = [...]` and `shared_credentials_files = [...]`. | when set |
| `skip_credentials_validation`, `skip_region_validation`, `skip_requesting_account_id`, `skip_metadata_api_check`, `skip_s3_checksum` | bool | false | The backend's skip flags. | when true |
| `use_dualstack_endpoint`, `use_fips_endpoint` | bool | false | Endpoint variants. | when true |
| `endpoints` | `StateEndpoints` \| None | None | `{dynamodb, s3, sts, iam, sso}` endpoint overrides; written as an object with the members that are set. | when set |
| `assume_role` | `AssumeRoleConfig` \| None | None | `{role_arn (required), duration, external_id, policy, policy_arns, session_name, source_identity, tags, transitive_tag_keys}`; written as an object. | when set |
| `assume_role_with_web_identity` | `AssumeRoleWithWebIdentityConfig` \| None | None | `{role_arn (required), duration, policy, policy_arns, session_name, web_identity_token, web_identity_token_file}`; written as an object. | when set |

**Refused at load**, each with what to do instead: `access_key` and
`secret_key` (credentials never live in the tree: name a `profile`, or
`assume_role`); `skips_credentials_validation` (the old spelling, never
read; the argument is `skip_credentials_validation`); `required_plugins`
(a state backend has no plugins). A setting that was declared encrypted is
written as its ciphertext and restored in the private copy tofu runs from.

The nested types are strict (an unknown member is refused) and live in
[tf_s3_state_models.py](src/cs_image_system/tf_s3_state_plugin/tf_s3_state_models.py);
they used to require a `name` member that no backend argument has.

**Key prefix rules** (`__post_init__`):

- an empty `key` raises `ValueError` ("cannot be empty for 's3' type");
- trailing slashes are stripped and exactly one `/` is appended, so
  `statefiles/csia` and `statefiles/csia/` both become `statefiles/csia/`;
- a workspace's state file is `<key><super_safe_name(workspace)>.tfstate`,
  where `super_safe_name` lowercases and turns `-`, `.`, `:`, `+`, `/`, `\`,
  `@` and spaces into `_`. The workspace `open-tofu` under the prefix
  `statefiles/csia-image-system-test/` has the state file
  `statefiles/csia-image-system-test/open_tofu.tfstate`. `get_state_file_path(builder_name)` returns it;
- the key is normalised again when a location is computed (stage 46):
  repeated slashes collapse, leading and trailing ones are stripped, and a
  `.` or `..` segment is refused -- at `validate`, not at load.

**`finalize()`** runs at configuration load, before any generation phase. It
converts the model with `to_backend_registration()` and calls
`TerraformCollector().register_backend(...)`, so every consumer in the run
sees the registration. Registering the same name twice with different
values raises `HclConfigConflictError`; from a configuration this cannot be
reached, because the loader refuses a duplicate name first.

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
up by registration name, and only by name. A workspace with no resolvable
backend is simply unbound: no backend block, no partial configuration file,
bare `init`. A registration without a kind is refused the moment it is
asked for a location.

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
returns. The `local` and `gcs` types
([local-state-plugin](../local-state-plugin/README.md),
[gcs-state-plugin](../gcs-state-plugin/README.md)) were added this way.

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
   `TerraformCollector().bind_workspace(<workspace>, <own state_configuration>, <its runtime's>)`,
   which binds the first value that names a backend -- the root's own, else
   its runtime's, else `default` -- with `set_backend`. An identity root has
   no runtime and passes its own value alone. A workspace bound a second
   time to a *different* backend is refused (`HclConfigConflictError`);
   rebinding to the same one is a no-op.
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
     clone with no `.terraform/` can execute it;
   - a root whose state **moves** this run (`run --no-dry-run --migrate-state <root>`)
     inits with `init -input=false -migrate-state -force-copy -backend-config=<file>`
     instead, between a `state-migration begin` and a `state-migration finish`
     step (stage 46.4.3; see "Where state lives" in
     [docs/OPERATIONS.md](../../docs/OPERATIONS.md)).
5. **Remote state between roots.** A consumer calls
   `reference_remote_state(consumer, producer)`; `generate_remote_state_datasources`
   then writes `data "terraform_remote_state" "<producer label>"` with
   `backend = "<producer's backend type>"` and a `config` the producer's
   kind renders -- for an S3 producer `bucket`, `key` (the producer's state
   file path), `region` and `profile`. The backend used is the producer's
   own binding, else the default. `encrypt` and `use_lockfile` are not part
   of a remote-state `config`. This is how the instance root reads the
   storage roots' `storage_<label>` outputs and the identity root's
   `group_gids`, across backends and across types.
6. **The runner-script header.** Each `run-<lifecycle>.sh` starts with one
   `# state: workspace <name> -> s3://<bucket>/<state file path>` line per
   bound workspace of that lifecycle.
7. **The location record.** After every generation, dry or real, the run
   writes each bound workspace's resolved location and backend-file
   settings to `meta-state/state-locations.yaml` (stage 46.4); a later
   run's move guard compares against that record, not the emission.

The whole mechanism is gated by `config.use_state_backends` in
`cfg/_config.yml`. When it is false, `workspace_backend()` answers None for
every workspace: no backend block, no `.tfbackend.hcl`, no remote-state data
sources, and `init` runs bare.

## Emission

From the frozen golden emission over the test fixture. The fixture binds
its storage roots to `s3-east1`, its instance roots to `s3-east2` (stage 46)
and its identity roots to the `local` backend `local-dev` (stage 47), so
there is one partial configuration per root; the seven S3 ones all carry
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

The two identity roots' files,
[oktagroups-group-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/oktagroups/group-generation/oktagroups-group-generation.tfbackend.hcl)
and
[okta-tf-users-user-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/identity/okta-tf-users/user-generation/okta-tf-users-user-generation.tfbackend.hcl),
are `local` renderings (a `path` line alone) and are not this plugin's.

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
`data "terraform_remote_state"` blocks. Five (`aws_efs`, `aws_ebs`,
`aws_s3`, `gcp_pd`, `gcp_gcs`) carry `backend = "s3"` and a `config`
naming the PRODUCER's bucket (`s3-east1`'s), its state file under the
producer's prefix, the region and the profile; the sixth (`oktagroups`)
carries `backend = "local"` and a `path`, because the identity root keeps
its state on disk.

The runner scripts,
[run-storage.sh](../../tests/fixtures/v2_golden/generated/storage/run-storage.sh)
and
[run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh),
carry the `# state: workspace ... -> s3://...` header lines and, per root,
`tofu init -input=false -reconfigure -backend-config=<file>` before the
plan. The golden's
[meta-state/state-locations.yaml](../../tests/fixtures/v2_golden/meta-state/state-locations.yaml)
is the location record the same run writes.

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

The fixture's storage roots name `s3-east1` in
[cfg/storage-builders.yml](../../tests/fixtures/config/cfg/storage-builders.yml).
A root that omits `state_configuration:` gets `default`, which inherits its
runtime's `state_configuration` when that names a backend, else resolves to
the one entry with `is_default: true` -- `s3-east2` here. The live
configuration keeps every root on its default backend by decision.

The gate, in [cfg/_config.yml](../../tests/fixtures/config/cfg/_config.yml):

```yaml
config:
  use_state_backends: true
```

## Prerequisites and integration

Everything below must exist **outside** the system. The plugin creates
nothing and checks nothing on AWS: the first thing to touch the bucket is
tofu's `init` in a real run, and the first thing to fail when a
prerequisite is missing is that `init` (or the `plan` after it).

**The bucket.** An S3 bucket named by `bucket`, in the region named by
`region`, that the caller can read and write under the prefix named by
`key`. The system never creates it, never checks that it exists, and never
lists it; `validate` reasons about the declaration alone. Nothing in the
system requires versioning or a bucket policy; the live bucket's tags and
lifecycle are read by the state query for other reasons (the storage
plugins), not by this plugin.

**Permissions.** Whatever identity tofu runs as needs, on the state bucket:
read of every object under the prefix for a `plan` (its own state file and
every producer's state file a `terraform_remote_state` data source names --
those may be in *another* backend's bucket, so read there too), and write
of its own state file for an `apply`. With `use_lockfile: true` (the
default) tofu also creates and deletes a `<state file>.tflock` object
beside the state file during every state write, so write access must
cover that key. In CI the read-only role (`AWS_ROLE_ARN`) carries read on
the state bucket and the write role (`AWS_APPLY_ROLE_ARN`) read/write on
this configuration's state prefix; the `live` job never plans against
remote state because a plan needs the bucket (see
[docs/OPERATIONS.md](../../docs/OPERATIONS.md), "The `live` job").

**Credentials.** The plugin passes exactly one credential hint to tofu:
`profile`, written as `profile = "<name>"` into the `.tfbackend.hcl` and
into every remote-state `config` that names this backend. Tofu's S3
backend resolves that profile from `~/.aws/config` and
`~/.aws/credentials` at `init` and `plan` time; an SSO profile needs a live
session (`aws sso login --profile <name>`), and the CI credentials shim
writes the federated keys into `~/.aws/credentials` under the profile's
section so a named profile still finds them. With `profile` unset, no
`profile =` line is written and tofu uses the default AWS credential chain
(`AWS_PROFILE`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/
`AWS_SESSION_TOKEN`, then the shared files). `assume_role`,
`assume_role_with_web_identity`, the shared files and `endpoints` are
passed through when declared (stage 63), so they steer tofu the way the
terraform backend documents; static keys are refused at load, so
credentials still come from the profile, the environment or an assumed
role. The configuration
load checks the *runtime's* AWS session (the runtime's
`credentials.profile_name`), not the backend's `profile`; a backend whose
profile is unknown or expired fails at tofu's `init`, not at load.

**Tools.** Tofu (or terraform) with an `s3` backend that accepts
`use_lockfile` -- S3-native locking, no DynamoDB table is declared or
needed. The binary is the *consumer root's* `executable` (an entry of
`cfg/executables.yml`, `open-tofu-1` with `version: ">1,<2"` in the
fixture). A backend's own `executable`, when declared, must name an entry
of that list, which `validate` version-checks (stage 63). The
`gate-plan` step that follows every plan needs the same binary.

**Network.** From wherever tofu runs, HTTPS to S3 in the bucket's region
(`s3.<region>.amazonaws.com`) and to STS for the profile's credentials.
`endpoints`, `http_proxy`, `https_proxy`, `no_proxy`, `use_fips_endpoint`
and `use_dualstack_endpoint` are passed through when declared (stage 63);
tofu's own environment (`HTTPS_PROXY`, `AWS_ENDPOINT_URL_S3`) still works
when they are not. A
dry run needs no network for the backend at all: its `init -backend=false`
never contacts S3.

**Inside the system.** The plugin depends on `cs-image-system-system` and
`cs-image-system-hashicorp-utils` ([pyproject.toml](pyproject.toml)); the
collector it registers into, the roots mixin that builds the `init`
arguments and the location record all live in `hashicorp-utils`. It is
wired to the rest of the configuration by:

- `config.use_state_backends` in `cfg/_config.yml` -- off (the default is
  `false`), nothing below is emitted;
- `state_configuration` on every instance, storage and identity builder
  and on both runtime types -- the names that bind a root to an entry;
- `cs_image_system.plugins.state` -- the entry-point group the loader
  reads; the `local` and `gcs` types register under the same group and
  share the collector, which is why an S3 root can read a `local` root's
  state.

## Configuration reference

The YAML this plugin owns is one entry of `state_backends:` with
`type: s3`. Every field the model accepts is listed; **read** says who
reads it. "Accepted, not read" means the load validates the value's type
and nothing else ever looks at it -- a typo in such a field is refused
(unknown key), a wrong value is not.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The backend's name; what `state_configuration:` names. Trimmed, lowercased, spaces and `:` to `_`; `/` and `\` refused; `default`, `self` and `""` refused. Read by the collector (registration key), the `.tfbackend.hcl` header comment and the location record. |
| `type` | str | required | `s3`. Read by the loader (selects this model) and written as the terraform backend type in `backend "s3" {}` and every remote-state `backend = "s3"`. |
| `description` | str or null | null | Accepted, not read. |
| `aliases` | list[str] | `[]` | Extra names the backend answers to: `state_configuration: <alias>` binds to it (stage 63). An alias equal to another entry's name or alias is refused at load. |
| `is_default` | bool | `false` | The entry `state_configuration: default` (and an omitted value, when the runtime names nothing) resolves to. At most one per class; a second is refused at load. Read by the collector's `resolve_backend`. |
| `executable` | str or null | null | When declared, must name a `cfg/executables.yml` entry (`validate`), which is version-checked; unset, nothing is checked. |
| `required_plugins` | | | Refused at load: a state backend has no plugins. |
| `config` | mapping | `{}` | Accepted, not read. |
| `gitignore` | list[str] | `[]` | Accepted, not read. |
| `tags` | mapping | `{}` | Accepted, not read. |
| `bucket` | str | required | The state bucket. Emitted as `bucket =` in the backend file and every remote-state `config`; part of the location. |
| `key` | str | required, non-empty | The key prefix; a trailing `/` is enforced at load, the location normalises it again. Emitted as `key = <prefix><workspace>.tfstate`. |
| `region` | str | `us-east-2` | The bucket's region. Emitted as `region =` in both places. |
| `encrypt` | bool | `false` | Server-side encryption of the state objects. Emitted as `encrypt = true` or `encrypt = false` in the backend file only. The fixture and the live tree declare `true` everywhere (stage 39); the test bar requires it of every declared and emitted S3 backend. |
| `use_lockfile` | bool | `true` | S3-native locking. Emitted as `use_lockfile = true` or `use_lockfile = false` in the backend file only. |
| `profile` | str or null | null | The AWS profile. Emitted as `profile =` in both places when set; omitted when null or empty. |
| `allowed_account_ids`, `forbidden_account_ids` | list[str] | `[]` | Passed through when non-empty (stage 63). |
| `http_proxy`, `https_proxy` | str or null | null | Passed through when set. |
| `no_proxy` | list[str] | `[]` | Passed through when non-empty, as a comma-separated string. |
| `insecure` | bool | `false` | Passed through when true. |
| `max_retries` | int | `5` | Passed through when not 5. |
| `access_key`, `secret_key` | | | Refused at load: static keys never live in the tree. |
| `shared_config_file`, `shared_credentials_file` | str or null | null | Passed through when set, as the one-element lists `shared_config_files` / `shared_credentials_files`. |
| `skip_credentials_validation` | bool | `false` | Passed through when true. The old spelling `skips_credentials_validation` is refused by a message naming this one. |
| `skip_region_validation`, `skip_requesting_account_id`, `skip_metadata_api_check`, `skip_s3_checksum` | bool | `false` | Passed through when true. |
| `use_dualstack_endpoint`, `use_fips_endpoint` | bool | `false` | Passed through when true. |
| `endpoints` | mapping or null | null | `{dynamodb, s3, sts, iam, sso}`; passed through as an object of the members set. |
| `assume_role` | mapping or null | null | `{role_arn (required), duration, external_id, policy, policy_arns, session_name, source_identity, tags, transitive_tag_keys}`; passed through as an object. |
| `assume_role_with_web_identity` | mapping or null | null | `{role_arn (required), duration, policy, policy_arns, session_name, web_identity_token, web_identity_token_file}`; passed through as an object. |
| `parameters` | | | Refused at load with a message naming `variables:`. |

Fields the plugin reads from **other** YAML:

| Where | Field | Effect on this plugin |
|---|---|---|
| `cfg/_config.yml` | `config.use_state_backends` (bool, default `false`) | The gate on every emission: the backend block, the backend file, the remote-state data sources, the runner header, the location record and the `validate` location checks all exist only when it is `true`. |
| instance, storage and identity builders | `state_configuration` (str, default `default`) | Names the entry the root binds to. |
| runtime builders (`aws`, `gce`) | `state_configuration` (str, default `default`) | The second rung: a root at `default` inherits its runtime's value when that names a backend. |

### Variations

- **Dry run vs real run.** In a dry run (the CLI default) every terraform
  root's generation-time `init` is `init -backend=false`: providers are
  installed and the emission validated, and the bucket is never contacted.
  In a real run (`--no-dry-run`) the generation-time `init` is
  `init -reconfigure -backend-config=<file>`, which reads the bucket and
  writes nothing to it until the deferred `apply`. Both modes emit the same
  files, the same runner scripts (always in the real-run form) and the
  same location record; only the in-process `init` differs.
- **Apply flag on vs off.** No difference to this plugin: the backend is
  initialised at generation in every real run, and the deferred sequence's
  own `init` runs whether or not an `apply` follows it. Only the
  `state-migration finish` recording step is tied to the apply gate, and
  that belongs to a migration run.
- **`use_state_backends: true` vs `false`.** Off: `workspace_backend()` is
  None for every workspace, the terraform block carries no `backend`
  block, no `.tfbackend.hcl` is written, no remote-state data source is
  emitted (a consumer that references a producer gets nothing, not an
  error), `init` is bare, the runner headers carry no `# state:` line,
  `validate` skips the location checks and the run records no locations.
  The registrations still happen at load, so a bad entry is refused either
  way.
- **`state_configuration` names this backend vs `default` vs an
  alias.** A name binds directly. `default` (or an omitted value) inherits
  the root's runtime's `state_configuration` when that names a backend,
  else the one `is_default` entry, else nothing -- an unbound root, no
  backend block, bare `init`, no line in the runner header, no location
  record. An alias binds exactly as the name does (stage 63).
- **`is_default: true` vs not.** Only the default entry is reachable
  through `default`; a non-default entry has to be named. Two defaults are
  refused at load.
- **`profile` set vs unset.** Set: `profile = "<name>"` in the backend
  file and in every remote-state `config` that reads this backend's state.
  Unset (or empty): the line is absent in both, and tofu's default
  credential chain applies.
- **`encrypt` and `use_lockfile` true vs false.** Both are always written
  to the backend file, lowercase and unquoted, whichever value they hold;
  neither is ever written to a remote-state `config`. Changing either
  under an already-initialised root is what `-reconfigure` is for: without
  it tofu refuses with "Backend configuration changed".
- **`key` spelled with or without a trailing slash, or with `//`.** All
  spellings of one prefix are one location: `statefiles/csia`,
  `statefiles/csia/` and `statefiles//csia` all emit
  `key = "statefiles/csia/<workspace>.tfstate"` and compare equal in the
  collision check. A prefix carrying `.` or `..` is refused at `validate`.
- **One S3 backend vs several, vs another type.** Several S3 entries may
  coexist; roots bound to different ones read each other's state through
  data sources that name the producer's bucket, so both buckets must be
  readable from wherever the consumer plans. A producer on another type
  (`local`, `gcs`) renders its own data-source `config`; nothing in this
  plugin changes. Two entries whose bucket and normalised prefix coincide
  are one location, and two roots bound to them collide at `validate`.
- **A normal run vs `--migrate-state <root>`.** A normal real run inits
  with `-reconfigure`, which tells tofu to *discard* any previous backend
  record without copying state. A migration run for that root inits with
  `-migrate-state -force-copy` between `state-migration begin` (writes the
  previous location as `<root>.tfbackend.previous.hcl` from the record,
  requires the new location to be empty, pulls a backup) and
  `state-migration finish` (records the move). The flag is refused on a dry
  run.
- **In-process execution vs the committed runner script.** Both perform
  the same `init -input=false -reconfigure -backend-config=<file>` before
  the plan; the script exists so a fresh clone with no `.terraform/` can
  run it. Since stage 49 the roots that must read plaintext are copied
  into the private mirror and initialised there; the backend file goes
  with the root, and the argument stays the bare file name.

## What it tests and verifies

**At load (pydantic, every entry, every command that loads the
configuration).** Unknown keys are refused (`extra="forbid"`); `parameters:`
is refused with the `variables:` message; `name` and each alias are
checked for `/` and `\`, for `default`/`self`/empty, and normalised; an
empty `key` is refused; `key` gains its trailing slash; nested `endpoints`,
`assume_role` and `assume_role_with_web_identity` values must fit their
dataclasses (each needs a `name`). The loader then refuses a duplicate name
in the class, an alias that collides with another entry's name or alias,
and a second `is_default: true`. The model's `finalize()` registers the
backend in the collector; a registration under a name already registered
with different settings is refused (`HclConfigConflictError`), though the
duplicate-name check fires first. Verdict: a pydantic `ValidationError` or
`ValueError` naming the model and the entry, logged as
`Failed to structure item ... for plugin key 'state_backends'`, the command
exits 1, nothing is generated.

**At `validate` (`just cli validate`, and the same checks at the start of
every `run`).** With `use_state_backends: true`, `check_state_locations`
resolves every terraform root's backend from the declarations alone --
the root's own `state_configuration`, its runtime's, the default -- and
refuses: a name (or alias) that is not a declared backend; a prefix with a
`.`/`..` segment; two roots that would share one state object (same bucket
and normalised prefix under two names, two root names that collapse under
`super_safe_name`, `//` against `/`); and a root whose resolved location
differs from the one recorded in `meta-state/state-locations.yaml` while
the records show resources standing in it (a storage not destroyed, a
group or user attributed to the root after an applied identity run, an
instance pinned to a build) -- the move guard, which names the root, both
locations, what stands in it and both ways out. A root with nothing
deployed moves with one INFO line
(`workspace '<ws>' moves its state from ... to ...: nothing is deployed`).
The executable/version check does **not** cover state backends (their
`executable` is not read). Verdict: one line per error on stderr, `validate`
exits 1 with `Validation failed with N error(s).`; a `run` stops before
generating anything with the same errors in `generated/run-summary.json`
under `validation_errors`, `ok: false`, exit 1.

**At generation.** The collector refuses a workspace bound a second time
to a different backend (`Workspace '<ws>' is bound to state backend '<a>'
and cannot be rebound to '<b>'`), more than one `is_default` registration
when `default` is resolved (`Multiple default state backends registered`),
and a remote-state reference whose producer has no backend
(`Workspace '<ws>' references remote state of '<producer>' but no backend
is registered for it`) -- all `HclConfigConflictError`, which fails the
lifecycle's generation. `generate_terraform_block` and
`generate_remote_state_datasources` also run the collector's provider
`validate_all()` first. In a real run the generation-time `init` then
proves the backend reachable: tofu's own exit code fails the run. After
generation, dry or real, `_record_state_locations` writes every bound
workspace's location to `meta-state/state-locations.yaml` (a migrating
workspace keeps its old record until `finish`).

**At apply.** Nothing of the plugin's own. The deferred sequence's `init`
re-proves the backend and `-reconfigure` absorbs a changed argument; the
lock is tofu's (`.tflock`); the gate reads the plan, not the state.

**After apply (post-finalize hooks).** Nothing. The builder implements no
hooks.

**In the state query.** Nothing: the state query does not consult the
backend or the location record. `state-locations.yaml` is read by
`validate`'s move guard and by `state-migration begin`.

**Tests that pin the behaviour.**
[test_terraform_collector.py](../hashicorp-utils/tests/test_terraform_collector.py)
(the partial block, the file contents, the gate, default resolution,
duplicate registration, the chain, rebinding, collisions, cross-backend
reads, the backend record);
[test_roots.py](../hashicorp-utils/tests/test_roots.py) (the `init`
arguments in dry and real runs, the runner's init, the backend file path);
[tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py)
(every root resolves and is recorded, the runtime rung, collisions and
undeclared names refused, the move guard with and without deployed
resources, the migration operation over a fake tofu, the dry-run refusal);
[tests/test_v2_state_encryption.py](../../tests/test_v2_state_encryption.py)
(every declared and emitted S3 backend encrypts); and the golden
comparison, which pins every emitted `.tfbackend.hcl`, remote-state block
and runner header.

## When it fails

Failures that have happened, first.

- **2026-09-15, CI (ledger 91).** A dry run executed each root's
  generation-time `tofu init` *with* the S3 backend, under a read-only role
  with nothing on S3. Symptom: `tofu init` failed at generation with an S3
  access error, before any plan. Cause: the backend was initialised in a
  mode that needs no state. Fix, standing since: a dry run's `init` is
  `init -backend=false`. If you see a dry run reach S3, the run is not dry
  (check `dry_run` in `generated/run-summary.json`).
- **2026-09-16, operator and fresh clone (ledger 93).** After a dry run
  (whose `.terraform/` is backend-less) or in a fresh clone (no
  `.terraform/` at all), a hand-run `run-<lifecycle>.sh` failed at its
  first `tofu plan`: the backend had never been initialised. Fix, standing
  since stage 38: every root's deferred block begins with its own
  `tofu init -input=false -reconfigure -backend-config=<file>`. A script
  from before that stage needs the `init` by hand. Found on the way: a
  generation-time `tofu init` run concurrently with the test bar over the
  same provider plugin cache failed; alone it passed. One tofu-using
  process at a time on a machine.
- **2026-09-16, live and fixture (stage 39, ledger 94).** `encrypt` was
  flipped from the accepted `false` to `true` under roots that were already
  initialised. Symptom without `-reconfigure`: tofu refuses `init` with
  "Backend configuration changed" and asks for `-reconfigure` or
  `-migrate-state`. Fix, standing since: every real-run `init` carries
  `-reconfigure` (the state is remote; there is nothing to migrate). An
  existing state object is re-encrypted server-side when next written.

Failures the code raises that have not happened live.

| Symptom (as the operator sees it) | Meaning | Where to look | What to do |
|---|---|---|---|
| `Value error, Terraform state backend 'key' cannot be empty for 's3' type.` in a `ValidationError for TofuS3StateBuilderModel` at load | `key: ""` or `key:` with nothing | the entry in `cfg/state-backends*.yml` | give the prefix (`statefiles/<something>/`) |
| `<field>` / `Unexpected keyword argument` at load | a key the model does not have (a typo, or a terraform backend argument this model never had) | the entry | fix the spelling or delete the key; see the field table |
| `` `parameters` was retired (stage 26) `` at load | `parameters:` on the entry | the entry | delete it |
| `Name '<name>' contains invalid characters: {'/', '\\'}` at load | a `/` or `\` in `name` or an alias | the entry | rename |
| `Name cannot be in '['default', None, '', 'self']'` at load | the name (or an alias) is a reserved sentinel | the entry | rename |
| `Default value for type 'state_backend_model' is already set to '<a>'. Cannot override with '<b>'.` at load | two entries with `is_default: true` | every `cfg/state-backends*.yml` | keep one default |
| `two TofuS3StateBuilderModel entries collide on the registry key 's3_east2': 'S3-East2' and 's3-east2' (a TofuS3StateBuilderModel) normalise to the same name; rename one` at load | two entries share a name after normalisation (until stage 63 item 5, 2026-09-24, this was a misleading `has no unique 'id' or 'name'` message followed by the whole model dump, `access_key` and `secret_key` included) | every `cfg/state-backends*.yml` | rename one |
| `Alias '<x>' is already registered under classification ...` at load | an alias equals another entry's name or alias | the entries | remove the alias |
| `workspace '<ws>' names state backend '<name>', which is not declared` from `validate` | the root's (or its runtime's) `state_configuration` names no entry -- a typo, a file not loaded, or an **alias** (aliases do not resolve) | the root's builder file, `cfg/state-backends*.yml` | name the entry by its `name` |
| `workspace '<ws>': state key '...' carries a '..' segment` from `validate` | `key` has a `.` or `..` path segment | the entry | remove it |
| `state location collision: workspaces <a>, <b> would share the state object s3://...` from `validate` | two roots resolve to one state file: two backends on one bucket and prefix, two root names that collapse (`aws-ebs`/`aws_ebs`), or `//` against `/` | both entries and both roots | give one of them another prefix or name |
| `workspace '<ws>' would move its state from s3://... to s3://... while <resources> stand(s) in it ...` from `validate` | the resolved location changed since the last recorded run and the records say resources live in the old state | `meta-state/state-locations.yaml`, `storage-state.yaml`, `identity.yaml`, `pins.yaml` | move the state with `run --no-dry-run <lifecycle> --migrate-state <ws>`, or correct the records through the state query's import and forget paths; never rebind past it |
| `--migrate-state moves state and needs --no-dry-run: a dry run never moves state` (exit 2 from the CLI, or `error` in the run summary) | the flag on a dry run | the command line | add `--no-dry-run` |
| `Workspace '<ws>' is bound to state backend '<a>' and cannot be rebound to '<b>'` at generation | a builder bound its workspace twice to different backends; not reachable from configuration | the consumer plugin's `generate_items_before` | a code defect in the consumer |
| `Multiple default state backends registered: [...]` at generation | two defaults reached the collector; the load refuses this first | the entries | keep one default |
| `Workspace '<ws>' references remote state of '<producer>' but no backend is registered for it` at generation | a consumer reads a producer that resolved no backend and there is no default | the producer's `state_configuration`, `is_default` | bind the producer, or declare a default |
| `State backend '<name>' (type '<t>') was registered without a kind` at generation | a state plugin registered a `BackendRegistration` with `kind=None`; not this plugin (it always passes `S3_KIND`) | the other plugin's `finalize()` | a code defect in that plugin |
| `Backend configuration changed` from `tofu init` | an init without `-reconfigure` after a backend argument changed -- only a hand-run `init` can do this now | the root's `.terraform/terraform.tfstate` | run the runner script, or `tofu init -reconfigure -backend-config=<file>` by hand |
| `tofu init`/`plan` fails with `AccessDenied`, `NoSuchBucket`, an expired token or a credential error | the bucket, the prefix permissions, the profile or the session named by `profile` (or by the environment) are not what the run assumed | the `.tfbackend.hcl` beside the root (`bucket`, `region`, `profile`), `aws sts get-caller-identity --profile <name>`, `~/.aws/sso/cache` expiry (`preflight` prints it) | log in, fix the role or the bucket; the declaration is not at fault unless the file names the wrong bucket |
| `tofu` reports the state locked (`Error acquiring the state lock`, a `.tflock` object under the state key) | another tofu holds the lock, or a previous run died holding it (`use_lockfile: true`) | the bucket, key `<state file>.tflock` | wait; if no run is alive, remove the lock object -- a records decision, not the system's |
| a `plan` that wants to create everything again against an empty state | the root points at a new location (a changed `bucket`/`key`/name) and the guard did not fire -- meta-state shows nothing deployed, or the record was edited | `meta-state/state-locations.yaml`, the `# state:` header of the runner | stop; restore the previous location or migrate; never apply such a plan |

## Related

- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)
  and [cs-image-system-tf-gcp-plugin](../tf-gcp-plugin/README.md): the
  consumers whose `state_configuration:` names a backend.
- [cs-image-system-local-state-plugin](../local-state-plugin/README.md) and
  [cs-image-system-gcs-state-plugin](../gcs-state-plugin/README.md): the
  other two backend types, built on the same collector contract.
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
- [tests/test_v2_state_locations.py](../../tests/test_v2_state_locations.py):
  the location, collision, move-guard and migration tests.
- [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md), section 10: the
  configuration manual's entry for `cfg/state-backends*.yml`.
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md): the operator's view of
  state, dry runs, runner scripts and "Where state lives".
