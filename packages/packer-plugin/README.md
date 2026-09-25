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

The package depends on `cs-image-system-system`,
`cs-image-system-aws-runtime-plugin`, `cs-image-system-hashicorp-utils`,
`Jinja2`, `python-hcl2`, `pydantic` and `PyYAML`
([pyproject.toml](pyproject.toml)). It makes no cloud API call of its own:
everything provider-specific goes through the runtime plugin bound by
`runtime`.

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
| `default_machine_type` | `ImageBuilderModel` | `default` | Accepted, not read. The bake's machine type is the image's runtime subconfig `machine_type`, whose own default is the RUNTIME's `default_machine_type`; the runtime plugins' source generators never look at the image builder's value (see the configuration reference below). |
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
  and `base_image_version` (string, emitted as
  `default = env("BASE_IMAGE_VERSION")`, empty when the variable is unset;
  since stage 63 item 3 its description says exactly that instead of
  promising a `1.0.0` that was never written). There is no field for extra
  variables, and an image's `variables:` mapping is read by nothing.
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
     `image_version`. No emitted source refers to either local; the only
     variable a source uses is `var.release` (`force_deregister =
     !var.release` on `amazon-ebs`).
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

## Prerequisites and integration

What must exist outside the system before a Packer builder can bake, and
how the plugin finds each thing. The plugin itself opens no cloud
connection: the source block, the credentials it names and the build VM's
network all come from the runtime plugin bound by `runtime`, and the
after-build tagging is the runtime plugin's call. What this section lists
is therefore the union of what Packer needs and what the bound runtime
needs for a bake.

**The Packer binary.** An `executables:` entry
([CONFIGURATION.md section 3](../../docs/CONFIGURATION.md)) whose name is
the builder's `executable` (`packer` in the fixture, `packer-1.9.4` for a
second builder pinned to an older release). The entry's `binary` is the
path the emitted runner script calls (`/usr/local/bin/packer build .`);
its `version` is a PEP 440 requirement (`">=1.14, <1.15"` in the fixture;
the floor CI's runners ran in 2026-09, stage 48.1). `PackerVersionChecker`
reads the version with `packer version -machine-readable` and takes the
fourth field of the first line (`1789674564,,version,1.14.3` -> `1.14.3`);
the checker is found under the entry's name, then its `type` (`type:
packer` on an entry with another name). The check runs at `validate` and
at the start of every run. A missing entry name, a missing binary or a
version outside the requirement fails validation by name (see "When it
fails").

**Packer plugins and the network to fetch them.** Every plugin the emitted
root uses must be in the builder's `required_plugins`: `amazon` for an AWS
runtime, `googlecompute` for a GCE runtime, `ansible` when any modification
is an ansible one. `packer init .` runs at GENERATION time, in-process, in
every block directory, dry run included, and downloads the plugins from
their `source` (`github.com/hashicorp/<name>`) into Packer's plugin
directory, so generation needs outbound access to GitHub releases (or a
pre-populated `PACKER_PLUGIN_PATH`). A plugin the provisioners use but the
list omits fails `packer validate .`, also at generation.

**Local tools the provisioners call.** An `ansible` provisioner runs
`ansible-playbook` on the machine running Packer; that is the ansible
plugin's prerequisite ([ansible-plugin](../ansible-plugin/README.md)),
declared as an `executables:` entry like Packer. Shell provisioners need
nothing local.

**The runtime's credentials and network (AWS, `packer-ebs`).** The bound
runtime's `credentials` name the AWS profile the emitted `data
"amazon-ami"` and `source "amazon-ebs"` blocks carry (`profile = "noaa"`
in the golden), so the bake needs a live session for that profile (`aws
sso login --profile noaa`, or `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
/ `AWS_SESSION_TOKEN` in the environment; the session must outlive the
bake, see [OPERATIONS.md](../../docs/OPERATIONS.md), "Credentials and
sessions"). The runtime's `networking` supplies `vpc_id` and `subnet_id`;
the build VM launches with `associate_public_ip_address = false`, so the
subnet must route outbound traffic (package repositories, the SSM agent
download from `s3.<region>.amazonaws.com`) through a NAT or equivalent.
When the runtime declares `session_mechanism: ssm`, the source sets
`ssh_interface = "session_manager"` and `iam_instance_profile` to the
runtime's `session_instance_profile` (else `iam_instance_profile`), and a
`user_data` bootstrap installs the SSM agent before Packer connects: that
instance profile must exist and allow SSM, and the caller's role must be
allowed `ssm:StartSession`. The vendor AMI is read through the AWS API at
resolution time (the OS builder's declared source), so the AMI query
permissions are needed before generation. Details and the exact fields:
[aws-runtime-plugin](../aws-runtime-plugin/README.md).

**The runtime's credentials and network (GCE, `packer-gce`).** Application
Default Credentials impersonating the runner service account (`gcloud
auth application-default login
--impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com`);
the source carries the runtime's `project_id`, `zone`, `subnetwork` and
`service_account_email`. On an IAP runtime (`session_mechanism: iap`) the
source sets `use_iap = true`, so the bake tunnels like a session does and
needs the IAP firewall rule (`35.235.240.0/20` -> `tcp:22`) and
`roles/iap.tunnelResourceAccessor` on the RUNNER service account, not only
on the operators; without it every bake times out "waiting for SSH". The
build VM keeps its ephemeral external IP for egress (`omit_external_ip` is
never emitted). Details: [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md)
and the GCP section of [OPERATIONS.md](../../docs/OPERATIONS.md).

**The age identity, for encrypted values.** An admin public key (or any
other value) declared as `ENC[age:...]` is emitted as that ciphertext. The
runner script runs each block through `cs-image-system materialize .
--root-dir "$CSIS_ROOT"` and `packer build .` in the private mirror it
prints (`_private/<same relative path>`), so the process running the
script needs `CSIS_CONFIG_IDENTITY` (the `AGE-SECRET-KEY-1...` string, an
identity file, or a directory of `*.age-identity` files) exactly as a
configuration load does. Packer's `manifest.json` is written in the
mirror; the plugin reads it from there first.

**From the core, nothing to install:** `meta-state/lineage.yaml` and
`meta-state/pins.yaml` (written by `post_finalize_phase`), the run's
`PackerCollector`, the OS builders (base images and their update policy),
the identity, storage and modification plugins whose provisioners land in
the build file. The plugin registers nothing with the state query; the
runtime plugin's `query_images` finds built images by the `csis_*` tags
this plugin stamped.

## Configuration reference

Every field the plugin reads from the YAML it owns (`image_builders:`
entries of `type: packer-ebs` or `type: packer-gce`). Model:
[packer_models.py](src/cs_image_system/packer_plugin/packer_models.py);
inherited fields from
[image_builder_model.py](../base/src/cs_image_system/base/models/image_builder_model.py)
and [builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name` | str | required | The builder name; `safe_name`-normalised; `/` and `\` refused; not `default`. It is the workspace of the emission (`generated/<lifecycle>/<name>/image-generation/block-NNN/`), the `PackerCollector` key, and the `build {}` block's name prefix. Every image's `runtimes[].image_builder` names it. |
| `type` | str | required | `packer-ebs` or `packer-gce`; no aliases. The two behave identically; the runtime decides the source type. |
| `runtime` | str (foreign key to `runtime_builders`) | `default` | The runtime this builder bakes on. `default` is resolved to the default runtime at load; a name that is no runtime is refused at `validate` (stage 48.3). Everything provider-specific comes from it: source type, source block, credentials, machine type, session mechanism, bake finalization, manifest artifact-id parsing, after-build tagging. |
| `executable` | str or null | null | The `executables:` entry whose binary is Packer. Read at generation for `fmt`, `init`, `validate` and the deferred `build`; an entry that does not exist raises at generation (`Executable '<x>' not found for builder '<name>'`), and `validate` reports it first (`Executable <x> specified for provider <name> not found in executables list`). A builder with no executable cannot bake. |
| `required_plugins` | list | `[]` | The `packer { required_plugins { <name> { version, source } } }` block of every block root. Entries are deduplicated per builder; two entries for one plugin must agree on `source` and have satisfiable `version` requirements. |
| `required_plugins[].name` | str | required | The plugin's block label. |
| `required_plugins[].version` | str | required | The version constraint, quoted as given (`'>= 1.0.0'`). |
| `required_plugins[].source` | str or null | null | The `source` attribute (`github.com/hashicorp/amazon`). Omitted from the block when null; Packer then needs the plugin already installed. |
| `required_plugins[].config` | mapping | `{}` | Accepted, not read. |
| `is_default` | bool | `false` | Makes this builder the one an image's `runtimes[]` entry gets when it names none (`image_builder` absent or `default`). Read by the image models, not by this plugin. |
| `tags` | mapping[str, str] | `{}` | Merged into every source's tags first, under the image's tags and the runtime subconfig's tags, under the lineage tags (`csis_*` always win). Read through the subconfig's `get_tags()`. |
| `aliases` | list[str] | `[]` | Extra names an image's `image_builder` may use. |
| `description` | str or null | null | Accepted, not read. |
| `default_machine_type` | str | `default` | Accepted, not read. The bake's machine type is the image's runtime subconfig `machine_type`; its default is the runtime's `default_machine_type`, never this field. |
| `config` | mapping | `{}` | Accepted, not read by this plugin. (`config.admin_public_keys` in the README above is the GLOBAL `config:` of `cfg/_config.yml`, not this field.) |
| `gitignore` | list[str] | `[]` | Accepted, not read for image builders (the emitted `.gitignore` comes from the global `config.gitignore`). |
| `parameters` | | | Refused at load with a message naming the replacement (stage 26). |

The plugin also declares two Packer variables in every block root and
reads them nowhere itself:

| Variable | Type | Emitted default | Used by |
|---|---|---|---|
| `release` | bool | `true` | `force_deregister = !var.release` on every `amazon-ebs` source (the AWS plugin's block), and the `snapshot` local. The runner script passes no `-var`; only a hand-run `packer build -var release=false .` changes it. |
| `base_image_version` | string | `env("BASE_IMAGE_VERSION")` (empty when the variable is unset; no literal default, and the description says so since stage 63 item 3) | The `image_version` local, which no source references. |

The image-side fields the plugin reads (`runtimes[].image_builder`,
`machine_type`, `ssh_username`, `image_identifier`, `tags`, `owners`,
`source_image`, `parent_policy`, `modifications`, `group`, `tests`,
`tags`; a base image's `identity_types`, `storage_types`, `admin_user`,
`admin_public_keys`) are documented in "The image models this builder
consumes" above and in [CONFIGURATION.md](../../docs/CONFIGURATION.md)
sections 5 and 11. An image's `variables:` mapping is accepted by the
image model and read by nothing in this plugin: no `name = value` variable
lines are emitted.

### Variations

- **Base-image lifecycle vs instance-image lifecycle.** `get_blocks()`
  reads the run's current lifecycle: under `base-image` the builder sees
  only the OS builders' base images (OS update, admin user, prerequisites,
  session agent, verification, finalization); under `instance-image` only
  the declared images (modifications, activation, local bundle,
  verification, finalization). Each lifecycle's emission is wiped and
  regenerated on its own; a run of one leaves the other's tree untouched.
  With no lifecycle current (a direct generation call) both ranges are
  emitted, base images first, block numbers continuing.
- **`packer-ebs` vs `packer-gce`.** The builder body is one class; the
  runtime plugin's `packer_source_type()` decides `amazon-ebs` or
  `googlecompute`, and its `packer_source_blocks()` writes the source
  file. A runtime that declares no source type gets `amazon-ebs` and a
  debug log line. On GCE the artifact name is sanitised to a GCE name, the
  tags become `image_labels` (lower-case, `,` -> `-`), the series becomes
  `image_family`, and `build_id_from_artifact` is the identity (the image
  name); on AWS the manifest's `<region>:<ami-id>` becomes the AMI id.
- **`parent_policy: pinned` vs `follow` vs first bake.** `image_to_source`
  asks `pinned_parent_build`. With a pin, the source is an exact query
  (`filters = { image-id = "<ami>" }, owners = ["self"]` on AWS;
  `source_image = <build name>` on GCE), so a rebake never moves the base
  edge. Under `follow` with a newer parent head, the exact query targets
  that head and the pin moves after the bake succeeds (`pin moved ...
  (parent_policy: follow)` in the log, `op: follow` in `pins.yaml`). With
  no pin yet and the parent built in THIS run, there is no id to pin: the
  source is a most-recent name-pattern query on the parent's series
  (`basic-rh-10-aws-east2-runtime*`, owner `self`; `source_image_family`
  on GCE), and `post_finalize_phase` first-binds the pin from the manifest
  (`First bind: image <x> -> build <id>`). With no pin and a parent that
  is NOT baking this run, the pin binds now, to the recorded series head.
- **Selected vs skipped images.** `get_images()` is the single choke
  point: `--only <image>` / `--only <image>@<runtime>`, `--only-runtime`
  (also implied by `--apply-runtime`), `--only none`, and the convergent
  bake decision (`bake_reason`, cached per run) all filter here. A skipped
  image has NO source file, NO entry in `sources`, NO provisioners and NO
  `packer build` line; its absence from `generated/` is not drift. A
  builder whose images are all skipped emits no block at all and no
  commands. `--force-bake <image>` (or `all`) bakes a current image.
- **Modifications present vs absent.** An instance image with no
  `modifications` gets no modification provisioners and no local bundle
  (the three upload provisioners are omitted); activation and
  verification are still emitted. A base image that carries
  `modifications` keeps them out of the build with a warning.
- **Storage types with and without a plugin on this runtime.** A declared
  storage type whose plugins are all bound to ANOTHER runtime produces a
  comment line (`# storage type 'gcs' declared but has no plugin on
  runtime aws-east2-runtime: nothing to bake here`) and no verification
  for it; a plugin with no runtime, or on this runtime, bakes and
  verifies its prerequisites. Identity types are not runtime-bound: the
  first group builder of the type bakes on every runtime.
- **Session mechanism declared vs not.** With `session_mechanism: ssm`
  (AWS) the source gains `ssh_interface = "session_manager"`,
  `iam_instance_profile` and the SSM bootstrap `user_data`, and the base
  image bakes and verifies the SSM agent; with `iap` (GCE) the source
  gains `use_iap = true` and the base image bakes the guest agent; with
  none, Packer connects over SSH to the address it can reach, and the
  provisioner and its assertion are absent.
- **Encrypted vs clear admin keys.** A clear key is written into the
  `authorized_keys` provisioner as text. An `ENC[age:...]` key is written
  as its ciphertext (`emit()`), and the verification assertion computes
  the key body IN THE SHELL (`$(echo '<marker>' | awk '{print $2}')`) so
  the committed HCL carries no plaintext; `materialize` substitutes the
  key in the private mirror before `packer build`. `packer validate` at
  generation runs on the ciphertext form, which is a valid string literal.
- **Runtime bake finalization present vs absent.** A runtime whose
  `bake_finalize_commands()` returns lines (GCE: the google-sudoers
  membership, finding 47) gets one last `provisioner "shell"` after
  verification; AWS returns none and the verification provisioner is the
  last.
- **Dry run vs real run.** Both generate every file and run `packer fmt`,
  `packer init` and `packer validate` in every block at generation. A dry
  run (the default) only logs `[DRY RUN] ... would execute ... packer
  build .` and skips `post_finalize_phase` entirely: no manifest is read,
  no lineage record, no pin, no tag. A `--no-dry-run` run executes the
  runner script's `packer build .` per block through the private mirror,
  then `post_finalize_phase` reads each block's `manifest.json`.
- **One Packer executable vs another.** Each builder names its own
  `executable`; the golden's `some-other-builder` bakes with
  `packer-1.9.4` while `pckr-ebs-ans` uses `packer`. Both are
  version-checked against their own entry's requirement.
- **`base_image_version` set vs unset in the environment.** Only the
  unused `image_version` local changes. Nothing else in the emission
  reads it.

## What it tests and verifies

**At load (pydantic, on every configuration read).** `required_plugins`
entries must carry a string `name` and a string `version` (a missing
`version` is a validation error at load); `parameters:` is refused with the
stage-26 message; `name` and `aliases` may not contain `/` or `\` or be
`default`. `runtime` is resolved to a runtime builder model during
structuring and a name that resolves to nothing is recorded for `validate`.
Verdict: the load fails with pydantic's error text, exit 1, before any
generation.

**At `validate` (and at the start of every run).** Nothing of the plugin's
own beyond the registered `PackerVersionChecker`, which the core rules
call:

- every `executables:` entry's binary exists and, with a `version`
  requirement, satisfies it; the packer entry's version is read with
  `packer version -machine-readable`. One INFO line lists what was checked;
  each failure is a named error and validation fails (exit 1).
- every image builder's `executable` names an existing entry
  (`check_existence_of_executable`).
- every foreign key resolves, `runtime` included (`check_foreign_keys`,
  stage 48.3), with the declared candidates listed.
- the core base-image rules that shape this plugin's provisioners
  ([v2_validation.py](../base/src/cs_image_system/base/v2_validation.py)):
  every declared identity and storage type has a plugin, the admin public
  keys parse as public keys, `admin_user` is not empty, every base image
  has a debug path (a key or a session mechanism), every `tests:` map uses
  known keys, and every instance image chains to a base image whose
  capabilities cover its group's identity type and its instances'
  storage types.

**At generation.** In this order, each a hard stop for the run (exit 1,
the message in the log):

- the `PackerCollector` refuses a plugin requested with two different
  sources, or with version requirements that cannot all be met
  (`HclConfigConflictError`), when the plugins file is rendered;
- the image dependency graph is sorted topologically; a `source_image`
  cycle raises (`Error during topological sort of images`). A
  `source_image` that is not among the builder's images (a base image in
  the instance-image lifecycle) is treated as satisfied and the image
  becomes a block root ([test_block_ordering.py](tests/test_block_ordering.py));
- `image_to_source` raises `ValueError` when the image has no runtime
  subconfig for the builder's runtime, when no provider-specific image is
  registered for its source on that runtime (`No provider-specific image
  registered for source '<parent>' of image <x> on runtime <rt>`), or when
  the final-name template renders empty;
- a modification whose `type` names no modification builder fails an
  assertion (`No mod builder <type> found in context for <image>`);
- after the files are written, `packer fmt .`, `packer init .` and
  `packer validate .` run in every block directory. A nonzero exit is
  logged (`Command failed after phase image-generation: <executable>
  (Return code: N)`) with Packer's stdout and stderr, and the lifecycle
  fails (`after-phase hooks failed for image-generation`). This is the
  syntax and plugin check of the whole root: a provisioner from any
  plugin that does not parse fails here, in a dry run too.

Warnings that do not stop generation: a base image with `modifications`
(ignored), a base image with no OS builder (`skipping OS update`), a
playbook or script named by a modification that is not found beside the
root, in the configuration root or as given (`local mods: <file> for
<mod> not found; the bundle will lack it`; the modification builder's own
copy is unaffected).

**At apply (a `--no-dry-run` run).** `packer build .` is the verdict on
the image: the in-bake verification provisioner runs every assertion under
`set -e` as the last (or second-to-last) provisioner, so a build that
EXISTS is one whose assertions passed. The assertions are: the admin user
exists, has an `authorized_keys`, and it contains each key's body; each
identity plugin's `verify_commands`; each on-runtime storage plugin's
`verify_commands`; the runtime's `session_verify_commands`; for an
instance image the group builder's `activation_verify_commands`; then the
image's declared `tests:` (`files`, `packages`, `commands`,
`services_enabled`, `users`; each written so that it can ABORT a `set -e`
script, stage 53). The count is written as a comment above the
provisioner (`# in-bake verification for base image basic-rh-10: 13
assertion(s)`) and recorded in lineage as `tests: {in_bake: true,
assertions: N}`. A failing build returns nonzero to the runner script; the
run logs `Final execution failed for command in phase image-generation`,
the lifecycle is `failed` in `run-summary.json` and `meta-state/runs.yaml`,
and the exit code is 1. The failed image leaves no manifest entry, hence
no lineage record and no pin: the next run bakes it again for the same
reason.

**After apply (`post_finalize_phase`).** For every block: the manifest is
read from the private mirror first, then from the generated block
directory; only builds whose `packer_run_uuid` is the manifest's
`last_run_uuid` count ([test_manifest_parsing.py](tests/test_manifest_parsing.py)).
Per built image: `Built image <name> -> <id> (from <path>)` at INFO; a
resolved provider-specific image is registered; `record_build` appends the
lineage record (`meta-state/lineage.yaml`: build id, series, runtime,
name, parent, `input_fingerprint`, run, capabilities, mods, `local_mods`,
tests, update policy, chain) and first-binds or follows the parent pin
(`meta-state/pins.yaml`); the runtime re-tags the artifact with
`csis_parent` and `csis_fingerprint` (an idempotent `create-tags`).
Absences are warnings, not failures: `No packer manifest at <path>; built
image ids unavailable` (nothing was built, or the build failed) and `No
runtime builder for <builder>; cannot resolve built images from
manifests`; a manifest that is not JSON is an error line and an empty
result. Either way the run continues and the lineage stays as it was.

**In the state query.** Nothing of the plugin's own. The runtime plugin's
`query_images` lists the cloud's images by the `csis_series` tag this
plugin stamped and diffs them against `lineage.yaml`; an image this
plugin built but whose lineage record is missing (a run that died between
the build and the manifest read) shows there as unrecorded.

**In the package's tests** ([tests/](tests)): block ordering with external
parents, manifest parsing (last run only, region prefix stripped, missing
and malformed manifests). The repository's tests cover the emission
itself: the golden tree under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated),
the assertion enforcement of stage 53, the local bundle, the GCE parity,
and the encrypted-key emission.

## When it fails

Failures that have happened come first, with their dates where the record
has them (the repository's history starts at the public commit of
2026-09-16; what was found before that is dated "before the public
history").

**A false in-bake assertion could not stop the bake (stage 53, fixed
2026-09-20).** Stage 19's first image baked green twice while asserting
`rpm -q vim` on AlmaLinux 10, which has no package of that name; the
instance launched from that AMI then failed the same check. A `packages:`
assertion was written `a || { b && c; }`, and POSIX suppresses `set -e`
inside an AND-OR list, so Packer's shell provisioner ran on. The storage
and runtime prerequisite checks shared the shape, which is the likely
reason an absent EFS client went uncaught at bake time. Symptom: a green
bake, a lineage record with a healthy assertion count, and a machine that
fails the check. Now every generated assertion tests and exits for itself
and names the package on stderr (`package vim is not installed`), and
[test_v2_in_bake_tests_enforce.py](../../tests/test_v2_in_bake_tests_enforce.py)
runs each form under `sh -e` with a sentinel. If a bake is green and the
machine is wrong, read the build log for the verification provisioner's
output and compare the assertion count in the `# in-bake verification`
comment with the lineage record; an assertion that prints nothing and
aborts nothing is the shape to look for.

**GCE bakes timed out "waiting for SSH" after the default SSH firewall
rule was removed (finding 54, found live, before the public history).**
Packer reached the build VM over its external IP on `tcp:22`, which only
worked while the default VPC's `default-allow-ssh` rule existed; deleting
it (deliberate hygiene) timed out every bake. Now an IAP runtime's source
carries `use_iap = true` and the bake tunnels like a session; the runner
service account needs `roles/iap.tunnelResourceAccessor` (the tunnel
authenticates as the impersonated runner) and the IAP firewall rule must
exist. Symptom: `Timeout waiting for SSH` in the build log after the
instance is created. Where to look: the runtime's `session_mechanism`, the
project's firewall rules and the runner's IAM bindings, in that order.

**`scp: /tmp/csis-mods: Not a directory` on the local bundle upload
(found live, before the public history).** Packer's `file` provisioner
cannot create the destination directory. A `provisioner "shell"` with
`mkdir -p /tmp/csis-mods` now precedes the `file` provisioner. If the
message returns, the shell provisioner before the upload was removed or
reordered; the three bundle provisioners must stay together, in
[v2_local_mods.py](src/cs_image_system/packer_plugin/v2_local_mods.py)'s
order.

**`packer fmt` failed on a provisioner line containing `%{` (found live,
before the public history).** An rpm query with `--qf '%{NAME}...'`
inside an `inline` line broke the root at generation, because `${` and
`%{` open Packer's interpolation and directive syntax inside string
literals. `_quote()` in
[v2_provisioners.py](src/cs_image_system/packer_plugin/v2_provisioners.py)
now writes `$${` and `%%{`. Symptom: `Command failed after phase
image-generation: packer (Return code: 1)` at generation with an HCL
parse error naming the line. Any provisioner line that reaches the build
file through another path (a modification builder's own emission) must
escape the same two sequences.

**A `runtimes[].image_builder` naming no builder was accepted for months
(stage 48.3, fixed 2026-09-17).** The foreign-key fallback to the raw id
let the fixture and the live tree name a non-existent image builder; the
image silently baked nowhere. `validate` now refuses: `<Model> '<image>':
field 'image_builder' names '<x>', which is no image_builder_model
(declared: ...)`. If an image you expect to bake has no source file under
`generated/`, run `validate` before reading the bake plan.

**The version checkers never ran (stage 48.1, fixed 2026-09-17).** The
checkers were registered by name while the lookup keyed on the type in
the wrong table, so no `executables:` version requirement had ever been
enforced; the packer requirement in the fixture was rewritten as the floor
alone (`>=1.14, <1.15`) and CI bakes with the latest inside it. A CI
failure that names `packer <version> does not meet its requirement`
means the runner's Packer moved outside the floor, not that the code
changed.

**`manifest.json` entered commits (stage 48.6, fixed 2026-09-17).**
Packer's manifest is run-local since then: named in the emitted
`.gitignore`, never staged by `--commit`, removed from the index of a
configuration repository that tracked it. A manifest you find committed
predates the change.

**A Debian-derived instance image baked as `ec2-user` never authenticated
(AWS plugin, found live, before the public history).** Only the vendor
image's default user receives Packer's key; the AWS source now derives
`ssh_username` from the chain's ROOT base family (`admin` for Debian,
`ubuntu` for Ubuntu, `ec2-user` otherwise) unless something names one,
the last step of the bake-user order every source follows since stage 63
([CONFIGURATION 5.1.1](../../docs/CONFIGURATION.md#511-the-bake-ssh-user)). Symptom: `Timeout waiting for SSH` over the SSM tunnel
on an AWS bake of an image whose base is Debian. See
[aws-runtime-plugin](../aws-runtime-plugin/README.md).

**First SSH to a GCE image refused after the bake (finding 47, found live
at the gce-test launch, before the public history).** The guest agent's
first-boot cleanup of the bake's ssh user aborted its metadata key setup
when that user's `google-sudoers` membership was missing, so no operator
key was ever provisioned. The GCE runtime's `bake_finalize_commands`
guarantee the membership as the bake's last provisioner. A GCE image
whose build file lacks the `# runtime bake finalization` provisioner was
generated by an older tree; regenerate.

**A GCE dask bake fell through to a 1 GB machine and OOMed at 65 minutes
(finding 41, found live, before the public history).** The bake size is
the subconfig `machine_type`, else the runtime's default; set
`machine_type` on the image's runtime entry for anything that compiles.
The image builder's `default_machine_type` is NOT in that chain.

Failures the code raises that have not happened in a recorded run:

| Message or symptom | Meaning | Where to look; what to do |
|---|---|---|
| `packer: binary '/usr/local/bin/packer' not found (declared in cfg/executables.yml; an absolute path, or a name on PATH)` | `validate` (or the run's start) could not find the binary the entry names | `cfg/executables.yml` `binary`; install or symlink Packer there (CI symlinks into `/usr/local/bin`) |
| `packer 1.15.0 does not meet its requirement >=1.14, <1.15 (cfg/executables.yml)` | the installed Packer is outside the declared floor | move the floor deliberately, or install the version the tree names |
| `packer: could not read its version (`/usr/local/bin/packer version -machine-readable`): ...` / `PackerVersionChecker could not parse a version from ...` | the binary exists but its version output is not Packer's (a wrapper, a broken install) | run the command by hand; the fourth comma-separated field of the first line must be the version |
| `Executable <x> specified for provider <builder> not found in executables list.` (validate) / `Executable '<x>' not found for builder '<name>' of type 'packer-ebs'` (generation) | the builder's `executable` names no `executables:` entry | add the entry or fix the name; `validate` catches it first |
| `<Model> '<builder>': field 'runtime' names '<x>', which is no runtime_builder_model (declared: ...)` | the builder's `runtime` resolves to nothing | name a declared runtime; `default` needs a runtime with `is_default: true` |
| `<builder>: `parameters` was retired (stage 26) ...` at load | a `parameters:` key on the builder | delete it; the command line is the plugin's own |
| `Packer plugin '<name>' requested with different sources: [...]` / an unsatisfiable version set (`HclConfigConflictError`) at generation | two `required_plugins` entries for one plugin disagree | keep one entry per plugin per builder |
| `Error during topological sort of images: ...` (a `CycleError`) | `source_image` declarations form a cycle | fix the chain; every instance image must reach a base image |
| `Image <x> does not have runtime-specific data for runtime <rt> required to convert to source configuration.` | the image lists this builder but no subconfig was built for the builder's runtime (usually a wrong or duplicated `image_builder` entry) | the image's `runtimes:` list; one entry per builder, the builder's `runtime` must resolve |
| `No provider-specific image registered for source '<parent>' of image <x> on runtime <rt>; cannot convert to source configuration.` | the parent's image was not resolved on this runtime: the OS builder's vendor query found nothing, the base image is not baked on that runtime, or the parent image does not list this builder | `runtime describe`, the OS builder's `runtimes[]` for that runtime, the parent image's `runtimes[]`; for a vendor query, the AWS or GCP session |
| `Image <x> does not have a valid output image name ...` | the subconfig's final-name template rendered empty | `image_identifier` / the name template on the runtime entry |
| `AssertionError: No mod builder <type> found in context for <image>` | a modification's `type` names no `mod_builders:` entry | fix the `type`; `default` uses the default modification builder |
| `Command failed after phase image-generation: packer (Return code: N)` with Packer's output above it | `packer fmt`, `init` or `validate` failed in a block at generation | the block directory named in the debug log: run the same command there; `init` failures are network or a wrong `source`; `validate` failures are a provisioner from some plugin, or a plugin missing from `required_plugins` |
| `Final execution failed for command in phase image-generation: /usr/local/bin/packer build . (Return code: 1)` | a real bake failed: the build VM never came up, a provisioner exited nonzero, or an in-bake assertion fired | the terminal log of the runner script; Packer prints the failing provisioner and, for a package assertion, `package <p> is not installed`. Nothing to undo: no manifest entry means no record; the next run bakes again. A half-built AMI or GCE image Packer could not clean up shows in `state query` as unrecorded |
| `No packer manifest at <mirror>/manifest.json; built image ids unavailable` (warning) | the build for that block ran nothing or failed before the post-processor | the build log; a dry run never reaches this hook |
| `Could not parse packer manifest <path>: ...` (error, run continues) | the manifest is not valid JSON (a truncated write) | re-run the bake; `packer build` rewrites the manifest |
| `No runtime builder for <builder>; cannot resolve built images from manifests` (warning) | the builder's runtime vanished from the context between generation and finalization | should not occur in one run; report it |
| `Base image <x> carries modifications; base images do not receive modifications -- ignoring them` (warning) | an OS builder declares `modifications` | move them to an instance image |
| `No OS builder found for base image <x>; skipping OS update` (warning) | the base image has no OS builder of the same name | should not occur: base images are synthesised by OS builders |
| `local mods: <file> for <mod> not found; the bundle will lack it` (warning) | the bundle could not copy a playbook or script; the modification's own provisioner may still find it | the file's path relative to the configuration root; `csis-mods rerun` on the image will lack that step |
| `Runtime <rt> declares no packer source type; assuming amazon-ebs` (debug) | the runtime plugin has no `packer_source_type()` | expected only for a runtime plugin that does not bake; the AWS and GCE plugins both answer |
| A bake that runs with a `-SNAPSHOT` name or deregisters an existing AMI | someone passed `-var release=false` by hand; the runner script never does | the exact command that ran; the emission's `force_deregister = !var.release` |

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
  `session_agent_commands`, `bake_ssh_username`, `default_bake_user`,
  `one_bake_user_per_chain`); the bake user itself comes from
  [bake_user.py](../base/src/cs_image_system/base/bake_user.py).
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
- Manuals: [CONFIGURATION.md](../../docs/CONFIGURATION.md) (sections 3, 6,
  11), [OPERATIONS.md](../../docs/OPERATIONS.md) (lifecycles, bake rules,
  credentials, what a green bake proves), [DESIGN.md](../../docs/DESIGN.md)
  (N17, N23, the bake-time-only contract).
- Tests: [tests/](tests) -- block ordering and manifest parsing.
