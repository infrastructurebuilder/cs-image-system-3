# cs-image-system-tf-ebs-instance-plugin

This package is the OpenTofu plugin for AWS. It registers one **instance
builder** (`tofu`), which turns every declared instance into a `module` call
against `tfmodules/aws_instance`, and three **storage builders**
(`tf-aws-ebs`, `tf-aws-efs`, `tf-aws-s3`), which turn every declared storage
into a `module` call against the matching `tfmodules/aws_storage_*` module.
Instances and storages live in one plugin so the instance root can bind to
the storage roots' outputs through `terraform_remote_state`. Each builder owns
one terraform root (a workspace), writes a partial backend configuration for
it, and defers its `plan -> gate -> apply` sequence to the lifecycle runner
script. The GCE instance root (`tofu-gce`) and the GCP storage builders are
**not** here: they live in
[cs-image-system-tf-gcp-plugin](../tf-gcp-plugin/README.md) and subclass the
classes in this package.

## What it registers

The entry point, from [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.instance"]
tf-ebs-instance-plugin = "cs_image_system.tf_ebs_instance_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/tf_ebs_instance_plugin/main.py)
returns a `TFEbsTofuTypes` metadata object (plugin metadata version `1`,
Python `3.13`). The classification of every class comes from its own
`csis_classifier()`, not from the entry-point group, which is why storage
builders can be registered from an `instance` entry point.

| Service name (`type:` of a builder entry) | Model class | Builder class | Classifications (VCT) | Also registered |
|---|---|---|---|---|
| `tofu` | `TofuInstanceBuilderModel` | `TofuInstanceBuilder` | `INSTANCE_BUILDER_MODEL`, `INSTANCE_BUILDER` | `TofuVersionChecker` (`VERSION_CHECKER`) |
| `tf-aws` | `TofuStorageBuilderModel` | `TofuStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` | `TofuStorageVersionChecker` (`VERSION_CHECKER`) |
| `tf-aws-ebs` | `TofuEbsStorageBuilderModel` | `TofuEbsStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` | |
| `tf-aws-efs` | `TofuEfsStorageBuilderModel` | `TofuEfsStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` | |
| `tf-aws-s3` | `TofuS3StorageBuilderModel` | `TofuS3StorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` | |

`tf-aws` is a base. Its `module_dirname()` and `module_args()` raise
`NotImplementedError`, so a builder entry with `type: tf-aws` cannot emit
anything; it exists so the three AWS subclasses and the GCP plugin share one
implementation. Each subclass binds the base's model type parameter to its
own model; `TofuS3StorageBuilder` has had its own parameter bound to
`TofuS3StorageBuilderModel` since stage 63 (a typing change only, so
`self.model` is known to carry the S3 fields; no behaviour changed).

The version checkers are selected by an **executable** entry, not by a
builder: an entry in `cfg/executables.yml` with `type: tofu` is checked by
`TofuVersionChecker`, which runs `<binary> --version -json` and reads
`terraform_version`. `TofuStorageVersionChecker` does the same under the name
`tf-aws`.

### Two levels of `type:`

1. A **builder entry** under `instance_builders:` or `storage_builders:`
   selects a plugin class by `type:` = the service name above (`tofu`,
   `tf-aws-ebs`, ...). The entry's `name:` (for example `open-tofu`,
   `aws-ebs`) becomes the terraform workspace name and the directory under
   `generated/`. Its `aliases:` register extra names for the same builder.
2. An **instance entry** under `instances:` selects a builder by `type:` =
   that builder's name or alias (`type: open-tofu`). `type: default`, or no
   `type:` at all, resolves to the instance builder with `is_default: true`.
   A **storage entry** under `storages:` does the same against the storage
   builders (`type: aws-efs`; `default` resolves to the one with
   `is_default: true`).

## Models

All models are pydantic dataclasses (`CSIS_MODEL_CONFIG`): unknown keys are
refused at load. The base class chain is
`NameTyped -> BuilderModel -> RuntimeEnabledBuilderModel -> InstanceBuilderModel | StorageBuilderModel`
in [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py),
[instance_builder.py](../base/src/cs_image_system/base/models/instance_builder.py)
and [storage_builder.py](../base/src/cs_image_system/base/models/storage_builder.py).

Fields every builder model inherits from the base:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | Builder name; normalized (lowercase, spaces to `_`). `/` and `\` are refused. |
| `type` | str | required | The service name that selects the plugin class. |
| `description` | str \| None | None | Free text. |
| `aliases` | set[str] | {} | Extra names the registry resolves to this builder. |
| `executable` | str \| None | None (base) | Name of an entry in `cfg/executables.yml`. |
| `is_default` | bool | false | The builder chosen for `type: default`. |
| `config` | dict | {} | Arbitrary map; not read by this plugin. |
| `gitignore` | list[str] | [] | Extra ignore patterns; not read by this plugin. |
| `tags` | dict[str, str] | {} | Not read by this plugin (the instance's and storage's own tags are). |
| `runtime` | str | `default` | Foreign key to a runtime builder; `default` resolves to the default runtime. Required at generation. |

The base refuses a `parameters:` key on any builder with a message naming
`variables:` as the replacement.

### `TofuInstanceBuilderModel` (`tofu`)

Defined in
[tf_instance_models.py](src/cs_image_system/tf_ebs_instance_plugin/tf_instance_models.py).
Extends `InstanceBuilderModel`
([instance_builder.py](../base/src/cs_image_system/base/models/instance_builder.py)),
which adds no fields of its own over `RuntimeEnabledBuilderModel`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `executable` | str \| None | `"tofu"` | Overrides the base default of None. |
| `required_plugins` | list[`TFTofuPluginModel`] | [] | Terraform providers for the root's `required_providers`: `name` (required), `version` (required), `source` (optional), `config` (accepted, not read). Empty means one `aws` provider from `hashicorp/aws` with no version constraint. |
| `state_configuration` | str (foreign key to `STATE_BACKEND_MODEL`) | `default` | The state backend for this workspace, by backend name. `default` resolves through the chain: the runtime's `state_configuration`, else the backend with `is_default: true`. |

Not supported: `variables:` (an instance root's module inputs are computed
from the instance and the runtime), `modifications:` (those belong on
images), `parameters:` (refused).

### The `Instance` item this builder reads

The builder consumes base `Instance` items from
[instance.py](../base/src/cs_image_system/base/models/instance.py). The
fields that reach the emission:

| Field | Type | Default | Meaning | Allowed values |
|---|---|---|---|---|
| `type` | str | `default` | The instance builder (name or alias). | any registered instance builder |
| `image` | str | None | The image to launch; required for generation. The image's `group` is the instance's owning group. | any declared image |
| `runtime` | str | `default` | The runtime builder. | any runtime |
| `storages` | list[`StorageMapping`] | [] | Per-instance attachments: `name` (a storage), `mount_point` (default `/mnt/storage`), `min_size` (default 100; not read by this plugin). The same storage listed twice keeps the later mapping. | storages the image's group may use |
| `userdata` | str | "" | Extra shell lines appended to the generated launch script, before the completion marker. | |
| `image_policy` | str | `pinned` | `pinned` keeps the launched build until an explicit upgrade; `follow` plans a gated replacement whenever the image's series head moves. | `pinned`, `follow` |
| `ephemeral` | bool | false | Launch, verify and tear down in the same run. | |
| `on_failure` | str \| None | None | What a failed verification of an ephemeral does: `keep` leaves it standing and fails the run; `teardown` tears it down and still fails the run. None inherits the runtime builder's value, else `keep`. | `keep`, `teardown` |
| `teardown_after` | str \| None | None | Duration (`"2h"`, `"30m"`, `"1d"`) after a failed verification past which the next run tears a standing ephemeral down without re-verifying. | |
| `machine_type` | str | "" | EC2 instance type; empty means the runtime's `default_machine_type`. | |
| `availability_zone` | str \| None | None | Declared zone. Not read by the module call (an instance lands in the runtime's default subnet); read by the zone-compatibility validator. | |
| `tags` | dict[str, str] | {} | Passed to the module as `tags`. | |
| `description`, `config`, `aliases` | | | Not read by this plugin. | |

A per-instance `groups:` key is refused: ownership lives on the image.

### `TofuStorageBuilderModel` (`tf-aws`)

Defined in
[tf_storage_models.py](src/cs_image_system/tf_ebs_instance_plugin/tf_storage_models.py).
Extends `StorageBuilderModel`
([storage_builder.py](../base/src/cs_image_system/base/models/storage_builder.py)),
which adds the private `_storages` list the loader fills with the builder's
storage items.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `executable` | str \| None | `"tofu"` | Overrides the base default. |
| `required_plugins` | list[`TFTofuPluginModel`] | [] | As for the instance builder; empty means `aws` from `hashicorp/aws`. |
| `state_configuration` | str (foreign key) | `default` | State backend by name; `default` resolves through the same chain (runtime's, then the default backend). |
| `variables` | `ModuleVariables` | `ModuleVariables()` | Declared inputs to the module call. Each subclass narrows the type. |

### The `variables:` models

`ModuleVariables`
([module_variables.py](../base/src/cs_image_system/base/models/module_variables.py))
is the base: every field is optional and `None` means "not declared", so the
module's own default applies. `as_module_args()` returns the declared fields
except `tags`; `merged_tags(item_tags)` puts the builder's tags under the
storage item's. Each provider subclass lists exactly its module's variable
names, so a misspelt key (`performance-mode`, `volume-type`) is refused at
load instead of being dropped.

| Class | Fields (all optional) | Module |
|---|---|---|
| `EbsVariables` | `volume_type: str`, `encrypted: bool`, `tags` | [aws_storage_ebs/variables.tf](../../tfmodules/aws_storage_ebs/variables.tf) |
| `EfsVariables` | `performance_mode: str`, `encrypted: bool`, `tags` | [aws_storage_efs/variables.tf](../../tfmodules/aws_storage_efs/variables.tf) |
| `S3Variables` | `force_destroy: bool`, `tags` | [aws_storage_s3/variables.tf](../../tfmodules/aws_storage_s3/variables.tf) |

Precedence in the module call: what the builder computes from the storage
item (name, groups, lifecycle, restore snapshot, placement) always wins;
declared `variables` win over the module's defaults; tags merge with the
item's over the builder's.

### `TofuEbsStorageBuilderModel` (`tf-aws-ebs`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `size` | int | 100 | Volume size in GB. A builder field, not a variable: `size` under `variables:` is refused. |
| `variables` | `EbsVariables` | `EbsVariables()` | `volume_type`, `encrypted`, `tags`. |

### `TofuEfsStorageBuilderModel` (`tf-aws-efs`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `variables` | `EfsVariables` | `EfsVariables()` | `performance_mode`, `encrypted`, `tags`. |

### `TofuS3StorageBuilderModel` (`tf-aws-s3`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `bucket_name` | str | required | Required and validated, but **read by nothing** since stage 63: the module call, the wipe and the state query all take the bucket from the storage item (its `bucket_name`, else its name; see below). Until 2026-09-25 the state query read this field, so two S3 storages on one builder both reported this one bucket. `get_bucket_name()` still returns it and nothing calls it. |
| `variables` | `S3Variables` | `S3Variables()` | `force_destroy`, `tags`. |

### The `Storage` item the storage builders read

Base `Storage` from
[storage.py](../base/src/cs_image_system/base/models/storage.py):

| Field | Type | Default | Meaning | Read by |
|---|---|---|---|---|
| `type` | str | `default` | The storage builder (name or alias). | all |
| `runtime` | str | `default` | Accepted; the builder's runtime governs the root and the provider. | none |
| `groups` | list[str] | [] | Groups allowed to use the storage. Each gets a private root-level subtree `/<group>/`. The value `ALL` is refused. | EBS (launch script), EFS (access points), S3 (prefixes) |
| `public_read` | bool | false | Anyone may mount read-only; POSIX permissions still govern. | EFS, S3 |
| `share_mode` | str | `"2770"` | Subtree mode: `2770` group-private, `2775` read-shared. | EBS (launch script), EFS |
| `state` | str | `active` | The **requested** lifecycle state. | all |
| `availability_zone` | str \| None | None | The zone a zonal storage lives in. On EBS the storage's own declaration wins over the runtime's default zone in the module call. | EBS |
| `bucket_name` | str \| None | None | S3 bucket name; falls back to the storage name. | S3 |
| `config` | dict | {} | `file_system_id` binds an existing EFS filesystem instead of creating one. | EFS |
| `lifecycle` | dict \| None | None | Data lifecycle. S3: `transition_days`, `storage_class`, `expire_days`, `prefix`. EFS: `ia_days`, `archive_days`. Refused on EBS. | EFS, S3 |
| `tags` | dict[str, str] | {} | Merged over the builder's `variables.tags`. | all |
| `mount_point`, `source`, `ephemeral`, `generative`, `singleton`, `is_default` | | | Not read by these builders. The mount point that matters is the one on the instance's `StorageMapping`. | none |

Allowed `state` values: `active`, `archived`, `destroyed`. Allowed
`share_mode` values: `2770`, `2775`.

## The builder

Every builder hook is keyed on an `ExecutionLifecyclePhase`. For a phase the
runner calls, in order, `generate_items_before`, `get_commands_to_run_before`,
`generate_items_during`, `get_commands_to_run_during`,
`generate_items_after`, `get_commands_to_run_after`. Each `get_commands_*`
hook returns two lists: commands that run at generation time, and
**deferred** commands that reach the lifecycle's `run-<lifecycle>.sh`. At
finalization the runner calls `pre_finalize_phase`, then the phase's deferred
commands, then `post_finalize_phase`. A file for phase `P` of builder `B` is
written at `<B>/<P>/<B>-<P>[-<label>]<suffix>`; the backend/init plumbing
comes from `TerraformRootMixin` in
[roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py).

### `TofuInstanceBuilder` (phase `instance-generation`)

Source: [tf_instance_builder.py](src/cs_image_system/tf_ebs_instance_plugin/tf_instance_builder.py).

The root is emitted only when `_root_has_work()`: the builder's runtime is
in the run's `--only-runtime` scope, and either instances are declared or a
recorded (launched) instance is no longer declared. An instance-less root is
terraform + provider + backend only, and its plan is exactly the pending
destroys.

**1. `generate_items_before`** writes the root file
`<B>-instance-generation.tf` and the partial backend file:

- provider requirements from `required_plugins`, or `aws`/`hashicorp/aws`;
- a `provider "aws"` block with `region` from the runtime and `profile` from
  the runtime's `credentials.profile_name`, aliased to the workspace name
  (`open_tofu`); module calls bind it with `providers = { aws = aws.open_tofu }`;
- one `variable "<label>_ami_id"` (string, default `""`) per instance, where
  `<label>` is the instance name with `-` and `.` turned into `_`;
- `variable "ephemeral_present"` (bool, default `true`) when any instance is
  ephemeral;
- `variable "sft_enrollment_token"` (string, sensitive, default `""`);
- the workspace's backend binding (`state_configuration`), a
  `terraform_remote_state` reference to every storage builder that owns
  storages, and one to every identity workspace that owns an instance
  image's group (so gids enter by reference);
- the `terraform {}` block (with an empty `backend "s3" {}` when
  `config.use_state_backends` is true), the provider blocks, the variable
  blocks, the remote-state data sources;
- `<B>-instance-generation.tfbackend.hcl`, the partial backend configuration;
- when the runtime names a concrete VPC (`networking.network`), a
  `data "aws_vpc" "csis_instances"` and a
  `resource "aws_security_group" "csis_instances"`: SSH ingress from the
  runtime's `ssh_ingress_security_group_ids` (or the VPC CIDR when none), all
  egress, `create_before_destroy`. Both bind the aliased provider explicitly.

**2. `generate_items_during`** writes, per instance,
`<B>-instance-generation-instance-<label>.tf` and `user-data-<label>.sh.tftpl`.
The `.tf` file holds `module "instance_<label>"` with `source` pointing at
`tfmodules/aws_instance` (resolved from `config.module_source_base`) and
these arguments:

| Argument | Value |
|---|---|
| `count` | `var.ephemeral_present ? 1 : 0`, only for ephemeral instances |
| `name` | the instance name |
| `ami_id` | the pinned build id when meta-state pins the instance; else the resolved provider-specific image id; else `var.<label>_ami_id` |
| `ami_name_pattern` | `"<deferred name pattern>*"`, only while the image is deferred (built later in the same run) |
| `instance_type` | `machine_type`, or the runtime's default machine type |
| `associate_public_ip_address` | `false` |
| `vpc_security_group_ids` | `[aws_security_group.csis_instances.id, <runtime addl_security_groups>...]` when the VPC is known |
| `subnet_id` | the runtime's default subnet |
| `iam_instance_profile` | the runtime's `session_instance_profile()` when it has one |
| `tags` | the instance's tags |
| `user_data` | `templatefile("${path.module}/user-data-<label>.sh.tftpl", {...})` |
| `ebs_volumes` | `{ <storage> = { volume_id = <remote-state ref>.volume_id, device_name = "/dev/xvdf" } }` for every EBS mount |

The template variables are all terraform references: `group_gid` =
`data.terraform_remote_state.<identity ws>.outputs.group_gids["<group>"]`;
`ebs` = per-storage `{volume_id, device_name}`; `efs` = per-storage
`{file_system_id, access_point_id}` (the group's access point, or the
`public_read` one); `sft_enrollment_token` = `var.sft_enrollment_token`,
or `(var.sft_enrollment_token != "" ? var.sft_enrollment_token : <group
builder's token reference>)` when the group's identity plugin supplies one.

**Launch parameters.** `compute_launch_params()` in
[launch_params.py](../base/src/cs_image_system/base/launch_params.py)
derives, from validated configuration only: the image, the pinned build (or
`unbound`), the owning group (the image's), the identity type, the mounts
(storage, capability type, builder, mount point, group, share mode,
public_read, and for EBS the device `/dev/xvdf`, `/dev/xvdg`, ... in
declaration order), the enrollment trigger from the group builder, the
runtime's session mechanism, the canonical hostname (`<name>-NNN`, the
declared name plus the generation the machine will be), the pool alias when
one is drawn, `ephemeral`, and any `userdata`.
`user_data_template()` renders them as a bash script: set the hostname,
create each mount point, wait for the device (EBS falls back to the
`/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<id>` name), `mkfs -t xfs`
when blank, add an `fstab` line, mount, create and `chgrp`/`chmod` the
group's subtree, write the enrollment token when one is supplied, then the
instance's own `userdata` lines, then the completion marker
`/var/lib/csis/launch-applied`. The parameters are recorded in
`meta-state/launch-params.yaml` and are **immutable after launch**: a change
is refused by a validator unless it is a mount removal (a detach) or the
instance is being replaced.

**3. `get_commands_to_run_after`** returns, at generation time, `fmt`,
`init` and `validate` in the root directory. `init` is `init -backend=false`
in a dry run; in a real run it is
`init -reconfigure -backend-config=<B>-instance-generation.tfbackend.hcl`
when a backend is bound, else bare `init`. No `plan` runs at generation.

The **deferred** commands (these are what `run-instance-image.sh` contains)
come from `gated_apply_commands()`:

| Step | Command (in the root directory) |
|---|---|
| 1 | `rm -f tfplan` |
| 2 | `tofu init -input=false -reconfigure [-backend-config=<file>]` |
| 3 | `cs-image-system --root-dir ... --no-dry-run unmount storage --instance <i> --storage <s> --mount-point <mp> --workdir <dir>` for every mount a launched instance's declaration dropped |
| 4 | `tofu plan -input=false -out=tfplan [-replace=<addr>...]` |
| 5 | `cs-image-system gate-plan --planfile tfplan --tofu <binary> [--allow-destroy <addr>]... [--require-unmounted <instance>:<storage>]...` |
| 6 | only when this root may apply: `cs-image-system apply-check --lifecycle instances --root <B> --root-alias <runtime> [--overlay <path>]... [--apply-runtime <rt>]` |
| 7 | only when this root may apply: `tofu apply -input=false tfplan` |

"May apply" is `config.apply_instances`: `true`, or a list naming the
builder or its runtime (`--apply-runtime <rt>` sets that list for the run).
The gate fails unless every destroy in the plan is whitelisted. The
whitelist holds: `module.instance_<label>` for every recorded instance that
is no longer declared (a decommission, scoped to this runtime by the build's
lineage record); `module.instance_<label>.aws_volume_attachment.this` for
every detach; and, for every instance this plan replaces,
`module.instance_<label>.aws_instance.this` (the `-replace` address itself)
and `module.instance_<label>.aws_volume_attachment.this` (an attachment
binds a volume to the instance's id, so replacing the instance replaces the
attachment). `-replace=module.instance_<label>.aws_instance.this` is added
for instances with a pending explicit upgrade or a `follow` target.

**Ephemeral instances.** When the root may apply and it has ephemeral
instances, `_ephemeral_commands()` appends, after step 7: for each
ephemeral, `cs-image-system ... verify instance <name>` (with
`--record-only` when its policy is `teardown`), unless a failed verification
older than `teardown_after` is on record (then no re-verification); then a
second `rm -f tfplan`, `init`, `plan ... -var=ephemeral_present=false`,
`gate-plan` whitelisting each `module.instance_<label>`, `apply-check`, and
`apply`. Under `keep`, a failed `verify` stops the runner before the
teardown, so the instance stays standing. After a real run the ephemerals'
launch records and pins are forgotten; under `teardown` a failed verdict
still fails the run from that hook.

**4. `pre_finalize_phase`** runs before the deferred commands, and only for
a root inside the run's runtime scope (`--only-runtime`, explicit or implied
by `--apply-runtime`; stage 63, it used to act for out-of-scope roots too
until 2026-09-25) and only for the `instance-image` lifecycle (the `release`
and `retention` lifecycles extend the same phase and used to get the file
too). For every instance
whose provider-specific image is now resolved (the image builder's post-hook
has read the packer manifest), it writes
`<B>/instance-generation/instances.auto.tfvars` with one line
`<label>_ami_id = "<ami id>"`, so the module uses the exact artifact instead
of the name-pattern fallback. The file is run-local: a `--commit` never
stages `*.tfvars`.

**5. `post_finalize_phase`** runs after the deferred commands succeed and only
when the root is inside the run's runtime scope (stage 63: a root out of
scope applied nothing to bind) and applied. For every non-ephemeral instance: a `follow` target
moves the pin to the new head; an unpinned instance is bound to the resolved
image id (first bind); when the image was deferred and the runtime can query
the booted image, the pin is bound from what actually booted, provided
lineage records it.

### `TofuStorageBuilder` and its subclasses (phase `storage-generation`)

Source: [tf_storage_builder.py](src/cs_image_system/tf_ebs_instance_plugin/tf_storage_builder.py).

The root is emitted when `_has_work()`: the runtime is in scope, and the
builder owns declared storages or recorded storages that left the YAML.

**Storage state machine.** The YAML declares the *requested* state; the
authoritative current state is in `meta-state`. The legality rules are in
[storage_state.py](../base/src/cs_image_system/base/storage_state.py):

| From | To | Conditions |
|---|---|---|
| never applied | `active` | a new storage must start `active` |
| `active` | `archived` | unattached; the builder must support archiving |
| `archived` | `active` | a restore |
| `active` | `destroyed` | unattached |
| `archived` | `destroyed` | |
| `destroyed` | `active` | a new generation of the name; no data continuity |
| recorded, not destroyed, no longer declared | `destroyed` | the record must name the owning builder |

Attaching a storage that is not `active` is an error. A storage that is
destroyed stays a tombstone in the records.

**1. `generate_items_before`** writes `<B>-storage-generation.tf`: provider
requirements, the aliased `provider "aws"` block (region, profile), the
backend binding, one `terraform_remote_state` reference per identity
workspace whose gids this root consumes, the terraform/provider/remote-state
blocks, and `<B>-storage-generation.tfbackend.hcl`.

**2. `generate_items_during`** writes, per *live* storage (requested state
not `destroyed`, and not `archived` on a builder that supports archiving),
`<B>-storage-generation-storage-<label>.tf` with a comment naming the allowed
groups, `public_read` and the requested state, then
`module "storage_<label>"` (source `tfmodules/<module_dirname>`, the aliased
provider, `module_args(storage)`), then
`output "storage_<label>" { value = module.storage_<label> }` for the
instance root to read. Tombstones and archived storages get a comment-only
file.

Gids never appear as literals: `gid_reference(group)` is
`data.terraform_remote_state.<identity ws>.outputs.group_gids["<group>"]`,
and `group_subtrees(storage)` maps each allowed group to
`{gid, path: "/<group>", permissions: <share_mode>}`.

**3. `get_commands_to_run_after`** returns `fmt`, `init`, `validate` at
generation time and, deferred:

- for every tombstone and every undeclared storage whose current state is
  not `destroyed`: the builder's `transition_actions(cur -> destroyed)`,
  then `module.storage_<label>` on the destroy whitelist (unless the storage
  is already archived on an archiving builder, whose volume is already gone);
- on archiving builders, for every storage requested `archived` whose
  current state is `active`: `transition_actions(active -> archived)`, then
  the whitelisted destroy; and for every live storage currently recorded
  `archived`: `post_transition_actions(archived -> active)` after the apply;
- then `rm -f tfplan`, `init`, `plan`, `gate-plan --allow-destroy ...`, and,
  when `config.apply_storage` allows this root (builder name or runtime),
  `apply-check --lifecycle storage --root <B> --root-alias <runtime>` and
  `apply -input=false tfplan`, followed by the post-transition scripts.

Transition scripts are written beside the root as
`archive-<label>.sh`, `unarchive-<label>.sh`, `restore-<label>.sh` and run
with `bash`.

**`query_state()`** answers `cs-image-system state query`: for every owned
storage (declared ones and recorded ones that left the YAML), `present`, the
capability type and the provider record found by `Name` tag (or, when
recorded `archived`, the archive snapshot).

#### Per-subclass behaviour

| | `TofuEbsStorageBuilder` (`tf-aws-ebs`) | `TofuEfsStorageBuilder` (`tf-aws-efs`) | `TofuS3StorageBuilder` (`tf-aws-s3`) |
|---|---|---|---|
| Module | [aws_storage_ebs](../../tfmodules/aws_storage_ebs/variables.tf) | [aws_storage_efs](../../tfmodules/aws_storage_efs/variables.tf) | [aws_storage_s3](../../tfmodules/aws_storage_s3/variables.tf) |
| Capability type (what a base image declares in `storage_types`) | `ebs` | `efs` | `s3` |
| Attachment cardinality | single | many | many |
| Zonal (`is_zonal()`) | yes: the zone takes part in the compatibility check and changing it replaces the volume | no | no |
| POSIX | yes | yes | no (groups become prefixes; `public_read` is a same-account read policy) |
| Supports `archived` | yes: snapshot named `csis-<label>-archive`, then the volume is destroyed; restore creates the volume from that snapshot and deletes it after the apply | no | no |
| `lifecycle:` keys | refused | `ia_days` in {1,7,14,30,60,90,180,270,365}; `archive_days` in {90,180,270,365} | `transition_days` (positive int), `storage_class` in {STANDARD_IA, ONEZONE_IA, INTELLIGENT_TIERING, GLACIER_IR, GLACIER, DEEP_ARCHIVE}, `expire_days` (positive int), `prefix`; a class needs `transition_days`; at least one of the two day counts |
| `destroyed` transition action | delete the archive snapshot when the volume was archived | none | `aws s3 rm s3://<bucket> --recursive [--profile <p>]` before the destroy |
| Base-image prerequisites | none (a comment) | `nfs-common` (Debian family) or `amazon-efs-utils`/`nfs-utils`; verify: `mount.efs`/`mount.nfs`/`mount.nfs4` present | AWS CLI installed via the official zip (`unzip` first: it is not on RHEL-family images); verify: `aws` present |
| State query | `describe_volumes` by `Name` tag, or `describe_snapshots` when archived | `describe_file_systems` matched by name, plus the lifecycle policy | `get_bucket_tagging` on the **storage's** bucket (its `bucket_name`, else its name: the bucket its module call creates; stage 63, it read the builder's `bucket_name` until 2026-09-25); `NoSuchBucket` means absent, any other failure is "unavailable" |

Module arguments (`module_args(storage)`), in emission order:

| Builder | Arguments |
|---|---|
| EBS | declared `variables` (`volume_type`, `encrypted`); `name`; `size` (the builder's); `snapshot_name = csis-<label>-archive` when the storage is recorded archived and declared active (restore); `availability_zone` from the storage's own `availability_zone`, else the runtime's `networking.default_availability_zone`, else `subnet_id` from the runtime's default subnet (the module derives the zone from it); merged `tags` |
| EFS | declared `variables` (`performance_mode`, `encrypted`); `name`; `existing_file_system_id` from `config.file_system_id`; `transition_to_ia = AFTER_<ia_days>_DAYS`; `transition_to_archive = AFTER_<archive_days>_DAYS`; `access_points` = the group subtrees (gid by reference); `public_read = true` when set; when the runtime declares `networking` with private subnets and `addl_security_groups`: `vpc_id`, `mount_target_subnet_ids` (one private subnet per availability zone, in declaration order) and `client_security_group_ids` (the runtime's `addl_security_groups`), so the module creates the mount targets; merged `tags` |
| S3 | declared `variables` (`force_destroy`); `bucket_name` = the storage's `bucket_name` or its name; `lifecycle_rules = [{id = "csis", prefix, transition_days, storage_class, expire_days}]` when a lifecycle is declared; `group_prefixes` = sorted allowed groups; `public_read = true` when set; merged `tags` |

Undeclared `variables` are absent from the call, so the module default
applies.

## Emission

Everything below is from the frozen golden emission over the test fixture.

Instance root (`open-tofu`), under
[generated/instance-image/open-tofu/instance-generation/](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/):

| File | Content |
|---|---|
| [open-tofu-instance-generation.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation.tf) | `terraform {}` with `required_providers` and `backend "s3" {}`; `provider "aws"` (region `us-east-2`, profile `noaa`, alias `open_tofu`); `variable "test_ami_id"`, `variable "test2_ami_id"`, `variable "sft_enrollment_token"`; `data "terraform_remote_state"` for `aws_efs`, `aws_ebs`, `aws_s3`, `gcp_pd`, `gcp_gcs`, `oktagroups`; `data "aws_vpc"` and `resource "aws_security_group" "csis_instances"` |
| [open-tofu-instance-generation-instance-test2.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation-instance-test2.tf) | `module "instance_test2"` calling `../../../../../tfmodules/aws_instance` with `ami_id = var.test2_ami_id`, `ami_name_pattern = "imgfile-basic-dask-pckr-ebs-ans*"`, `instance_type = "t3.medium"`, the security groups, `subnet_id`, `iam_instance_profile`, `user_data = templatefile(...)`, and `ebs_volumes` for `mnt_data` on `/dev/xvdf` |
| [open-tofu-instance-generation-instance-test.tf](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation-instance-test.tf) | the same shape for `test`, with no storages |
| [user-data-test2.sh.tftpl](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/user-data-test2.sh.tftpl) | the launch script: hostname, the `mnt_data` mount at `/mnt/data`, the `coops` subtree with mode `2770`, the enrollment block |
| [open-tofu-instance-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/instance-image/open-tofu/instance-generation/open-tofu-instance-generation.tfbackend.hcl) | `bucket`, `key = "statefiles/csia-image-system-test/open_tofu.tfstate"`, `region`, `encrypt = true`, `use_lockfile = true`, `profile` |
| [run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh) | the deferred sequence per root, each step entered through `cs-image-system materialize .`: `rm -f tfplan`, `init -input=false -reconfigure -backend-config=...`, `plan -input=false -out=tfplan`, `gate-plan` (no apply: the fixture sets `apply_instances: false`) |

Storage roots, under
[generated/storage/](../../tests/fixtures/v2_golden/generated/storage/):

| File | Content |
|---|---|
| [aws-ebs/storage-generation/aws-ebs-storage-generation.tf](../../tests/fixtures/v2_golden/generated/storage/aws-ebs/storage-generation/aws-ebs-storage-generation.tf) | terraform block, `provider "aws"` alias `aws_ebs`, remote state of `oktagroups` |
| [aws-ebs/storage-generation/aws-ebs-storage-generation-storage-mnt_data.tf](../../tests/fixtures/v2_golden/generated/storage/aws-ebs/storage-generation/aws-ebs-storage-generation-storage-mnt_data.tf) | `module "storage_mnt_data"` against `tfmodules/aws_storage_ebs`: `volume_type = "gp3"`, `encrypted = true`, `name`, `size = 100`, `subnet_id`, merged `tags`; `output "storage_mnt_data"` |
| [aws-efs/storage-generation/aws-efs-storage-generation-storage-efs_storage.tf](../../tests/fixtures/v2_golden/generated/storage/aws-efs/storage-generation/aws-efs-storage-generation-storage-efs_storage.tf) | `module "storage_efs_storage"`: `performance_mode`, `encrypted`, `transition_to_ia = "AFTER_30_DAYS"`, `access_points` for `coops` and `stofs` with gids by reference and permissions `2775` |
| [aws-s3/storage-generation/aws-s3-storage-generation-storage-default_bucket.tf](../../tests/fixtures/v2_golden/generated/storage/aws-s3/storage-generation/aws-s3-storage-generation-storage-default_bucket.tf) | `module "storage_default_bucket"`: `bucket_name`, `lifecycle_rules` (30 days to `STANDARD_IA`), `public_read = true`, merged `tags` |
| `<B>-storage-generation.tfbackend.hcl` | one per root, e.g. [aws-ebs-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/aws-ebs/storage-generation/aws-ebs-storage-generation.tfbackend.hcl) |
| [run-storage.sh](../../tests/fixtures/v2_golden/generated/storage/run-storage.sh) | the deferred sequence per root |

Meta-state written from these lifecycles:
[meta-state/launch-params.yaml](../../tests/fixtures/v2_golden/meta-state/launch-params.yaml)
(the recorded launch parameters) and
[meta-state/storage.yaml](../../tests/fixtures/v2_golden/meta-state/storage.yaml)
(the storage read-model: builder, plugin, cardinality, attachments, states).
A real run with applies on also writes, through the base package's
after-apply hooks, `storage-state.yaml` (the storage transitions), `pins.yaml`
(instance pins, moved by this builder's post-finalize hook),
`instance-state.yaml` (instance generations) and `verifications.yaml` (the
ephemerals' verdicts); none of these appear in the dry golden.

Modules called: [tfmodules/aws_instance](../../tfmodules/aws_instance/main.tf),
[tfmodules/aws_storage_ebs](../../tfmodules/aws_storage_ebs/main.tf),
[tfmodules/aws_storage_efs](../../tfmodules/aws_storage_efs/main.tf),
[tfmodules/aws_storage_s3](../../tfmodules/aws_storage_s3/main.tf). The
`source` is computed from `config.module_source_base` (default
`../tfmodules`, relative to the configuration root) as a relative path from
the workspace directory; absolute paths and remote URLs pass through.

## Example configuration

From the test fixture. The instance builder,
[cfg/instance-builders.yml](../../tests/fixtures/config/cfg/instance-builders.yml):

```yaml
instance_builders:
  - name: open-tofu
    type: tofu
    is_default: true
    runtime: aws-east2-runtime
    executable: open-tofu-1
    required_plugins:
      - name: aws
        source: hashicorp/aws
        version: '>= 4.0.0'
    state_configuration: s3-east2
```

The storage builders,
[cfg/storage-builders.yml](../../tests/fixtures/config/cfg/storage-builders.yml):

```yaml
storage_builders:
  - name: aws-efs
    type: tf-aws-efs
    executable: open-tofu-1
    runtime: aws-east2-runtime
    variables:
      performance_mode: generalPurpose
      encrypted: true
      tags:
        Project: MyProject
        Environment: Development
  - name: aws-ebs
    type: tf-aws-ebs
    executable: open-tofu-1
    is_default: true
    runtime: aws-east2-runtime
    size: 100
    variables:
      volume_type: gp3
      encrypted: true
      tags:
        Project: MyProject
        Environment: Development
  - name: aws-s3
    type: tf-aws-s3
    executable: open-tofu-1
    runtime: aws-east2-runtime
    bucket_name: noscsb-csis-test-514190660293-default-bucket
    variables:
      tags:
        Project: MyProject
        Environment: Development
```

The executable both name,
[cfg/executables.yml](../../tests/fixtures/config/cfg/executables.yml):

```yaml
executables:
  - name: open-tofu-1
    type: tofu
    binary: /usr/local/bin/tofu
    version: ">1,<2"
```

The storages, [storages/storage0.yaml](../../tests/fixtures/config/storages/storage0.yaml):

```yaml
storages:
  - name: mnt_data
    mount_point: /mnt/data
    is_default: true
    groups:
      - coops
    state: active
  - name: default-bucket
    is_default: false
    runtime: default
    type: aws-s3
    singleton: true
    bucket_name: noscsb-csis-test-514190660293-default-bucket
    public_read: true
    lifecycle:
      transition_days: 30
      storage_class: STANDARD_IA
    tags:
      env: production
      team: devops
  - name: efs-storage
    type: aws-efs
    groups:
      - coops
      - stofs
    share_mode: "2775"
    lifecycle:
      ia_days: 30
```

`mnt_data` has no `type:`, so it belongs to `aws-ebs` (`is_default: true`).

An instance that mounts it,
[instances/instances.yaml](../../tests/fixtures/config/instances/instances.yaml):

```yaml
instances:
  - name: test2
    machine_type: t3.medium
    image: imgfile-basic-dask
    description: Test deploy of CSB Base Image AlmaLinux 9 - Snapshot
    tags:
      hype: test
    storages:
      - name: mnt_data
        mount_point: /mnt/data
```

`test2` has no `type:` and no `runtime:`, so it is built by `open-tofu` on
`aws-east2-runtime`. Its owning group is `coops`, the group of
`imgfile-basic-dask`, which is on `mnt_data`'s allowed list.

The flags that gate the roots, in
[cfg/_config.yml](../../tests/fixtures/config/cfg/_config.yml) under
`config:`: `use_state_backends: true`, `apply_instances: false`,
`apply_storage: false`, `module_source_base: ../tfmodules`. The optional
`require_released_builds: true` makes a validator refuse an instance pinned
to a build that is not a released build of its image, with one grace (the
series head while its own proof is under way; see "What it tests and
verifies").

## Prerequisites and integration

Everything the plugin needs from outside the system, and how it finds each
thing. Where a value is "read from the runtime", the runtime is the `aws`
runtime builder the builder entry's `runtime:` names
([cs-image-system-aws-runtime-plugin](../aws-runtime-plugin/README.md),
model in
[aws_runtime_models.py](../aws-runtime-plugin/src/cs_image_system/aws_runtime/aws_runtime_models.py)).
The manuals' versions of the same facts are
[CONFIGURATION.md section 4](../../docs/CONFIGURATION.md) (the runtime
fields) and [OPERATIONS.md "Credentials contract"](../../docs/OPERATIONS.md).

| Prerequisite | Why | How the plugin finds it |
|---|---|---|
| An OpenTofu (or terraform) binary | every root is `fmt`/`init`/`validate`d at generation and planned, gated and applied by the runner | the builder's `executable:` names an entry in `cfg/executables.yml`; that entry's `binary:` is the path and `type: tofu` selects `TofuVersionChecker`, which runs `<binary> --version -json`. The entry's `version:` requirement is enforced: `validate` and every run refuse a binary outside it. The default `executable` value is the literal `"tofu"`, so an entry of that name must exist unless the builder names another. |
| The terraform modules | each root is a `module` call against `tfmodules/aws_instance`, `aws_storage_ebs`, `aws_storage_efs` or `aws_storage_s3` | `config.module_source_base` in `cfg/_config.yml` (default `../tfmodules`, relative to the configuration root; an absolute path or a git/registry URL passes through). A fixture copy needs the `tfmodules` directory beside it. |
| An AWS account, region and credentials | the `provider "aws"` block, every plan and apply, the state queries (boto3), the archive/restore/wipe scripts (the AWS CLI) | `region` from the runtime's `region:`; `profile` from the runtime's `credentials.profile_name` (emitted into the provider block, the backend file and the CLI scripts as `--profile`). With no profile named, the provider and boto3 fall back to the environment (`AWS_PROFILE`, or `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_SESSION_TOKEN`). An SSO profile needs a live session (`aws sso login --profile <p>`): the load itself refuses on an expired one, and a session that lapses mid-run is environmental. |
| The `aws` CLI on the runner's `PATH` | `archive-<label>.sh` (`describe-snapshots`, `create-snapshot`, `wait snapshot-completed`), `unarchive-<label>.sh` and `restore-<label>.sh` (`delete-snapshot`), and the S3 wipe `aws s3 rm --recursive` before a bucket's destroy | run as deferred steps of `run-storage.sh` with `bash` and `aws` found on `PATH`; the EBS scripts pass `--region` and `--profile` from the runtime, the S3 wipe passes `--profile` only. Nothing checks the CLI's presence before the step runs. |
| `cs-image-system` on `PATH` and the configuration identity | the runner scripts call `cs-image-system materialize`, `gate-plan`, `apply-check`, `unmount storage` and `verify instance`; `materialize` and every configuration-loading step open `ENC[age:...]` values | `just` and `uv run` put the CLI on `PATH`; `CSIS_CONFIG_IDENTITY` must be in the environment of whoever runs the script (OPERATIONS "Encrypted values"). |
| A VPC, subnets and existing security groups | instances launch in the runtime's default subnet, wear a security group this root creates plus the groups the runtime lists, and take SSH only from the relay's group; EFS mount targets need one private subnet per zone and the clients' groups | all from the runtime's `networking:` block: `network` (the VPC id; when it is unset or a placeholder, no `aws_vpc`/`aws_security_group` blocks are emitted and the module gets no `vpc_security_group_ids`), `default_subnet_id`, `default_availability_zone`, `subnets[]` (`subnet_id`, `availability_zone`, `public`), `ssh_ingress_security_group_ids`, `addl_security_groups`. Existing groups, subnets and routes are never modified (the standing network rule); only the `csis-instances` group and the EFS module's mount-target group are created. |
| No internet gateway is assumed | instances get no public IP and sftd advertises the private address | `associate_public_ip_address = false` is hard-coded; the launch script writes `AccessAddress` from `hostname -I` when the group enrolls through `sftd-token`. |
| Session access (SSM) and its instance profile | the runtime's `verify instance`, the unmount before a detach, the post-bake tests and the alias pass all reach the machine over the session mechanism; the instance must be able to reach SSM | the runtime's `session_mechanism: ssm` and `session_instance_profile:`; the profile is passed as `iam_instance_profile` and must exist in the account (operator wiring; the system generates no IAM). |
| The identity root, applied first | gids and the enrollment token enter by `terraform_remote_state` from the identity workspace's outputs (`group_gids`, and the group builder's token reference) | the group builder of the image's owning group (`group_builder_of`) names the workspace; the storage lifecycle and the instance-image lifecycle run after `identity` in every run, and the reference resolves only when that state has been applied. A group with no identity builder is a generation-time error on a storage root. |
| The state backend | the workspace's own state, the partial backend file, and the remote-state data sources that read the storage and identity roots | `state_configuration` on the builder, else the runtime's, else the backend marked `is_default` in `cfg/state-backends*.yml` (an S3 backend needs the same AWS session; see [cs-image-system-tf-s3-state-plugin](../tf-s3-state-plugin/README.md)). Everything about state is gated by `config.use_state_backends`; note under "Variations" what happens when it is off. |
| `TF_VAR_sft_enrollment_token` (optional) | an explicit override of the enrollment token, and the only source when the group's identity plugin mints none | read by tofu at plan/apply as `var.sft_enrollment_token`; the variable is sensitive and never recorded. |
| `TF_PLUGIN_CACHE_DIR` (optional) | provider downloads are reused across roots | exported by the Justfile; a run started outside `just` needs it in the environment to benefit. One tofu process at a time: the recipes take `.tofu-plugin-cache/.lock`. |
| The alias pool (optional) | a memorable name for every new durable machine | `meta-state/aliases.txt` in the configuration root, hand-appended; absent means no aliases and no error. |
| Base images that declare the storage type | an instance may mount a storage only when its image's root base build was stamped with that capability type (`ebs`, `efs`, `s3`); the EFS and S3 prerequisites (mount tooling, the AWS CLI) are baked then | the base image's `storage_types:`; the plugin supplies `base_image_prerequisites()` and `verify_commands()` per type to the base-image bake. |

Nothing here is read from this package's own environment variables: the
plugin declares none.

## Configuration reference

The field tables under "Models" above are the complete list of fields on the
builder models this plugin owns (`TofuInstanceBuilderModel`,
`TofuStorageBuilderModel` and its three subclasses, the `variables:` models)
and of the `Instance`, `StorageMapping` and `Storage` fields the builders
read, with the ones that are accepted but not read named as such. This
section lists everything else the plugin reads: the `config:` keys, the
runtime fields, the executable entry, the meta-state it consults, and the
run options that change its output. Manual references:
[CONFIGURATION.md sections 2.3, 8, 11.3 and 11.4](../../docs/CONFIGURATION.md).

`config:` keys in `cfg/_config.yml` (and in overlays):

| Key | Type | Default | Meaning for this plugin |
|---|---|---|---|
| `apply_instances` | bool or list[str] | `false` | whether the instance root's runner carries `apply-check` + `apply`; a list names builders or runtimes. Also gates the ephemeral verify/teardown block, the post-finalize pin binds, and (through the base hooks) the `launched` marker, the forgets and the alias draw. |
| `apply_storage` | bool or list[str] | `false` | the same for each storage root, and for the post-transition (restore) scripts. |
| `use_state_backends` | bool | `false` | when true: `backend "s3" {}` in the terraform block, the `.tfbackend.hcl` file, the `-backend-config=` init argument and every `data "terraform_remote_state"` block are emitted. |
| `module_source_base` | str | `../tfmodules` | where the four modules are. |
| `require_released_builds` | bool | `false` | read by the base validator, not by the builder: an instance's pin must be a released build, or the series head under the release grace. |

Runtime fields (the `aws` runtime the builder's `runtime:` names):

| Field | Read by | Used for |
|---|---|---|
| `region` (`get_region()`) | both | the provider block's `region`; the EBS/EFS/S3 CLI flags and boto3 sessions |
| `credentials.profile_name` (`get_credentials()`) | both | the provider block's `profile`; `--profile` on the CLI scripts; the boto3 session. It is the only source of the profile: stage 63 removed the storage builder's dead fallback to a `profile` attribute on the runtime model (`rtb.model.profile`, which no runtime declares; removed 2026-09-25). |
| `state_configuration` | both | the second rung of the backend chain |
| `networking.network` | instance | the VPC for `data "aws_vpc"` and the `csis-instances` security group; also gates `vpc_security_group_ids` |
| `networking.ssh_ingress_security_group_ids` | instance | the SSH ingress sources of `csis-instances`; empty falls back to the VPC's CIDR |
| `networking.addl_security_groups` | instance, EFS | extra groups every instance wears; the EFS mount targets' client groups |
| `networking.default_subnet_id` | instance, EBS | `subnet_id` of the instance; the EBS zone fallback |
| `networking.default_availability_zone` | EBS | the volume's zone when the storage declares none |
| `networking.subnets[]` (`subnet_id`, `availability_zone`, `public`) | EFS | one private subnet per zone becomes a mount target |
| `default_machine_type` | instance | `instance_type` when the instance's `machine_type` is empty |
| `session_mechanism`, `session_instance_profile` | instance | `iam_instance_profile` when the mechanism is `ssm` and a profile is named |
| `on_failure`, `teardown_after` | instance | the ephemeral defaults an instance inherits |
| `self_to_aws_client_config()` | storage | the boto3 session of the state query |

The executable entry (`cfg/executables.yml`, `type: tofu`): `name` (what the
builder's `executable:` names), `binary` (the path the roots run), `version`
(the requirement the checker enforces).

Meta-state the builders read at generation (the configuration root's
`meta-state/`):

| File | Read for |
|---|---|
| `pins.yaml` | the instance's pinned build (`ami_id`), pending replacements (`-replace`), the decommission whitelist |
| `launch-params.yaml` | launched instances and their recorded mounts (detaches), the decommission whitelist, the recorded hostname and alias |
| `lineage.yaml` | the pinned build's runtime (scoping the decommission whitelist to this root), series heads (`follow`), what a booted image is |
| `storage-state.yaml` | each storage's current state (transitions, restore, the archive lookup in the state query) and the facts of undeclared storages (builder, bucket name) |
| `verifications.yaml` | a standing ephemeral's last verdict (`teardown_after`) |
| `instance-state.yaml` | the generation counters behind the canonical hostname |
| `aliases.txt` | the alias pool |

Run options that change the emission: `--dry-run` (the default) versus
`--no-dry-run`; `--only-runtime <rt>` and `--apply-runtime <rt>`; `--overlay`
and `--undeclare instance:<name>` / `{name: X, undeclare: true}` (a
decommission for one invocation); `--migrate-state <root>` (the runner's
init becomes `-migrate-state -force-copy` and the plan `-detailed-exitcode`,
wrapped in `state-migration begin`/`finish`).

### Variations

- **Ephemeral versus durable instance.** When `ephemeral: true` is declared,
  the module call gets `count = var.ephemeral_present ? 1 : 0` and the root
  declares `variable "ephemeral_present"`; when the root may apply, the
  runner appends `verify instance <name>` and a second plan/gate/apply with
  `-var=ephemeral_present=false` whitelisting `module.instance_<label>`;
  the post-finalize hook binds no pin for it; no alias is drawn from the
  pool; its hostname counts on the `ephemeral` generation counter, so a
  durable machine of the same name never moves. A durable instance keeps
  its module call unconditional, is bound to its build after the first
  applied launch, and is replaced only through an upgrade or a follow.
- **`on_failure: keep` versus `teardown`, and `teardown_after`.** Under
  `keep` (the default, inherited from the runtime when the instance says
  nothing) a failed `verify instance` stops the runner before the teardown
  and the machine stays standing; under `teardown` the verify runs with
  `--record-only`, the teardown proceeds, and the failed verdict fails the
  run from the after-apply hook after the record is forgotten. When a
  failed verification older than `teardown_after` is on record, the next
  run emits no `verify` step for that instance and tears it down directly.
- **`image_policy: pinned` versus `follow`.** Pinned: `ami_id` is the
  recorded pin and a newer series head changes nothing until
  `upgrade instance`. Follow: when the series head is newer than the pin,
  the plan carries `-replace=module.instance_<label>.aws_instance.this`,
  the replace address and the instance's volume attachments are
  whitelisted, `ami_id` is the head, the canonical hostname takes the next
  generation, and the pin moves in the post-finalize hook after the apply.
- **A pending upgrade.** `upgrade instance <name>` leaves a pending
  replacement marker; the next generation treats the instance exactly like
  a follow target (the `-replace`, the attachment whitelist, the new
  hostname and alias), and `mark_launched` clears the marker after the
  apply. Under `require_released_builds: true` the unreleased pin is
  admitted by the release grace while the proof is under way.
- **Image resolved, deferred, or pinned.** `ami_id` is the pin when
  meta-state has one; else the resolved provider-specific image id; else
  (the image bakes later in this run) `var.<label>_ami_id` with
  `ami_name_pattern` as the module's fallback, and `pre_finalize_phase`
  writes `instances.auto.tfvars` once the packer manifest is read. With no
  provider-specific image at all, no `ami_id` is emitted and a warning is
  logged.
- **Dry run versus real run.** A dry run runs `init -backend=false` at
  generation, enumerates the deferred commands in the log without running
  them, runs neither finalize hook, draws no alias (it logs the name it
  would take), forgets no record and binds no pin. A real run inits with
  `-reconfigure -backend-config=<file>` (or bare `init` with no backend),
  executes the runner, and the hooks act.
- **Apply flag on, off, or a list.** Off: the runner still plans and gates
  every root (a decommission can be dry-run repeatedly) but carries no
  `apply-check`/`apply`, no ephemeral block, and the post-finalize hook
  returns at once. A list (`[gcloud-east1]`, or `--apply-runtime`) enables
  only the roots whose builder name or runtime is listed; the other roots
  still plan and gate. `apply-check` re-reads the flag at execution time.
- **`--only-runtime <rt>` (explicit or implied by `--apply-runtime`).**
  A builder whose runtime is not `<rt>` emits no root at all and contributes
  no commands; with no scope every root of every runtime is generated and
  planned. Both finalize hooks of an out-of-scope instance builder return
  at once (stage 63): `pre_finalize_phase` writes no `instances.auto.tfvars`
  and `post_finalize_phase` binds nothing, matching the root's own empty
  emission. Until 2026-09-25 another runtime's builder still ran
  `pre_finalize_phase`, wrote tfvars for a root that emitted nothing, and
  logged `No resolved provider-specific images for instances; modules will
  use their name-pattern fallback` on every scoped run (visible in every GCE
  cycle).
- **`use_state_backends` on versus off.** On: the terraform block gets an
  empty `backend "s3" {}`, the `.tfbackend.hcl` file is written, init
  carries `-backend-config=`, and every `data "terraform_remote_state"`
  block is emitted. Off: none of those, while the module calls and the
  launch template still reference `data.terraform_remote_state.<ws>...`
  for gids, enrollment tokens, volume ids and access points, so an
  instance with an owning group or a mount, or a storage with allowed
  groups, produces a root that does not validate. The flag is effectively
  required for anything but a groupless, mountless emission.
- **`required_plugins` declared or not.** Declared: exactly those providers
  with their sources and version constraints. Not declared: one `aws`
  provider from `hashicorp/aws` with no constraint.
- **`state_configuration` own, runtime's, or default.** The workspace binds
  to the first that names a backend; a consumer's remote-state data source
  carries the producer's backend, whichever type it is (the golden reads
  `oktagroups` from a `local` backend and the storage roots from a second
  S3 bucket).
- **A concrete VPC or not.** With `networking.network` set to a real id,
  the root creates `csis-instances` and the module wears it plus
  `addl_security_groups`; with `ssh_ingress_security_group_ids` empty the
  SSH ingress is the VPC's own CIDR instead of a group reference. Without
  a VPC no security group is created and `vpc_security_group_ids` is
  absent (the module leaves it null).
- **`machine_type` set or empty; a session profile or none.** Empty falls
  back to the runtime's `default_machine_type`; `iam_instance_profile` is
  emitted only under `session_mechanism: ssm` with a
  `session_instance_profile`.
- **Requested storage state: `active`, `archived`, `destroyed`; and an
  entry that left the YAML.** `active` emits the module call and the
  output; `archived` on EBS emits a comment-only file, `archive-<label>.sh`
  (snapshot, wait) before the plan and whitelists `module.storage_<label>`;
  `archived` on EFS or S3 is refused at validate; `destroyed` emits a
  comment-only tombstone file, the builder's destroy action (S3: the
  bucket wipe; EBS from archived: the snapshot delete) and the whitelist;
  an undeclared recorded storage is planned like `destroyed` from its
  record's facts, without any file.
- **A restore (recorded `archived`, declared `active`).** The EBS module
  call carries `snapshot_name = csis-<label>-archive`; after a successful
  apply `restore-<label>.sh` deletes the snapshot.
- **EBS placement.** `availability_zone` from the storage's own declaration
  wins; else the runtime's `default_availability_zone`; else `subnet_id`
  from the runtime's default subnet and the module derives the zone.
  Declaring a zone pins the volume; a zone change replaces it.
- **EFS created or adopted; networking or not.** With
  `config.file_system_id` the module adopts that filesystem
  (`existing_file_system_id`) and applies no lifecycle policy of its own;
  otherwise it creates one. With a runtime `networking` block that has
  private subnets and `addl_security_groups`, the call carries `vpc_id`,
  `mount_target_subnet_ids` and `client_security_group_ids`; with either
  list empty none of the three is passed and the module makes no mount
  target, so nothing can mount the filesystem.
- **S3 bucket name.** The storage's `bucket_name`, else its name, is the
  bucket the module manages, the wipe empties and (stage 63) the state
  query reads, so two S3 storages on one builder each report their own
  bucket. The builder's own `bucket_name` is still required but nothing
  reads it; until 2026-09-25 it was the bucket the state query read, and
  every storage on the builder reported that one bucket.
- **Groups versus `public_read`.** Allowed groups become EBS subtrees in the
  launch script, EFS access points (`access_points`) and S3 prefixes
  (`group_prefixes`), each gid by reference; `public_read: true` adds the
  EFS root access point / the S3 same-account read policy, and the instance
  template mounts a `public_read` EFS through the public access point
  rather than the group's.
- **Declared `variables` or not; tags.** A declared variable is passed
  verbatim; an undeclared one is absent so the module default applies
  (`volume_type` `gp3`, `encrypted` true, `performance_mode`
  `generalPurpose`, `force_destroy` false). Tags are the builder's
  `variables.tags` under the storage item's, and are absent when both are
  empty.
- **Encrypted versus clear values.** The plugin treats an `ENC[age:...]`
  value like any other string: the committed emission carries the
  ciphertext and each runner step enters the root through
  `cs-image-system materialize .`, which writes the plaintext mirror the
  tofu commands run in (OPERATIONS "Encrypted values"). Nothing in this
  package decrypts.

## What it tests and verifies

What this plugin and the base machinery around it check, when, and where
the verdict lands. "Validator" means a function registered on the run's
validator list: `cs-image-system validate` and every `run` execute them
before anything is emitted, and one failure is exit 1 with every message
printed and recorded in `generated/run-summary.json` under
`validation_errors`.

**At load (pydantic, before any validator).** The verdict is a
`ValidationError` naming the file and key; the load stops.

- Unknown keys on any model this package owns are refused
  (`CSIS_MODEL_CONFIG`); `parameters:` on a builder is refused with a
  message naming `variables:` as the replacement.
- `variables:` keys are typed per provider: `performance-mode`,
  `volume-type`, or `size` under `variables:` on `tf-aws-ebs` are refused.
- `bucket_name` is required on a `tf-aws-s3` builder (still required,
  although since stage 63 nothing reads it: the state query takes the
  storage's bucket).
- A `Storage` refuses `state` outside `active`/`archived`/`destroyed`,
  `share_mode` outside `2770`/`2775`, the `ALL` group value, an empty
  `runtime` or `type`.
- An `Instance` refuses a `groups:` key; a `StorageMapping` refuses an
  empty `mount_point` or a non-positive `min_size` (its `aliases` are
  dropped with a warning).
- A builder `name` containing `/` or `\` is refused.

**At `validate` (and at the start of every `run`).** Base validators, in
[v2_validation.py](../base/src/cs_image_system/base/v2_validation.py),
[launch_params.py](../base/src/cs_image_system/base/launch_params.py),
[lineage.py](../base/src/cs_image_system/base/lineage.py),
[release.py](../base/src/cs_image_system/base/release.py),
[validate.py](../base/src/cs_image_system/base/commands/validate.py) and
[alias_pool.py](../base/src/cs_image_system/base/alias_pool.py), some of
which call back into this plugin:

- the storage attach rule: a storage's allowed groups exist; an instance's
  owning group is on the list (or the storage is `public_read`);
- attachment cardinality: two instances on one `ebs` storage are refused,
  naming the multi-host builders on that runtime (this plugin's
  `attachment_cardinality()`);
- `lifecycle:` declarations, through this plugin's `validate_lifecycle()`:
  refused outright on EBS; the EFS and S3 keys and values as tabled above;
- the storage state machine: illegal transitions, a new storage not
  starting `active`, a transition out of `active` while attached,
  `archived` on a builder that cannot archive (`supports_archive()`), an
  undeclared storage whose record names no builder, an attachment of a
  storage that is not `active`;
- capabilities: a mounted storage's type (`capability_type()`) must be in
  the image's root base build's stamped `storage_types`;
- launch-parameter immutability: a launched instance whose recomputed
  parameters differ from `launch-params.yaml` (other than a mount removal
  or a sanctioned replacement) is refused naming the changed keys;
- claimed hostnames: only when the instance-image lifecycle is requested
  and `apply_instances` is on, each canonical hostname is checked against
  the group's OPA registry; a registered name for an unlaunched instance,
  two registrations for a launched one, or a registry that did not answer
  are refusals;
- policies: `image_policy`, `on_failure` and `teardown_after` values;
- released pins: under `require_released_builds`, a pin that is not a
  released build is refused unless the release grace admits it (the
  series head on its runtime, verified in bake, no failed post-bake
  record, and the instance is a pending replacement onto it or stands on
  it) -- the grace is logged as a warning, the refusal names what is
  missing;
- availability zones: more than one distinct zone across an instance, the
  zonal storages it mounts (`is_zonal()`) and its runtime's effective
  subnet is refused naming each claimant;
- the alias pool: a free line that is not a legal hostname label, repeats
  another, or is a declared instance name;
- every declared executable exists and its version satisfies the
  requirement (`TofuVersionChecker`).

**At generation.** Each emitted root runs `tofu fmt`, `tofu init`
(`-backend=false` in a dry run) and `tofu validate` in its directory; a
non-zero exit fails the generation with a log line naming the builder and
the command. A storage whose allowed group has no identity builder raises
`ValueError` from `gid_reference`. An instance with no provider-specific
image logs a warning and gets no `ami_id`. A `tf-aws` builder entry raises
`NotImplementedError` at its first module call. The alias draw logs what it
took or would take. Nothing plans at generation.

**In the runner (apply time).** `gate-plan` refuses a missing or stale
planfile and any destroy that is not whitelisted, and refuses a detach
without a successful receipt in `unmount-receipts/<instance>__<storage>.json`
(the unmount step writes it after running the unmount over SSM);
`apply-check` refuses when the flag is off now, an overlay is gone, or no
`cfg/_config.yml` is found; `verify instance <name>` (ephemerals) runs the
runtime's checks (over SSM on AWS: the completion marker, the mounts, the
booted AMI) plus the image's `tests.post_bake`, records the verdict in
`meta-state/verifications.yaml` and the post-bake result in
`meta-state/image-tests.yaml`, and raises on failure unless `--record-only`.
`archive-<label>.sh` exits 1 when no volume of that name exists. All of
these stop the runner under `set -euo pipefail`; the run summary records
the lifecycle's apply as `failed` and the run exits 1.

**After apply (post-finalize and the base hooks), only when the root's
apply flag was on and the root is inside the run's runtime scope (stage
63).** `post_finalize_phase` binds first pins and moves
`follow` pins in `meta-state/pins.yaml` (a booted image lineage does not
record is logged and left unbound). The base hooks then mark instances
`launched`, open or close generations in `instance-state.yaml` and confirm
them against the provider's instance id, retire the replaced machine's OPA
registration, forget decommissioned and ephemeral records, re-record
detached mounts, write the AltNames aliases, and record storage
transitions in `storage-state.yaml`. Every verdict is a log line and a
meta-state write; a `--commit` run commits them.

**In the state query.** `query_state()` on each storage builder reports
every owned storage as `present` or not with the provider record;
[state_query.py](../base/src/cs_image_system/base/state_query.py) turns that
into drift lines in `generated/state-report.json`: `missing [HARD]` for a
recorded non-destroyed storage that is absent, `stale` for a destroyed
record that still exists, for a provider state other than
available/in-use/active/ready, and for a declared lifecycle the resource
does not carry yet, `foreign` for a present storage with no record, and an
`unavailable:` line when the lookup raised (an S3 permission or transport
error is raised on purpose so it is never read as absent). The instance
root has no state query of its own: an instance's booted image, power
state, generation and aliases are read by the runtime plugin.

## When it fails

The failures this plugin produces or takes part in, with what the operator
sees, what it means, where to look and what to do. Failures that have
happened live come first, dated; the sources are
[OPERATIONS.md](../../docs/OPERATIONS.md), the findings ledger in
[docs/history/LEDGER.md](../../docs/history/LEDGER.md), the tests named
below and the commit messages on this package.

### Failures that have happened

- **2026-09-02 (findings 20 and 21): an apply-less storage run recorded
  `None -> active`.** The fixture carried no `apply_storage` key, so the run
  planned and gated with zero applies, and the transition recorder wrote
  the requested state anyway; the state query's `missing [HARD]` caught the
  lie. Since then every reality-claiming recorder (storage transitions, the
  `launched` marker, pin binds, the forgets) runs only when the lifecycle's
  apply flag was on. What to expect now: a dry or apply-less run leaves
  `storage-state.yaml`, `launch-params.yaml` `launched` and `pins.yaml`
  exactly as they were.
- **Stage 1, 2026-08-31 to 2026-09-02 (finding 22): the S3 state query
  reported the system's own bucket as HARD-missing** because it looked for
  a `Name` tag the module never sets. `_lookup` now treats a reachable
  bucket as present; only `NoSuchBucket`/`404` is absent and any other
  error is re-raised into an `unavailable:` line.
- **Stage 1 (finding 24): `apply_*` flags gated generation only**, so a
  runner script generated under a flag kept applying after the flag was
  turned off. Now every apply is preceded by `cs-image-system apply-check`,
  which re-reads `cfg/_config.yml` and the overlays at execution and exits
  3 with `apply_instances is false NOW in <path>/cfg/_config.yml ... not
  applying.`
- **Stage 1 (finding 25): a `t2.micro` OOM-killed the SSM agent** minutes
  after boot. `machine_type` on the instance overrides the runtime default;
  size the machine for its image.
- **Stage 1 (finding 26): the module's default public IP poisoned sftd's
  advertised address** in a VPC with no internet gateway, so `sft ssh`
  hung. The module call now sets `associate_public_ip_address = false` and
  the launch script pins `AccessAddress` to the private IP.
- **Stage 1 (findings 27, 29, 30, 31): instances wore only the VPC default
  security group**, which blocked the Okta gateway's inbound SSH relay. The
  root now creates `csis-instances` with SSH ingress from
  `ssh_ingress_security_group_ids` (never a CIDR of the shared networks),
  `create_before_destroy` (a delete-first replacement hit
  `DependencyViolation` because instances wear the group), and every
  instance also wears `addl_security_groups` (the relay requires the
  OKTA-GATEWAY group on the target). Symptom without them: `sft ssh` hangs
  or is refused while every step reports success.
- **Stage 1 (finding 28): user-data died at `mkfs`** because on Nitro
  instances (`t3` and later) the EBS volume never appears as `/dev/xvdf`
  and RHEL-family AMIs create no legacy symlink; everything after the
  `mkfs` line never ran and the mount was missing. The launch script waits
  for either the declared device or the
  `/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_<volume id>` name.
  Where to look: the instance's cloud-init/user-data log, and `verify
  instance` (the completion marker `/var/lib/csis/launch-applied` is
  written only when every line above it succeeded).
- **Stage 1 (finding 33): `gate-plan` accepted a stale planfile** left by a
  failed plan. Every sequence now begins with `rm -f tfplan` and the gate
  refuses with `STALE PLANFILE: tfplan is older than <file>` (exit 3) or
  `tfplan does not exist`.
- **2026-09-04 (finding 45): the root-level `aws_vpc` and
  `aws_security_group` blocks bound the DEFAULT aws provider**, which has no
  configuration, so they only ever planned from a shell with ambient AWS
  credentials. Both now carry `provider = aws.<alias>`. Symptom: a plan
  that fails on the VPC lookup with a credentials or region error while
  the module calls are fine.
- **2026-09-05 (findings 52 and 53), tearing down the first GCE instance,
  fixed in both instance builders
  ([test_v2_decommission.py](../../tests/test_v2_decommission.py)):**
  undeclaring the last instance on a runtime made its root vanish, so
  nothing ever planned the destroy and the VM would have stayed orphaned;
  and the forget of the launch record ran at generation, so a dry run
  erased it before any destroy and the gate then had nothing to whitelist.
  Now `_root_has_work()` emits an instance-less root whenever a recorded
  instance is undeclared, the decommission whitelist is scoped to the root
  of the runtime the pinned build was baked on, and the forget is an
  after-apply hook. A decommission can be dry-run as often as needed.
- **2026-09-05/06 (finding 49): a pin was re-bound to a new series head
  without replacing the instance**, so meta-state claimed a build reality
  did not run. The post-finalize hook now binds from what actually booted
  when the parent was deferred, and the state query reports
  `booted image <x> != pinned build <y>` as `changed`.
- **2026-09-09 (ledger 68,
  [test_v2_ephemeral.py](../../tests/test_v2_ephemeral.py)): a torn-down
  ephemeral kept its launch record** because a `verify assert` as the
  runner's last step failed the script before the after-apply hook ran.
  Under `on_failure: teardown` the verdict now fails the run from
  `forget_ephemerals`, after the record is forgotten.
- **2026-09-10 (ledger 70): a run scoped to AWS planned the GCE instance
  root too**, whose image-family lookup returned 404 because the previous
  cycle had disposed every GCE image, and the run failed before the dask
  bake. Under `--only-runtime` (explicit or implied by `--apply-runtime`)
  another runtime's instance and storage roots emit nothing, and since
  stage 63 (2026-09-25) the out-of-scope instance builder's finalize hooks
  do nothing either.
- **Until 2026-09-25 (stage 63): every scoped run logged `No resolved
  provider-specific images for instances; modules will use their
  name-pattern fallback`** (seen in every GCE cycle), because the AWS
  instance builder's `pre_finalize_phase` still ran for a root the scope
  had left empty and wrote an `instances.auto.tfvars` nothing read. Both
  finalize hooks now return early for a root outside the runtime scope.
- **Until 2026-09-25 (stage 63): two S3 storages on one builder reported
  the same bucket.** The state query read the builder's `bucket_name`, not
  the storage's, so the second storage's presence and tags were the
  first's. `_lookup` now asks for the storage's own bucket (its
  `bucket_name`, else its name)
  ([test_v2_defects_dead.py](../../tests/test_v2_defects_dead.py),
  `test_the_s3_lookup_asks_for_the_storages_own_bucket`).
- **2026-09-19 (stage 52,
  [test_v2_availability_zones.py](../../tests/test_v2_availability_zones.py)):
  a zone was inferred from the subnet and never checked.** Pointing the
  runtime at a subnet in another zone planned `forces replacement, 1 to
  add, 1 to destroy` on a 100 GiB data volume; the gate refused it as an
  unwhitelisted destroy, but at apply time and naming the volume rather
  than the cause. Now a subnet, a storage and an instance may declare
  `availability_zone`, `validate` refuses an incompatible set naming each
  claimant, and the EBS builder passes the declared zone to the module.
- **2026-09-20 (stage 19,
  [test_storage_module_calls.py](tests/test_storage_module_calls.py)): no
  instance in the account could mount an EFS storage.** The module made a
  filesystem and its access points and no mount targets, so `mount.efs`
  could not even resolve the filesystem's DNS name; `verify instance`
  failed on the mount. The module now creates one mount target per zone and
  a security group for them, and the builder passes the runtime's private
  subnets (one per zone) and `addl_security_groups` as the clients. If the
  runtime declares no `networking`, or no private subnets, or no
  `addl_security_groups`, the call carries none of the three and the
  filesystem is again unmountable: check the emitted
  `<B>-storage-generation-storage-<label>.tf` for `mount_target_subnet_ids`.
- **2026-09-20: `coops-model` was destroyed through the gate but its pin
  and launch parameters stayed**, which with `require_released_builds` on
  made `validate` refuse every run. The mechanism is proven in the fixture,
  so the live failure remains unexplained; the recourse is
  `cs-image-system forget instance <name>`, which drops the records without
  editing meta-state by hand.
- **2026-09-22, the first live replacement (`coops-model` ->
  `coops-model-002`), four traps:** the gate refused
  `module.instance_coops_model.aws_volume_attachment.this["mnt_data"]` as
  an unwhitelisted destroy (the attachment binds the volume to the
  instance id, so the `-replace` replaces it too) -- now
  `_replacement_attachments()` whitelists it; the strict state query
  reported the booted image behind the moved pin as drift and refused the
  very run that finishes the upgrade -- now a pending replacement is a
  `note`; the replaced machine's OPA registration outlived it and would
  have claimed the new machine's alias -- now `mark_launched` retires it;
  and the alias pass ran before the new machine had enrolled and wrote
  nothing -- now it waits. Proof in
  [test_v2_gate5_capabilities_activation.py](../../tests/test_v2_gate5_capabilities_activation.py)
  and [test_v2_provider_aliases.py](../../tests/test_v2_provider_aliases.py);
  the procedure is OPERATIONS "A model image, end to end".
- **2026-09-20 and 2026-09-22: `require_released_builds` had to be switched
  off by hand** for the window between `upgrade instance` and the release,
  because a durable instance whose volume allows one attachment can only
  prove a build on itself. Since 2026-09-23 (stage 61 item 4) the release
  grace admits the series head while its own proof is under way; the
  refusal now reads `instance '<name>' is pinned to build <id> of '<image>',
  which is not a released build (config.require_released_builds; no grace:
  <what is missing>)`. Proved live the same day as the third release
  (`coops-model-003`, the pool's first draw).
- **Until 2026-09-23 (stage 61 item 5): the `release` and `retention`
  lifecycles wrote `instances.auto.tfvars` under their own generation
  directories**, where no instance root exists; the file lingered untracked
  after every release run. `pre_finalize_phase` now acts for the
  `instance-image` lifecycle alone
  ([test_v2_hygiene_five.py](../../tests/test_v2_hygiene_five.py)).
  Since stage 63 both finalize hooks also return early for a root outside
  the run's runtime scope
  ([test_v2_defects_dead.py](../../tests/test_v2_defects_dead.py),
  `test_an_out_of_scope_instance_root_writes_no_tfvars`).
- **Found live, undated: the S3 prerequisite bake failed on RHEL-family
  images** because `unzip` is not installed there (`curl` is). The
  prerequisite now installs `unzip` before fetching the AWS CLI zip.

### Failures the code raises that have not happened

Each with the message or symptom, what it means, where to look, what to do.

- `NotImplementedError: TofuStorageBuilder must name its terraform module`
  at generation: a builder entry declares `type: tf-aws`. Use
  `tf-aws-ebs`, `tf-aws-efs` or `tf-aws-s3`.
- `ValueError: Storage builder <B>: group '<g>' has no identity builder` at
  generation: a storage's allowed group is not owned by any group builder,
  so no `group_gids` output can be referenced. Declare the group under a
  group builder, or remove it from `groups:` (the validator's `storage
  '<name>' allows unknown group '<g>'` usually catches it first).
- Log warning `No provider-specific image for image '<img>' of instance
  <name>; the module call will not resolve an AMI`: the image is not baked
  on the instance's runtime and lineage has no head. The emitted call has
  no `ami_id`; `tofu validate` passes but the plan fails on the module's
  `data "aws_ami"` with an empty pattern. Bake the image on that runtime
  first.
- Log info `No resolved provider-specific images for instances; modules
  will use their name-pattern fallback` at pre-finalize: nothing baked this
  run, so no `instances.auto.tfvars`; the module resolves `ami_id` from the
  pin or the most recent AMI matching the pattern. Expected on a launch
  that re-bakes nothing. Since stage 63 it is never logged for a root
  outside the run's `--only-runtime` scope (the hook returns before it).
- Log warning `Instance <name> booted <ami>, which lineage does not record;
  pin left unbound`: the parent was deferred and the machine booted an
  image outside lineage (a foreign AMI matched the name pattern). Run
  `state import` or dispose the foreign image, then `upgrade instance` onto
  a recorded build.
- `DESTROY NOT WHITELISTED: <address>` from `gate-plan` (exit 3): the plan
  destroys something no operation sanctioned. Common causes on these
  roots: `volume_type`, `size` or `availability_zone` changed on an EBS
  storage (all force replacement; declare what exists, or archive and
  restore), a subnet in another zone, a renamed storage (a new module
  address is a create plus a destroy; retire the old name through
  `state: destroyed` or by removing the entry), an instance's changed
  image without an upgrade. Read `tofu show tfplan` in the root; nothing
  applied.
- `DETACH NOT UNMOUNTED: <instance>:<storage> has no successful unmount
  receipt` (exit 3): the unmount step did not write
  `unmount-receipts/<instance>__<storage>.json` with `ok: true`. Look at the
  runner's `unmount storage` output; when the machine is gone or the mount
  point was never mounted, `unmount storage --confirm ...` records the
  operator's word instead.
- `unmount of <mount point> on <instance> failed (exit <n>): ...`: the
  session command could not unmount (a process holds the mount, or SSM
  cannot reach the machine). The runner stops before the plan.
- `STALE PLANFILE: tfplan does not exist` or `... is older than <file>`
  (exit 3): the plan step failed or the root changed after it. Re-run the
  lifecycle; never hand the gate an old file.
- `apply_<lifecycle> is false NOW in <path>/cfg/_config.yml [for root
  '<B>'] ... not applying.` (exit 3), `apply-check: overlay <path> is gone;
  refusing to apply`, `apply-check: no cfg/_config.yml found from the
  working directory up`: the execution-time guard. Turn the flag on (or
  list the root/runtime), restore the overlay, or run from a checkout that
  holds the tree.
- `instance <name> failed verification: <check>: <detail>` from `verify
  instance`: an ephemeral's launch did not complete (the marker
  `/var/lib/csis/launch-applied` is missing: a launch-script line failed,
  including a declared `userdata` line), a mount is absent, the booted AMI
  is not the expected build, or a post-bake assertion failed. Under `keep`
  the machine stands for inspection and the state query reports `ephemeral
  instance is STANDING ...` until it is decommissioned (undeclare it and
  run with the root allowed to apply); under `teardown` the run still fails
  after the teardown. `verify <name>: SKIPPED -- the machine is stopped ...`
  records nothing.
- `Ephemeral instance <name>: teardown_after elapsed since its failed
  verification; tearing down without re-verifying` (log): expected on the
  run after the duration.
- `instance '<name>' was launched (run <r>) and its launch parameters
  changed (<keys>); launch parameters are immutable after launch -- replace
  the instance (upgrade instance, or decommission and redeclare) (N26)`:
  a mount was added, a mount point or `userdata` changed, the image or
  group changed. Removing a mount is the one in-place change; anything else
  is a replacement.
- `instance '<name>': canonical hostname '<h>' is already registered to N
  server(s) in group '<g>' ...` / `... could not check whether canonical
  hostname ... (group '<g>'s server registry did not answer); refusing to
  launch on silence`: only on an applies-on instance-image run. Retire the
  stale registration (a decommission does it; or `DELETE` the server under
  the resource group's project), or restore the OPA credentials.
- `instance '<name>' is pinned to build <id> of '<image>', which is not a
  released build (config.require_released_builds; no grace: ...)`: release
  the build, `upgrade instance` onto a released one, or read what the grace
  needs (the build must be the series head, verified in bake, with no failed
  post-bake record, and the instance a pending replacement onto it or
  standing on it).
- `storage '<name>' (<builder>) is single-attach but instances [...] all
  attach it (N16); multi-host storage builders on <rt>: [...]`: an EBS
  volume attaches to one instance; use EFS or S3 for a shared storage.
- `storage '<name>' cannot move <cur> -> <req> while attached by [...]
  (detach in one run, transition in the next; N21)`, `storage '<name>'
  (<builder>) requests archived, which its builder does not realize`,
  `storage '<name>' has never been applied; a new storage must start
  'active'`, `storage '<name>': transition <a> -> <b> is not legal`,
  `instances [...] attach storage '<name>' which is <state>`: the state
  machine at validate. Two runs for detach-then-archive.
- `storage '<name>': lifecycle.<key> must be one of [...]`, `... unknown
  lifecycle keys [...] (efs: ia_days, archive_days)`, `... lifecycle
  declares neither transition_days nor expire_days`, `storage '<name>'
  (<builder>) declares a data lifecycle, which its builder does not realize
  (no lifecycle on ebs storages)`: fix the declaration per the table
  above.
- `instance '<name>' (image '<img>', group '<g>') may not attach storage
  '<s>': allowed groups are [...] (N2)` and `instance '<name>' (image
  '<img>') attaches storage '<s>' of type '<t>' which base '<b>' does not
  declare`: add the group to the storage's `groups:` (or `public_read`),
  or declare the type on the base image and bake forward.
- `no volume named <name> to archive` (exit 1 from `archive-<label>.sh`):
  the volume the `Name` tag should find is gone. Check the state query; if
  the archive snapshot already exists the script reuses it and exits 0.
- `aws: command not found` or `bash: aws: No such file or directory` in a
  storage runner: the AWS CLI is not on the runner's `PATH`; install it
  where the script runs.
- `Reference to undeclared resource` from `tofu validate` at generation:
  `use_state_backends` is off while the emission references remote state
  (any instance with a group or mount, any storage with groups). Turn the
  flag on and declare a backend.
- `Backend configuration changed` from `tofu init`: only when a root is
  initialised by hand without `-reconfigure`; the generated commands always
  carry it. A root whose state must move is `--migrate-state <root>`, never
  a hand `init`.
- `Instance <name>: the alias pool is EMPTY; launching <hostname> without
  an alias (append names to aliases.txt to refill it)` (warning): the
  launch proceeds; append names.
- `Instance <name>: its OPA registration as '<h>' was NOT retired (<e>); a
  stale server will answer to that name until it is deregistered by hand`
  (error, never fatal to the forget): deregister by hand under the
  resource group's project.
- State query lines `storages/<B>: ... unavailable` (a lookup raised: a
  permission error, an expired session, no network) and `storage <name>
  recorded <state> but not found in reality [HARD]` (the volume, filesystem
  or bucket is gone out of band): a HARD line refuses every run until the
  record is corrected through `state import`/the forget paths, never by
  hand-editing meta-state.
- `Instance builder <B> does not specify a runtime provider.` /
  `... has runtime provider <rt> which is not configured`: the builder's
  `runtime:` resolves to nothing; name a declared runtime.

## Related

- [cs-image-system-tf-gcp-plugin](../tf-gcp-plugin/README.md): the GCE
  instance root and the GCP storage builders, subclasses of this package.
- [cs-image-system-tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the
  S3 state backend the `state_configuration` field names.
- [cs-image-system-aws-runtime-plugin](../aws-runtime-plugin/README.md): the
  runtime whose region, credentials, networking and session mechanism these
  roots read, and whose hooks verify instances and read their booted image.
- [hashicorp-utils collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py):
  the run-scoped `TerraformCollector` that renders the terraform, provider,
  variable, backend and remote-state blocks.
- [hashicorp-utils roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py):
  `TerraformRootMixin`, the init arguments and the gated apply sequence.
- [base launch_params.py](../base/src/cs_image_system/base/launch_params.py),
  [base storage_state.py](../base/src/cs_image_system/base/storage_state.py),
  [base lineage.py](../base/src/cs_image_system/base/lineage.py),
  [base alias_pool.py](../base/src/cs_image_system/base/alias_pool.py),
  [base generations.py](../base/src/cs_image_system/base/generations.py),
  [base release.py](../base/src/cs_image_system/base/release.py): launch
  parameters, the storage state machine, pins and image policies, the alias
  pool, instance generations, the release grace.
- [base commands/gate.py](../base/src/cs_image_system/base/commands/gate.py),
  [base commands/unmount.py](../base/src/cs_image_system/base/commands/unmount.py),
  [base commands/verify_instance.py](../base/src/cs_image_system/base/commands/verify_instance.py):
  the gate, the unmount receipt, the verification.
- [tests/test_instance_module_calls.py](tests/test_instance_module_calls.py)
  and [tests/test_storage_module_calls.py](tests/test_storage_module_calls.py):
  the unit tests that pin the module arguments described here.
- [docs/DESIGN.md](../../docs/DESIGN.md), [docs/OPERATIONS.md](../../docs/OPERATIONS.md)
  and [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md): the system
  design, the operator's view of the lifecycles, and the configuration
  manual.
