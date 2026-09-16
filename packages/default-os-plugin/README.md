# cs-image-system-default-os-plugin

The OS builders. An OS builder declares a base operating system (family and
version), how to find its vendor image on each runtime, and how to update its
packages during a bake. This package registers five OS families as builder
types: `debian`, `ubuntu`, `rhel`, `fedora` and `alpine`. Each family is a
model that knows its package manager's update commands and a builder that
turns the model into a resolved base image and, at bake time, an OS-update
provisioner. It also registers the pseudo-builder that wraps each OS
builder's per-runtime entry.

## What it registers

The entry point is declared in [pyproject.toml](pyproject.toml):

```toml
[project.entry-points."cs_image_system.plugins.os"]
default_os_plugin = "cs_image_system.default_os_plugin.main:initialize"
```

`initialize()` in [main.py](src/cs_image_system/default_os_plugin/main.py)
returns a `DefaultOsTypes` metadata object. Its services map each family key
to a model and a builder; its `builders_for_models` binds each model to its
builder and binds the base `OSBuilderBaseImageBuilderSubconfig` to
`DefaultOSImageBuilderConfigBuilder`.

| `type:` key | Model (`VCT.OS_BUILDER_MODEL`) | Builder (`VCT.OS_BUILDER`) |
|---|---|---|
| `debian` | `DebianOsBuilderModel` ([debian_type.py](src/cs_image_system/default_os_plugin/debian_type.py)) | `DebianOsBuilder` ([debian_os_builder.py](src/cs_image_system/default_os_plugin/debian_os_builder.py)) |
| `ubuntu` | `UbuntuOsBuilderModel` ([ubuntu_os_type.py](src/cs_image_system/default_os_plugin/ubuntu_os_type.py)) | `UbuntuOsBuilder` ([ubuntu_os_builder.py](src/cs_image_system/default_os_plugin/ubuntu_os_builder.py)) |
| `rhel` | `RhelOsBuilderModel` ([rhel_type.py](src/cs_image_system/default_os_plugin/rhel_type.py)) | `RhelOsBuilder` ([rhel_os_builder.py](src/cs_image_system/default_os_plugin/rhel_os_builder.py)) |
| `fedora` | `FedoraOsBuilderModel` ([fedora_type.py](src/cs_image_system/default_os_plugin/fedora_type.py)) | `FedoraOsBuilder` ([fedora_os_builder.py](src/cs_image_system/default_os_plugin/fedora_os_builder.py)) |
| `alpine` | `AlpineOsBuilderModel` ([alpine_type.py](src/cs_image_system/default_os_plugin/alpine_type.py)) | `AlpineOsBuilder` ([alpine_os_builder.py](src/cs_image_system/default_os_plugin/alpine_os_builder.py)) |

A YAML entry under `os_builders:` selects a family with `type: <key>`. The
`csis_name()` of model and builder is the key; there are no type aliases.
An entry's own `aliases:` list gives that OS builder extra names.

Also registered, without a `type:` key of its own:

| Class | `csis_name()` | `csis_classifier()` | Role |
|---|---|---|---|
| `DefaultOSImageBuilderConfigBuilder` ([os__image_bldr_config_builder.py](src/cs_image_system/default_os_plugin/os__image_bldr_config_builder.py)) | `default_os_runtime_config_builder` | `VCT.OS_IMAGE_BUILDER_SUBCONFIG` | The builder for every `runtimes[]` entry of every OS builder. It adds nothing to `OsRuntimeConfigBuilderBase`. |

Present in the package but not registered: the intermediate models
`AptOsBuilderModel` ([apt_type.py](src/cs_image_system/default_os_plugin/apt_type.py))
and `DnfOsBuilderModel` ([dnf_type.py](src/cs_image_system/default_os_plugin/dnf_type.py)),
which hold the package-manager logic the families share;
`SourceModel`, `ContainerSourceConfig` and `DockerSourceModel`
([os_sources.py](src/cs_image_system/default_os_plugin/os_sources.py),
[docker_os_source_types.py](src/cs_image_system/default_os_plugin/docker_os_source_types.py)),
which no service list names; and [aws_os_source_types.py](src/cs_image_system/default_os_plugin/aws_os_source_types.py),
which is empty.

## Models

Every family model extends `OsBuilderModel` in
[os_builder_model.py](../base/src/cs_image_system/base/models/os_builder_model.py),
which extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
The families add almost no fields; they differ in the commands they return.

### The base: `OsBuilderModel`

Fields every family inherits:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `name`, `type`, `description`, `aliases` | `NameTyped` | `name`/`type` required | `type` selects the family. |
| `executable`, `is_default`, `config`, `gitignore`, `tags` | `BuilderModel` | | `tags` merge into the base image's tags; `is_default` makes this the OS builder `default` resolves to. |
| `family` | `str` | required | The OS family name. Free text; it drives the SSH-user fallback (`debian` -> `admin`, `ubuntu` -> `ubuntu`, else `ec2-user`), the `os_family` argument the runtime plugins receive, and the AWS root-device guess. |
| `family_version` | `str` | required | Parsed with `packaging.version`; RHEL reads the major to enable repositories. |
| `architecture` | `str` | `DEFAULT` | Declared architecture. |
| `default_primary_disk_size` | `str \| int` | `DEFAULT` (becomes `200`) | Boot disk size in GB for the base image when neither the runtime nor its entry says otherwise. |
| `owners` | `list[str]` | `[]` | Vendor-image owners; the runtime plugin maps them (AWS account ids and aliases, GCE projects and aliases). |
| `query` | `dict` | `{}` | Vendor-image query inputs shared by every runtime entry; an entry's own `query` overrides key by key. |
| `runtimes` | `list[OSBuilderBaseImageBuilderSubconfig]` | required, non-empty | One entry per image builder this OS bakes on. `image_builder` must be unique across entries. |
| `config_username` | `str \| None` | `None` | SSH user for provisioning; the fallback for entries that declare none. |
| `auto_update` | `bool` | `False` | Alias for `update: {policy: full}`. |
| `update` | `dict \| str \| None` | `None` | The update policy: `policy` (`none`, `security`, `packages`, `full`), `packages`, `exclude`, `pin` (`{package: version}`), `refresh_days`. Takes precedence over `auto_update`. |
| `identity_types` | `list[str]` | `[]` | Identity types (for example `okta`) the base image bakes prerequisites for and that images downstream may use. |
| `storage_types` | `list[str]` | `[]` | Storage types (for example `ebs`, `efs`, `s3`, `pd`, `gcs`) the base image bakes prerequisites for. |
| `admin_user` | `str` | `csisadmin` | The mandatory local admin user baked into the base image. |
| `admin_public_keys` | `list[str] \| None` | `None` | Public keys for that user; `None` uses the global `admin_public_keys`. |
| `local_test_image` | `str \| None` | `None` | Container image standing in for this OS when modifications are tested locally. |
| `tests` | `dict` | `{}` | In-bake assertions (`packages`, `files` with `path`/`contains`) for the base image. |

Each `runtimes[]` entry is an `OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py):

| Field | Type | Default | Meaning |
|---|---|---|---|
| `image_builder` | `str` | `DEFAULT` | The image builder that bakes this OS here; `default` resolves to the runtime's `default_image_builder`. Its runtime is the entry's runtime. |
| `name` | `str \| None` | `None` | Any unique label. |
| `default_machine_type` | `str \| None` | `None` | Bake machine type; else the image builder's, else the runtime's. |
| `default_primary_disk_size` | `int` | `100` | Declared; the base image takes the OS builder's value. |
| `owners` | `list[str]` | `[]` | Appended after the OS builder's owners and the runtime's `default_owners`. |
| `query` | `dict` | `{}` | Overrides the OS builder's `query` key by key. |
| `ssh_username` | `str` | `DEFAULT` | Bake user on this runtime; unset falls back to the OS builder's `config_username`, then the runtime's `default_config_username`, then the family fallback. |
| `auto_update` | `bool \| None` | `None` | `true` turns a `none` policy into `full` for bakes on this runtime. |
| `tags` | `dict` | `{}` | Merged over the OS builder's tags. |
| `tests` | `dict \| None` | `None` | When set, replaces the OS builder's `tests` for bakes on this runtime. |
| `image_id`, `image_name` | `str \| None` | `None` | Declared; not read by the emitters. |

`aliases` on an entry are refused.

The base `commands_for_policy()` knows only `none` (no commands) and `full`
(`get_command_to_update()`); any other policy, or a pin or exclude, raises
`NotImplementedError` unless a family overrides it.

### `AptOsBuilderModel` (not registered) and the `debian` and `ubuntu` families

`AptOsBuilderModel` adds no fields. It overrides:

- `get_command_to_update()`: a single `sudo -s` heredoc running `apt-get update`, `upgrade -y`, `full-upgrade -y`, `autoremove -y`, `autoclean -y`.
- `commands_for_policy(policy)`: `apt-get update`; `apt-mark hold` for every `exclude`; `security` upgrades only packages whose candidate comes from a `security` suite (via a simulated `dist-upgrade` piped through `awk`), plus `--only-upgrade` of any named `packages`; `packages` upgrades only the named ones; `full` runs the four upgrade steps; every `pin` is installed as `package=version` with `--allow-downgrades` and held; the excludes are unheld at the end.

`DebianOsBuilderModel` (`type: debian`) and `UbuntuOsBuilderModel`
(`type: ubuntu`) extend it and add nothing but their name. They do not
support subscription management or dnf-style version locks.

### `DnfOsBuilderModel` (not registered) and the `rhel` and `fedora` families

`DnfOsBuilderModel` adds no fields. It provides `repo_setup_commands()`
(empty by default) and overrides `commands_for_policy(policy)`: the repo
setup, `dnf clean all`, then `--exclude=<pattern>` on every update for each
`exclude`; `security` runs `dnf -y update --security` plus a guarded
targeted update of any named `packages`; `packages` runs only the targeted
update; `full` runs `dnf -y upgrade`, `autoremove`, `autoclean`; every
`pin` installs `package-version` and adds a `versionlock` (installing the
plugin first). Every update command is retried once after a fresh
`dnf clean all`, and targeted updates run only when `dnf check-update`
reports pending updates, so both dnf 4 and dnf 5 exit cleanly.

`RhelOsBuilderModel` (`type: rhel`) adds one field:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `subscription_id` | `str \| None` | `None` | Declared; nothing reads it. |

It overrides `repo_setup_commands()`: the `family_version` major must be 8,
9 or 10 (anything else is a `ValueError` at generation); when the system is
registered with `subscription-manager`, it refreshes and enables exactly the
`baseos`, `appstream` and `codeready-builder` repositories for that major;
an unregistered system (a vendor RHUI or pay-as-you-go image, AlmaLinux,
Rocky) prints a note and uses its repositories as they are. Its
`get_command_to_update()` is the `full` policy through those commands.

`FedoraOsBuilderModel` (`type: fedora`) adds no fields and no repository
setup. Its `get_command_to_update()` returns `dnf clean all`, `dnf -y
upgrade --refresh`, `dnf -y autoremove`; the bake path is the shared dnf
`commands_for_policy()`, which uses `dnf -y upgrade` for `full`.

### `AlpineOsBuilderModel` (`type: alpine`)

Extends `OsBuilderModel` directly and adds no fields. Its
`get_command_to_update()` returns `sudo apk update` and `sudo apk upgrade
--available`. It relies on the base `commands_for_policy()`, so it supports
only `policy: none` and `policy: full` (or `auto_update: true`); `security`,
`packages`, `exclude` and `pin` raise `NotImplementedError`. The commands
use `sudo`; an Alpine image that ships only `doas` needs the command list
changed.

### What the models do not support

No family model accepts unknown keys (the shared model config forbids
extras). None validates `family` against a fixed list: the `OSFamilies`
enum in [constants.py](../base/src/cs_image_system/base/constants.py) exists
but is not consulted. Modifications declared on an OS builder are ignored
with a warning: base images receive no modification elements, only the OS
update.

## The builder

Every family builder extends `OsBuilderBase` in
[builder_base_os.py](../base/src/cs_image_system/base/basic/builder_base_os.py)
and adds only `csis_name()`. The per-runtime pseudo-builder
`DefaultOSImageBuilderConfigBuilder` extends `OsRuntimeConfigBuilderBase`
in the same file and adds only its name. The hooks that do the work, in the
order a run reaches them:

| When | Hook | What it does |
|---|---|---|
| Configuration load | `OsBuilderBase.__post_init__()` | Stamps the builder's global id on every `runtimes[]` entry so each entry knows its OS builder. |
| Resolution | runtime's `query_provider_image(entry)` | Not this plugin's hook, but its input: the entry's merged `owners` and `query` are what the runtime plugin turns into an AMI or GCE image lookup. |
| Resolution | `generate_resolved_image(phase, image_id, owners, query_result, resolved, resolutions)` | Synthesises one `BaseImage` ([base_image.py](../base/src/cs_image_system/base/models/base_image.py)) named after the OS builder, `source_image: self`, with one runtime subconfig per `runtimes[]` entry: the entry's image builder's runtime, the resolved vendor image identifier for that runtime, the machine type (entry, else image builder, else runtime), the merged tags, the owners, the SSH user (entry, else the family fallback), and `auto_update`. The image also carries the OS builder's `identity_types`, `storage_types`, `admin_user`, `admin_public_keys` and `tests`. The image is registered so image builders and downstream images can chain from it. |
| Image generation | `generate_items_for_os_update(image, image_builder, phase, build_path)` | Called by the packer image builder for each base image it bakes. Computes the effective policy (`update`, else `auto_update`, promoted to `full` when the runtime entry says `auto_update: true`); when it is not a no-op, asks the model for `commands_for_policy()`, appends the package-manifest commands (`/var/lib/csis/packages.txt`), and returns a `provisioner "shell"` scoped with `only = ["<source>.<image>"]` for the build file. Nothing is returned for a `none` policy. |

What an OS builder contributes to an image bake, then, is: the vendor image
the bake starts from (through its `owners` and `query`), the bake's SSH user
and machine type defaults, the boot disk size default, the tags, and the OS
update provisioner. The admin user, the identity and storage prerequisites,
the session agent and the in-bake tests it declares are carried on the
synthesised base image and emitted by the packer, identity, storage and
runtime plugins, not by this one.
[tests/test_os_update_hook.py](tests/test_os_update_hook.py) pins the
update hook: emitted only with a policy, scoped to the image, and each
family's full-update command list.

## Emission

This plugin writes no files of its own. Its provisioner lines land in the
image builders' build files, and its resolved vendor images in their source
files, under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated):

- [pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl):
  one `# OS update for base image <name> (policy=..., packages=[...],
  exclude=[...], pin={...}, <family>)` shell provisioner per base image with
  a policy. `basic-rh-10` (`rhel`, `security` plus `openssl`, excluding
  `kernel*`) shows the guarded `subscription-manager` block, `dnf clean
  all`, `dnf -y update --security --exclude=kernel*` with its retry, the
  `check-update` guarded targeted update of `openssl`, and the package
  manifest. `basic-rhel-9` shows the same without a targeted package.
  `my-deb-11` declares no policy and gets no update provisioner.
- [pckr-gce-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-gce-ans/image-generation/block-000/pckr-gce-ans-image-generation-block-000-build.pkr.hcl):
  the same `basic-rh-10` provisioner scoped to `googlecompute.basic-rh-10`.
- [pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-source-basic-rh-10-block-000.pkr.hcl):
  the resolved vendor image (`image-id` and `owners` in the `data
  "amazon-ami"` block), `instance_type = "t3.medium"` from the entry's
  `default_machine_type`, `ssh_username = "ec2-user"` from the family
  fallback, and `volume_size = 200` from `default_primary_disk_size`.

## Example configuration

From
[tests/fixtures/config/cfg/os-builders.yml](../../tests/fixtures/config/cfg/os-builders.yml),
the default OS builder, baked on both runtimes:

```yaml
os_builders:
  - name: basic-rh-10
    is_default: true
    type: rhel
    family: rhel
    family_version: 10
    # the only identity and storage types usable downstream of this base image
    identity_types: [okta]
    storage_types: [ebs, efs, s3, pd, gcs]
    # in-bake assertions; the bake fails if any fails
    tests:
      packages: [nfs-utils]
      files:
        - path: /etc/yum.repos.d/oktapam-stable.repo
          contains: "dist.scaleft.com"
    # security patches plus openssl, never the kernel; the bake records the package manifest
    update:
      policy: security
      packages: [openssl]
      exclude: ["kernel*"]
    runtimes:
      - name: aws-my-rhel8
        default_machine_type: t3.medium
        # AlmaLinux OS Foundation's official x86_64 AMIs
        owners:
          - "self"
          - "764336703387"
        query:
          filters:
            name: "AlmaLinux OS 10*x86_64"
            state: available
            root_device_type: ebs
            architecture: x86_64
            virtualization_type: hvm
      - name: gcp-my-rh10
        image_builder: pckr-gce-ans
        # one bake user for every GCE bake
        ssh_username: packer
        # replaces the builder-level tests on this runtime
        tests:
          packages: [google-guest-agent]
          files:
            - path: /etc/yum.repos.d/oktapam-stable.repo
              contains: "dist.scaleft.com"
        default_machine_type: e2-small
        owners:
          - almalinux-cloud
        query:
          filters:
            name: "almalinux-10-v*"
```

The first entry names no `image_builder`, so it resolves to the default
runtime's `default_image_builder`. The AWS-only filter keys in its query are
dropped by the GCE runtime plugin, which is why the second entry can be
terse. The same file declares `my-deb-11` (`type: debian`, no update policy)
and `basic-rhel-9` (`type: rhel`, `security` policy).

## Related

- [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md): how each runtime turns an entry's `owners` and `query` into a vendor image.
- Base classes: [os_builder_model.py](../base/src/cs_image_system/base/models/os_builder_model.py), [os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py), [update_policy.py](../base/src/cs_image_system/base/models/update_policy.py), [base_image.py](../base/src/cs_image_system/base/models/base_image.py), [builder_base_os.py](../base/src/cs_image_system/base/basic/builder_base_os.py).
- [docs/DESIGN.md](../../docs/DESIGN.md) for the capability axes (`identity_types`, `storage_types`) and the admin user; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.

- [The configuration reference](../../docs/CONFIGURATION.md) — every field of the YAML this plugin reads, with an example.
