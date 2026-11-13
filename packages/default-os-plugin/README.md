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
which hold the package-manager logic the families share. There are no
source classes here: an OS picks its source per runtime through its
`runtimes:` entries and the image-source catalog, and the docker runtime
resolves through the catalog's `docker` block like the clouds through
theirs.

## Models

Every family model extends `OsBuilderModel` in
[os_builder_model.py](../base/src/cs_image_system/base/models/os_builder_model.py),
which extends `BuilderModel` and `NameTyped` in
[builder_model.py](../base/src/cs_image_system/base/models/builder_model.py).
The families add almost no fields; they differ in the commands they return.

### The base: `OsBuilderModel`

The field table is [CONFIGURATION 5](../../docs/CONFIGURATION.md#5-cfgos-buildersyml); what
follows is what each key means to this plugin.

- `type` selects the family, and so the package manager. It may be left
  out when exactly one type serves what the family is (`families()` on
  each model class: the rhel type serves `rhel`, `alma-linux`,
  `rocky-linux`, `centos`, `centos-stream`); a type that does not serve
  it is refused at load.
- `family` (required) is what the vendor image IS: the image-source
  catalog's key (CONFIGURATION 5a). `get_vendor_family()` is the token as
  written; `get_family()` is what the catalog says it IS (`alma-linux` IS
  `rhel`), and that is what drives the SSH-user fallback (`debian` ->
  `admin`, `ubuntu` -> `ubuntu`, else `ec2-user`), the `os_family`
  argument the runtime, identity and storage plugins receive, and the
  mod-test container (the catalog's `docker` block). It does not choose
  the package manager; `type` does.
- `family_version` (required; a bare number is coerced to a string) is
  parsed with `packaging.version`; RHEL reads the major to enable
  repositories. It is also the catalog's `{version}`, and so the mod-test
  container tag.
- `architecture` (`default`) is handed to the runtime's provider-specific
  image when not the default.
- `default_primary_disk_size` (`default`, which becomes `200`) is the
  bake disk size in GB for the base image when neither the runtime
  (`default_disk_size`) nor the entry for that runtime
  (`default_primary_disk_size`) declares one. The order is
  `lineage.bake_disk_size`, the one rule both packer sources and the
  input fingerprint use; see the Variations below.
- `owners` and `query` are the vendor-image inputs shared by every
  runtime entry: the runtime plugin maps the owners (AWS account ids and
  aliases, GCE projects and aliases), and an entry's own `query`
  overrides key by key.
- `runtimes` (required, non-empty): one entry per image builder this OS
  bakes on. `image_builder` must be unique across entries; two entries
  naming one image builder are refused at load.
- `config_username`: the sudo-capable ssh user on this OS's vendor image,
  for every runtime whose entry names none: step 3 of
  [the bake-user order](../../docs/CONFIGURATION.md#511-the-bake-ssh-user), after the image's
  and this OS's entry and ahead of anything the runtime says.
- `auto_update` (`false`) is an alias for `update: {policy: full}`.
  `update`, always a mapping (`policy` of `none`, `security`, `packages`
  or `full`; `packages`, `exclude`, `pin` as `{package: version}`,
  `refresh_days`), takes precedence over it. A bare policy name
  (`update: none`) is refused; write `update: {policy: none}`.
- `identity_types` and `storage_types`: the identity types (for example
  `okta`) and storage types (for example `ebs`, `efs`, `s3`, `pd`, `gcs`)
  the base image bakes prerequisites for and that images downstream may
  use.
- `admin_user` (`csisadmin`) is the mandatory local admin user baked into
  the base image; `admin_public_keys` are its public keys, `None` meaning
  the global `config.admin_public_keys`.
- `local_test_image`: the container image standing in for this OS when
  modifications are tested locally. Unset: the image-source catalog's
  `docker` block for the family (its own, else the family it IS), as a
  reference (`almalinux:10`, `rockylinux:9`, `debian:12`,
  `quay.io/centos/centos:stream9`); a family with no such block is
  `unsupported`.
- `tests`: in-bake assertions (`packages`, `files` with
  `path`/`contains`) for the base image.
- `tags` merge into the base image's tags; `is_default` makes this the
  OS builder `default` resolves to; `name`, `description` and `aliases`
  are the usual.

Each `runtimes[]` entry is an `OSBuilderBaseImageBuilderSubconfig` in
[os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py);
its field table is [CONFIGURATION 5.1](../../docs/CONFIGURATION.md#51-runtimes-entries). What
this plugin does with each key:

- `image_builder` (`default`, which resolves to the runtime's
  `default_image_builder`) is the image builder that bakes this OS here;
  its runtime is the entry's runtime.
- `name` is any unique label; `type` (the OS builder's name, templated)
  and `description` are set by the loader and accepted, not read by the
  emitters.
- `image_id` pins the vendor image this OS bakes from on this runtime.
  When set, the vendor query (`owners` and `query`) is skipped and the
  runtime looks the image up by id through its `query_provider_image_by_id`
  hook: on AWS the AMI id (`ami-...`), on GCE the image name, searched in
  the entry's owner projects. An id the provider does not know stops
  resolution. Pinning makes a base bake reproducible: the same vendor
  image every time, where a query follows the newest match. The id is
  part of the input fingerprint's vendor-source record, so setting or
  changing it re-bakes the base on that runtime.
- `default_machine_type`: the bake machine type; else the image
  builder's, else the runtime's.
- `default_primary_disk_size`: the base image's bake disk in GB on this
  runtime, when declared. The runtime's own `default_disk_size` still
  wins when the runtime declares one (GCE); unset, the OS builder's
  `default_primary_disk_size` (200 by default) applies.
- `owners` are appended after the OS builder's owners and the entry's
  runtime's `default_owners` (the runtime is the entry's image
  builder's); `query` overrides the OS builder's `query` key by key.
- `ssh_username` (`default`): the bake user on this runtime for this OS
  and every image built on it: step 2 of
  [the bake-user order](../../docs/CONFIGURATION.md#511-the-bake-ssh-user). It wins over the OS
  builder's `config_username` and everything the runtime declares, on
  both clouds.
- `auto_update: true` turns a `none` policy into `full` for bakes on
  this runtime; `tags` are merged over the OS builder's tags; `tests`,
  when set, replaces the OS builder's `tests` for bakes on this runtime.
- `config` (`{}`): a free-form mapping for templating. `get_config()`
  returns it, and the load-time template walker lets this entry's
  `config` shadow the enclosing `config` key by key for the entry's
  subtree, so `{{ config.x }}` in the entry's templated fields (for
  example `description`) resolves from the entry's own `config` first,
  then the OS builder's, then the document's.

`image_name` is not a field: declaring it is an unknown-key refusal at
load (`Extra inputs are not permitted`); pin a vendor image with
`image_id` ([when this changed](../../docs/CHANGES.md#s63)). The input fingerprint's
vendor-source record carries an `image_name: null` member, so the key's
absence moves no fingerprint.

`aliases` on an entry are refused.

The base `commands_for_policy()` knows only `none` (no commands) and `full`
(`get_command_to_update()`, which the base answers with an empty list);
any other policy, or a pin or exclude, raises `NotImplementedError` unless a
family overrides it. The apt and dnf families override
`commands_for_policy()` itself, so the bake never reaches their
`get_command_to_update()`; only `alpine` answers `full` through it.

### `AptOsBuilderModel` (not registered) and the `debian` and `ubuntu` families

`AptOsBuilderModel` adds no fields. It overrides one method:

- `commands_for_policy(policy)`: `apt-get update`; `apt-mark hold` for every `exclude`; `security` upgrades only packages whose candidate comes from a `security` suite (via a simulated `dist-upgrade` piped through `awk`), plus `--only-upgrade` of any named `packages`; `packages` upgrades only the named ones; `full` runs `upgrade`, `full-upgrade`, `autoremove` and `autoclean`, one `sudo` line each; every `pin` is installed as `package=version` with `--allow-downgrades` and held; the excludes are unheld at the end. Every `apt-get` command it emits carries `-o DPkg::Lock::Timeout=600`, so a bake waits up to ten minutes for a concurrent `unattended-upgrades` on a freshly booted machine instead of failing on the lock.

`DebianOsBuilderModel` (`type: debian`) and `UbuntuOsBuilderModel`
(`type: ubuntu`) extend it and add nothing but their name. They do not
support subscription management or dnf-style version locks.
`DebianOsBuilderModel` is keyword-only (`kw_only`) like every other family
model, and the `ubuntu` registration in `main.py` lists the model before
the builder like the others.

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

`RhelOsBuilderModel` (`type: rhel`) adds one field, `subscription_id`
(`str | None`, `None`): accepted and not read, reserved for a future step
that registers the bake machine with `subscription-manager`. The plugin
never registers a system.

At load (`RhelOsBuilderModel.__post_init__`) the `family_version` must
parse and its major must be 8, 9 or 10, whatever the update policy;
anything else is a `ValueError` and the configuration does not load, so a
`policy: none` OS builder with an unsupported major is refused like any
other.

It overrides `repo_setup_commands()` (the major check is the load's): when
the system is registered with `subscription-manager`, it refreshes and
enables exactly the `baseos`, `appstream` and `codeready-builder`
repositories for that major; an unregistered system (a vendor RHUI or
pay-as-you-go image, AlmaLinux, Rocky) prints a note and uses its
repositories as they are. The bake path goes through
`commands_for_policy()` directly; the base `get_command_to_update()` hook
remains as alpine's one path.

`FedoraOsBuilderModel` (`type: fedora`) adds no fields, no repository
setup and no methods: every bake goes through the shared dnf
`commands_for_policy()`, which uses `dnf -y upgrade` for `full`.

### `AlpineOsBuilderModel` (`type: alpine`)

Extends `OsBuilderModel` directly and adds no fields. Its
`get_command_to_update()` returns `sudo apk update` and `sudo apk upgrade
--available`. It relies on the base `commands_for_policy()`, so it supports
only `policy: none` and `policy: full` (or `auto_update: true`); `security`,
`packages`, `exclude` and `pin` raise `NotImplementedError`. The commands
use `sudo`; an Alpine image that ships only `doas` needs the command list
changed. It answers every package-manager hook (next section) with `apk`
and OpenRC lines, so a plugin's prerequisites bake on alpine through the
hooks without the plugin knowing the family.

### The package-manager hooks

The OS type owns the package manager. Every plugin that bakes a package
into an image -- an identity type's agent, a storage type's mount tooling,
a runtime's session agent, the in-bake `packages:` assertion, the local
modification tests' python for ansible -- asks the type that serves the
image's family and never writes a manager's command line itself. The hooks
are classmethods on the model (declared on the contract's
`OsBuilderModelProtocol`; the core's `OsBuilderModel` raises
`NotImplementedError` naming the type for each one it does not implement),
and the core finds the type from a family with
`cs_image_system.base.os_types.os_type_for_family(family, reg)` over the
run's registry (the class whose `families()` names it; a `ValueError`
names the family and the families every installed type serves when none
does). A plugin asks the run instead:
`ctx.services.images.os_type_for_family(family)`.

| Hook | `AptOsBuilderModel` (`debian`, `ubuntu`) | `DnfOsBuilderModel` (`rhel`, `fedora`) | `AlpineOsBuilderModel` |
|---|---|---|---|
| `package_format()` | `deb` | `rpm` | `apk` |
| `package_install_command(packages, *, lock_timeout=None)` | `sudo apt-get [-o DPkg::Lock::Timeout=<n>] install -y <packages>` | `sudo yum install -y <packages>` (a package may be an rpm URL; the timeout is ignored: dnf waits for the rpm database on its own) | `sudo apk add --no-cache <packages>` (no timeout option) |
| `package_update_command(*, lock_timeout=None)` | `sudo apt-get [-o DPkg::Lock::Timeout=<n>] update -y` | `sudo yum -y makecache` | `sudo apk update` |
| `package_present_check(package)` | the rpm-then-dpkg test below | the same test | `if ! apk info -e <package> ...; then printf ...; exit 1; fi` |
| `service_enable_command(service)` | `sudo systemctl enable <service>` | `sudo systemctl enable <service>` | `sudo rc-update add <service> default` (OpenRC) |
| `ansible_python_install_command()` | `apt-get install -y python3` when there is no python3 | the newest of python3.12/3.11/3.9 the release offers, else python3 | `apk add --no-cache python3` when there is no python3 |

Two things to know about the table:

- **The lines are exactly what the bakes carried before the type owned
  them, differences included.** The dnf type's bake lines say `yum`, the
  compatibility name every supported release (EL 8, 9 and 10; Fedora)
  answers to, while its update policy says `dnf`; the apt type's lines take
  `lock_timeout` (`PACKAGE_LOCK_TIMEOUT` in the contract's
  `operating_system` module is the 600 seconds every caller passes) so a
  bake waits for a freshly booted machine's own updater instead of failing
  on the lock, and its `update` carries `-y` where the update policy's does
  not. Making those one is a decision to take against a running bake, not
  inside this table.
- **The package assertion of the apt and dnf types is one line**
  (`helpers.rpm_or_dpkg_present_check`): rpm's answer, else dpkg's where
  dpkg exists, and an exit naming the package when neither says installed.
  Both types answer with it so the bake's bytes stand; one manager each is
  a later decision. Every type's assertion exits for itself: under `set -e`
  a bare `query || fail` cannot stop a bake, because the shell ignores a
  failing command in an AND-OR list.

A plugin that needs a different artifact per format (an agent shipped as a
deb and as an rpm; a vendor repository recipe) branches on
`package_format()` and uses the hooks for the lines; a plugin whose vendor
ships nothing for a format says so (`ValueError`) rather than emitting
another family's line.

### What the models do not support

No family model accepts unknown keys (the shared model config forbids
extras). None validates `family` against a fixed list: the `OSFamilies`
enum in [constants.py](../contract/src/cs_image_system/contract/constants.py) exists
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
| Resolution | runtime's `query_provider_image(entry)`, or `query_provider_image_by_id(entry, image_id)` when the entry declares `image_id` | Not this plugin's hooks, but their input: the entry's merged `owners` and `query` are what the runtime plugin turns into an AMI or GCE image lookup; a declared `image_id` skips that query and is looked up by id instead. |
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
  `my-deb-12` declares no policy and gets no update provisioner.
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
terse. The same file declares `my-deb-12` (`type: debian`, no update policy)
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
| A bake machine with enough memory for the package manager | A 1 GB machine is OOM-killed under `dnf update` ([the incident](../../docs/INCIDENTS.md#a-1-gb-bake-host-starved-the-package-manager-and-the-ssm-agent)). | The entry's `default_machine_type`, else the image builder's, else the runtime's `default_machine_type`. |
| docker and a pullable container image, for local modification tests only | `just test-mods` runs modifications against a container standing in for this OS. | `local_test_image`; unset, derived from `family` and `family_version` (`almalinux:<v>` for `rhel` 10 and above, `rockylinux:<v>` below, `debian:<v>`, `ubuntu:<v>`, `fedora:<v>`). A family the table does not know gets no image and the test is skipped. |
| Python 3.13 | The plugin metadata declares it. | The package's `requires-python` and the metadata object. |

Beyond that: nothing beyond the core. The packer, identity, storage and
runtime plugins that consume the synthesised base image carry their own
prerequisites.

## Configuration reference

The YAML this plugin owns is the `os_builders:` list in
`cfg/os-builders.yml`. Its field tables are
[CONFIGURATION 5](../../docs/CONFIGURATION.md#5-cfgos-buildersyml) (the OS builder),
[5.1](../../docs/CONFIGURATION.md#51-runtimes-entries) (the `runtimes[]` entry) and
[5.2](../../docs/CONFIGURATION.md#52-update) (the `update` mapping); the Models section above
says what each field means to this plugin. This section collects them by
who reads them.

Read by this plugin or the OS builder base: `name`, `type`, `family`,
`family_version`, `architecture`, `default_primary_disk_size`, `tags`,
`owners`, `query`, `runtimes`, `auto_update`, `update`, `identity_types`,
`storage_types`, `admin_user`, `admin_public_keys`, `local_test_image`,
`tests`, `is_default`, `aliases`, `description` and `config_username`; on
an entry `image_builder`, `name`, `default_machine_type`, `owners`,
`query`, `ssh_username`, `auto_update`, `tags`, `tests`, `image_id` (pins
the vendor image), `default_primary_disk_size` (the bake disk on that
runtime) and `config` (templating scope).

Accepted, not read (the loader takes them, nothing consults them): on the
OS builder `executable`, `config`, `gitignore`, and `subscription_id`
on `rhel` (reserved for a future register step); on an entry `type` and
`description` (templated at load, not read by the emitters).

Refused: `image_name` on an entry (an unknown key; pin with `image_id`);
`parameters` on an OS builder (retired).

The `update` mapping
([update_policy.py](../base/src/cs_image_system/base/models/update_policy.py))
has its table in CONFIGURATION 5.2; the rules this plugin's reader and
validator hold are these. `policy` (`none` by default, `full` when
`auto_update: true`) is case-insensitive with whitespace stripped; a bare
string in place of the mapping (`update: none`) is refused, because the
field is a mapping, and `UpdatePolicy.from_config` refuses anything that
is not a mapping. `packages` are exactly what a `packages` policy updates
and what a `security` policy updates after the security update; `full`
and `none` ignore them. `exclude` patterns are never touched
(`--exclude=` on every dnf update, `apt-mark hold` around the apt run)
and may not overlap `packages`. Each `pin` is installed at that version
and locked (`versionlock` on dnf, `apt-mark hold` on apt), sorted by
package name; a version may not be empty or contain a space.
`refresh_days` re-bakes the series when its head is at least that many
days old, must be positive, and is the only way package updates reach a
new build without a configuration change.

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
  The whole order is in CONFIGURATION 5.1.1.
- When the entry declares `tests`, they replace the OS builder's `tests`
  for bakes on that runtime (not merge); an entry without `tests` inherits
  the builder's.
- When the entry declares `default_machine_type`, the bake uses it; else
  the image builder's; else the runtime's; else a warning and the `default`
  sentinel.
- The bake disk follows one rule, `lineage.bake_disk_size`, which both
  packer sources (AWS `volume_size`, GCE `disk_size`) and the input
  fingerprint use: the runtime's own `default_disk_size` when it declares
  one (the GCE runtimes do); else the entry's `default_primary_disk_size`
  for that runtime when declared; else the OS builder's
  `default_primary_disk_size` (200 GB unset). Because the fingerprint
  hashes what is baked, the two can never disagree; a fingerprint
  recorded under an older rule reads DUE until
  `lineage restamp --runtime <rt> --commit` records the current one
  ([when the rule changed](../../docs/CHANGES.md#s63)).
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
  series changes and the base re-bakes on each. On `type: rhel` the new major
  must be 8, 9 or 10 or the configuration does not load.

## What it tests and verifies

| When | Check | Where the verdict lands |
|---|---|---|
| Load (pydantic, `CSIS_MODEL_CONFIG`) | Unknown keys refused (`extra="forbid"`), including `image_name` on an entry; `name`, `type`, `family`, `family_version` required; numbers coerced to strings; `parameters` refused as retired; `update` must be a mapping. | A pydantic validation error naming the field; the load fails. |
| Load (`OsBuilderModel.__post_init__`) | `runtimes` non-empty; `image_builder` unique across entries; `default_primary_disk_size: default` becomes 200. Every entry is parented to this OS builder's model (its `model_id`), before the resolver's first pass renders the entry's `type` as this OS builder's name. | `ValueError` from the loader. |
| Load (`RhelOsBuilderModel.__post_init__`) | `type: rhel`: `family_version` parses and its major is 8, 9 or 10, whatever the update policy. | `ValueError` from the loader. |
| Load (`OSBuilderBaseImageBuilderSubconfig.__post_init__`) | `image_builder` non-empty after stripping; no `aliases` on an entry. | `ValueError` from the loader. |
| Load (`OsBuilderBase.__post_init__`) | Every entry's parent is refined from this OS builder's model to the OS builder itself (its global id), which every entry holds after the load. | Nothing visible; a missing parent shows later as `identified_model` raising `ValueError`. |
| `validate` (`validate_update_policies`) | `update` is a mapping (a bare name is already refused at load); `policy` is one of `none`, `security`, `packages`, `full`; `packages` needs `packages` and/or `pin`; every pin version is a non-empty string without spaces; `packages` and `exclude` do not overlap; `refresh_days` is positive. | Validation errors prefixed `base image '<name>':`; `validate` (and every run, which validates first) exits non-zero. |
| `validate` (`validate_test_specs`) | `tests` keys are known; every `files` entry has `path`; every `commands` entry has `run`; `post_bake` is a map with known keys and absolute `mounts`. Both the builder's and each entry's `tests`. | Validation errors prefixed `base image '<name>'` or `base image '<name>' runtime '<entry>'`. |
| `validate` (`validate_base_images`) | Every `identity_types` and `storage_types` entry has a configured plugin of that type; every admin public key parses as a public key; `admin_user` is non-empty; every runtime has a debug path (a key or a session mechanism). | Validation errors prefixed `base image '<name>'`. |
| `validate` (`validate_capabilities`) | Downstream: an instance image's group identity type and attached storage types are among what this base declares. | Validation errors naming the instance and `base '<name>'`. |
| Resolution (`predefined_resolve`) | The entry's image builder exists; its runtime exists; on the base-image lifecycle the vendor query returns an image, or a pinned `image_id` is known to the provider; `generate_resolved_image` finds a machine type and an SSH user. | Exceptions that stop the run (`Image Builder for OS ... not found`, `No resolved Image identifiers for OS ...`, `OS builder ...: image_id ... is not known to the provider`, `No resolved image for runtime ...`); warnings in the log for a missing machine type, a missing `ssh_username`, a tag overwrite, and modifications declared on an OS builder. |
| Generation (`generate_items_for_os_update`, `RhelOsBuilderModel.repo_setup_commands`) | The policy is realisable by the family (Alpine: only `none`/`full` without exclude or pin); `rhel` `family_version` parses and its major is 8, 9 or 10 (checked again; the load already refused anything else). | `NotImplementedError` or `ValueError` that stops generation; on success, the `# OS update for base image ...` comment line and the provisioner in the build file. |
| Generation (lineage) | The effective policy is recorded with the build (`update_policy_of`) and enters the input fingerprint; `refresh_days` is compared with the series head's age. | The build record; the bake plan's reason, `update policy: head <build> is <n> days old (refresh_days: <d>)`, or `skip: current`. |
| Apply (the bake) | The commands run under packer's `/bin/sh -e`: any non-zero exit fails the provisioner and the bake. The `check-update` guard exits with dnf's own code when it is neither 0 nor 100. | Packer's output and exit code; no image is registered. On success, `/var/lib/csis/packages.txt` inside the image holds the package manifest. |
| After apply (post-finalize hooks) | Nothing. This plugin registers no hook. The in-bake `tests` it carries are verified by the packer plugin's last provisioner (`image_tests.py`), not by this one. | The bake's verification provisioner output. |
| State query | Nothing. The OS builder has no runtime state; the images it produced are the packer and runtime plugins' concern. | Nothing. |

## When it fails

What the operator sees, what it means, where it surfaces and what to do.
Where the fix for a failure that has happened is a guard in the emitted
commands, the guard is what you see today; the failures that have
happened live are recorded, dated, in [INCIDENTS.md](../../docs/INCIDENTS.md), and a row
below links its entry where one exists.

| Message or symptom | Meaning | Where | What to do |
|---|---|---|---|
| packer loses the connection mid-provisioner during a `full` update of a large base ([the entry](../../docs/INCIDENTS.md#a-full-upgrade-severed-the-ssm-build-tunnel)) | A several-hundred-package upgrade breaks the session manager tunnel. `policy: security` with `exclude: ["kernel*"]` is the proven-survivable shape; a `full` policy on a large base is still that risk. | The bake. | Narrow the policy; look at packer's output for the provisioner that lost the session. |
| `This system is not yet registered` from `subscription-manager` ([the entry](../../docs/INCIDENTS.md#a-cloud-rhel-image-said-it-was-not-registered)) | Cloud vendor RHEL images are RHUI or pay-as-you-go, not subscription-managed. The repo enablement is guarded on `subscription-manager identity`: the bake prints `not subscription-registered (RHUI image): using vendor repos as-is` and continues. | The bake. | If you expect subscription repositories, register the image before the bake; the plugin does not. |
| `Errno 2` on a downloaded rpm during `dnf update` ([the entry](../../docs/INCIDENTS.md#a-downloaded-rpm-vanished-under-dnf-update)) | RHUI repositories flip their cache path mid-run when the point release moves. Every dnf update command reads `<cmd> \|\| { sudo dnf clean all; <cmd>; }`; a second `Errno 2` after the retry is a real repository problem. | The bake. | Look at the packer output for the retried line. |
| The SSH/SSM session dies with no package error ([the entry](../../docs/INCIDENTS.md#a-1-gb-bake-host-starved-the-package-manager-and-the-ssm-agent)) | A 1 GB `t2.micro` cannot keep the package manager and the SSM agent alive. The resolved machine type is written to `machine_type` as well, so an emission cannot refill it from the runtime default. | The bake. | Declare `default_machine_type` on the entry (the fixture uses `t3.medium` on AWS and `e2-small` on GCE). |
| `Timeout waiting for SSH` on a Debian-derived bake ([the entry](../../docs/INCIDENTS.md#a-debian-chain-baked-as-ec2-user-never-authenticated)) | The bake ran as a user the Debian AMI does not have; only the vendor user's `authorized_keys` receives packer's key. The bake user falls back by the chain root's `family` (`admin`, `ubuntu`, else `ec2-user`, the AWS runtime's family default). | The bake. | A timeout on a family outside that map means the entry needs `ssh_username`. |
| A baked AMI carries two root-slot volumes and its instances never boot ([the entry](../../docs/INCIDENTS.md#a-baked-ami-carried-two-root-slot-volumes)) | On HVM `/dev/sda1` and `/dev/xvda` alias one slot. The AWS runtime takes the vendor query's `RootDeviceName`, else `/dev/xvda` for `debian`/`amazon` and `/dev/sda1` otherwise; a family the map does not know and a query without `RootDeviceName` still gets `/dev/sda1`. | The bake; the instance. | Resolve the vendor query, or use a family the map knows. |
| `E: Could not get lock /var/lib/dpkg/lock-frontend` ([the entry](../../docs/INCIDENTS.md#apt-could-not-get-the-lock-on-a-freshly-booted-debian)) | A concurrent `unattended-upgrades` on a freshly booted Debian held the lock for longer than the 600-second `DPkg::Lock::Timeout` every emitted `apt-get` carries, so the bake waited ten minutes before failing. | The bake. | Re-run; if it recurs, find what runs apt at boot on that vendor image. |
| `exit "$rc"` from the targeted update block with a code other than 0 or 100 ([the entry](../../docs/INCIDENTS.md#dnf-5-exited-1-on-a-package-that-was-already-current)) | dnf 5 exits 1 on `dnf update <pkg>` when the package is already current (`No packages marked for upgrade`) where dnf 4 exited 0, so targeted updates run only behind `dnf -q check-update <pkgs>` (100 = updates exist, 0 = none, anything else re-raised). Another code is dnf's own error. | The bake. | Look at the packer output just above the exit. |
| SSH authentication fails at the instance bake on GCE ([the entry](../../docs/INCIDENTS.md#one-gce-chain-baked-its-images-as-two-different-users)) | The base and the instance baked as different users, and the guest agent aborts its whole metadata-ssh-key setup when removing the stale other-name user fails (`not a member of google-sudoers`). The GCE family default is `packer`, and `validate` refuses a GCE chain whose images would bake as different users. | The bake; the build VM's serial console. | One declared `ssh_username: packer` on the GCE entry covers the chain. |
| A GCE bake disk of 200 GB ([the entry](../../docs/INCIDENTS.md#the-gce-bake-and-boot-disks-were-200-gb)) | The image inherited the OS builder's `default_primary_disk_size`; the GCE runtime's `default_disk_size` wins when declared, and every instance launched from the image has exactly that boot disk. | Generation. | Declare `default_disk_size` on the GCE runtime. |
| `Unsupported RHEL version '<v>' in OS builder <name> (supported: 8, 9, 10)` ([the entry](../../docs/INCIDENTS.md#the-first-almalinux-10-base-was-refused-as-an-unsupported-rhel-version)) | `type: rhel` with a major other than 8, 9 or 10, checked at load whatever the update policy. EL10 emits `rhel-10-*` repository names (a no-op on an unregistered image). | The load. | Use a supported major, or another family `type`. |
| The mod-test container `rockylinux:10` does not exist ([the entry](../../docs/INCIDENTS.md#the-modification-tests-had-no-container-for-el-10)) | Docker Hub's `rockylinux` library stops at 9; from major 10 the derived stand-in is `almalinux:<v>`. | `just test-mods`. | A pull failure on another family is a `local_test_image` matter. |
| The builder-level `tests: packages: [nfs-utils]` fails the GCE bake ([the entry](../../docs/INCIDENTS.md#a-builder-level-package-assertion-failed-the-gce-bake)) | `nfs-utils` is what the EFS prerequisite installs, and EFS never runs on GCE. Per-entry `tests` replace the builder's for that runtime. | The bake. | Declare the runtime's own assertions on its entry. |
| `Extra inputs are not permitted` naming a key under an OS builder or entry | Unknown key; the model forbids extras. | The load, before validate. | Remove or rename the key; `parameters` is retired, and `image_name` on an entry is refused (use `image_id` to pin a vendor image). |
| `OS builder <name> must have at least one runtime configuration.` | `runtimes` empty or absent. | The load. | Add an entry. |
| ``OS builder <name>: two `runtimes` entries name image builder <ib>; one entry per image builder`` | Two entries name the same `image_builder`. | The load. | One entry per image builder. |
| `Unsupported RHEL version '<v>' in OS builder <name> (supported: 8, 9, 10)` | `type: rhel` with a major other than 8, 9 or 10 (checked at load, whatever the update policy). | The load. | Use a supported major, or another family `type`. |
| `Could not determine RHEL version from family_version '<v>' in OS builder <name>` | `type: rhel` with a `family_version` that does not parse. | The load; again at generation. | A version string such as `10`. |
| `Input should be a valid dictionary` under `update` | `update:` is a bare policy name (`update: none`), a list or a number. | The load. | `update: {policy: <name>}`. |
| `Aliases are not allowed for runtime configurations, but got ...` | `aliases:` on an entry. | The load. | Remove it; aliases belong on the OS builder. |
| `Runtime configuration type cannot be empty for ...` | `image_builder: ""`. | The load. | Name an image builder or omit the key (`default`). |
| `Multiple default builders found: <a> and <b>` | Two OS builders with `is_default: true`. | The load. | Keep one. |
| ``base image '<name>': update: must be a mapping (`update: {policy: <name>}`), got <type>`` | `update` is not a mapping when the policy is computed. The load refuses such a value first, so from YAML this is not reached; it guards other callers of `UpdatePolicy.from_config`. | `validate`. | A mapping. |
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
| `OS builder <name>: image_id '<id>' on runtime <rt> is not known to the provider` | The entry pins an `image_id` the runtime cannot find: on AWS, DescribeImages does not know the AMI in this region (or it is malformed, or deregistered); on GCE, no image of that name exists in the entry's owner projects. | Resolution of the base-image lifecycle. | Check the id against the console in the runtime's region or projects; an AMI id is per region. Remove `image_id` to go back to the query. |
| `No resolved image for runtime <rt> in OS builder <name>` | A runtime the OS builder names had no resolution. | Resolution. | Every entry's runtime must resolve. |
| Warning `No default machine type specified for runtime ...; using default.` | No machine type on entry, image builder or runtime. | Resolution, in the log. | Declare `default_machine_type`; the `default` sentinel will not bake. |
| `the ssh user for OS builder <b> on runtime <r> could not be inferred: set ...` | Nothing in the bake-user order names a user, and the runtime has no family default. | `validate`; generation. | Name one where the message says. |
| Warning `OS builder <name> declares modifications, but base images do not receive modifications` | Modifications on an OS builder. | Resolution, in the log. | Move them to an instance image. |
| Warning `Tag <k> from OS builder ... is overwriting tag with same key from runtime builder` | The entry's tag shadows the image builder's. | Resolution, in the log. | Intended precedence; rename if not. |
| `OS builder <name> (alpine) does not implement update policy '<p>' with exclude/pin; use a dnf/apt family or policy: full` | `security`, `packages`, `exclude` or `pin` on Alpine. | Generation; `NotImplementedError`. | `policy: full` or `none`. |
| Warning `No OS builder found for base image <name>; skipping OS update` | The packer plugin met a base image whose name is not an OS builder. | Generation, in the log. | Should not happen for images this plugin synthesises. |
| `sudo: not found` (or `doas` only) at the first command | The vendor image has no `sudo`. | The bake; packer fails the provisioner. | Choose an image with `sudo` or change the command list. |
| `dnf versionlock` plugin install fails | Neither `python3-dnf-plugin-versionlock` nor `dnf-plugins-core` is available. | The bake, only with a `pin`. | Enable a repository that carries it, or drop the pin. |
| The bake succeeds but `/var/lib/csis/packages.txt` is missing | The policy was a no-op, so no update provisioner (and no manifest) ran. | Inside the image. | Expected for `policy: none` without pins. |

## Related

- [aws-runtime-plugin](../aws-runtime-plugin/README.md) and [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md): how each runtime turns an entry's `owners` and `query` into a vendor image.
- Base classes: [os_builder_model.py](../base/src/cs_image_system/base/models/os_builder_model.py), [os_builder_runtime_config.py](../base/src/cs_image_system/base/models/os_builder_runtime_config.py), [update_policy.py](../base/src/cs_image_system/base/models/update_policy.py), [base_image.py](../base/src/cs_image_system/base/models/base_image.py), [builder_base_os.py](../base/src/cs_image_system/base/basic/builder_base_os.py).
- [docs/DESIGN.md](../../docs/DESIGN.md) for the capability axes (`identity_types`, `storage_types`) and the admin user; [docs/PLUGINS.md](../../docs/PLUGINS.md) for the package index.
- [The configuration reference](../../docs/CONFIGURATION.md) -- every field of the YAML this plugin reads, with an example.
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) for the bake plan (`skip: current`, `refresh_days`) and `just test-mods`.
