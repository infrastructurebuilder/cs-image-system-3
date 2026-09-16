# cs-image-system-tf-gcp-plugin

This package is the OpenTofu plugin for Google Cloud. It registers one
**instance builder** (`tofu-gce`), which turns every declared instance into a
`module` call against `tfmodules/gce_instance`, and three **storage
builders** (`tf-gcp-pd`, `tf-gcp-filestore`, `tf-gcp-gcs`), which turn every
declared storage into a `module` call against the matching
`tfmodules/gcp_storage_*` module. It contains no generic machinery of its
own: every class subclasses the AWS classes in
[cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md)
and swaps the `aws` provider for a `google` one, the AMI for a GCE image, EBS
for persistent disks, and the AWS CLI transition scripts for `gcloud` ones.
The runtime it targets is a `gcloud` runtime builder from
`cs-image-system-gcloud-runtime-plugin`, which supplies the project, region,
zone, network and session mechanism.

## What it registers

The entry point, from [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.instance"]
tf-gcp-plugin = "cs_image_system.tf_gcp_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/tf_gcp_plugin/main.py)
returns a `TFGcpTypes` metadata object (plugin metadata version `1`, Python
`3.13`). The package depends on `cs-image-system-tf-ebs-instance-plugin`
(the base classes) and `cs-image-system-gcloud-runtime-plugin` (the runtime
model, `gce_name`, `gce_label`, and the GCP client helpers).

| Service name (`type:` of a builder entry) | Model class | Builder class | Classifications (VCT) |
|---|---|---|---|
| `tofu-gce` | `TofuGceInstanceBuilderModel` | `TofuGceInstanceBuilder` | `INSTANCE_BUILDER_MODEL`, `INSTANCE_BUILDER` |
| `tf-gcp` | `TofuGcpStorageBuilderModel` | `TofuGcpStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-pd` | `TofuPdStorageBuilderModel` | `TofuPdStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-filestore` | `TofuFilestoreStorageBuilderModel` | `TofuFilestoreStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |
| `tf-gcp-gcs` | `TofuGcsStorageBuilderModel` | `TofuGcsStorageBuilder` | `STORAGE_BUILDER_MODEL`, `STORAGE_BUILDER` |

`tf-gcp` is a base: it inherits the abstract `module_dirname()` and
`module_args()` from `TofuStorageBuilder`, so a builder entry with
`type: tf-gcp` cannot emit anything. This package registers no version
checker; an executable entry with `type: tofu` is checked by the
`TofuVersionChecker` of the AWS plugin.

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
The AWS-plugin fields every class here inherits:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `executable` | str \| None | `"tofu"` | Name of an entry in `cfg/executables.yml`. |
| `required_plugins` | list[`TFTofuPluginModel`] | [] | Terraform providers for the root. Empty means one `google` provider from `hashicorp/google` with no version constraint. |
| `state_configuration` | str (foreign key to `STATE_BACKEND_MODEL`) | `default` | The state backend for the workspace, by name. A GCP root may use the S3 backend. |

### `TofuGceInstanceBuilderModel` (`tofu-gce`)

Extends `TofuInstanceBuilderModel` from
[tf_instance_models.py](../tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_instance_models.py),
which extends the base `InstanceBuilderModel`
([instance_builder.py](../base/src/cs_image_system/base/models/instance_builder.py)).
It adds no fields; it only changes `type` to `tofu-gce`.

The `Instance` items it reads are the base ones from
[instance.py](../base/src/cs_image_system/base/models/instance.py):
`image`, `runtime`, `storages` (each `name` + `mount_point`), `userdata`,
`image_policy` (`pinned` | `follow`), `ephemeral`, `on_failure`
(`keep` | `teardown`), `teardown_after`, `tags`. Differences from the AWS
root:

- `machine_type` on the instance is **not read**: the module's
  `machine_type` is always the runtime's `default_machine_type`.
- `tags` become GCE `labels`, each key and value passed through `gce_label`
  (lowercase; anything outside `[a-z0-9_-]` becomes `-`).
- The instance name is passed through `gce_name` (lowercase; anything
  outside `[a-z0-9-]` becomes `-`), so `gce-test` stays `gce-test` and a
  name such as `gce_data` becomes `gce-data`.

### `TofuGcpStorageBuilderModel` (`tf-gcp`)

Extends `TofuStorageBuilderModel` from
[tf_storage_models.py](../tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_storage_models.py)
(which extends the base `StorageBuilderModel`,
[storage_builder.py](../base/src/cs_image_system/base/models/storage_builder.py)).
It adds no fields; `type` is `tf-gcp`. Its `variables` field keeps the base
type `ModuleVariables`.

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

Persistent disk: the EBS equivalent, single-attach, POSIX.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `size` | int | 100 | Disk size in GB. |
| `disk_type` | str | `"pd-balanced"` | GCE disk type (for example `pd-standard`, `pd-balanced`, `pd-ssd`). |
| `variables` | `GcpVariables` | `GcpVariables()` | Default labels. |

### `TofuFilestoreStorageBuilderModel` (`tf-gcp-filestore`)

Filestore: the EFS equivalent, many-attach NFS, POSIX.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `tier` | str | `"BASIC_HDD"` | Filestore tier. |
| `capacity_gb` | int | 1024 | Capacity; the module notes 1024 GB as the minimum for BASIC tiers. |
| `variables` | `GcpVariables` | `GcpVariables()` | Default labels. |

### `TofuGcsStorageBuilderModel` (`tf-gcp-gcs`)

GCS bucket: the S3 equivalent, many-attach object store, non-POSIX.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `bucket_name` | str | required | Bucket name used when the storage item declares none. |
| `location` | str \| None | None | Bucket location; None means the runtime's `region`. |
| `variables` | `GcpVariables` | `GcpVariables()` | Default labels. |

### The `Storage` item the storage builders read

Base `Storage` from
[storage.py](../base/src/cs_image_system/base/models/storage.py):
`type`, `runtime`, `groups`, `public_read`, `share_mode` (`2770` | `2775`),
`state` (`active` | `archived` | `destroyed`), `bucket_name` (GCS), `tags`.
`lifecycle:` is **refused** on all three GCP builders: none of them realizes
a data lifecycle, so the base `validate_lifecycle` rejects any declaration.
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

The hook order, file naming and the deferred `plan -> gate -> apply`
sequence are those of the AWS plugin; see
[its README](../tf-ebs-instance-plugin/README.md#the-builder). This section
lists what the GCP classes override and what they inherit unchanged.

### `TofuGceInstanceBuilder` (phase `instance-generation`)

Source:
[tf_gce_instance_builder.py](src/cs_image_system/tf_gcp_plugin/tf_gce_instance_builder.py).
Extends `TofuInstanceBuilder`.

**Overridden: `generate_items_before`.** Writes `<B>-instance-generation.tf`
and `<B>-instance-generation.tfbackend.hcl` with: the `ephemeral_present`
variable when any instance is ephemeral; provider requirements from
`required_plugins` or `google`/`hashicorp/google`; a `provider "google"`
block (`project`, `region`, `zone`) aliased to the workspace name
(`tofu_gce`); one `variable "<label>_image"` (string, default `""`) per
instance; `variable "sft_enrollment_token"` (sensitive); the backend
binding; a `terraform_remote_state` reference to every storage builder that
owns storages and to every identity workspace owning an instance image's
group; then the terraform, provider, variable and remote-state blocks. It
emits **no** security group or VPC data source: network access is the
runtime's firewall and the IAP tunnel.

**Overridden: `generate_items_during`.** Per instance,
`<B>-instance-generation-instance-<label>.tf` with `module "instance_<label>"`
against `tfmodules/gce_instance`, and `user-data-<label>.sh.tftpl`. The
module arguments:

| Argument | Value |
|---|---|
| `count` | `var.ephemeral_present ? 1 : 0`, only for ephemeral instances |
| `name` | `gce_name(<instance name>)` |
| `image` | the pinned build (a GCE image name) when meta-state pins the instance; else the resolved provider-specific image; else `var.<label>_image` |
| `image_family` | `gce_name(<image name>)`, only while the image is deferred: GCE resolves "latest in family" natively |
| `machine_type` | the runtime's default machine type |
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

**Overridden helpers.** `_attachment_address()` returns None: a persistent
disk attachment is an in-place attribute of `google_compute_instance`, so a
detach adds an `unmount storage` step and a `--require-unmounted` gate
requirement but no destroy whitelist entry. `_replacements()` names
`module.instance_<label>.google_compute_instance.this` for pending upgrades
and `follow` targets.

**Inherited unchanged.** `get_commands_to_run_after` (generation-time `fmt`,
`init`, `validate`; deferred `rm -f tfplan`, `init -input=false
-reconfigure [-backend-config=...]`, unmounts, `plan -out=tfplan
[-replace=...]`, `gate-plan`, and `apply-check --lifecycle instances --root
<B> --root-alias <runtime>` plus `apply` when `config.apply_instances`
allows the root), the ephemeral verify-and-teardown sequence, the
decommission whitelist, `pre_finalize_phase` and `post_finalize_phase`.

Two consequences of the inheritance:

- `pre_finalize_phase` writes `instances.auto.tfvars` with `<label>_ami_id`
  lines. The GCE root declares `<label>_image`, not `<label>_ami_id`, so
  those values do not reach the GCE module call. An image that is deferred
  at generation launches through `image_family`.
- `post_finalize_phase` then binds the pin from reality: the gcloud runtime
  answers `can_query_instance_boot_image()`, so an unpinned, non-ephemeral
  instance is bound to the image it actually booted, provided lineage
  records that build.

### `TofuGcpStorageBuilder` and its subclasses (phase `storage-generation`)

Source:
[tf_gcp_storage_builder.py](src/cs_image_system/tf_gcp_plugin/tf_gcp_storage_builder.py).
Extends `TofuStorageBuilder`; the storage state machine, the live/tombstone/
archived split, the `output "storage_<label>"` blocks, the gid-by-reference
rule and the deferred command sequence (`apply_storage` gates the apply) are
inherited.

**Overridden on the base: `generate_items_before`.** The same root file as
on AWS with a `provider "google"` block (`project`, `region`, `zone`, alias =
workspace name) from `google_provider_config(runtime)` instead of an `aws`
one. **`_labels(storage)`**: the builder's `variables.tags` under the item's
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
| State query | `compute_v1.DisksClient.get` by disk name (or `SnapshotsClient.get` on the archive when recorded archived); `NotFound` means absent | not implemented: reports as unavailable | `gcloud storage buckets describe gs://<bucket> --format=json`; "not found" means absent, any other failure is "unavailable" |

Module arguments (`module_args(storage)`):

| Builder | Arguments |
|---|---|
| PD | `name = gce_name(<storage>)`; `size` and `disk_type` from the builder; `labels`; `zone` from the runtime; `snapshot = csis-<gce name>-archive` when the storage is recorded archived and declared active (restore) |
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

## Related

- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md):
  the base classes, the full hook description, the launch parameters and
  the storage state machine.
- [cs-image-system-tf-s3-state-plugin](../tf-s3-state-plugin/README.md): the
  state backend the fixture's GCP roots use.
- [gcloud-runtime-plugin gcp_runtime_models.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_runtime_models.py)
  and [gcp_packer_source.py](../gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/gcp_packer_source.py):
  the runtime model this plugin reads and the `gce_name`/`gce_label` rules.
- [base launch_params.py](../base/src/cs_image_system/base/launch_params.py):
  the launch script, including the `pd` and `filestore` mount forms.
- [tests/test_storage_variables.py](tests/test_storage_variables.py): the
  unit test that pins the label merge.
- [docs/DESIGN.md](../../docs/DESIGN.md) and
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md).
