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
implementation.

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
| `required_plugins` | list[`TFTofuPluginModel`] | [] | Terraform providers (`name`, `source`, `version`) for the root's `required_providers`. Empty means one `aws` provider from `hashicorp/aws` with no version constraint. |
| `state_configuration` | str (foreign key to `STATE_BACKEND_MODEL`) | `default` | The state backend for this workspace, by backend name. `default` resolves to the backend with `is_default: true`. |

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
| `userdata` | str | "" | Extra shell lines appended to the generated launch script. | |
| `image_policy` | str | `pinned` | `pinned` keeps the launched build until an explicit upgrade; `follow` plans a gated replacement whenever the image's series head moves. | `pinned`, `follow` |
| `ephemeral` | bool | false | Launch, verify and tear down in the same run. | |
| `on_failure` | str \| None | None | What a failed verification of an ephemeral does: `keep` leaves it standing and fails the run; `teardown` tears it down and still fails the run. None inherits the runtime builder's value, else `keep`. | `keep`, `teardown` |
| `teardown_after` | str \| None | None | Duration (`"2h"`, `"30m"`, `"1d"`) after a failed verification past which the next run tears a standing ephemeral down without re-verifying. | |
| `machine_type` | str | "" | EC2 instance type; empty means the runtime's `default_machine_type`. | |
| `tags` | dict[str, str] | {} | Passed to the module as `tags`. | |
| `description`, `config` | | | Not read by this plugin. | |

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
| `state_configuration` | str (foreign key) | `default` | State backend by name. |
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
| `bucket_name` | str | required | The bucket the builder's **state query** reads (`get_bucket_name()`). The module call takes the bucket name from the storage item instead (see below). |
| `variables` | `S3Variables` | `S3Variables()` | `force_destroy`, `tags`. |

### The `Storage` item the storage builders read

Base `Storage` from
[storage.py](../base/src/cs_image_system/base/models/storage.py):

| Field | Type | Default | Meaning | Read by |
|---|---|---|---|---|
| `type` | str | `default` | The storage builder (name or alias). | all |
| `runtime` | str | `default` | The runtime builder. | all |
| `groups` | list[str] | [] | Groups allowed to use the storage. Each gets a private root-level subtree `/<group>/`. The value `ALL` is refused. | EBS (launch script), EFS (access points), S3 (prefixes) |
| `public_read` | bool | false | Anyone may mount read-only; POSIX permissions still govern. | EFS, S3 |
| `share_mode` | str | `"2770"` | Subtree mode: `2770` group-private, `2775` read-shared. | EBS (launch script), EFS |
| `state` | str | `active` | The **requested** lifecycle state. | all |
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
runtime's session mechanism, the hostname, `ephemeral`, and any `userdata`.
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
builder or its runtime. The gate fails unless every destroy in the plan is
whitelisted. The whitelist holds: `module.instance_<label>` for every
recorded instance that is no longer declared (a decommission, scoped to this
runtime by the build's lineage record); and
`module.instance_<label>.aws_volume_attachment.this` for every detach.
`-replace=module.instance_<label>.aws_instance.this` is added for instances
with a pending explicit upgrade or a `follow` target.

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

**4. `pre_finalize_phase`** runs before the deferred commands. For every
instance whose provider-specific image is now resolved (the image builder's
post-hook has read the packer manifest), it writes
`<B>/instance-generation/instances.auto.tfvars` with one line
`<label>_ami_id = "<ami id>"`, so the module uses the exact artifact instead
of the name-pattern fallback.

**5. `post_finalize_phase`** runs after the deferred commands succeed and only
when the root applied. For every non-ephemeral instance: a `follow` target
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
storage, `present`, the capability type and the provider record found by
`Name` tag (or, when recorded `archived`, the archive snapshot).

#### Per-subclass behaviour

| | `TofuEbsStorageBuilder` (`tf-aws-ebs`) | `TofuEfsStorageBuilder` (`tf-aws-efs`) | `TofuS3StorageBuilder` (`tf-aws-s3`) |
|---|---|---|---|
| Module | [aws_storage_ebs](../../tfmodules/aws_storage_ebs/variables.tf) | [aws_storage_efs](../../tfmodules/aws_storage_efs/variables.tf) | [aws_storage_s3](../../tfmodules/aws_storage_s3/variables.tf) |
| Capability type (what a base image declares in `storage_types`) | `ebs` | `efs` | `s3` |
| Attachment cardinality | single | many | many |
| POSIX | yes | yes | no (groups become prefixes; `public_read` is a same-account read policy) |
| Supports `archived` | yes: snapshot named `csis-<label>-archive`, then the volume is destroyed; restore creates the volume from that snapshot and deletes it after the apply | no | no |
| `lifecycle:` keys | refused | `ia_days` in {1,7,14,30,60,90,180,270,365}; `archive_days` in {90,180,270,365} | `transition_days` (positive int), `storage_class` in {STANDARD_IA, ONEZONE_IA, INTELLIGENT_TIERING, GLACIER_IR, GLACIER, DEEP_ARCHIVE}, `expire_days` (positive int), `prefix`; a class needs `transition_days`; at least one of the two day counts |
| `destroyed` transition action | delete the archive snapshot when the volume was archived | none | `aws s3 rm s3://<bucket> --recursive [--profile <p>]` before the destroy |
| Base-image prerequisites | none (a comment) | `nfs-common` (Debian family) or `amazon-efs-utils`/`nfs-utils`; verify: `mount.efs`/`mount.nfs` present | AWS CLI installed via the official zip; verify: `aws` present |
| State query | `describe_volumes` by `Name` tag, or `describe_snapshots` when archived | `describe_file_systems` matched by name, plus the lifecycle policy | `get_bucket_tagging` on the **builder's** `bucket_name`; `NoSuchBucket` means absent, any other failure is "unavailable" |

Module arguments (`module_args(storage)`), in emission order:

| Builder | Arguments |
|---|---|
| EBS | declared `variables` (`volume_type`, `encrypted`); `name`; `size` (the builder's); `snapshot_name = csis-<label>-archive` when the storage is recorded archived and declared active (restore); `availability_zone` from the runtime's default AZ, else `subnet_id` from its default subnet; merged `tags` |
| EFS | declared `variables` (`performance_mode`, `encrypted`); `name`; `existing_file_system_id` from `config.file_system_id`; `transition_to_ia = AFTER_<ia_days>_DAYS`; `transition_to_archive = AFTER_<archive_days>_DAYS`; `access_points` = the group subtrees (gid by reference); `public_read = true` when set; merged `tags` |
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
| [run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh) | the deferred sequence per root: `rm -f tfplan`, `init -input=false -reconfigure -backend-config=...`, `plan -input=false -out=tfplan`, `gate-plan` (no apply: the fixture sets `apply_instances: false`) |

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
to a build that is not a released build of its image.

## Related

- [cs-image-system-tf-gcp-plugin](../tf-gcp-plugin/README.md): the GCE
  instance root and the GCP storage builders, subclasses of this package.
- [cs-image-system-tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the
  S3 state backend the `state_configuration` field names.
- [hashicorp-utils collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py):
  the run-scoped `TerraformCollector` that renders the terraform, provider,
  variable, backend and remote-state blocks.
- [hashicorp-utils roots.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/roots.py):
  `TerraformRootMixin`, the init arguments and the gated apply sequence.
- [base launch_params.py](../base/src/cs_image_system/base/launch_params.py),
  [base storage_state.py](../base/src/cs_image_system/base/storage_state.py),
  [base lineage.py](../base/src/cs_image_system/base/lineage.py): launch
  parameters, the storage state machine, pins and image policies.
- [tests/test_instance_module_calls.py](tests/test_instance_module_calls.py)
  and [tests/test_storage_module_calls.py](tests/test_storage_module_calls.py):
  the unit tests that pin the module arguments described here.
- [docs/DESIGN.md](../../docs/DESIGN.md) and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md): the system design and the
  operator's view of the lifecycles.
