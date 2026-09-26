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
returns a `DefaultOsTypes` metadata object (metadata version `1`, Python
floor `3.13`). Its services map each family key to a model and a builder;
its `builders_for_models` binds each model to its builder and binds the base
`OSBuilderBaseImageBuilderSubconfig` to `DefaultOSImageBuilderConfigBuilder`.

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
| `family` | `str` | required | The OS family name. Free text; it drives the SSH-user fallback (`debian` -> `admin`, `ubuntu` -> `ubuntu`, else `ec2-user`), the `os_family` argument the runtime, identity and storage plugins receive, the AWS root-device guess and the mod-test container image. It does not choose the package manager; `type` does. |
| `family_version` | `str` | required | A bare number is coerced to a string. Parsed with `packaging.version`; RHEL reads the major to enable repositories. Also the mod-test container tag. |
| `architecture` | `str` | `DEFAULT` | Declared architecture; handed to the runtime's provider-specific image when not the default. |
| `default_primary_disk_size` | `str \| int` | `DEFAULT` (becomes `200`) | Bake disk size in GB for the base image when neither the runtime (`default_disk_size`) nor the entry for that runtime (`default_primary_disk_size`) declares one. The order is `lineage.bake_disk_size`, the one rule both packer sources and the input fingerprint use (stage 63); see the Variations below. |
| `owners` | `list[str]` | `[]` | Vendor-image owners; the runtime plugin maps them (AWS account ids and aliases, GCE projects and aliases). |
| `query` | `dict` | `{}` | Vendor-image query inputs shared by every runtime entry; an entry's own `query` overrides key by key. |
| `runtimes` | `list[OSBuilderBaseImageBuilderSubconfig]` | required, non-empty | One entry per image builder this OS bakes on. `image_builder` must be unique across entries; two entries naming one image builder are refused at load. |
| `config_username` | `str \| None` | `None` | The sudo-capable ssh user on this OS's vendor image, for every runtime whose entry names none: step 3 of [the bake-user order](../../docs/CONFIGURATION.md#511-the-bake-ssh-user), after the image's and this OS's entry and ahead of anything the runtime says (stage 63 item 22; it was read by nothing before 2026-09-25). |
| `auto_update` | `bool` | `False` | Alias for `update: {policy: full}`. |
| `update` | `dict \| None` | `None` | The update policy, always a mapping: `policy` (`none`, `security`, `packages`, `full`), `packages`, `exclude`, `pin` (`{package: version}`), `refresh_days`. Takes precedence over `auto_update`. A bare policy name (`update: none`) is refused; write `update: {policy: none}`. |
| `identity_types` | `list[str]` | `[]` | Identity types (for example `okta`) the base image bakes prerequisites for and that images downstream may use. |
| `storage_types` | `list[str]` | `[]` | Storage types (for example `ebs`, `efs`, `s3`, `pd`, `gcs`) the base image bakes prerequisites for. |
| `admin_user` | `str` | `csisadmin` | The mandatory local admin user baked into the base image. |
| `admin_public_keys` | `list[str] \| None` | `None` | Public keys for that user; `None` uses the global `config.admin_public_keys`. |
| `local_test_image` | `str \| None` | `None` | Container image standing in for this OS when modifications are tested locally. Unset derives one from `family` and `family_version`: `almalinux:<v>` for `rhel` 10 and above, `rockylinux:<v>` below, `debian:<v>`, `ubuntu:<v>`, `fedora:<v>`. |
| `tests` | `dict` | `{}` | In-bake assertions (`packages`, `files` with `path`/`contains`) for the base image. |

Each `runtimes[]` entry is an `OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py):

| Field | Type | Default | Meaning |
|---|---|---|---|
| `image_builder` | `str` | `DEFAULT` | The image builder that bakes this OS here; `default` resolves to the runtime's `default_image_builder`. Its runtime is the entry's runtime. |
| `name` | `str \| None` | `None` | Any unique label. |
| `type` | `str` | the OS builder's name (templated) | Set by the loader; accepted, not read by the emitters. |
| `description` | `str` | templated | Free text. |
| `image_id` | `str \| None` | `None` | Pins the vendor image this OS bakes from on this runtime (stage 63). When set, the vendor query (`owners` and `query`) is skipped and the runtime looks the image up by id through its `query_provider_image_by_id` hook: on AWS the AMI id (`ami-...`), on GCE the image name, searched in the entry's owner projects. An id the provider does not know stops resolution. Pinning makes a base bake reproducible: the same vendor image every time, where a query follows the newest match. The id is part of the input fingerprint's vendor-source record, so setting or changing it re-bakes the base on that runtime. It used to be accepted and read by nothing (until 2026-09-25). |
| `default_machine_type` | `str \| None` | `None` | Bake machine type; else the image builder's, else the runtime's. |
| `default_primary_disk_size` | `int \| None` | `None` | The base image's bake disk in GB on this runtime, when declared (stage 63). The runtime's own `default_disk_size` still wins when the runtime declares one (finding 51, GCE); unset, the OS builder's `default_primary_disk_size` (200 by default) applies. Until 2026-09-25 it defaulted to `100` and was read only by the input fingerprint, while AWS bakes used the OS builder's 200. |
| `owners` | `list[str]` | `[]` | Appended after the OS builder's owners and the entry's runtime's `default_owners` (the runtime is the entry's image builder's; stage 63 item 22 fixed the lookup, which never found it). |
| `query` | `dict` | `{}` | Overrides the OS builder's `query` key by key. |
| `ssh_username` | `str` | `DEFAULT` | Bake user on this runtime for this OS and every image built on it: step 2 of [the bake-user order](../../docs/CONFIGURATION.md#511-the-bake-ssh-user). It wins over the OS builder's `config_username` and everything the runtime declares, on both clouds (stage 63 item 23; a runtime's `ssh_username` used to override it). |
| `auto_update` | `bool \| None` | `None` | `true` turns a `none` policy into `full` for bakes on this runtime. |
| `tags` | `dict` | `{}` | Merged over the OS builder's tags. |
| `tests` | `dict \| None` | `None` | When set, replaces the OS builder's `tests` for bakes on this runtime. |
| `config` | `dict` | `{}` | A free-form mapping for templating (stage 63). `get_config()` returns it (until 2026-09-25 it returned `{}` always), and the load-time template walker lets this entry's `config` shadow the enclosing `config` key by key for the entry's subtree, so `{{ config.x }}` in the entry's templated fields (for example `description`) resolves from the entry's own `config` first, then the OS builder's, then the document's. |

`image_name` is no longer a field (stage 63): it was accepted and read by
nothing, and declaring it is now an unknown-key refusal at load (`Extra
inputs are not permitted`). Pin a vendor image with `image_id`. The input
fingerprint's vendor-source record still carries an `image_name: null`
member, so removing the field moved no fingerprint.

`aliases` on an entry are refused.

The base `commands_for_policy()` knows only `none` (no commands) and `full`
(`get_command_to_update()`, which the base answers with an empty list);
any other policy, or a pin or exclude, raises `NotImplementedError` unless a
family overrides it. The apt and dnf families override
`commands_for_policy()` itself, so the bake never reaches their
`get_command_to_update()`; only `alpine` answers `full` through it.

### `AptOsBuilderModel` (not registered) and the `debian` and `ubuntu` families

`AptOsBuilderModel` adds no fields. It overrides one method:

- `commands_for_policy(policy)`: `apt-get update`; `apt-mark hold` for every `exclude`; `security` upgrades only packages whose candidate comes from a `security` suite (via a simulated `dist-upgrade` piped through `awk`), plus `--only-upgrade` of any named `packages`; `packages` upgrades only the named ones; `full` runs `upgrade`, `full-upgrade`, `autoremove` and `autoclean`, one `sudo` line each; every `pin` is installed as `package=version` with `--allow-downgrades` and held; the excludes are unheld at the end. Every `apt-get` command it emits carries `-o DPkg::Lock::Timeout=600` (stage 63), so a bake waits up to ten minutes for a concurrent `unattended-upgrades` on a freshly booted machine instead of failing on the lock; until 2026-09-25 no lock wait was set.

It used to override `get_command_to_update()` as well, with a single
`sudo -s` heredoc that nothing on the bake path reached; stage 63 removed
it (2026-09-25).

`DebianOsBuilderModel` (`type: debian`) and `UbuntuOsBuilderModel`
(`type: ubuntu`) extend it and add nothing but their name. They do not
support subscription management or dnf-style version locks.
`DebianOsBuilderModel` is keyword-only (`kw_only`) like every other family
model, and the `ubuntu` registration in `main.py` lists the model before
the builder like the others (both tidied in stage 63; neither changes what
a configuration may say).

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
| `subscription_id` | `str \| None` | `None` | Accepted and not read: reserved for a future step that registers the bake machine with `subscription-manager` (stage 63 kept it on purpose). Today the plugin never registers a system. |

At load (`RhelOsBuilderModel.__post_init__`, stage 63) the `family_version`
must parse and its major must be 8, 9 or 10, whatever the update policy;
anything else is a `ValueError` and the configuration does not load. Until
2026-09-25 the check ran only when update commands were generated, so a
`policy: none` OS builder with an unsupported major was never refused.

It overrides `repo_setup_commands()` (the major check is the load's, stage 67): when
the system is registered with `subscription-manager`, it refreshes and
enables exactly the `baseos`, `appstream` and `codeready-builder`
repositories for that major; an unregistered system (a vendor RHUI or
pay-as-you-go image, AlmaLinux, Rocky) prints a note and uses its
repositories as they are. The bake path goes through
`commands_for_policy()` directly (stage 67 removed rhel's unreachable
`get_command_to_update()`/`commands_to_update()`; the base hook remains as
alpine's one path).

`FedoraOsBuilderModel` (`type: fedora`) adds no fields, no repository
setup and no methods: every bake goes through the shared dnf
`commands_for_policy()`, which uses `dnf -y upgrade` for `full`. It used to
carry its own `get_command_to_update()` (`dnf clean all`, `dnf -y upgrade
--refresh`, `dnf -y autoremove`), which only the unit tests called; stage
63 removed it (2026-09-25).

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
| Resolution | runtime's `query_provider_image(entry)`, or `query_provider_image_by_id(entry, image_id)` when the entry declares `image_id` | Not this plugin's hooks, but their input: the entry's merged `owners` and `query` are what the runtime plugin turns into an AMI or GCE image lookup; a declared `image_id` skips that query and is looked up by id instead (stage 63). |
| Resolution | `generate_resolved_image(phase, image_id, owners, query_result, resolved, resolutions)` | Synthesises one `BaseImage` ([base_image.py](../base/src/cs_image_system/base/models/base_image.py)) named after the OS builder, `source_image: self`, with one runtime subconfig per `runtimes[]` entry: the entry's image builder's runtime, the resolved vendor image identifier for that runtime, the machine type (entry, else image builder, else runtime), the merged tags, the owners, the SSH user (entry, else the family fallback), and `auto_update`. The image also carries the OS builder's `identity_types`, `storage_types`, `admin_user`, `admin_public_keys` and `tests`. The image is registered so image builders and downstream images can chain from it. |
| Image generation | `generate_items_for_os_update(image, image_builder, phase, build_path)` | Called by the packer image builder for each base image it bakes. Computes the effective policy (`update`, else `auto_update`; a no-op policy is promoted to `full` when the runtime entry says `auto_update: true`); when it is not a no-op, asks the model for `commands_for_policy()`, appends the package-manifest commands (`/var/lib/csis/packages.txt`), and returns a `provisioner "shell"` scoped with `only = ["<source>.<image>"]` for the build file. Nothing is returned for a no-op policy (`none` without a `pin`). |

What an OS builder contributes to an image bake, then, is: the vendor image
the bake starts from (through its `owners` and `query`, or a pinned
`image_id`), the bake's SSH user
and machine type defaults, the boot disk size default, the tags, and the OS
update provisioner. The admin user, the identity and storage prerequisites,
the session agent and the in-bake tests it declares are carried on the
synthesised base image and emitted by the packer, identity, storage and
runtime plugins, not by this one.
[tests/test_os_update_hook.py](tests/test_os_update_hook.py) pins the
update hook: emitted only with a policy, scoped to the image, and each
family's full-update command list (for the apt families, that every
`apt-get` line carries `DPkg::Lock::Timeout=600`).

## Emission

This plugin writes no files of its own. Its provisioner lines land in the
image builders' build files, and its resolved vendor images in their source
files, under
[tests/fixtures/v2_golden/generated](../../tests/fixtures/v2_golden/generated):

- [pckr-ebs-ans-image-generation-block-000-build.pkr.hcl](../../tests/fixtures/v2_golden/generated/base-image/pckr-ebs-ans/image-generation/block-000/pckr-ebs-ans-image-generation-block-000-build.pkr.hcl):
  one `# OS update for base image <name> (policy=..., packages=[...],
  exclude=[...], pin={...}, <type>)` shell provisioner per base image with
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
  `default_machine_type`, `ssh_username = "ec2-user"` from the AWS
  runtime's family default (the last step of the bake-user order), and `volume_size = 200` from `lineage.bake_disk_size`: the
  AWS runtime declares no `default_disk_size` and the entry no
  `default_primary_disk_size`, so the OS builder's default of 200 applies.

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
and `basic-rhel-9` (`type: rhel`, `security` policy excluding `kernel*`).

## Prerequisites and integration

This plugin holds no credentials, opens no session and calls no API of its
own. Everything it needs from outside the system is reached through another
plugin's configuration; what it needs from the world is listed here so a
bake does not surprise anyone.

| Prerequisite | Why | How the plugin finds it |
|---|---|---|
| A vendor image visible to the runtime's credentials | The base image bakes FROM it. The query (or, for a pinned `image_id`, the lookup by id) is made by the runtime plugin at resolution, with the credentials that plugin configures (an AWS profile, GCP application default credentials); this plugin only supplies the inputs. | `owners` and `query` on the OS builder, overridden key by key by the entry's `owners` and `query`; the runtime's `default_owners` are appended. An entry's `image_id` replaces the query with a lookup of that one image (on GCE still searched in the entry's owner projects). Which runtime: the entry's `image_builder`, whose image builder names its runtime. See [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md) for the credential fields. |
| A sudo-capable login on the vendor image | Every update command runs through `sudo`; packer connects as this user with a temporary key. | The bake-user order (CONFIGURATION 5.1.1): the image's entry, then this OS builder's entry `ssh_username`, its `config_username`, the runtime's `ssh_username` and `default_config_username`, and last the runtime's family default: on AWS `family: debian` -> `admin`, `ubuntu` -> `ubuntu`, anything else -> `ec2-user`; on GCE `packer`, because `googlecompute` creates the account from metadata keys. |
| `sudo` on the image | The command lists are written with `sudo` on every line, Alpine included. | Nothing configurable; an image without `sudo` (an Alpine that ships only `doas`) fails at the first command. |
| Network egress from the bake machine to the package repositories | `apt-get`, `dnf` and `apk` fetch metadata and packages during the bake. On a cloud vendor RHEL/Alma image that is the RHUI or vendor mirror; on Debian/Ubuntu the vendor mirrors. | The runtime's networking (subnet, NAT, security groups), not this plugin. |
| A registered `subscription-manager` when RHEL subscription repositories are wanted | The `rhel` type enables `rhel-<major>-for-x86_64-{baseos,appstream}-rpms` and `codeready-builder-for-rhel-<major>-x86_64-rpms` only if `subscription-manager identity` succeeds. The plugin never registers a system; `subscription_id` is not read (it is reserved for a future register step). | Whether the vendor image is registered. An unregistered image prints `not subscription-registered (RHUI image): using vendor repos as-is` and continues. |
| `python3-dnf-plugin-versionlock` or `dnf-plugins-core` in the repositories | Only when a `pin` is declared on a dnf family; the plugin installs one, then the other, before adding the lock. | The `update.pin` mapping. |
| A bake machine with enough memory for the package manager | A 1 GB machine is OOM-killed under `dnf update` (found 2026-08-31). | The entry's `default_machine_type`, else the image builder's, else the runtime's `default_machine_type`. |
| docker and a pullable container image, for local modification tests only | `just test-mods` runs modifications against a container standing in for this OS. | `local_test_image`; unset, derived from `family` and `family_version` (`almalinux:<v>` for `rhel` 10 and above, `rockylinux:<v>` below, `debian:<v>`, `ubuntu:<v>`, `fedora:<v>`). A family the table does not know gets no image and the test is skipped. |
| Python 3.13 | The plugin metadata declares it. | The package's `requires-python` and the metadata object. |

Beyond that: nothing beyond the core. The packer, identity, storage and
runtime plugins that consume the synthesised base image carry their own
prerequisites.

## Configuration reference

The YAML this plugin owns is the `os_builders:` list in
`cfg/os-builders.yml` ([docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)
section 5). Every field is listed in the tables under
[Models](#models) above; this section collects them by who reads them.

Read by this plugin or the OS builder base: `name`, `type`, `family`,
`family_version`, `architecture`, `default_primary_disk_size`, `tags`,
`owners`, `query`, `runtimes`, `auto_update`, `update`, `identity_types`,
`storage_types`, `admin_user`, `admin_public_keys`, `local_test_image`,
`tests`, `is_default`, `aliases`, `description`; on an entry
`image_builder`, `name`, `default_machine_type`, `owners`, `query`,
`ssh_username`, `auto_update`, `tags`, `tests`; on the OS builder
`config_username` (since stage 63 item 22); and, since stage 63, on an
entry `image_id` (pins the vendor image), `default_primary_disk_size` (the
bake disk on that runtime) and `config` (templating scope).

Accepted, not read (the loader takes them, nothing consults them): on the
OS builder `executable`, `config`, `gitignore`, and `subscription_id`
on `rhel` (reserved for a future register step); on an entry `type` and
`description` (templated at load, not read by the emitters).

Refused: `image_name` on an entry, removed in stage 63 (an unknown key);
`parameters` on an OS builder, retired in stage 26.

The `update` mapping ([update_policy.py](../base/src/cs_image_system/base/models/update_policy.py)):

| Key | Type | Default | Meaning |
|---|---|---|---|
| `policy` | `str` | `none` (`full` when `auto_update: true`) | `none`, `security`, `packages` or `full`; case-insensitive, whitespace stripped. A bare string in place of the mapping (`update: none`) is refused: the field is a mapping, so the load refuses it, and `UpdatePolicy.from_config` refuses anything that is not a mapping (stage 63 removed a branch there that seemed to accept a bare name, which the load never let through). |
| `packages` | `list[str]` | `[]` | With `packages`: exactly these are updated. With `security`: also these, after the security update. Ignored by `full` and `none`. |
| `exclude` | `list[str]` | `[]` | Patterns never touched: `--exclude=` on every dnf update, `apt-mark hold` around the apt run. May not overlap `packages`. |
| `pin` | `mapping[str, str]` | `{}` | Package to version, installed at that version and locked (`versionlock` on dnf, `apt-mark hold` on apt). Sorted by package name. A version may not be empty or contain a space. |
| `refresh_days` | `int \| None` | `None` | Re-bake the series when its head is at least this many days old; must be positive. The only way package updates reach a new build without a configuration change. |

### Variations

- When `update:` is declared, `auto_update` on the OS builder is ignored
  for the policy name (`update.policy` defaults to `full` only when
  `auto_update: true` and the mapping names no `policy`). When neither is
  declared, the policy is `none` and no update provisioner is emitted.
- When the runtime entry says `auto_update: true` and the effective policy
  is a no-op, the bake on that runtime runs `policy: full` instead of
  nothing. It does not change a non-no-op policy. `auto_update: false` on
  the entry does not suppress a declared policy.
- When `policy: none` is declared with a `pin`, the policy is not a no-op:
  the family's commands run (repo setup and `clean all` on dnf, `apt-get
  update` on apt) and the pins are installed and locked, with no other
  update.
- When the OS builder is `type: rhel` or `type: fedora`, the update runs
  through dnf with the retry and `check-update` guard; when `type: debian`
  or `type: ubuntu`, through apt with hold/unhold; when `type: alpine`, only
  `none` and `full` are possible and anything else raises
  `NotImplementedError` at generation. The package manager follows `type`,
  never `family`.
- When `family` is `debian` or `ubuntu`, the fallback bake user is `admin`
  or `ubuntu` and the AWS root device guess is `/dev/xvda`; any other
  family gets `ec2-user` and `/dev/sda1`. The AWS runtime prefers the
  vendor query's `RootDeviceName` when it has one.
- When the entry declares `ssh_username`, it is the bake user on that
  runtime for every image of the chain, whatever the runtime declares;
  when it does not, the OS builder's `config_username`, then the runtime's
  `ssh_username`, then its `default_config_username`, then the runtime's
  family default (`packer` on GCE). An image's own runtime entry can name
  a user for itself alone, except that on GCE it must match the chain's.
  The whole order is in CONFIGURATION 5.1.1 (stage 63 items 22 and 23).
- When the entry declares `tests`, they replace the OS builder's `tests`
  for bakes on that runtime (not merge); an entry without `tests` inherits
  the builder's.
- When the entry declares `default_machine_type`, the bake uses it; else
  the image builder's; else the runtime's; else a warning and the `default`
  sentinel.
- The bake disk follows one rule, `lineage.bake_disk_size`, which both
  packer sources (AWS `volume_size`, GCE `disk_size`) and the input
  fingerprint use (stage 63): the runtime's own `default_disk_size` when it
  declares one (finding 51; the GCE runtimes do); else the entry's
  `default_primary_disk_size` for that runtime when declared; else the OS
  builder's `default_primary_disk_size` (200 GB unset). Before 2026-09-25
  the fingerprint hashed the entry's value (then defaulting to 100) while
  AWS bakes used the OS builder's 200; because the fingerprint now hashes
  what is baked, every AWS base image's recorded fingerprint moved once and
  reads DUE until `lineage restamp --runtime <rt> --commit` records the new
  one. GCE was unaffected, since its runtime's `default_disk_size` already
  won.
- When the entry declares `image_id`, the base-image run skips the vendor
  query on that runtime and looks the image up by id; `owners` and `query`
  are not used for the lookup on AWS, and on GCE only the owner projects
  are (the name is searched there). An unknown id stops resolution. Without
  `image_id` the query picks the newest matching image, so a base bake can
  start from a newer vendor image each time.
- When the entry declares `config`, its keys shadow the OS builder's (and
  the document's) `config` for templates inside that entry; other entries
  and the OS builder itself do not see them.
- When an OS builder names several `runtimes[]`, exactly one `BaseImage`
  is synthesised with one runtime subconfig per entry, and the vendor image
  is resolved per runtime; the query keys a runtime does not understand are
  dropped by that runtime's plugin.
- When the run is the base-image lifecycle, the vendor query is made and
  the base image is handed to the image builder (`resolved=True`). When the
  run is the instance-image lifecycle, the base image is synthesised for
  chaining metadata only (`resolved=False`, no query, `image_identifier`
  stays `None`) and the base run's built artifact is located by name.
- Dry run versus real run: no difference in this plugin. The vendor query
  is made at resolution in both, so a dry base-image run still needs the
  runtime's credentials.
- Apply flags: none are read here. The bake is packer's; `apply_*` flags
  gate identity and storage applies, not the OS update.
- Ephemeral versus durable, pinned versus follow: neither is a property of
  an OS builder. A base image's `source_image` is `self`; the only
  age-based re-bake is `update.refresh_days`.
- When `is_default: true`, `source_image: default` on an image resolves to
  this OS builder; two defaults are refused at load (`Multiple default
  builders found`).
- When `admin_public_keys` is declared on the OS builder, it replaces the
  global `config.admin_public_keys` for this base (an empty list means no
  key, which the validator refuses unless the runtime has a session
  mechanism). An entry that is an `ENC[age:...]` marker keeps its
  ciphertext through the helper's strip.
- When `local_test_image` is declared, the mod-test harness uses it as is;
  unset, it derives one as listed above.
- When `family_version` changes, the input fingerprint of every runtime's
  series changes and the base re-bakes on each (recorded 2026-09-10 when
  `basic-rh-10` moved to 10 on both clouds). On `type: rhel` the new major
  must be 8, 9 or 10 or the configuration does not load.

## What it tests and verifies

| When | Check | Where the verdict lands |
|---|---|---|
| Load (pydantic, `CSIS_MODEL_CONFIG`) | Unknown keys refused (`extra="forbid"`), including `image_name` on an entry since stage 63; `name`, `type`, `family`, `family_version` required; numbers coerced to strings; `parameters` refused as retired (stage 26); `update` must be a mapping. | A pydantic validation error naming the field; the load fails. |
| Load (`OsBuilderModel.__post_init__`) | `runtimes` non-empty; `image_builder` unique across entries; `default_primary_disk_size: default` becomes 200. | `ValueError` from the loader. |
| Load (`RhelOsBuilderModel.__post_init__`, stage 63) | `type: rhel`: `family_version` parses and its major is 8, 9 or 10, whatever the update policy. | `ValueError` from the loader. |
| Load (`OSBuilderBaseImageBuilderSubconfig.__post_init__`) | `image_builder` non-empty after stripping; no `aliases` on an entry. | `ValueError` from the loader. |
| Load (`OsBuilderBase.__post_init__`) | Every entry is parented to this OS builder (its `model_id`). | Nothing visible; a missing parent shows later as `identified_model` being `None`. |
| `validate` (`validate_update_policies`) | `update` is a mapping (a bare name is already refused at load); `policy` is one of `none`, `security`, `packages`, `full`; `packages` needs `packages` and/or `pin`; every pin version is a non-empty string without spaces; `packages` and `exclude` do not overlap; `refresh_days` is positive. | Validation errors prefixed `base image '<name>':`; `validate` (and every run, which validates first) exits non-zero. |
| `validate` (`validate_test_specs`) | `tests` keys are known; every `files` entry has `path`; every `commands` entry has `run`; `post_bake` is a map with known keys and absolute `mounts`. Both the builder's and each entry's `tests`. | Validation errors prefixed `base image '<name>'` or `base image '<name>' runtime '<entry>'`. |
| `validate` (`validate_base_images`) | Every `identity_types` and `storage_types` entry has a configured plugin of that type; every admin public key parses as a public key; `admin_user` is non-empty; every runtime has a debug path (a key or a session mechanism). | Validation errors prefixed `base image '<name>'`. |
| `validate` (`validate_capabilities`) | Downstream: an instance image's group identity type and attached storage types are among what this base declares. | Validation errors naming the instance and `base '<name>'`. |
| Resolution (`predefined_resolve`) | The entry's image builder exists; its runtime exists; on the base-image lifecycle the vendor query returns an image, or a pinned `image_id` is known to the provider (stage 63); `generate_resolved_image` finds a machine type and an SSH user. | Exceptions that stop the run (`Image Builder for OS ... not found`, `No resolved Image identifiers for OS ...`, `OS builder ...: image_id ... is not known to the provider`, `No resolved image for runtime ...`); warnings in the log for a missing machine type, a missing `ssh_username`, a tag overwrite, and modifications declared on an OS builder. |
| Generation (`generate_items_for_os_update`, `RhelOsBuilderModel.repo_setup_commands`) | The policy is realisable by the family (Alpine: only `none`/`full` without exclude or pin); `rhel` `family_version` parses and its major is 8, 9 or 10 (checked again; the load already refused anything else). | `NotImplementedError` or `ValueError` that stops generation; on success, the `# OS update for base image ...` comment line and the provisioner in the build file. |
| Generation (lineage) | The effective policy is recorded with the build (`update_policy_of`) and enters the input fingerprint; `refresh_days` is compared with the series head's age. | The build record; the bake plan's reason, `update policy: head <build> is <n> days old (refresh_days: <d>)`, or `skip: current`. |
| Apply (the bake) | The commands run under packer's `/bin/sh -e`: any non-zero exit fails the provisioner and the bake. The `check-update` guard exits with dnf's own code when it is neither 0 nor 100. | Packer's output and exit code; no image is registered. On success, `/var/lib/csis/packages.txt` inside the image holds the package manifest. |
| After apply (post-finalize hooks) | Nothing. This plugin registers no hook. The in-bake `tests` it carries are verified by the packer plugin's last provisioner (`image_tests.py`), not by this one. | The bake's verification provisioner output. |
| State query | Nothing. The OS builder has no runtime state; the images it produced are the packer and runtime plugins' concern. | Nothing. |

## When it fails

Failures that have happened, oldest first. Where the fix is a guard in the
emitted commands, the guard is what an operator sees today.

- **2026-08-31, stage 1 first bakes: a full upgrade severed the SSM build
  tunnel twice.** `basic-rhel-8` declared `auto_update: true` (= `policy:
  full`); a 599-package upgrade broke the session manager tunnel about 27
  minutes in, twice. Symptom: packer loses the connection mid-provisioner.
  The fixture moved to `policy: security` with `exclude: ["kernel*"]`, the
  proven-survivable shape; a `full` policy on a large base is still that
  risk. Look at packer's output for the provisioner that lost the session.
- **2026-08-31, stage 1: `This system is not yet registered` from
  `subscription-manager`.** Cloud vendor RHEL images are RHUI or
  pay-as-you-go, not subscription-managed. The repo enablement is now
  guarded on `subscription-manager identity`; the bake prints
  `not subscription-registered (RHUI image): using vendor repos as-is` and
  continues. If you expected subscription repositories, register the image
  before the bake; the plugin does not.
- **2026-08-31, stage 1: `Errno 2` on a downloaded rpm during `dnf
  update`.** RHUI repositories flip their cache path mid-run when the point
  release moves (seen twice live). Every dnf update command now reads
  `<cmd> || { sudo dnf clean all; <cmd>; }`; a second `Errno 2` after the
  retry is a real repository problem. Look at the packer output for the
  retried line.
- **2026-08-31, stage 1: the bake machine was OOM-killed under `dnf
  update`.** A 1 GB `t2.micro` cannot keep the package manager and the SSM
  agent alive; symptom: the SSH/SSM session dies with no package error.
  Declare `default_machine_type` on the entry (the fixture uses `t3.medium`
  on AWS and `e2-small` on GCE). A related emission fault, `t3.medium` bakes
  staying `t2.micro` because the subconfig's templated `machine_type`
  refilled itself from the runtime default, was fixed by writing the
  resolved value to `machine_type` as well.
- **2026-08-31, stage 1: `Timeout waiting for SSH` on a Debian-derived
  bake.** The instance image baked as `ec2-user`, an account the Debian AMI
  does not have; only the vendor user's `authorized_keys` receives packer's
  key. The bake user now falls back by the chain root's `family` (`admin`,
  `ubuntu`, else `ec2-user`, the AWS runtime's family default). A timeout on
  a family outside that map means the entry needs `ssh_username`.
- **2026-08-31, stage 1: a baked AMI carried two root-slot volumes and its
  instances never booted (the `deb-11` chain).** The root device name was
  hard-coded; on HVM `/dev/sda1` and `/dev/xvda` alias one slot. The AWS
  runtime now takes the vendor query's `RootDeviceName`, else `/dev/xvda`
  for `debian`/`amazon` and `/dev/sda1` otherwise. A family the map does
  not know and a query without `RootDeviceName` still gets `/dev/sda1`.
- **2026-08-31, stage 1: apt lock timeouts and tooling bootstrap on
  Debian.** Recorded in the ledger among findings 1 to 15. Since stage 63
  every `apt-get` command the plugin emits carries `-o
  DPkg::Lock::Timeout=600`, so a concurrent `unattended-upgrades` run on a
  freshly booted Debian makes the bake wait up to ten minutes for the lock
  rather than fail at once (until 2026-09-25 no wait was set). A `Could
  not get lock` after that wait means the other apt process ran longer than
  ten minutes; re-run the bake.
- **2026-09-04, finding 42 (first AlmaLinux 10 bake): dnf 5 exits 1 on
  `dnf update <pkg>` when the package is already current** (`No packages
  marked for upgrade`) where dnf 4 exited 0. Targeted updates now run only
  behind `dnf -q check-update <pkgs>` (100 = updates exist, 0 = none, any
  other code is re-raised with `exit "$rc"`). An `exit` with another code
  is dnf's own error; look at the packer output just above it.
- **2026-09-04, finding 43 (first Alma 10 dask bake on GCE): SSH
  authentication failed at the instance bake.** The base bake ran as
  `ec2-user` (the AWS-ism fallback) and the instance bake as `packer`; the
  new guest agent aborts its whole metadata-ssh-key setup when removing the
  stale other-name user fails (`not a member of google-sudoers`). One
  declared `ssh_username: packer` on the GCE entry is the fix, and the
  entry's `get_ssh_username()` (previously a no-op that always returned
  `None`) now honours it. Diagnosed from the build VM's serial console.
  Since stage 63 the GCE family default is `packer` too, and `validate`
  refuses a GCE chain whose images would bake as different users.
- **2026-09-05/06, finding 51: the GCE bake disk was 200 GB.** The image
  inherited the OS builder's `default_primary_disk_size` default; the GCE
  runtime's `default_disk_size` (40 GB on `gcloud-east1`) now wins, and
  every instance launched from the image has exactly that boot disk.
- **2026-09-10, stage 13: `Unsupported RHEL version '10'` at
  generation.** The `rhel` type accepted only majors 8 and 9; EL10 is
  accepted since, and emits `rhel-10-*` repository names (a no-op on an
  unregistered image). Since stage 63 any other major is refused at load,
  whatever the update policy, with `Unsupported RHEL version '<v>' in OS
  builder <name> (supported: 8, 9, 10)`; until 2026-09-25 it was raised
  only when an update policy was generated, so a `none` policy on an
  unsupported major was never refused.
- **2026-09-10, first `just full-test`: the mod-test container
  `rockylinux:10` does not exist.** Docker Hub's `rockylinux` library stops
  at 9. From major 10 the derived stand-in is `almalinux:<v>`; a pull
  failure on another family is a `local_test_image` matter.
- **Finding 40 (undated in the ledger): the builder-level `tests:
  packages: [nfs-utils]` failed the GCE bake.** `nfs-utils` is what the
  EFS prerequisite installs, and EFS never runs on GCE. Per-entry `tests`
  replace the builder's for that runtime; declare the runtime's own
  assertions on its entry.

Failures the code raises that have not been seen live:

| Message or symptom | Meaning | Where | What to do |
|---|---|---|---|
| `Extra inputs are not permitted` naming a key under an OS builder or entry | Unknown key; the model forbids extras. | The load, before validate. | Remove or rename the key; `parameters` is retired, and `image_name` on an entry was removed in stage 63 (use `image_id` to pin a vendor image). |
| `OS builder <name> must have at least one runtime configuration.` | `runtimes` empty or absent. | The load. | Add an entry. |
| ``OS builder <name>: two `runtimes` entries name image builder <ib>; one entry per image builder`` | Two entries name the same `image_builder`. Until 2026-09-25 the message read `Duplicate runtime configuration name ...`, which said "name" but compared `image_builder`. | The load. | One entry per image builder. |
| `Unsupported RHEL version '<v>' in OS builder <name> (supported: 8, 9, 10)` | `type: rhel` with a major other than 8, 9 or 10 (stage 63: checked at load, whatever the update policy). | The load. | Use a supported major, or another family `type`. |
| `Could not determine RHEL version from family_version '<v>' in OS builder <name>` | `type: rhel` with a `family_version` that does not parse. | The load (stage 63); again at generation. | A version string such as `10`. |
| `Input should be a valid dictionary` under `update` | `update:` is a bare policy name (`update: none`), a list or a number. | The load. | `update: {policy: <name>}`. |
| `Aliases are not allowed for runtime configurations, but got ...` | `aliases:` on an entry. | The load. | Remove it; aliases belong on the OS builder. |
| `Runtime configuration type cannot be empty for ...` | `image_builder: ""`. | The load. | Name an image builder or omit the key (`default`). |
| `Multiple default builders found: <a> and <b>` | Two OS builders with `is_default: true`. | The load. | Keep one. |
| ``base image '<name>': update: must be a mapping (`update: {policy: <name>}`), got <type>`` | `update` is not a mapping when the policy is computed. The load refuses such a value first, so from YAML this is not reached; it guards other callers of `UpdatePolicy.from_config` (stage 63 reworded it; it used to say "must be a mapping or a policy name"). | `validate`. | A mapping. |
| `base image '<name>': update.policy '<p>' is not one of (...)` | Unknown policy name. | `validate`. | One of `none`, `security`, `packages`, `full`. |
| `... update.policy 'packages' needs update.packages and/or update.pin` | `packages` with nothing to update. | `validate`. | Name packages or pins. |
| `... update.pin[<pkg>] must be a version string` | Empty or space-containing version. | `validate`. | One version token. |
| `... packages both updated and excluded: [...]` | A package in both lists. | `validate`. | Remove it from one. |
| `... update.refresh_days must be a positive number of days` | Zero or negative. | `validate`. | A positive integer, or omit. |
| `base image '<name>' declares identity type '<t>' but no identity plugin of that type is configured` (and the storage twin) | A declared capability with no plugin. | `validate`. | Configure the plugin or drop the type. |
| `base image '<name>': admin public key rejected: <reason>` | A key in `admin_public_keys` (or the global list) is not a public key. | `validate`. | Public keys only; never a private key. |
| `base image '<name>': admin_user may not be empty` | `admin_user: ""`. | `validate`. | Name the user or omit for `csisadmin`. |
| `base image '<name>' on runtime '<rt>' has NO debug path` | No admin key anywhere and no session mechanism on the runtime. | `validate`. | Add a key or a session mechanism. |
| `base image '<name>': unknown tests keys [...]` and the other `tests` messages | Malformed `tests` on the builder or an entry. | `validate`. | See section 5.3 of the configuration manual. |
| `Image Builder for OS <name> not found in predefined_resolve: <ib>` | The entry's `image_builder` names nothing. | Resolution; the run stops. | Name a configured image builder. |
| `Runtime Builder for OS <name> not found in predefined_resolve: <rt>` | The image builder's runtime names nothing. | Resolution. | Fix the image builder. |
| `No resolved Image identifiers for OS <name> in predefined_resolve` | The vendor query returned nothing: wrong owners, filters that match nothing in this region, or credentials that cannot see the owner's images. | Resolution of the base-image lifecycle. | Check `owners` and `query.filters` against the console; check the runtime's credentials and region. |
| `OS builder <name>: image_id '<id>' on runtime <rt> is not known to the provider` | The entry pins an `image_id` the runtime cannot find: on AWS, DescribeImages does not know the AMI in this region (or it is malformed, or deregistered); on GCE, no image of that name exists in the entry's owner projects (stage 63). | Resolution of the base-image lifecycle. | Check the id against the console in the runtime's region or projects; an AMI id is per region. Remove `image_id` to go back to the query. |
| `No resolved image for runtime <rt> in OS builder <name>` | A runtime the OS builder names had no resolution. | Resolution. | Every entry's runtime must resolve. |
| Warning `No default machine type specified for runtime ...; using default.` | No machine type on entry, image builder or runtime. | Resolution, in the log. | Declare `default_machine_type`; the `default` sentinel will not bake. |
| `the ssh user for OS builder <b> on runtime <r> could not be inferred: set ...` | Nothing in the bake-user order names a user, and the runtime has no family default. | `validate`; generation. | Name one where the message says (stage 63 item 22; the warning `No ssh_username specified ...` that used to precede an AWS family guess is gone). |
| Warning `OS builder <name> declares modifications, but base images do not receive modifications` | Modifications on an OS builder. | Resolution, in the log. | Move them to an instance image. |
| Warning `Tag <k> from OS builder ... is overwriting tag with same key from runtime builder` | The entry's tag shadows the image builder's. | Resolution, in the log. | Intended precedence; rename if not. |
| `OS builder <name> (alpine) does not implement update policy '<p>' with exclude/pin; use a dnf/apt family or policy: full` | `security`, `packages`, `exclude` or `pin` on Alpine. | Generation; `NotImplementedError`. | `policy: full` or `none`. |
| Warning `No OS builder found for base image <name>; skipping OS update` | The packer plugin met a base image whose name is not an OS builder. | Generation, in the log. | Should not happen for images this plugin synthesises. |
| `sudo: not found` (or `doas` only) at the first command | The vendor image has no `sudo`. | The bake; packer fails the provisioner. | Choose an image with `sudo` or change the command list. |
| `E: Could not get lock /var/lib/dpkg/lock-frontend` | Another apt process held the lock for longer than the 600-second `DPkg::Lock::Timeout` every emitted `apt-get` carries (stage 63). | The bake. | Re-run; if it recurs, find what runs apt at boot on that vendor image. |
| `dnf versionlock` plugin install fails | Neither `python3-dnf-plugin-versionlock` nor `dnf-plugins-core` is available. | The bake, only with a `pin`. | Enable a repository that carries it, or drop the pin. |
| The bake succeeds but `/var/lib/csis/packages.txt` is missing | The policy was a no-op, so no update provisioner (and no manifest) ran. | Inside the image. | Expected for `policy: none` without pins. |

## Related

- [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md): how each runtime turns an entry's `owners` and `query` into a vendor image.
- Base classes: [os_builder_model.py](../base/src/cs_image_system/base/models/os_builder_model.py), [os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py), [update_policy.py](../base/src/cs_image_system/base/models/update_policy.py), [base_image.py](../base/src/cs_image_system/base/models/base_image.py), [builder_base_os.py](../base/src/cs_image_system/base/basic/builder_base_os.py).
- [docs/DESIGN.md](../../docs/DESIGN.md) for the capability axes (`identity_types`, `storage_types`) and the admin user; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the bake plan (`skip: current`, `refresh_days`) and `just test-mods`.
