# cs-image-system-tf-gcp-plugin

This package is the OpenTofu plugin for Google Cloud. It registers one
**instance builder** (`tofu-gce`), which turns every declared instance into a
`module` call against `tfmodules/gce_instance`, and three **storage
builders** (`tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs`), which turn every
declared storage into a `module` call against the matching
`tfmodules/gcp_storage_*` module. It contains no generic machinery of its
own: every builder subclasses the provider-neutral terraform roots of
[cs-image-system-hashicorp-utils](../hashicorp-utils/README.md#the-terraform-roots)
(`TofuInstanceBuilderBase`, `TofuStorageBuilderBase`) and answers their
hooks with what is Google Cloud's own: the `google` provider configured
from the runtime's project, region and zone, the `gce_instance` and
`gcp_storage_*` modules, a GCE image resolved through its family, a
persistent disk attached as an in-place attribute, and `gcloud`
transition scripts. It does not depend on the AWS root
([cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)),
which is another subclass of the same bases. The runtime it targets is
a `gcloud` runtime builder from `cs-image-system-gcloud-runtime-plugin`,
which supplies the project, region, zone, network and session mechanism.

## What it registers

The entry point, from [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.instance"]
tf-gcp-plugin = "cs_image_system.tf_gcp_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/tf_gcp_plugin/main.py)
returns a `TFGcpTypes` metadata object (plugin metadata version `1`, Python
`3.13`). The package depends on `cs-image-system-hashicorp-utils` (the
neutral roots, their models and the version checker) and
`cs-image-system-gcloud-runtime-plugin` (the runtime model, `gce_name`,
`gce_label`, and the GCP client helpers); not on the AWS root.

| Service name (`type:` of a builder entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `tofu-gce` | `TofuGceInstanceBuilderModel` | `TofuGceInstanceBuilder` | `INSTANCE_BUILDER_MODEL`, `INSTANCE_BUILDER`; also `TofuVersionChecker` (`VERSION_CHECKER`, under the name `tofu`) |
| `tf-gcp` | `TofuGcpStorageBuilderModel` | `TofuGcpStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-pd` | `TofuPdStorageBuilderModel` | `TofuPdStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-filestore` | `TofuFilestoreStorageBuilderModel` | `TofuFilestoreStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-gcs` | `TofuGcsStorageBuilderModel` | `TofuGcsStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |

`tf-gcp` is a base: it answers the provider hooks of
`TofuStorageBuilderBase` (the `google` provider and the root's header)
and leaves `module_dirname()` and `module_args()` unanswered, so it
cannot emit anything. A builder entry with `type: tf-gcp` is therefore
refused when the tree loads, naming the three concrete types, rather than
loading and failing at generation. The entry point also registers
hashicorp-utils' `TofuVersionChecker` (under the service `tofu-gce`; its
own name is `tofu`), so an executable entry with `type: tofu` is checked
in a tree whose only terraform roots are GCE roots; the registry takes
the one class from several plugins as one registration, so a tree with
the AWS root installed as well sees no collision.

### Two levels of `type:`

1. A **builder entry** under `instance_builders:` or `storage_builders:`
   selects a plugin class by `type:` = a service name above. Its `name:`
   (`tofu-gce`, `gcp-pd`, `gcp-gcs` in the fixture) is the terraform
   workspace name and the directory under `generated/`; its `aliases:`
   register extra names.
2. An **instance entry** selects a builder by `type:` = the builder's name
   or alias (`type: tofu-gce`); a **storage entry** does the same
   (`type: gcp-pd`). `default` resolves to the builder with
   `is_default: true`, which in the fixture is an AWS builder, so GCP items
   always name their builder.

## Models

Source:
[tf_gcp_models.py](src/cs_image_system/tf_gcp_plugin/tf_gcp_models.py). All
models are pydantic dataclasses; unknown keys are refused at load, and a
`parameters:` key is refused with a message naming `variables:`.

The inherited base fields (`name`, `type`, `description`, `aliases`,
`executable`, `is_default`, `config`, `gitignore`, `tags`, `runtime`) are
those of every builder model; see
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
The full field tables are the configuration reference's
([instance builders](../../docs/CONFIGURATION.md#81-instance-builders),
[storage builders](../../docs/CONFIGURATION.md#82-storage-builders)).
What this package does with the fields every class here inherits from
the neutral models of hashicorp-utils
([tofu_models.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/tofu_models.py)):

- `executable` names an entry in `cfg/executables.yml` (default `tofu`).
- `required_plugins` lists the terraform providers for the root; empty
  means one `google` provider from `hashicorp/google` with no version
  constraint.
- `state_configuration` names the state backend for the workspace; a GCP
  root may use the S3 backend.

### `TofuGceInstanceBuilderModel` (`tofu-gce`)

Extends `TofuInstanceBuilderModelBase` from
[tofu_models.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/tofu_models.py)
(`executable`, `required_plugins`, `state_configuration`), which extends
the base `InstanceBuilderModel`
([instance_builder.py](../base/src/cs_image_system/base/models/instance_builder.py)).
It adds no fields; it only sets `type` to `tofu-gce`.

The `Instance` items it reads are the base ones from
[instance.py](../base/src/cs_image_system/base/models/instance.py):
`image`, `runtime`, `storages` (each `name` + `mount_point`), `userdata`,
`image_policy` (`pinned` | `follow`), `ephemeral`, `on_failure`
(`keep` | `teardown`), `teardown_after`, `tags`. Differences from the AWS
root:

- `machine_type` on the instance is read as on AWS: the module's
  `machine_type` is the instance's own when it declares one, else the
  runtime's `default_machine_type`.
- `tags` become GCE `labels`, each key and value passed through `gce_label`
  (lowercase; anything outside `[a-z0-9_-]` becomes `-`; cut to 63
  characters). `gce_label` cannot supply a leading letter, so `validate`
  refuses a tag key whose label form does not start with a lowercase
  letter, rather than letting it reach GCE and fail at apply.
- The instance name is passed through `gce_name` (lowercase; anything
  outside `[a-z0-9-]` becomes `-`; leading and trailing `-` stripped; an
  `i-` prefix when the result does not start with a letter; cut to 63
  characters), so `gce-test` stays `gce-test` and a name such as
  `gce_data` becomes `gce-data`.

### `TofuGcpStorageBuilderModel` (`tf-gcp`)

Extends `TofuStorageBuilderModelBase` from
[tofu_models.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/tofu_models.py)
(`executable`, `required_plugins`, `state_configuration`, `variables`;
it extends the base `StorageBuilderModel`,
[storage_builder.py](../base/src/cs_image_system/base/models/storage_builder.py)).
It adds no fields; `type` is `tf-gcp`. Its `variables` field keeps the base
type `ModuleVariables`. Its `__post_init__` refuses an instance of this
exact class (`type: tf-gcp`) with `storage builder '<name>': type 'tf-gcp'
is the shared base of the GCP storage plugins and emits nothing; use
'tf-gcp-pd' ..., 'tf-gcp-filestore' ... or 'tf-gcp-gcs' ...`; the three
subclasses pass through.

### `GcpVariables`

Extends `ModuleVariables`
([module_variables.py](../base/src/cs_image_system/base/models/module_variables.py))
and adds no fields: the only declarable input is `tags`, a map of
builder-wide default **labels**. The builders emit them as `labels`, with
the storage item's own tags over the builder's, then `csis_storage=<name>`
and `csis_group_<group>=true` on top. Anything else under `variables:` is
refused; the module tunables (`size`, `disk_type`, `tier`, `capacity_gb`,
`location`) are builder fields.

### `TofuPdStorageBuilderModel` (`tf-gcp-pd`)

Persistent disk: the EBS equivalent, single-attach, POSIX. Its own keys
(the full table is in the
[configuration reference](../../docs/CONFIGURATION.md#82-storage-builders)):

- `size` (default 100): disk size in GB.
- `disk_type` (default `pd-balanced`): the GCE disk type, for example
  `pd-standard`, `pd-balanced`, `pd-ssd`.
- `variables`: a `GcpVariables`, the default labels.

### `TofuFilestoreStorageBuilderModel` (`tf-gcp-filestore`)

Filestore: the EFS equivalent, many-attach NFS, POSIX. Its own keys:

- `tier` (default `BASIC_HDD`): the Filestore tier.
- `capacity_gb` (default 1024): the capacity; the module notes 1024 GB
  as the minimum for BASIC tiers.
- `variables`: a `GcpVariables`, the default labels.

### `TofuGcsStorageBuilderModel` (`tf-gcp-gcs`)

GCS bucket: the S3 equivalent, many-attach object store, non-POSIX. Its
own keys:

- `bucket_name` (required): the bucket name used when the storage item
  declares none.
- `location` (optional): the bucket location; unset means the runtime's
  `region`.
- `variables`: a `GcpVariables`, the default labels.

### The `Storage` item the storage builders read

Base `Storage` from
[storage.py](../base/src/cs_image_system/base/models/storage.py):
`type`, `runtime`, `groups`, `public_read`, `share_mode` (`2770` | `2775`),
`state` (`active` | `archived` | `destroyed`), `bucket_name` (GCS), `tags`.
Its `tags` keys are checked at `validate` against the builder's runtime:
on a `gcloud` runtime a key whose `gce_label` form does not start with a
lowercase letter is refused, naming the storage and the key.
`lifecycle:` is **refused** on all three GCP builders: none of them realizes
a data lifecycle, so the base `validate_lifecycle` rejects any declaration.
`availability_zone` is checked by `validate` (a persistent disk is zonal,
so it joins the zone-compatibility check) and **pins the disk**:
`_disk_zone(storage)` returns it when declared and the runtime's `zone`
otherwise, and the module call, the state query's lookup and the archive
script all read it there.
`mount_point`, `source`, `ephemeral`, `generative`, `singleton`,
`is_default` and `config` are not read.

### The runtime builder the plugin reads

A `gcloud` runtime builder (`type: gcloud`, from the gcloud runtime plugin)
supplies, by attribute name: `project_id`, `region`, `zone`,
`networking.network`, `networking.subnets` (the default one becomes
`subnetwork`), `networking.network_tags`, `session_mechanism()` (`iap`
disables the public IP), `default_machine_type`, and
`self_to_gcp_client_config()` for the state query. Credentials are never
emitted: the `google` provider block carries only `project`, `region` and
`zone`, and authentication comes from the environment (application default
credentials or `GOOGLE_APPLICATION_CREDENTIALS`).

## The builder

The hook order, the file naming, the variables, the state binding and
remote-state references, the module-call rendering, the deferred
`plan -> gate -> apply` sequence, the detach and decommission whitelists,
the ephemeral sequence, the finalization hooks, the storage state
machine and the state query are the neutral roots' of hashicorp-utils;
see [The terraform roots](../hashicorp-utils/README.md#the-terraform-roots)
there for what the bases own and the full hook table. This section lists
what the GCP classes answer and what they leave at the base's default.

### `TofuGceInstanceBuilder` (phase `instance-generation`)

Source:
[tf_gce_instance_builder.py](src/cs_image_system/tf_gcp_plugin/tf_gce_instance_builder.py).
Extends `TofuInstanceBuilderBase`
([tofu_instance_builder.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/tofu_instance_builder.py)).

**The hooks it answers.** `_provider_name()` is `google` and
`_provider_source()` `hashicorp/google`; `_provider_config(rtb)` is
`google_provider_config(runtime)` (`project`, `region`, `zone`, each only
when the runtime names it), or `None` for no provider block when it
names none; `_module_dirname()` is `gce_instance`; `_module_resource()`
is `google_compute_instance`, so a replacement names
`module.instance_<label>.google_compute_instance.this`;
`_instance_word()` is `GCE instance`; `_root_header_lines()` opens the
main file with `# Terraform configuration for GCE instances generated by
...`; and `_module_args` and `_launch_args` are the two tables below.
Everything else is the base's default: `_image_var` names
`var.<label>_image`, the launch template is `user-data-<label>.sh.tftpl`,
`_root_extra_blocks` adds nothing (the root emits **no** security group
or VPC data source: network access is the runtime's firewall and the IAP
tunnel), `_attachment_address` is `None` and `_own_resources_to_let_go`
is empty.

**The root file** (the base's `generate_items_before`) is
`<B>-instance-generation.tf` beside `<B>-instance-generation.tfbackend.hcl`,
with: the `ephemeral_present` variable when any instance is ephemeral;
provider requirements from `required_plugins` or
`google`/`hashicorp/google`; a `provider "google"` block (`project`,
`region`, `zone`) aliased to the workspace name (`tofu_gce`); one
`variable "<label>_image"` (string, default `""`) per instance;
`variable "sft_enrollment_token"` (sensitive); the backend binding; a
`terraform_remote_state` reference to every storage builder that owns
storages and to every identity workspace owning an instance image's
group; then the terraform, provider, variable and remote-state blocks.

**Per instance** (the base's `generate_items_during`),
`<B>-instance-generation-instance-<label>.tf` with `module "instance_<label>"`
against `tfmodules/gce_instance`, and `user-data-<label>.sh.tftpl`. The
module arguments (`_module_args`):

| Argument | Value |
|---|---|
| `count` | `var.ephemeral_present ? 1 : 0`, only for ephemeral instances |
| `name` | `gce_name(<instance name>)` |
| `image` | the pinned build (a GCE image name) when meta-state pins the instance; else the resolved provider-specific image; else `var.<label>_image` |
| `image_family` | `gce_name(<image name>)`, only while the image is deferred: GCE resolves "latest in family" natively |
| `machine_type` | the instance's own, else the runtime's default machine type |
| `zone` | the runtime's `zone` |
| `subnetwork` | the runtime's default subnet id |
| `network_tags` | the runtime's `networking.network_tags` when any |
| `public_ip` | `false` when the runtime's session mechanism is `iap` |
| `labels` | the instance's tags through `gce_label` |
| `startup_script` | `templatefile("${path.module}/user-data-<label>.sh.tftpl", {...})` |
| `attached_disks` | `{ <storage> = { disk_self_link = <remote-state ref>.self_link, device_name = gce_name(<storage>) } }` per persistent-disk mount |

The template variables: `group_gid` by reference from the identity
workspace; `efs = {}`; `filestore` = per-storage `{ip_address, share_name}`
by reference; `sft_enrollment_token = var.sft_enrollment_token` when the
group has an enrollment trigger (the GCE root does not add the identity
plugin's token reference the AWS root adds). The launch script is the same
`user_data_template()` as on AWS: a persistent disk is mounted from
`/dev/disk/by-id/google-<device_name>`, which is why the attachment's
`device_name` and the launch parameters use the same `gce_name` rule.

**Hooks left at the base's default, and what follows.**
`_attachment_address()` is `None`: a persistent disk attachment is an
in-place attribute of `google_compute_instance`, so a detach adds an
`unmount storage` step and a `--require-unmounted` gate requirement but
no destroy whitelist entry, and a replacement whitelists no attachment.
The base's `_replacements()` names
`module.instance_<label>.google_compute_instance.this` (from
`_module_resource()`) for pending upgrades and `follow` targets.

**The base's, unchanged.** `get_commands_to_run_after`: the
generation-time `fmt`, `init` and `validate`, then the deferred gated
sequence of [OPERATIONS.md](../../docs/OPERATIONS.md#the-apply-gate),
with this root's unmount steps and `-replace` targets on the plan and
`apply-check --lifecycle instances --root <B> --root-alias <runtime>`
plus `apply` only when `config.apply_instances` allows the root. Also
the base's: the ephemeral verify-and-teardown sequence, the
decommission whitelist, `pre_finalize_phase` and `post_finalize_phase`.

Two consequences of the inheritance:

- `pre_finalize_phase` writes `instances.auto.tfvars` with `<label>_image`
  lines (the base's `_image_var` default names the GCE root's own
  variable, so a build this run baked reaches the module call). An
  image that is deferred at generation launches through `image_family`.
- `post_finalize_phase` then binds the pin from reality: the gcloud runtime
  answers `can_query_instance_boot_image()`, so an unpinned, non-ephemeral
  instance is bound to the image it actually booted, provided lineage
  records that build.

### `TofuGcpStorageBuilder` and its subclasses (phase `storage-generation`)

Source:
[tf_gcp_storage_builder.py](src/cs_image_system/tf_gcp_plugin/tf_gcp_storage_builder.py).
Extends `TofuStorageBuilderBase`
([tofu_storage_builder.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/tofu_storage_builder.py));
the storage state machine, the live/tombstone/archived split, the
`output "storage_<label>"` blocks, the gid-by-reference rule, the state
query over every declared and recorded storage and the deferred command
sequence (`apply_storage` gates the apply) are the base's.

**The hooks the base `TofuGcpStorageBuilder` answers.** `_provider_name()`
is `google`, `_provider_source()` `hashicorp/google`, and
`_provider_config(rtb)` is `google_provider_config(runtime)` (`project`,
`region`, `zone`) or `None` when the runtime names none, so the root file
(the base's `generate_items_before`) carries a `provider "google"` block
aliased to the workspace name; `_root_header_lines()` opens it with
`# Terraform configuration for GCP storages generated by ...`.
`_lookup` raises `NotImplementedError` here and each service subclass
answers it. **`_labels(storage)`**: the builder's `variables.tags` under the item's
tags, all through `gce_label`, plus `csis_storage=<name>` and
`csis_group_<group>=true` per allowed group. **`_gce_resource_name(name)`**
applies `gce_name`, because GCE resource names must match
`[a-z]([-a-z0-9]*[a-z0-9])?`.

| | `TofuPdStorageBuilder` (`tf-gcp-pd`) | `TofuFilestoreStorageBuilder` (`tf-gcp-filestore`) | `TofuGcsStorageBuilder` (`tf-gcp-gcs`) |
|---|---|---|---|
| Module | [gcp_storage_pd](../../tfmodules/gcp_storage_pd/variables.tf) | [gcp_storage_filestore](../../tfmodules/gcp_storage_filestore/variables.tf) | [gcp_storage_gcs](../../tfmodules/gcp_storage_gcs/variables.tf) |
| Capability type (what a base image declares in `storage_types`) | `pd` | `filestore` | `gcs` |
| Attachment cardinality | single | many | many |
| POSIX | yes | yes | no |
| Supports `archived` | yes: `gcloud compute disks snapshot` to `csis-<gce name>-archive`, then the disk is destroyed; a restore creates the disk from the snapshot and deletes it after the apply | no | no |
| `lifecycle:` | refused | refused | refused |
| `destroyed` transition action | delete the archive snapshot when the disk was archived | none | `wipe-<label>.sh`: `gcloud storage rm --recursive gs://<bucket>/**`, treating "matched no objects" as success |
| Base-image prerequisites | none (a comment) | `nfs-common` (Debian family) or `nfs-utils`; verify: `mount.nfs`/`mount.nfs4` present | the gcloud CLI from the official installer; verify: `gcloud` present |
| State query | `compute_v1.DisksClient.get` by disk name (or `SnapshotsClient.get` on the archive when recorded archived); `NotFound` means absent | `gcloud filestore instances describe <name> --location <zone>` through the runtime's declared gcloud; not found means absent, any other failure is "unavailable" | `gcloud storage buckets describe gs://<bucket> --format=json`; "not found" means absent, any other failure is "unavailable" |

Module arguments (`module_args(storage)`):

| Builder | Arguments |
|---|---|
| PD | `name = gce_name(<storage>)`; `size` and `disk_type` from the builder; `labels`; `zone` from the storage's own `availability_zone`, else the runtime's; `snapshot = csis-<gce name>-archive` when the storage is recorded archived and declared active (restore) |
| Filestore | `name = gce_name(<storage>)`; `tier` and `capacity_gb` from the builder; `labels`; `zone`; `network` from the runtime's `networking.network` unless it is `default`; `group_subtrees` = sorted allowed groups (Filestore has no access points, so the per-group subtree is created and `chgrp`ed at first mount by the launch script; the module records the intent); `public_read = true` when set |
| GCS | `bucket_name` = the storage's `bucket_name`, else the builder's, else the storage name; `labels`; `location` = the builder's `location`, else the runtime's `region`; `group_prefixes` = sorted allowed groups; `public_read = true` when set |

The GCP builders read no `variables` other than `tags`, so no module
tunable comes from `variables:`; unset arguments are absent and the module
default applies.

## Emission

From the frozen golden emission over the test fixture (the fixture declares
`gcp-pd` and `gcp-gcs` builders and no Filestore, so there is no Filestore
root in the golden).

GCE instance root (`tofu-gce`), under
[generated/instance-image/tofu-gce/instance-generation/](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/):

| File | Content |
|---|---|
| [tofu-gce-instance-generation.tf](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation.tf) | `terraform {}` with `google` from `hashicorp/google` and `backend "s3" {}`; `provider "google"` (`project = "csis-sandbox"`, `region = "us-east1"`, `zone = "us-east1-b"`, alias `tofu_gce`); `variable "gce_test_image"`, `variable "sft_enrollment_token"`; `data "terraform_remote_state"` for `aws_efs`, `aws_ebs`, `aws_s3`, `gcp_pd`, `gcp_gcs`, `oktagroups` |
| [tofu-gce-instance-generation-instance-gce_test.tf](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation-instance-gce_test.tf) | `module "instance_gce_test"` calling `../../../../../tfmodules/gce_instance` with `name = "gce-test"`, `image = var.gce_test_image`, `image_family = "imgfile-basic-dask"`, `machine_type = "e2-micro"`, `zone`, `subnetwork`, `public_ip = false`, `startup_script = templatefile(...)`, and `attached_disks` for `gce_data` with `device_name = "gce-data"` |
| [user-data-gce_test.sh.tftpl](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/user-data-gce_test.sh.tftpl) | the launch script: the `gce_data` mount at `/mnt/gce-data` from `/dev/disk/by-id/google-gce-data`, the `coops` subtree |
| [tofu-gce-instance-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/instance-image/tofu-gce/instance-generation/tofu-gce-instance-generation.tfbackend.hcl) | the S3 partial backend configuration with `key = "statefiles/csia-image-system-test/tofu_gce.tfstate"` |
| [run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh) | the `tofu-gce/instance-generation` block: `rm -f tfplan`, `init -input=false -reconfigure -backend-config=...`, `plan`, `gate-plan` |

GCP storage roots, under
[generated/storage/](../../tests/fixtures/v2_golden/generated/storage/):

| File | Content |
|---|---|
| [gcp-pd/storage-generation/gcp-pd-storage-generation.tf](../../tests/fixtures/v2_golden/generated/storage/gcp-pd/storage-generation/gcp-pd-storage-generation.tf) | terraform block, `provider "google"` alias `gcp_pd`, remote state of `oktagroups` |
| [gcp-pd/storage-generation/gcp-pd-storage-generation-storage-gce_data.tf](../../tests/fixtures/v2_golden/generated/storage/gcp-pd/storage-generation/gcp-pd-storage-generation-storage-gce_data.tf) | `module "storage_gce_data"` against `tfmodules/gcp_storage_pd`: `name = "gce-data"`, `size = 30`, `disk_type = "pd-standard"`, `labels = { csis_group_coops = "true", csis_storage = "gce_data" }`, `zone`; `output "storage_gce_data"` |
| [gcp-gcs/storage-generation/gcp-gcs-storage-generation-storage-gce_bucket.tf](../../tests/fixtures/v2_golden/generated/storage/gcp-gcs/storage-generation/gcp-gcs-storage-generation-storage-gce_bucket.tf) | `module "storage_gce_bucket"` against `tfmodules/gcp_storage_gcs`: `bucket_name`, `labels = { csis_storage = "gce_bucket" }`, `location = "us-east1"`; `output "storage_gce_bucket"` |
| [gcp-pd-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/gcp-pd/storage-generation/gcp-pd-storage-generation.tfbackend.hcl), [gcp-gcs-storage-generation.tfbackend.hcl](../../tests/fixtures/v2_golden/generated/storage/gcp-gcs/storage-generation/gcp-gcs-storage-generation.tfbackend.hcl) | the partial backend configurations |
| [run-storage.sh](../../tests/fixtures/v2_golden/generated/storage/run-storage.sh) | the deferred sequence per root |

The read-models record the GCP items with their plugin and capability type:
[meta-state/storage.yaml](../../tests/fixtures/v2_golden/meta-state/storage.yaml)
(`gce_data`: builder `gcp-pd`, plugin `tf-gcp-pd`, type `pd`, cardinality
`single`, attached by `gce-test`) and
[meta-state/launch-params.yaml](../../tests/fixtures/v2_golden/meta-state/launch-params.yaml)
(`gce-test`: session `iap`, mount device `/dev/disk/by-id/google-gce-data`).

Modules called: [tfmodules/gce_instance](../../tfmodules/gce_instance/main.tf),
[tfmodules/gcp_storage_pd](../../tfmodules/gcp_storage_pd/main.tf),
[tfmodules/gcp_storage_filestore](../../tfmodules/gcp_storage_filestore/main.tf),
[tfmodules/gcp_storage_gcs](../../tfmodules/gcp_storage_gcs/main.tf).

## Example configuration

From the test fixture. The instance builder,
[cfg/instance-builders.yml](../../tests/fixtures/config/cfg/instance-builders.yml):

```yaml
instance_builders:
  - name: tofu-gce
    type: tofu-gce
    runtime: gcloud-east1
    executable: open-tofu-1
    state_configuration: s3-east2
```

The storage builders,
[cfg/storage-builders.yml](../../tests/fixtures/config/cfg/storage-builders.yml):

```yaml
storage_builders:
  - name: gcp-pd
    type: tf-gcp-pd
    executable: open-tofu-1
    runtime: gcloud-east1
    size: 30
    disk_type: pd-standard
  - name: gcp-gcs
    type: tf-gcp-gcs
    executable: open-tofu-1
    runtime: gcloud-east1
    bucket_name: csis-sandbox-86233086783-default-bucket
```

The runtime they name, from
[cfg/runtime-builders.yml](../../tests/fixtures/config/cfg/runtime-builders.yml)
(the fields this plugin reads):

```yaml
runtime_builders:
    - name: gcloud-east1
      aliases:
        - gcp
        - google
        - us-east1
      type: gcloud
      project_id: csis-sandbox
      zone: us-east1-b
      session_mechanism: iap
      region: us-east1
      default_machine_type: e2-micro
      networking:
        network: default
        subnets:
        - name: subnet1
          subnet_id: projects/csis-sandbox/regions/us-east1/subnetworks/default
          is_default: true
          public: true
```

The storages, [storages/gce.yaml](../../tests/fixtures/config/storages/gce.yaml):

```yaml
storages:
- name: gce_data
  type: gcp-pd
  mount_point: /mnt/gce-data
  groups:
  - coops
  state: active
- name: gce_bucket
  type: gcp-gcs
  bucket_name: csis-sandbox-86233086783-default-bucket
```

The instance, from
[instances/instances.yaml](../../tests/fixtures/config/instances/instances.yaml):

```yaml
instances:
  - name: gce-test
    image: imgfile-basic-dask
    runtime: gcloud-east1
    type: tofu-gce
    description: First GCE instance (GCP readiness); free-tier e2-micro
    storages:
      - name: gce_data
        mount_point: /mnt/gce-data
```

An overlay that declares the same instance for one invocation and lets only
the GCE root apply,
[overlays/gce-cycle-launch.yaml](../../tests/fixtures/config/overlays/gce-cycle-launch.yaml):

```yaml
config:
  apply_instances: [gcloud-east1]
instances:
  - name: gce-test
    image: imgfile-basic-dask
    runtime: gcloud-east1
    type: tofu-gce
    description: "GCE change-cycle instance (free-tier e2-micro); exists only for the cycle"
    storages:
      - name: gce_data
        mount_point: /mnt/gce-data
```

Adding `ephemeral: true` to such an instance makes the root launch it,
verify it and tear it down in the same run. The companion overlays
[gce-cycle-decommission.yaml](../../tests/fixtures/config/overlays/gce-cycle-decommission.yaml)
(`undeclare: true`, a gated destroy) and
[gce-cycle-storage-teardown.yaml](../../tests/fixtures/config/overlays/gce-cycle-storage-teardown.yaml)
(`state: destroyed` for both storages, with `apply_storage: [gcloud-east1]`)
drive the rest of a change cycle.

## Prerequisites and integration

Everything a terraform root needs applies here unchanged (the `tofu`
executable, the state backend, the identity workspace, the `tfmodules/`
directory beside the configuration root, the system's own CLI on `PATH`
at execution time); see
[hashicorp-utils](../hashicorp-utils/README.md#prerequisites-and-integration),
whose roots these builders subclass. This section lists what the GCP
classes need on top of that, and how each is found.

**Python packages.** From [pyproject.toml](pyproject.toml):
`cs-image-system-contract` and `cs-image-system-base` (the contract and
the core's base classes, as for every built-in plugin),
`cs-image-system-hashicorp-utils` (the provider-neutral instance and
storage roots and their models, which every class here subclasses; the
`TofuVersionChecker` this plugin registers; the collector that renders
the terraform, provider, variable, backend and remote-state blocks),
`cs-image-system-gcloud-runtime-plugin` (the runtime model, `gce_name`,
`gce_label`, `resolve_project`, `make_credentials`),
`google-cloud-compute>=1.49` and `pydantic>=2.13`. The package does not
depend on `cs-image-system-tf-ebs-instance-plugin` or on
`cs-image-system-aws-runtime-plugin`: installing it installs no AWS
package and no `boto3`, which the neutral-root test
([tests/test_v2_stage_120_neutral_root.py](../../tests/test_v2_stage_120_neutral_root.py))
proves by syncing an environment for this plugin and the container one
alone. The compute client is imported lazily, inside
`TofuPdStorageBuilder._lookup`, so it is needed only by `state query`
and by the runs that perform one; generation never imports it.

**A `gcloud` runtime builder.** Found by the builder entry's `runtime:`
(a runtime builder name or alias; the fixture's `gcloud-east1`). It must
be `type: gcloud`
([gcp_runtime_models.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)),
because the plugin reads it by attribute name and a runtime of another
type simply lacks the attributes: `project_id`, `zone`, `region`,
`networking`, `session_mechanism`, `default_machine_type`,
`self_to_gcp_client_config()`. What each feeds is in the runtime table
under [Configuration reference](#configuration-reference). Nothing checks
that the runtime is a GCP one: with an AWS runtime named by mistake the
`google` provider block is emitted with no `project`, `region` or `zone`,
the module calls carry no `zone`, and the failure arrives from `tofu
plan` (a missing required argument) rather than from the system. The one
place the plugin itself notices is a pd archive, unarchive or
restore: its script needs a project, which an AWS runtime cannot supply,
so the storage is refused at generation (see
[When it fails](#when-it-fails)). The label-key check at `validate` also
asks the runtime, and an AWS runtime answers that any key is fine.

**A GCP project.** Named by the runtime's `project_id`. The plugin creates
compute instances, persistent disks and disk snapshots, reads images by
family, creates Filestore instances and Cloud Storage buckets and deletes
objects in them, so the project needs the Compute Engine, Filestore and
Cloud Storage APIs enabled and the identity below needs the matching
permissions. The plugin enables no API and grants no IAM; the system
generates no IAM changes anywhere (OPERATIONS, "IAP sessions on GCE").

**Credentials: Application Default Credentials, nothing else.** The
plugin emits no credential: the `provider "google"` block carries only
`project`, `region` and `zone`
(`google_provider_config()` in
[tf_gcp_storage_builder.py](src/cs_image_system/tf_gcp_plugin/tf_gcp_storage_builder.py)),
the transition scripts call `gcloud` with `--project` and `--zone` only,
and the pd state query builds a `DisksClient` with no explicit
credentials. All three therefore read ADC from the environment:
`GOOGLE_APPLICATION_CREDENTIALS` when set, else
`~/.config/gcloud/application_default_credentials.json`. The live form is
an impersonated login, `gcloud auth application-default login
--impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com`
([OPERATIONS.md](../../docs/OPERATIONS.md), "What each step needs").
`make_credentials()` does have a branch that reads
`credentials.service_account_key_file` from the runtime, but the `gcloud`
runtime's `credentials:` is the empty base
([credentials.py](../base/src/cs_image_system/base/models/credentials.py)):
any key under it is refused at load, so from a loaded configuration that
branch never runs. `preflight`, `state query` and every run report
whether ADC exists as a `session:` line; they never read the value.

**An AWS session as well, when the state is in S3.** The root's state
location is `state_configuration` on the builder, else the runtime's,
else the default backend. The fixture and the live tree keep
the GCE roots on the S3 backend, so every `tofu init`, `plan`, `apply`
and every `terraform_remote_state` read of a GCE root needs a live AWS
session, and a session that lapses mid-run stops GCE work with GCP fully
authenticated. Read the session's expiry before a long run.

**Tools on the machine that runs the scripts.**

| Tool | Found how | Used for |
|---|---|---|
| `tofu` (or terraform) | the builder's `executable:` names an entry in `cfg/executables.yml`; its `binary` is the path the runner calls and its `version:` is checked by `TofuVersionChecker` (`tofu --version -json`) at `validate` and at every run | `fmt`, `init`, `validate` at generation; `plan`, `apply` deferred |
| `gcloud` | the `binary` of the `cfg/executables.yml` entry the storage builder's RUNTIME names in its `executable` (default `gcloud`): the generated `archive-*.sh`, `unarchive-*.sh`, `restore-*.sh` and `wipe-*.sh` embed that path (shell-quoted), and `TofuGcsStorageBuilder._lookup` runs it for `gcloud storage buckets describe`; none of them calls a bare `gcloud` from `PATH`. The ON-IMAGE `gcloud` the gcs prerequisites install is the VM's own and stays a bare name | pd archive, restore and archive deletion; the GCS wipe; the GCS state query |
| `bash` | the scripts run as `bash <script>` from the root's directory | the transition scripts |
| the `hashicorp/google` provider | fetched by `tofu init` from the registry, or from `TF_PLUGIN_CACHE_DIR` when the Justfile exports it | every root |

**Network and access.** Under `session_mechanism: iap` the instance gets
no external address, so IAP is the only way in: the firewall rule for
`tcp:22` from `35.235.240.0/20` and `roles/iap.tunnelResourceAccessor`
for the operator's own Google user are operator wiring, listed in
[OPERATIONS.md](../../docs/OPERATIONS.md) under "IAP sessions on GCE".
The plugin depends on that wiring twice: the detach sequence's `unmount
storage` step runs on the instance through the runtime's session, and an
ephemeral instance's `verify instance` reads the serial console (no
session needed) but the post-bake tests run over the session. A
Filestore instance is reachable only from the network the module was
given (`networking.network`, or the project's `default`), which must be
the network the instance's `subnetwork` belongs to.

**What the roots consume from other workspaces.** Each storage root reads
`group_gids` from the identity workspace of every group it allows, and
the instance root reads `storage_<label>` outputs (`self_link` for a
disk, `ip_address` and `share_name` for a Filestore share) from every
storage builder that owns storages, plus `group_gids` for the image's
owning group. These are `terraform_remote_state` data sources, so the
producer must have applied before the consumer plans: identity, then
storage, then instances, which is the meta-workflow order.

**What the image must carry.** The launch script runs `mkfs -t xfs`,
`blkid`, `mount`, `mkdir`, `chgrp` and `chmod` for a persistent disk and
`mount` with type `nfs` for a Filestore share; the `filestore` capability
bakes `nfs-utils` (or `nfs-common` on the Debian family) and verifies
`mount.nfs`/`mount.nfs4`, the `gcs` capability installs the gcloud CLI
and verifies `gcloud`, and `pd` bakes nothing. A base image declares them
under `storage_types`; an instance may attach only storages whose type
its base image declared (the core's rule, checked at `validate`).

## Configuration reference

Every field below is read from YAML by this package's code or by the base
classes it inherits; a field marked "accepted, not read" is part of the
model (so it loads and is validated) but nothing in this package or its
bases consumes it. Unknown keys are refused at load on every model
(`extra="forbid"`), and a `parameters:` key on a builder is refused with a
message naming `variables:`.

### Builder entries (`cfg/instance-builders.yml`, `cfg/storage-builders.yml`)

Fields common to all five service names:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | the terraform workspace name, the directory under `generated/`, the provider alias (`super_safe_name`d) and the state key |
| `type` | str | required | a service name of this package (`tofu-gce`, `tf-gcp`, `tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs`) |
| `aliases` | list[str] | `[]` | extra names an item's `type:` may use (read by the core) |
| `is_default` | bool | `false` | the builder an item's `type: default` resolves to (read by the core) |
| `runtime` | str | `default` | the `gcloud` runtime builder, by name or alias; the provider block, the zone, the network, the machine type and the IAP decision all come from it |
| `executable` | str or null | `"tofu"` | an entry of `cfg/executables.yml` |
| `required_plugins` | list | `[]` | terraform providers for `required_providers`; entries `{name, version, source, config}` where `name` and `version` are required by the model ([plugin_config.py](../base/src/cs_image_system/base/helpers/plugin_config.py)) and `config` is accepted, not read. Empty means one `google` provider from `hashicorp/google` with no version constraint. The `provider "google"` block is emitted whatever this lists |
| `state_configuration` | str (foreign key to a state backend) | `default` | the root's state location; `default` inherits the runtime's, else the default backend |
| `description`, `config`, `gitignore`, `tags` | | | accepted, not read by this package |

`tofu-gce` and `tf-gcp` add no fields. `tf-gcp` cannot emit (abstract
`module_dirname`/`module_args`), so a builder entry of that type is refused
at load rather than failing at generation with `NotImplementedError`.

`tf-gcp-pd`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `size` | int | `100` | disk size in GB, passed as the module's `size` |
| `disk_type` | str | `"pd-balanced"` | passed as `disk_type` (`pd-standard`, `pd-balanced`, `pd-ssd`, ...) |
| `variables` | `GcpVariables` | `{}` | see below |

`tf-gcp-filestore`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `tier` | str | `"BASIC_HDD"` | passed as `tier` |
| `capacity_gb` | int | `1024` | passed as `capacity_gb`; the module notes 1024 GB as the BASIC-tier minimum, and the plugin does not check it |
| `variables` | `GcpVariables` | `{}` | see below |

`tf-gcp-gcs`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `bucket_name` | str | required | the bucket for every storage of this builder that declares no `bucket_name` of its own. Two such storages on one builder would name the same bucket twice; give each its own |
| `location` | str or null | `null` | the bucket location; null means the runtime's `region` (the module's own default of `US` is never reached, because the runtime's `region` is a required field) |
| `variables` | `GcpVariables` | `{}` | see below |

`variables:` (`GcpVariables`, one field):

| Field | Type | Default | Meaning |
|---|---|---|---|
| `tags` | map[str, str] | `{}` | builder-wide default labels, under the storage item's `tags`, under the `csis_*` labels; every key and value through `gce_label`. Unlike an item's `tags`, these keys are not checked by `validate`'s label-key check, so a key that does not start with a letter still fails at apply |

The AWS `variables` keys (`volume_type`, `encrypted`, `performance_mode`,
`force_destroy`) are not accepted here: a GCP builder that declares one
fails at load.

### The instance item (`instances/*.yaml`, `type: tofu-gce`)

| Field | Read by | Effect on the GCE root |
|---|---|---|
| `name` | the plugin | `gce_name(name)` is the instance's GCE name; `super_safe_name(name)` is the label in `module "instance_<label>"`, the file names and `var.<label>_image` |
| `image` | the plugin | the provider-specific image on the builder's runtime (`image` when resolved, else `var.<label>_image` with `image_family = gce_name(image)`), and the image's `group` (the identity workspace, `group_gid`) |
| `storages[].name`, `storages[].mount_point` | the core's `compute_launch_params`, then the plugin | `attached_disks` for `pd` mounts, `filestore` template variables for Filestore mounts; the launch script's mount lines |
| `ephemeral` | the plugin | `count = var.ephemeral_present ? 1 : 0` on the module call and the verify-and-teardown sequence |
| `image_policy` (`pinned`, `follow`) | the core's lineage, then `_replacements()` | `follow` puts `-replace=module.instance_<label>.google_compute_instance.this` on the plan when the series head moved |
| `tags` | the plugin; `validate`'s `check_label_keys` | `labels`, each key and value through `gce_label`; a key whose label form does not start with a lowercase letter (`2024`) is refused at `validate` |
| `userdata` | the core | extra lines in the launch script |
| `on_failure`, `teardown_after` | the base's ephemeral sequence | `--record-only` on the verify, and a teardown without re-verifying |
| `runtime` | the core | the session mechanism recorded in the launch parameters; the root's provider comes from the builder's runtime, not the instance's |
| `availability_zone` | the core's `validate` only | zone compatibility; the module call takes the runtime's `zone` regardless |
| `machine_type` | | the module's `machine_type`; unset, the runtime's `default_machine_type` |

### The storage item (`storages/*.yaml`, `type:` a GCP storage builder)

| Field | Read by | Effect |
|---|---|---|
| `name` | the plugin | `gce_name(name)` is the disk or Filestore instance name and the pd `device_name`; `super_safe_name(name)` is the module label and output name; `gce_label(name)` is the `csis_storage` label |
| `groups` | the plugin | one `csis_group_<group>=true` label each; Filestore `group_subtrees`, GCS `group_prefixes` (sorted); the remote-state reference to each group's identity workspace |
| `public_read` | the plugin | `public_read = true` on Filestore and GCS; nothing on pd |
| `share_mode` | the core's launch script | the mode of the per-group subtree created at first mount |
| `state` | the base | `active` emits the module call; `archived` (pd only) emits nothing and snapshots; `destroyed` emits a tombstone comment and whitelists the destroy |
| `bucket_name` | the plugin (GCS) | the bucket, over the builder's `bucket_name` |
| `tags` | the plugin; `validate`'s `check_label_keys` | labels, over the builder's `variables.tags`; a key whose `gce_label` form does not start with a lowercase letter is refused at `validate` against the builder's runtime |
| `lifecycle` | the base's `validate_lifecycle` | refused when set, on all three builders |
| `availability_zone` | the core's `validate`; the pd builder's `_disk_zone` | pd is zonal, so it takes part in the compatibility check, and a declared value is the disk's zone in the module call, the lookup and the archive script |
| `mount_point` | the instance side | not read by the storage builders |
| `runtime` | the core | must resolve; the storage root's runtime is the builder's |
| `source`, `ephemeral`, `generative`, `singleton`, `is_default`, `config` | | accepted, not read |

### The runtime builder (`cfg/runtime-builders.yml`, `type: gcloud`)

| Field | Where it lands |
|---|---|
| `project_id` | `provider "google" { project }` on every root; `--project` of the pd scripts, which are refused at generation when it is missing, so no script carries a literal `None`; the pd state query's project (`self_to_gcp_client_config()` then `resolve_project()`) |
| `region` | `provider "google" { region }`; the GCS `location` when the builder declares none |
| `zone` | `provider "google" { zone }`; `zone` of the instance and Filestore module calls; the pd's `zone`, `--zone` of its archive script and its state query's zone when the storage declares no `availability_zone` (with neither, archiving a pd is refused at generation) |
| `networking.subnets[]` (the `is_default: true` one) | `subnetwork` of the instance module call |
| `networking.network` | Filestore `network`, unless it is `default`, `none`, empty, null or `self` (`OOPS_DEFAULTS`), in which case the module's own default `default` applies. Not read by the instance root |
| `networking.network_tags` | `network_tags` of the instance module call, when any |
| `session_mechanism` | `public_ip = false` when `iap`; any other non-empty value raises `ValueError` from the runtime plugin at generation |
| `default_machine_type` | `machine_type` of the instance module call |
| `state_configuration` | the root's state location when the builder's is `default` |
| `credentials` | must stay empty (the runtime's rule); never emitted |

### Execution knobs read through the base

`config.apply_storage` and `config.apply_instances` in `cfg/_config.yml`
or an overlay (`true`, or a list naming the builder or its runtime)
decide whether a root's deferred sequence ends in `apply-check` and
`apply`; `config.use_state_backends` decides whether backend and
remote-state blocks are emitted at all; `--only-runtime <rt>` (explicit,
or implied by `--apply-runtime`) decides whether another runtime's root
emits anything; `--dry-run` (the default) decides whether the deferred
sequence runs. Meta-state read: `storage-state.yaml` (a storage recorded
`archived` and declared `active` is a restore), the instance pins and
launch records (the pinned build; the decommission whitelist) and the
pending replacements. All of these are the core's, documented in
[CONFIGURATION.md](../../docs/CONFIGURATION.md) and
[OPERATIONS.md](../../docs/OPERATIONS.md).

### Variations

- **Pinned, resolved or deferred image.** When meta-state pins the
  instance (or the pin's `follow` target), `image` is that build's GCE
  image name and no `image_family` is emitted. Else, when the image's
  provider-specific image is already resolved on the runtime, `image` is
  its identifier. Else (the image is baked later in this run, or by
  another run) `image = var.<label>_image` with `image_family =
  gce_name(<image>)`, and the module's `data "google_compute_image"`
  resolves the family's latest at plan time. With no provider-specific
  image at all the module call carries neither, a warning is logged, and
  the plan fails.
- **`image_policy: follow` or a pending upgrade** adds
  `-replace=module.instance_<label>.google_compute_instance.this` to the
  plan; `pinned` (the default) never replaces. Unlike AWS, no attachment
  address joins the replacement whitelist: the disk attachment is an
  attribute of the instance.
- **Ephemeral vs durable.** An ephemeral instance's module call is
  counted on `var.ephemeral_present`; when the root may apply, the
  sequence continues with `verify instance <name>` (`--record-only` under
  `on_failure: teardown`), a second plan with
  `-var=ephemeral_present=false`, gate, apply-check, apply. A durable
  instance stands, and after a real apply `post_finalize_phase` binds its
  pin. Ephemeral instances are never pin-bound.
- **Pin binding after apply.** A durable instance whose image resolved
  this run binds to that build; one launched from a family lookup binds
  to the image the GCE runtime reports its boot disk was created from,
  provided lineage records it (else a warning, pin left unbound).
- **`session_mechanism: iap` vs none.** `iap` sets `public_ip = false`;
  unset leaves the module default (`true`, an external address). Only
  `iap` is a legal non-empty value.
- **Network `default` vs named.** Filestore gets `network = <name>` only
  for a concrete name; the instance root never emits a network, only the
  default subnet's `subnetwork`.
- **`network_tags` declared or not.** Emitted only when the list is
  non-empty; the instance then wears them and the runtime warns at load
  about a tag no firewall rule targets.
- **`required_plugins` declared or not.** Declared: those providers, with
  their `version` constraints, in `required_providers`. Not declared: one
  unconstrained `google`. The `provider "google"` block is the same either
  way.
- **State location.** The builder's own `state_configuration`, else the
  runtime's, else the default backend; a GCE root on the S3 backend needs
  AWS credentials, one on `local` or `gcs` does not.
- **Storage state.** `active`: a module call and an `output`. `archived`
  (pd only): no module call; when the record says `active`, an
  `archive-<disk>.sh` snapshot runs before the whitelisted destroy.
  `active` again after `archived` (restore): the module call carries
  `snapshot = csis-<disk>-archive`, and `restore-<disk>.sh` deletes the
  snapshot after the apply. `destroyed`: a tombstone comment; pd from
  `archived` runs `unarchive-<disk>.sh` (snapshot deletion, "was not
  found" tolerated) with no destroy to whitelist; GCS runs
  `wipe-<label>.sh` then whitelists `module.storage_<label>`; Filestore
  only whitelists. A storage that left the YAML but is still recorded
  (undeclared) is treated as `destroyed` from its recorded state, with
  the record's `bucket_name` for the wipe. The three pd scripts are
  refused at generation when their project (and, for the archive, the
  disk's zone) cannot be resolved, so no script is written with a literal
  `None` that fails only when gcloud runs it.
- **Groups declared or not.** With groups: `csis_group_<g>` labels, the
  Filestore `group_subtrees` / GCS `group_prefixes` list, a remote-state
  reference to each group's identity workspace, and the launch script's
  `mkdir`/`chgrp`/`chmod` of `<mount>/<group>` on pd and Filestore mounts.
  Without: none of these; a group-gated attach is refused by the core's
  strict attach rule.
- **`public_read`** adds `public_read = true` on Filestore and GCS; pd
  ignores it.
- **`bucket_name` on the item vs the builder.** The item's wins; the
  builder's is the fallback; the storage name is a last resort the
  required builder field makes unreachable for declared storages.
- **`location` vs `region`.** The builder's `location` wins; else the
  runtime's `region`.
- **Labels.** The item's `tags` over the builder's `variables.tags`, then
  `csis_storage` and `csis_group_*` on top; every key and value through
  `gce_label` (lowercase, `[a-z0-9_-]`, 63 characters). Instance labels
  are the instance's `tags` alone. A key on an instance or storage item
  whose label form starts with a lowercase letter is emitted; one that
  does not (`2024`, `-env`) is refused by `validate` with the item's name
  and the key, so GCE never refuses it at apply. The builder's
  `variables.tags` keys are not checked.
- **Names.** Every GCE resource name and the pd `device_name` go through
  `gce_name`; the terraform labels (`instance_<label>`,
  `storage_<label>`, `<label>_image`, the file names) go through
  `super_safe_name`, which keeps underscores. `gce_data` is therefore
  `gce-data` on GCE and `gce_data` in terraform.
- **Detach.** A mount removed from a launched instance's declaration adds
  an `unmount storage` step before the plan and `--require-unmounted
  <instance>:<storage>` to the gate, and whitelists nothing: the
  attachment is in-place.
- **Decommission.** An instance recorded launched but no longer declared
  keeps its root emitted (terraform, provider, backend, remote state only
  when it was the last) and puts `module.instance_<label>` on the destroy
  whitelist, scoped to the runtime its pinned build was baked on.
- **`--only-runtime` / `--apply-runtime` another runtime.** The GCE roots
  emit nothing and run nothing (their old files are not regenerated).
- **Dry run vs real run.** Generation, the transition scripts written
  beside the root and the runner scripts are identical; the deferred
  sequence is only enumerated under `--dry-run`, and the
  `pre_finalize_phase`/`post_finalize_phase` hooks run only in-process
  under `--no-dry-run`.
- **Apply flag on vs off.** Off: the deferred sequence of
  [OPERATIONS.md](../../docs/OPERATIONS.md#the-apply-gate) ends at
  `gate-plan`, after this root's unmount steps and `-replace` targets.
  On: `apply-check --lifecycle <storage or instances> --root <B>
  --root-alias <runtime>` and `apply` follow; the ephemeral sequence, the
  pd post-restore script and the pin binding exist only with it on.
- **Encrypted vs clear values.** The plugin makes no distinction: it
  passes the values it reads through `str()` into the collector and
  neither recognises nor opens an `ENC[age:...]` marker. How a marker
  travels from the tree to the executing root is the core's rule
  ([OPERATIONS.md](../../docs/OPERATIONS.md), "Encrypted values").

## What it tests and verifies

**At load (pydantic).** The models refuse unknown keys, a `parameters:`
key, a non-integer `size`/`capacity_gb`, a missing GCS `bucket_name`, a
`variables:` key other than `tags` and a `credentials:` key on the
`gcloud` runtime. Verdict: a validation error naming the field path; the
configuration does not load, so `validate` and `run` exit 1 and
`preflight` reports the load failure. The plugin adds no validator of its
own; these are the base models' rules
([model_config.py](../base/src/cs_image_system/base/models/model_config.py),
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py)).

**At `validate` (the core, through this plugin's hooks).**
[v2_validation.py](../base/src/cs_image_system/base/v2_validation.py),
[storage_state.py](../base/src/cs_image_system/base/storage_state.py) and
[validate.py](../base/src/cs_image_system/base/commands/validate.py) ask
the builders:

| Hook | Answer | What is refused |
|---|---|---|
| `validate_lifecycle` | the base's: any `lifecycle:` is an error | `storage '<n>' (<type>) declares a data lifecycle, which its builder does not realize (no lifecycle on pd storages)` |
| `attachment_cardinality` | `single` (pd), `many` (Filestore, GCS) | two instances attaching one pd: `storage '<n>' (<type>) is single-attach but instances [...] all attach it (N16); multi-host storage builders on <rt>: [...]` |
| `supports_archive` | `true` (pd), `false` (Filestore, GCS) | `state: archived` on Filestore or GCS: `... requests archived, which its builder does not realize (snapshot + restore)` |
| `is_zonal` | `true` (pd), `false` (Filestore, GCS) | a pd whose `availability_zone` differs from its instance's or its runtime's subnet's |
| `capability_type` | `pd`, `filestore`, `gcs` | a base image `storage_types` entry with no builder of that type; an instance attaching a type its base image did not declare |
| `label_key_problem` (the gcloud RUNTIME's hook, asked by `check_label_keys`) | a reason when `gce_label(key)` does not start with a lowercase letter, else `None` | a tag key on an instance (its runtime) or a storage (its builder's runtime) that GCE cannot take as a label key: `<instance\|storage> '<name>': tag key '<key>' on runtime <rt>: GCE label keys must start with a lowercase letter; '<key>' becomes '<label>'; rename the key`. Refused here so that it does not fail at apply |
| the state machine (base) | | an illegal transition, a new storage not starting `active`, an `archived`/`destroyed` request while attached, attaching a non-active storage, an undeclared storage whose record names no builder |

Verdict: `validate` exits 1 listing every error; `run` exits 1 before
generation. The tool check of the `executable:` entry (`tofu --version
-json` against the entry's `version:`) also runs here and at every run.

**At generation.** Each root's generation-time commands are `tofu fmt`,
`tofu init` (with the backend configuration) and `tofu validate` in the
generated directory; a failing one fails the run (exit 1) with tofu's
message. The plugin itself checks little: an instance with no
provider-specific image logs `No provider-specific image for image ... the
module call will not resolve an image` and goes on; a runtime whose
`session_mechanism` is neither empty nor `iap` raises `ValueError` from
the runtime plugin. A missing `project_id` or `zone` is, in general, not
detected: the provider block omits the field and the module calls omit
`zone`, so the verdict is tofu's at plan time. The exception is the
persistent-disk transition scripts: `_require_script_inputs` runs for
exactly the three transitions that write a script and refuses the storage
when an input the script needs cannot be resolved. `archive-<disk>.sh`
(active to archived) needs the project and the disk's zone (the storage's
`availability_zone`, else the runtime's `zone`); `unarchive-<disk>.sh`
(archived to destroyed) and `restore-<disk>.sh` (archived to active) need
the project. The refusal is a `ValueError` that ends the run (exit 1):

```text
storage '<name>' on builder <b>: the archive scripts need <project and zone|project>, and the runtime declares none (set `project_id` and `zone` on the GCP runtime)
```

Without the check a script would carry the literal `None` in
`--project`/`--zone` and fail only when gcloud ran it. Every other
transition (and every storage that is not a pd) writes no script and is
not checked.

**Deferred, before apply.** `gate-plan` (exit 3) admits only the destroys
this plugin whitelisted: `module.storage_<label>` for a declared or
undeclared storage moving to `destroyed` (not for an archived pd, whose
disk is already gone), `module.instance_<label>` for a decommissioned or
ephemeral instance, and the `-replace` of an upgraded or `follow`
instance; and with `--require-unmounted <instance>:<storage>` it refuses
a detach without a successful unmount receipt. `apply-check` (exit 3)
re-reads the apply flag at execution time. Both are the core's commands;
what the plugin contributes is the whitelist and the requirement.

**After apply.** An ephemeral instance's `verify instance` (the GCE
runtime: the serial console until "Finished running startup scripts" with
no failure line, the booted image against a recorded build of its series,
the kernel's clean mounts against the declared data disks) records its
verdict in `meta-state/verifications.yaml`; a failed verdict stops the
sequence and leaves the instance standing under `on_failure: keep`.
`post_finalize_phase` binds unpinned durable instances and logs `First
bind: instance <n> -> build <b> (launched this run)` or `(booted image,
read from the cloud)`, moves a `follow` pin (`Instance <n> pin moved ...`),
or warns `Instance <n> booted <image>, which lineage does not record; pin
left unbound`; the verdict is the pin in meta-state. The core records
each storage transition in `meta-state/storage-state.yaml` after the
storage runner completes. A restored pd's `restore-<disk>.sh` runs after
the apply and its exit status is the run's.

**In the state query.** `query_state()` (inherited) calls `_lookup` for
every declared and undeclared storage of the builder:

- `tf-gcp-pd`: `compute_v1.DisksClient.get(project, zone, disk)`; a
  `NotFound` is "absent", any other exception is raised. For a storage
  recorded `archived`, `SnapshotsClient.get(project, snapshot)` on
  `csis-<disk>-archive` instead ("404" or "not found" in the message is
  absent). No project or zone raises `RuntimeError("no project/zone to
  query")`. The record carries the disk's `status` (`READY` counts as
  live) and labels.
- `tf-gcp-gcs`: `gcloud storage buckets describe gs://<bucket>
  --format=json`; "not found", "404" or "does not exist" in stderr is
  absent; any other non-zero exit raises `RuntimeError("gcloud storage
  buckets describe gs://<bucket>: <stderr tail>")`; a missing `gcloud`
  binary raises the `FileNotFoundError` from `subprocess`.
- `tf-gcp-filestore`: `_lookup` runs `<declared gcloud>
  filestore instances describe <gce name> --location <runtime zone>
  --project <project> --format=json`. A not-found answer (`NOT_FOUND`,
  "not found", 404) is absent; any other non-zero exit raises
  `RuntimeError("gcloud filestore instances describe <name>: <stderr
  tail>")`, which the query reports as unavailable. The record carries
  `id` (the instance's short name), `state` (`READY`, ...), `tags` (the
  labels) and `size` (the first file share's `capacityGb`).

Verdicts land in the state report: `missing storage <n>: recorded
<state> but not found in reality [HARD]`, `foreign storage <n>: <type>
<id> exists but meta-state has no record of it`, `stale storage <n>:
recorded destroyed but <id> still exists` or `recorded active but
provider state is <status>`, and `unavailable: storages/<builder>:
<error>` when `_lookup` raised. `state query --strict` exits 1 on hard
drift, on any class but `stale` and on an `unavailable:` line; a plain
run warns and continues. Instance-side checks (the booted image against
the pin, the power state) are the runtime plugin's, not this one's.

**Tests.** The package's own test,
[tests/test_storage_variables.py](tests/test_storage_variables.py), pins
the label merge only. The behaviour above is pinned by the repository's
generation tests over a GCE overlay of the fixture:
[test_v2_gcp_increment3.py](../../tests/test_v2_gcp_increment3.py) (the
roots, the module arguments, the launch parameters, a local `tofu
validate` of the generated GCE roots when tofu is installed),
[test_v2_explore_gcp.py](../../tests/test_v2_explore_gcp.py) (the device
name and mount path agree, IAP bakes),
[test_v2_gce_cycle.py](../../tests/test_v2_gce_cycle.py) (the wipe
script, the storage destroy whitelist, the cycle overlays),
[test_v2_decommission.py](../../tests/test_v2_decommission.py),
[test_v2_detach.py](../../tests/test_v2_detach.py),
[test_v2_ephemeral.py](../../tests/test_v2_ephemeral.py),
[test_v2_run_scoping.py](../../tests/test_v2_run_scoping.py) and
[test_v2_state_locations.py](../../tests/test_v2_state_locations.py).
Nothing reaches GCP from the tests.

## When it fails

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

Failures by symptom: what each means and what to do.

- **`tofu apply` refuses a disk whose `name` is invalid (a YAML name such
  as `gce_data`).** GCE resource names must match
  `[a-z]([-a-z0-9]*[a-z0-9])?`, so every resource name goes through
  `gce_name`. If the provider reports an invalid `name`, a name reached
  the module call without the sanitizer; the module call in
  `generated/storage/<B>/storage-generation/<B>-storage-generation-storage-<label>.tf`
  shows which.
- **The pd is attached but not mounted** (`df /mnt/gce-data` resolves to
  the root filesystem). GCE exposes an attached disk as
  `/dev/disk/by-id/google-<device_name>`, so the module's `device_name`
  and the launch script's device path must agree; both go through
  `gce_name`. Under `set -e` the script dies at a missing device and
  nothing after it runs either. The serial console (`gcloud compute
  instances get-serial-port-output <name>`, or the runtime's `verify
  instance`) shows the 60-iteration wait loop ending without the device;
  check the `device_name` in the module call against the `DEV=` line of
  `user-data-<label>.sh.tftpl`.
- **Undeclaring the last GCE instance plans no destroy, or a dry run
  erases its record.** The root stays emitted while any recorded instance
  is undeclared, so the whitelist names a module the plan contains; and
  the "forget launch params and pin" is an after-apply hook, never a
  generation step. Symptom: `gate-plan` reports `0 to destroy` for a
  decommission, or `state query` reports a `foreign` instance right after
  a dry run. Both mean the record and the plan disagree; run the
  decommission again with the record intact.
- **The teardown dies wiping an empty bucket.** `gcloud storage rm
  --recursive gs://<bucket>/**` exits 1 when nothing matches, and an
  empty bucket is the normal end of a cycle, so the wipe is
  `wipe-<label>.sh`, which prints `gs://<bucket> is already empty` and
  exits 0 on "matched no objects" and otherwise prints gcloud's output
  and exits with its status, stopping the run before terraform's destroy.
  Any other message in that output (permission denied, no credentials) is
  a real failure: fix ADC or the bucket's IAM and rerun the storage
  lifecycle; the transition is not recorded until the apply succeeds.
- **An ephemeral verification fails on "booted image" and leaves the
  instance standing.** The instance's image was baked in the same run, so
  nothing was pinned at launch; verification therefore requires the
  booted image to be a recorded build of the instance's image series
  rather than comparing against a literal `unbound`. Symptom: `state
  query` says `ephemeral instance <name> is STANDING`; the next
  `instance-image` run resumes the sequence (plan no-change, verify,
  teardown), which is the intended recovery.
- **`tofu plan` of the `tofu-gce` root fails with `No valid credential
  sources found ... backend s3 ... the SSO session has expired`.** The
  AWS SSO session lapsed mid-cycle, after preflight passed. The GCE roots
  keep their state in S3, so AWS is a hard dependency of every GCE
  lifecycle. `aws sso login` and rerun; the bakes of the failed run are
  recorded and are not repeated. The same dependency makes `empty
  --runtime gcloud-east1` need AWS credentials, because every runtime
  validates its networking at load.
- **`data.google_compute_image.family` returns 404 for
  `family/imgfile-basic-dask`.** A root whose instance image is deferred
  resolves it through its family at plan time, and the family holds no
  image on GCP (the previous cycle's retention disposed every GCE image,
  for example). A run scoped to one runtime plans no other runtime's
  root, so the symptom belongs to the root's own runtime. Bake the image
  first (the `instance-image` lifecycle bakes before it plans), or launch
  with a pinned build.
- **The post-bake suite fails (`python3 -c 'import dask'`) on the
  standing ephemeral instance.** Not this plugin's failure (the image is
  wrong), but the plugin's `on_failure: keep` behaviour is what the
  operator sees: the instance stands and the verdict is recorded per
  build. A decommission of an instance that is still declared re-runs
  the ephemeral sequence, which is why the `just gce-decommission` recipe
  uses `--undeclare instance:gce-test`.

Failures the code raises:

- **`storage '<n>' (<type>) declares a data lifecycle ...`,
  `... requests archived, which its builder does not realize ...`,
  `... is single-attach but instances [...] all attach it (N16) ...`** from
  `validate` (exit 1): remove the `lifecycle:`, use `destroyed` instead of
  `archived` on Filestore and GCS, or split the pd across instances.
- **`unavailable: storages/<builder>: no project/zone to query`** in the
  state report: the builder's runtime has no `project_id` or `zone`;
  declare them.
- **`unavailable: storages/<builder>: gcloud storage buckets describe
  gs://<bucket>: <stderr>`**: the CLI could not answer (no ADC, no
  permission, no network); the tail of stderr says which. **`...: [Errno
  2] No such file or directory: '<path>'`**: the `binary` of the gcloud
  entry the runtime names is not there (the lookup runs the declared
  binary, not a `gcloud` from `PATH`); fix the entry's
  `binary` in `cfg/executables.yml`, which `validate` also checks.
- **`unavailable: storages/<builder>: gcloud filestore instances describe
  <name>: <stderr tail>`**: the Filestore lookup could not answer. The
  stderr tail says why: no ADC, no permission, or the Filestore API not
  enabled.
- **``storage '<name>' on builder <b>: the archive scripts need <project
  and zone|project>, and the runtime declares none (set `project_id` and
  `zone` on the GCP runtime)``** at generation (a `ValueError`, exit 1):
  a pd storage is being archived (needs `project and zone`), destroyed
  from archived or restored from archived (need `project`), and the
  builder's runtime resolves no project (no `project_id`) or, for the
  archive, the disk has no zone (neither the storage's `availability_zone`
  nor the runtime's `zone`). Declare them on the GCP runtime and rerun.
  The refusal keeps a literal `--project "None"` (or `--zone "None"`) out
  of a script that would fail only inside gcloud when the storage
  lifecycle ran it.
- **`tofu plan`: `Unsupported attribute ... outputs.storage_<label>`** on
  the instance root, or **`... outputs.group_gids`** on a storage root:
  the producer workspace has not applied yet (or applied to a different
  state location). Apply identity, then storage, then instances.
- **`tofu plan` on the instance root with an empty `image` and
  `image_family`**: the warning `No provider-specific image for image ...`
  was logged at generation; the image is not declared for the builder's
  runtime. Add the image builder's runtime entry.
- **`<instance|storage> '<name>': tag key '<key>' on runtime <rt>: GCE
  label keys must start with a lowercase letter; '<key>' becomes
  '<label>'; rename the key`** from `validate` (exit 1; the check is
  `check_label_keys`, the reason the gcloud runtime's
  `label_key_problem`): `gce_label` lowercases and replaces characters but
  cannot force a leading letter, so a tag key such as `2024` or `-env` on
  an instance or storage item would become a label key GCE refuses at
  apply (`Invalid value for field 'resource.labels'` or similar). Rename
  the key in the YAML; it is never renamed silently. The builder's
  `variables.tags` keys are not part of the check, so a bad key there
  surfaces only at apply: rename it the same way.
- **`capacity_gb` below the tier's minimum**, an unknown `tier`, an
  unknown `disk_type`, a bucket name already taken: refused by the
  provider at apply, never by the plugin.
- **`gate-plan` exit 3, `detach not unmounted`**: the `unmount storage`
  step produced no successful receipt (the instance is stopped, the IAP
  tunnel or the operator key is not available, the unmount itself
  failed). `sft`/`gcloud compute ssh` in, unmount by hand, then `unmount
  storage --confirm ...` records the operator's word.
- **`Value for undeclared variable` warnings from tofu** on the GCE root
  after a bake in the same run: `pre_finalize_phase` writes
  `<label>_image = "..."` into `instances.auto.tfvars`, the variable the
  GCE root declares, so the build reaches the module call. The warning
  means the root and its tfvars disagree (a hand-edited tfvars, or a root
  regenerated under another label), and the instance then launches
  through the family instead of the build. Regenerate the root and look
  at the tfvars line.
- **The startup script stops before "Finished running startup scripts"**
  (`verify instance` times out or reports a failure line): under `set
  -e`, a failed `mkfs`, `mount` or `chgrp` ends it. The serial console
  shows the last command; the `nfs` mount needs the Filestore's network
  to be the instance's, and the pd mount needs the attachment to have
  landed (the script waits up to 120 s).

## Related

- [cs-image-system-hashicorp-utils](../hashicorp-utils/README.md#the-terraform-roots):
  the provider-neutral terraform roots these builders subclass, what the
  bases own, the full hook table and the version checker.
- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md):
  the AWS root on the same bases, with the launch parameters and the
  storage state machine described at length; not a dependency.
- [cs-image-system-tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the
  state backend the fixture's GCP roots use.
- [gcloud-runtime-plugin gcp_runtime_models.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)
  and [gcp_packer_source.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_packer_source.py):
  the runtime model this plugin reads and the `gce_name`/`gce_label` rules;
  [gcp_utils.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_utils.py)
  for `resolve_project` and `make_credentials`;
  [gcp_runtime_builders.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_runtime_builders.py)
  for `session_mechanism`, `verify_instance` and `query_instance_boot_image`.
- [base launch_params.py](../base/src/cs_image_system/base/launch_params.py):
  the launch script, including the `pd` and `filestore` mount forms.
- [tests/test_storage_variables.py](tests/test_storage_variables.py): the
  unit test that pins the label merge.
- [docs/DESIGN.md](../../docs/DESIGN.md) and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md).
