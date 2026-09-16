# cs-image-system-packer-plugin

The image builder plugin for HashiCorp Packer. It registers the two image
builders that turn the system's base images and instance images into Packer
roots: `packer-ebs` for an AWS runtime (`amazon-ebs` source) and
`packer-gce` for a Google Compute runtime (`googlecompute` source). The
builder writes one Packer root per dependency block of images, fills the
`build {}` block with provisioners it assembles from the OS builder, the
identity and storage plugins, the runtime plugin and the modification
builders, and defers `packer build .` to the lifecycle runner script. After
a real build it reads Packer's manifest to resolve the image ids and record
lineage.

## What it registers

Entry point ([pyproject.toml](pyproject.toml)):

```toml
[project.entry-points."cs_image_system.plugins.image"]
packer_plugin = "cs_image_system.packer_plugin.main:initialize"
```

`initialize()` ([main.py](src/cs_image_system/packer_plugin/main.py))
returns a `PackerEbsTypes` metadata object (metadata version `1`, Python
`3.13`) with three service keys:

| Service key (`type:`) | Classes | Classification (VCT) |
|---|---|---|
| `packer-ebs` | `PackerEbsImageBuilderModel`, `PackerEbsImageBuilder` | `IMAGE_BUILDER_MODEL` / `IMAGE_BUILDER` |
| `packer-gce` | `PackerGceImageBuilderModel`, `PackerGceImageBuilder` | `IMAGE_BUILDER_MODEL` / `IMAGE_BUILDER` |
| `packer` | `PackerVersionChecker` | `VERSION_CHECKER` |

An `image_builders:` entry selects a model with `type: packer-ebs` or
`type: packer-gce`; there are no aliases for these keys. An `executables:`
entry named or typed `packer` is version-checked by `PackerVersionChecker`
(`packer version -machine-readable`, fourth comma-separated field of the
first line).

The package depends on `cs-image-system-system`, `boto3` and
`cs-image-system-aws-runtime-plugin`.

## Models

### `PackerImageBuilderModel`

Defined in [packer_models.py](src/cs_image_system/packer_plugin/packer_models.py).
Extends
[`ImageBuilderModel`](../base/src/cs_image_system/base/models/image_builder_model.py).
Not registered on its own; it is the shared parent.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `required_plugins` | `list[PackerPluginConfig]` | `[]` | Packer plugins the root declares in its `packer { required_plugins {} }` block. Each entry has `name`, `version`, optional `source` and `config` ([plugin_config.py](../base/src/cs_image_system/base/helpers/plugin_config.py)). |

Inherited fields:

| Base field | From | Default | Meaning |
|---|---|---|---|
| `runtime` | `RuntimeEnabledBuilderModel` ([builder_model.py](../base/src/cs_image_system/base/models/builder_model.py)) | `default` | Name or alias of the `runtime_builders:` entry this builder bakes on. `default` resolves to the default runtime. Every source block, credential and machine type comes from that runtime. |
| `default_machine_type` | `ImageBuilderModel` | `default` | Machine type used when neither the image's runtime subconfig nor the runtime supplies one. |
| `name`, `type`, `description`, `aliases`, `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` / `NameTyped` | | `executable` must name an `executables:` entry whose binary is Packer; `tags` are merged into every source's tags. |

### `PackerEbsImageBuilderModel` (`packer-ebs`)

Extends `PackerImageBuilderModel`; adds no fields.

### `PackerGceImageBuilderModel` (`packer-gce`)

Extends `PackerEbsImageBuilderModel`; adds no fields. It exists so a
configuration can say `type: packer-gce`; the runtime plugin bound through
`runtime` decides what the source block looks like.

### Constraints and what is not supported

- `parameters:` is refused at load (a base-model rule); the builder
  assembles Packer's command line itself.
- The only Packer variables declared are `release` (bool, default `true`)
  and `base_image_version` (string, `env("BASE_IMAGE_VERSION")`, default
  `1.0.0`). There is no field for extra variables.
- No provisioner is configurable on the builder model. Modifications come
  from the modification builders; everything else is derived from the OS
  builder, the runtime, the identity and storage plugins and the image's
  `tests:`.
- The `type` class attribute on each model is documentation only; the
  registry keys on `csis_name()`.

### The image models this builder consumes

The plugin defines no image item models. It reads the base
[`Image`](../base/src/cs_image_system/base/models/image.py) and
[`BaseImage`](../base/src/cs_image_system/base/models/base_image.py)
models and their per-builder subconfigs:

| Item field | Used for |
|---|---|
| `Image.runtimes[].image_builder` | Attaches the image to this builder. One image may list several builders (one per runtime). |
| `Image.runtimes[].machine_type`, `ssh_username`, `image_identifier`, `tags`, `owners` | Passed to the runtime's source block. |
| `Image.source_image` | The parent image; orders images into blocks and selects the source AMI/image. |
| `Image.modifications` | The modification items; each is handed to its modification builder. |
| `Image.group` | The owning group; its group builder's activation commands are baked. |
| `Image.tests` | In-bake assertions (`packages`, `files`, `commands`, `users`, ...), the last provisioner before finalization. |
| `Image.tags` | Merged into the source's tags with the builder's and subconfig's tags and the lineage tags (`csis_series`, `csis_parent`, `csis_run`, `csis_fingerprint`, `csis_identity_types`, `csis_storage_types`). |
| `BaseImage.identity_types`, `storage_types` | Which plugins' prerequisites are baked. |
| `BaseImage.admin_user`, `admin_public_keys` | The mandatory local admin user (default `csisadmin`; keys from the base image or `config.admin_public_keys`). |
| `BaseImage.modifications` | Ignored with a warning: base images take no modifications. |

The OS update provisioner of a base image comes from the OS builder of the
same name (its `update:` policy); the plugin only asks for it.

## The builder

Class chain: `PackerImageBuilder`
([packer_builder.py](src/cs_image_system/packer_plugin/packer_builder.py))
-> `PackerEbsImageBuilder`
([packer_ebs_builder.py](src/cs_image_system/packer_plugin/packer_ebs_builder.py))
-> `PackerGceImageBuilder` (same file, differs only in `csis_name()`).
All extend
[`ImageBuilderBase`](../base/src/cs_image_system/base/basic/builder_base_image.py).
Every hook keys on the `image-generation` phase.

Two things shape every hook:

- The Packer source type is the runtime plugin's `packer_source_type()`
  (`amazon-ebs` for AWS, `googlecompute` for GCE); `amazon-ebs` when the
  runtime has no opinion. `build_target_label(image)` is
  `<source type>.<image name>`, the value every provisioner's `only = [...]`
  carries.
- `get_blocks()` orders the builder's images by their `source_image`
  dependencies into blocks `block-000`, `block-001`, ... Each block is its
  own Packer root directory. The base-image lifecycle hands the builder
  only base images; the instance-image lifecycle only instance images. A
  `--only` selection and the convergent-bake check (an image whose series
  head was built from the same inputs is skipped) both apply here.

Paths below are relative to the run's generation directory; `<ws>` is the
builder name and `<ph>` is `image-generation`.

1. `generate_items_before` registers the model's `required_plugins` and the
   two variables into the run's `PackerCollector`, then writes, per block,
   under `<ws>/<ph>/block-NNN/`:
   - `<ws>-<ph>-block-NNN-vars.pkr.hcl`: the `variable` blocks.
   - `<ws>-<ph>-block-NNN-plugins.pkr.hcl`: the `packer { required_plugins }`
     block.
   - `<ws>-<ph>-block-NNN-ebs-ansible-setup.pkr.hcl`: a `locals` block with
     `snapshot` (`""` when `var.release`, else `-SNAPSHOT`) and
     `image_version`.
   The parent class's builder-level setup and vars assets are not written;
   only the per-block files are.
2. `get_commands_to_run_before`: nothing.
3. `generate_items_during` writes, per block:
   - `<ws>-<ph>-source-<image>-block-NNN.pkr.hcl` per image: the runtime
     plugin's source block(s) (`image_to_source`). The plugin locates the
     provider-specific image of the parent (the image's own when it builds
     from `self`, otherwise its `source_image`'s: a resolved id, or a
     name-pattern query for an image a previous block builds), computes the
     artifact name from the subconfig's final-name template
     (`<image>-<image_builder>-<timestamp>` for instance images,
     `<image>-<runtime>-<timestamp>` for base images), merges tags, finds
     the pinned parent build, and hands all of it to the runtime's
     `packer_source_blocks()`.
   - `<ws>-<ph>-block-NNN-build.pkr.hcl`: one `build {}` block named
     `<ws>-block-NNN` whose `sources` list every image of the block,
     followed by provisioners in this order.

   For a base image:
   1. the OS update (from the OS builder of the same name);
   2. the admin user (`admin_user_commands`: create the user, sudoers,
      `authorized_keys` from the public keys);
   3. per declared identity type, the first group builder of that type's
      `base_image_prerequisites(family)`;
   4. per declared storage type, a storage builder of that type on this
      runtime; a comment line when no plugin exists on this runtime;
   5. the runtime's session agent (`session_agent_commands`);
   6. in-bake verification: one `provisioner "shell"` under `set -e` with
      every assertion (admin user, identity, storage and session
      verifications, then the image's `tests:`);
   7. the runtime's bake finalization commands, when it has any.

   For an instance image:
   1. per modification, in declared order: the modification builder's
      `copy_external_assets(block_dir, mod)`, the item's
      `remap_self_with_copied_assets`, then the builder's
      `generate_items_before_modification`,
      `generate_items_during_modification`,
      `generate_items_after_modification`, all appending to the build
      file;
   2. identity activation for the image's owning `group` (the group
      builder's `activation_commands`);
   3. the local modification bundle
      ([v2_local_mods.py](src/cs_image_system/packer_plugin/v2_local_mods.py)):
      `csis-mods/<image>/` is staged in the block directory with the
      `csis-mods` runner script, a `MANIFEST.yaml` index, and one
      `NN-<mod>/` directory per modification (its playbooks or scripts,
      an `inline.sh` for inline lines, a `run.sh` wrapper, a
      `MANIFEST.yaml` with type, operation, content hash, idempotence, run
      id). Three provisioners upload it: `mkdir -p /tmp/csis-mods`, a
      `file` provisioner, and a shell that moves it to `/opt/csis/mods`
      and installs `/usr/local/bin/csis-mods`. Skipped when the image has
      no modifications;
   4. in-bake verification (activation assertions, then the image's
      `tests:`);
   5. the runtime's bake finalization commands.

   The block ends with `post-processor "manifest" { output = "manifest.json"
   strip_path = true }`.
4. `get_commands_to_run_during`: nothing.
5. `generate_items_after`: nothing.
6. `get_commands_to_run_after` returns, per block, generation-time
   `packer fmt .`, `packer init .`, `packer validate .` (run in-process in
   the block directory) and one deferred `packer build .`, which is what
   reaches `run-base-image.sh` / `run-instance-image.sh`.
7. `pre_finalize_phase`: not overridden.
8. `post_finalize_phase` (after the builds ran): parses each block's
   `manifest.json` (builds of the last run only; the runtime turns
   `artifact_id` into its build id, `<region>:<ami-id>` -> ami id on AWS),
   registers a resolved provider-specific image per built image, records
   the build in lineage with its final name and parent, and re-tags the
   artifact with `csis_parent` and `csis_fingerprint`.

## Emission

Real file names from the golden emission under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated).
The base-image lifecycle emits under `base-image/`, the instance-image
lifecycle under `instance-image/`.

Base-image lifecycle, builder `pckr-ebs-ans`, block `block-000` (three base
images with no mutual dependencies):

| File | Content |
|---|---|
| [pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl) | `build "pckr-ebs-ans-block-000"`; per image: OS update, admin user, `okta` prerequisites, `ebs`/`efs`/`s3` prerequisites (`gcs` and `pd` as "no plugin on runtime" comments), SSM agent, verification; then the manifest post-processor. |
| [...-block-000-ebs-ansible-setup.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-ebs-ansible-setup.pkr.hcl) | The `locals` block. |
| [...-block-000-plugins.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-plugins.pkr.hcl) | `required_plugins` `amazon` and `ansible`. |
| [...-block-000-vars.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-vars.pkr.hcl) | `release` and `base_image_version`. |
| [...-source-basic-rh-10-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl), `-source-basic-rhel-9-`, `-source-my-deb-11-` | `data "amazon-ami"` (resolved image id) and `source "amazon-ebs"` (name, instance type, VPC, subnet, tags, SSM session interface, block device). |
| [run-base-image.sh](../../tests/fixtures/v2_golden/generated/base-image/run-base-image.sh) | `packer build .` in each block directory. |

The GCE builder `pckr-gce-ans` emits the same set of files under
[base-image/pckr-gce-ans/image-generation/block-000](../../tests/fixtures/v2_golden/generated/base-image/pckr-gce-ans/image-generation/block-000);
its source file holds a `source "googlecompute"` block with `image_name`,
`image_family`, `image_labels`, `use_iap`, `preemptible`, `disk_size`.

Instance-image lifecycle, builder `pckr-ebs-ans`:

| File | Content |
|---|---|
| [block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl) | Four images: their modification provisioners (`ansible`, `shell`), identity activation, local bundle upload, verification. |
| [block-000/...-source-imgfile-basic-dask-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-source-imgfile-basic-dask-block-000.pkr.hcl) | A `data "amazon-ami"` most-recent query on the parent series name (`basic-rh-10-aws-east2-runtime*`, owner `self`) and the `source "amazon-ebs"`. |
| [block-000/csis-mods/imgfile-basic-dask/](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-000/csis-mods/imgfile-basic-dask/MANIFEST.yaml) | The local bundle: `csis-mods`, `MANIFEST.yaml`, `01-dask-setup-jeffy/`, `02-derivative-setup/`. |
| `block-000/setup_dask.yml`, `setup_data_science.yml`, `mod_image.sh`, `modify_image.yml` | Playbooks and scripts copied beside the root by the modification builders. |
| [block-001/pckr-ebs-ans-image-generation-block-001-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/instance-image/pckr-ebs-ans/image-generation/block-001/pckr-ebs-ans-image-generation-block-001-build.pkr.hcl) | The second block: `imgfile-basic-cloudflow`, whose `source_image` is built in block-000. |
| [run-instance-image.sh](../../tests/fixtures/v2_golden/generated/instance-image/run-instance-image.sh) | `packer build .` per block for `pckr-ebs-ans` (two blocks), `pckr-gce-ans` and `some-other-builder` (with its own executable, `packer-1.9.4`), before the instance roots' terraform commands. |

## Example configuration

From
[tests/fixtures/config/cfg/image-builders.yml](../../tests/fixtures/config/cfg/image-builders.yml):

```yaml
image_builders:
  - name: pckr-ebs-ans
    is_default: true
    type: packer-ebs
    runtime: default
    executable: packer
    required_plugins:
      - name: amazon
        source: github.com/hashicorp/amazon
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
  - name: pckr-gce-ans
    type: packer-gce
    runtime: gcloud-east1
    executable: packer
    required_plugins:
      - name: googlecompute
        source: github.com/hashicorp/googlecompute
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
```

An instance image baked by both builders, from
[tests/fixtures/config/images/image1.yaml](../../tests/fixtures/config/images/image1.yaml)
(comments removed):

```yaml
images:
  - name: imgfile-basic-dask
    group: coops
    runtimes:
      - image_builder: pckr-ebs-ans
      - image_builder: pckr-gce-ans
        machine_type: e2-medium
    tags:
      dask: "true"
    type: pckr-ebs-ans
    source_image: basic-rh-10
    parent_policy: follow
    description: "Basic Dask head node with essential tools and configurations."
    tests:
      commands:
        - run: "git --version"
          contains: "git version"
      packages: [git]
      users: [csisadmin]
      post_bake:
        commands:
          - run: "python3 -c 'import dask'"
        files:
          - path: /var/lib/csis/launch-applied
        mounts: [/mnt/gce-data]
    release:
      model: default
    modifications:
      - name: dask-setup-jeffy
        type: ansible-default
        playbooks:
          - setup_dask.yml
        config:
          dask_version: "2023.9.1AA"
          jupyterlab_extension: true
      - name: derivative-setup
        type: bash-remote
        script:
          - "echo 'derivative setup'"
          - "sudo mkdir -p /opt/derivative && echo 1.0.0 | sudo tee /opt/derivative/VERSION"
        scripts:
          - mod_image.sh
        ensure:
          packages: [git]
          files:
            - path: /etc/derivative.conf
              content: "version=1.0.0\n"
              mode: "0644"
          commands:
            - run: "sudo mkdir -p /opt/derivative/data"
              unless: "test -d /opt/derivative/data"
        config:
          derivative_version: "1.0.0"
```

Base images are not declared as images: the OS builders in
[cfg/os-builders.yml](../../tests/fixtures/config/cfg/os-builders.yml)
synthesize them, and each OS builder's `runtimes[].image_builder` names
the Packer builder that bakes it.

## Related

- Base models extended:
  [image_builder_model.py](../base/src/cs_image_system/base/models/image_builder_model.py),
  [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py);
  items read:
  [image.py](../base/src/cs_image_system/base/models/image.py),
  [base_image.py](../base/src/cs_image_system/base/models/base_image.py),
  [moditem_type.py](../base/src/cs_image_system/base/models/moditem_type.py),
  [provider_specific_image.py](../base/src/cs_image_system/base/models/provider_specific_image.py).
- Base builder class:
  [builder_base_image.py](../base/src/cs_image_system/base/basic/builder_base_image.py);
  runtime hooks it calls:
  [builder_base_runtime.py](../base/src/cs_image_system/base/basic/builder_base_runtime.py)
  (`packer_source_type`, `packer_source_blocks`, `build_id_from_artifact`,
  `session_agent_commands`, `bake_ssh_username`).
- Provisioner helpers in this package:
  [v2_provisioners.py](src/cs_image_system/packer_plugin/v2_provisioners.py)
  (admin user, prerequisites, activation),
  [v2_local_mods.py](src/cs_image_system/packer_plugin/v2_local_mods.py)
  (the `csis-mods` bundle); in base:
  [image_tests.py](../base/src/cs_image_system/base/image_tests.py)
  (verification and finalization provisioners),
  [lineage.py](../base/src/cs_image_system/base/lineage.py).
- Library:
  [hashicorp-utils](../hashicorp-utils) --
  [collector.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py)
  (`PackerCollector`: plugins and variables),
  [hashicorp_models.py](../hashicorp-utils/src/cs_image_system/hashicorp_utils/hashicorp_models.py)
  (`PackerPluginConfig`).
- Runtime plugins that supply the source blocks:
  [aws-runtime-plugin](../aws-runtime-plugin),
  [gcloud-runtime-plugin](../gcloud-runtime-plugin).
- Modification plugins whose provisioners land in the build file:
  [ansible-plugin](../ansible-plugin),
  [bash-mod-plugin](../bash-mod-plugin).
- Tests: [tests/](tests) -- block ordering and manifest parsing.
