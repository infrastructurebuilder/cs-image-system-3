<!--
SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>

SPDX-License-Identifier: Apache-2.0
-->

# cs-image-system-docker-plugin

The docker provider, as one package with two halves:

- **The runtime** (`cs_image_system.docker_runtime`): the `docker` runtime
  type, a durable host's container daemon as a place where images bake and
  instances run, with the two terraform modules the roots call.
- **The roots** (`cs_image_system.tf_docker_plugin`): the instance builder
  `tofu-docker` and the storage builder `tf-docker-volume`, containers and
  volumes on that daemon as OpenTofu module calls.

Each half registers under a namespace of its own, `docker-runtime` and
`tf-docker`, so a qualified `type:` word reads `docker-runtime/docker`,
`tf-docker/tofu-docker` or `tf-docker/tf-docker-volume`. The package
takes the place of the two distributions
`cs-image-system-docker-runtime-plugin` and
`cs-image-system-tf-docker-plugin`, which carried those same namespaces;
`cs-image-system[docker]` installs it.

## The runtime

This plugin ships the docker terraform modules as package data
(`docker_container`, `docker_volume`, under
[src/cs_image_system/docker_runtime/tfmodules/](src/cs_image_system/docker_runtime/tfmodules)),
declared through the `cs_image_system.modules` entry point;
`cs-image-system modules` lists them.

The `docker` runtime type: a durable host running a daemon that
speaks the Docker Engine API, as a place where images bake and instances
run. Docker Engine, Docker Desktop, OrbStack, colima and Podman's API
service all qualify; the system reaches the daemon through the `docker` CLI
the tree's `cfg/executables.yml` names and the address the runtime declares
(`host`, a `DOCKER_HOST` URL, or `context`, a docker context), never through
a cloud API. containerd with nerdctl has no Docker API and is not a target.

A container runtime is the third kind of runtime beside the two clouds. It
differs from them in three ways the design records as decisions:

- **No init system.** An image this runtime bakes carries the keepalive
  `sleep infinity` as its command and runs under `--init`; the launch work
  is done by `exec` after the container is created. Services that need
  systemd are not supported on this runtime, and an image test that checks
  an enabled service does not apply here.
- **Images live in the daemon's store.** A build is its image id
  (`sha256:...`), and its names are tags: `<repository>:<final name>` and
  the series' floating `<repository>:<prefix>`, which a child image bakes
  from when its parent is deferred (the daemon has no "newest image matching
  a pattern" query; the tag is that query). The runtime's builder gives
  each image it makes its repository (`prepare_provider_specific_image`),
  so `DockerProviderSpecificImage.floating_tag()` reads the image's own
  `repository` and asks no run for it. A label is fixed when an image
  is built, so what the core stamps afterwards (the parent bound after the
  bake, the fingerprint, a release) is carried by tags that MOVE:
  `<repository>:<short id>--<key>--<value>`, one per key.
- **POSIX accounts only.** Access is through the daemon (`docker exec -u`);
  whoever can reach the daemon is root on the host. An OPA group on a docker
  runtime is refused at validation; enrolling `sftd` in a container is
  not yet supported.

### What it registers

| Class | `csis_name()` | `csis_classifier()` | Role |
|---|---|---|---|
| `DockerContainerBuilderModel` ([docker_runtime_models.py](src/cs_image_system/docker_runtime/docker_runtime_models.py)) | `docker` | `VCT.CONTAINER_BUILDER_MODEL` (folded into the runtime namespace by the loader) | The runtime's declaration: `host` or `context`, `repository`, `machine_types`, `networking`, `state_configuration`, `executable`. |
| `DockerContainerBuilder` ([docker_runtime_builders.py](src/cs_image_system/docker_runtime/docker_runtime_builders.py)) | `docker` | `VCT.RUNTIME_BUILDER` | Every runtime hook, answered against the daemon through the CLI. |
| `DockerCLIVersionChecker` (same file) | `docker` | `VCT.VERSION_CHECKER` | `docker --version` for the `docker` entry of `cfg/executables.yml`. |

Entry points: `cs_image_system.plugins.runtime` → `docker`, and
`cs_image_system.bootstrap` → `docker`, the container-host section of
the bootstrap interview ([bootstrap.py](src/cs_image_system/docker_runtime/bootstrap.py)):

| Class / function | Role |
|---|---|
| `docker_section()` → `Section` | The interview's "Container host" section. Wanted where the tree declares a docker runtime. It reads the runtime from the raw `cfg/` (never loading it, never printing an address: a `host` may be an `ENC[age:...]` marker) and asks two questions, which runtime and *can CI reach its daemon* (default yes for an `ssh://` host or for none declared, no for a socket, a context, a `tcp://` host or a marker). |

The section has no terraform module, because a daemon is a host somebody runs.
Its render says what remains by hand (the daemon and its host, the network,
CI's ssh key and `known_hosts` line, or, when CI cannot reach the daemon, to
name the runtime in `GUARD_RUNTIME`) and its audit lines are all BY HAND or
READ. The two secrets it concerns, `DOCKER_HOST_SSH_KEY` and
`DOCKER_HOST_KNOWN_HOSTS`, are the section's own (`Section.secrets`); the
GitHub section's script sets them from files with the rest, so the core never
names them.

### Models

#### `DockerContainerBuilderModel`

Extends the core's `ContainerBuilderModel` (`host`, `context`, `networking`,
`machine_types`) and the runtime model every runtime shares
(`default_machine_type`, `default_image_builder`, `credentials`, `ephemeral`,
`retention_keep`, ...). The field table is
[CONFIGURATION section 4.6](../../docs/CONFIGURATION.md#46-docker); what is
particular to this runtime:

- **Where the daemon is** is `host` (a `DOCKER_HOST` URL:
  `unix:///var/run/docker.sock`, `ssh://user@host`, `tcp://host:2376`,
  which may be an `ENC[age:...]` marker when the address itself is
  private) or `context` (a docker context name, `docker context ls`, set
  as `DOCKER_CONTEXT`). Declare one, not both. `tls_cert_path` and
  `tls_verify` are `DOCKER_CERT_PATH` and `DOCKER_TLS_VERIFY` for a
  `tcp://` host: TLS material by PATH, never a value.
- **How it is reached** is `executable`, the `cfg/executables.yml` entry
  whose `binary` every docker call on this runtime runs through;
  `validate` version-checks it.
- **Where builds go** is `repository` (default `csis/<runtime name>`,
  made a valid repository name, lowercase): where this runtime's builds
  are tagged.
- **What a container gets** is `networking.network` (default `bridge`:
  the network the bake container and every instance joins, by name;
  referenced, never created or changed; no subnets, no zones) and
  `machine_types` (a map from a name to `{cpus, memory}`, `--cpus 2`,
  `--memory 4g`; when any are declared, `default_machine_type` must name
  one).
- **Where its roots keep state** is `state_configuration`; a tree with no
  cloud declares `local`.

Nothing in the model is a credential: whoever reaches the daemon is root
on the host.

### The builder

#### The image query

The daemon answers the keys `name` (a repository), `version` (a tag),
`publisher` (a registry namespace; `library` is Docker Hub's and is
dropped), `architecture` (a platform, `x86_64` → `linux/amd64`) and
`native.image` (a reference verbatim). The release catalog's `docker` block
gives every family one (`almalinux:{version}`, `debian:{version}`, ...);
those blocks are this plugin's, shipped as package data in
[`data/image-sources.yml`](src/cs_image_system/docker_runtime/data/image-sources.yml)
and read by `DockerContainerBuilder.image_source_entries()`, so the
release catalog a tree sees carries a `docker` block when the tree
declares a docker runtime (and, for the local modification tests alone,
when this plugin is the installed stand-in). The query PULLS the reference and records its digest reference
(`<repository>@sha256:...`) as the identifier, so a vendor moving a tag shows
as a move. An entry's `image_id` pins a digest reference; a tag is refused
there, because a tag moves.

#### Image query translation

What `translate_image_query()` does with each key of the system's
vocabulary (`supported_query_keys()` is the set of rows not marked
refused, the same table the cloud runtime READMEs carry). The answer is
`{"reference": "<repository>:<tag>", "platform": "<os/arch>" | None}`:
what `docker pull` takes. `validate` refuses a query that uses a refused
key before anything runs; a query that names neither `name` nor
`native.image` is refused too, because the daemon needs a reference.

| System key | Daemon's word | Note |
| --- | --- | --- |
| `name` | the repository | `almalinux`, or `<publisher>/<name>` when a publisher is named |
| `family` | refused | a registry has no image families; name the repository |
| `version` | the tag | `<repository>:<version>`; unset, the reference carries no tag and the daemon's default tag applies |
| `architecture` | `--platform` | `x86_64` and `amd64` become `linux/amd64`, `arm64` and `aarch64` become `linux/arm64`; any other word passes no platform |
| `publisher` | the registry namespace | the first value prefixes the repository; `library` (Docker Hub's own) is dropped; it is also recorded as the image's owner, `library` when none is named |
| `state` | refused | a pulled image has no state |
| `virtualization` | refused | an EC2 particular |
| `root_device` | refused | an EC2 particular |
| `tags` | refused | a pull cannot search by label |
| `newest` | refused | a tag names one image; the pull resolves it |
| `native` | `native.image` verbatim | a complete reference, used instead of `name`, `publisher` and `version`; no other `native` member is read |

#### The local test target

The core's local modification tests (`cs-image-system test-mods`; the
harness is [`mod_tests.py`](../engine/src/cs_image_system/engine/mod_tests.py)
in the base package) run every modification of an instance image twice on
a throwaway container and compare the filesystem diffs. The harness
itself names no runtime: it asks the registered runtime builder classes
which one offers a local test target, and this plugin is the one that
does. `DockerContainerBuilder.local_test_target()` returns the factory
`make_local_target(image, executables)` from
[`local_target.py`](src/cs_image_system/docker_runtime/local_target.py),
and everything that is docker's about the test container lives there:

- the CLI: the `binary` of the tree's `docker` entry in
  `cfg/executables.yml` (its `name` when no binary is given), else
  `docker` from the host's PATH;
- the daemon probe: `docker info`. When the daemon does not answer the
  factory returns nothing and the harness records every modification as
  `skipped` with the detail `docker: the daemon is not available`, never
  as failed;
- the pull, retried (three attempts, 5 then 20 seconds apart) so that a
  registry that is down is named as such; a pull that fails every attempt
  or a `docker run` that refuses raises the core's `ContainerStartError`
  with docker's own last line, and the harness records the modifications
  as `unstarted` (the container, not the modification);
- the container itself, `DockerTarget`: `docker run -d --rm <image> sh -c
  'sleep infinity'`, then `exec`, `cp` and `diff` against it, and `rm -f`
  at close. Ansible modifications reach it through ansible's `docker`
  connection plugin (`ansible_connection`), and the target knows which
  `docker diff` lines are noise (`/tmp`, `/var/log`, the package caches,
  ansible's own directories, `/run`) and tells the harness to ignore them.

Which image the container starts from is the catalog's stand-in block,
keyed by this runtime's type: the family's own `docker` block, else the
block of the family it IS, with the OS builder's `local_test_image`
overriding both. The daemon this runs on is the host's own (the
local `docker` CLI's current context), not the daemon a `docker` runtime
entry in the tree declares: the tests are local by design.

#### Bakes

`packer_source_type()` is `docker`, HashiCorp's docker plugin. The source
block starts the build container from the parent image (`pull = false`: the
query pulled every vendor image, and our own builds are local), named
`csis-bake-<runtime>-<image>` so ansible reaches it by name, under `--init`,
on the runtime's network, with its machine type's limits, with `/run` a
tmpfs so the step runner never lands in the image; it `commit`s the result
with the lineage tags as `LABEL` instructions and `CMD ["sleep",
"infinity"]`. The runtime adds a `docker-tag` post-processor to the build
(the final name and the floating tag, in the repository), and the manifest
records the committed image id as the build id. The ansible provisioner
connects with `ansible_connection=docker ansible_host=<container name>`,
passed as `--extra-vars`, the way packer's provisioner documents for its
docker builder. Bakes run as `root`; the settle step installs `sudo` and
`python3` when the vendor image lacks them, because every later step is
written for a cloud image's unprivileged user. No cloud-init wait, no
session agent.

Every tool a bake runs (packer, the docker CLI, ansible's docker connection)
gets the runtime's `DOCKER_HOST` or `DOCKER_CONTEXT` in its environment
(`tool_environment()`), so a bake on a remote daemon reaches that daemon.

#### Names

A build's final name is written as a tag: `image_name_as_made` replaces what
a tag cannot carry with `-`; `image_name_problem` refuses a name longer than
128 characters once made (the cut would fall where the timestamp is). A
label key carries no whitespace and no `=`.

#### Images in the store

`query_images` lists every image labelled `csis_series`, its lineage facts
read from its labels as built with the movable tags' values on top;
`inventory` adds every container and volume, with the `csis_config` label
each carries. `dispose_image` removes a build and every tag with it, and is
REFUSED while a container was created from it. `retag_image` moves the
per-key tags; `release_commands` moves `<repository>:<series>--<model>`.

#### Instances

Every instance hook is answered against the daemon, by the container
that bears the instance's name (a container's name is unique on a
daemon): `docker container inspect <name>`, where a container of that
name labelled as another configuration's reads as absent.

- **Launch delivery** is by session: a container has no first boot, so
  the instance root uploads the launch script at creation and the system
  runs it by exec after the apply.
- **Power state** is `.State.Status` in the system's words: `running` is
  running; `created` and `exited` are stopped (the container exists and
  can be started); `paused` is suspended; `restarting` is starting;
  `removing` is stopping; `dead` is unknown; no such container is absent.
  `start_instance` and `stop_instance` are `docker start` and `docker
  stop`, each confirmed by reading the state back.
- **Identity** is the container id (a re-create is a new id, so a new
  generation, as the ledger expects) and the hostname the container was
  given. The **boot image** is the image id the container was created
  from (`.Image`), which on this runtime is the build id itself.
- **Sessions** are `docker exec -i -u root <name> bash -s` with the
  script on stdin; there is no ssh proxy command, because login is by
  exec.
- **Verification** runs one exec that reports the launch marker (the
  script's last act, so its presence means every launch parameter
  applied), each declared mount point's own line from the container's
  mount table (`/proc/mounts`), and reads the image the container was
  created from against the expected build; a declared mount count with
  no mount points named fails, because a container's mounts are checked
  by name.
- **Relabel** re-creates nothing: a container's labels are fixed when it
  is created, so `retag_instance` refuses, naming the labels the
  container would carry after a re-create (an upgrade, or a decommission
  and redeclaration), which is the way to get them.

### Example configuration

```yaml
runtime_builders:
  - name: docker-local
    type: docker
    context: orbstack                 # or host: unix:///var/run/docker.sock
    executable: docker
    repository: csis/local
    default_machine_type: small
    default_image_builder: pckr-docker-ans
    machine_types:
      small: { cpus: 1, memory: 1g }
      medium: { cpus: 2, memory: 4g }
    networking:
      network: bridge
    state_configuration: local-state

image_builders:
  - name: pckr-docker-ans
    type: packer-docker
    runtime: docker-local
    executable: packer
    required_plugins:
      - name: docker
        source: github.com/hashicorp/docker
        version: '>= 1.0.0'
      - name: ansible
        source: github.com/hashicorp/ansible
        version: '>= 1.0.0'
```

## The roots

The OpenTofu plugin for a container runtime: the
instance builder `tofu-docker` and the storage builder `tf-docker-volume`.
Each emits one terraform root on the `kreuzwerker/docker` provider against a
release-owned module (`tfmodules/docker_container`, `tfmodules/docker_volume`,
shipped as package data by the docker-runtime plugin and written into a
tree by `init-config`), exactly as the clouds' tofu plugins do against
theirs. The runtime is the `docker` runtime of
[the runtime half of this package](#the-runtime):
a durable host running a daemon that speaks the Docker Engine API.

Three things are different from a cloud, and each is a recorded decision:

- **The power state is the operator's.** A container is declared with
  `must_run = false`, so the next apply leaves a stopped container stopped
  (proved against the provider), and
  with the restart policy `unless-stopped`, so a daemon restart brings back
  what was running and nothing else.
- **No first boot.** A cloud runs the launch script from user data. A
  container has no user data: the root uploads the same rendered script
  into the container when it is created (`/var/lib/csis/launch.sh`), and
  the system runs it through `docker exec` after the apply, once, the way
  it runs the accounts script. Its last act writes
  `/var/lib/csis/launch-applied`, which the verification reads.
- **Labels are fixed at creation.** A container's and a volume's labels
  cannot change in place; `lineage relabel` reports what a re-create would
  set and re-creates nothing.

### What it registers

One entry point under `cs_image_system.plugins.instance`
(`tf-docker-plugin`), registering two `type:` keys:

| `type:` | Model | Builder | Classified as |
|---|---|---|---|
| `tofu-docker` | `TofuDockerInstanceBuilderModel` | `TofuDockerInstanceBuilder` | an instance builder |
| `tf-docker-volume` | `TofuDockerVolumeStorageBuilderModel` | `TofuDockerVolumeStorageBuilder` | a storage builder |

Both subclass the provider-neutral terraform roots of
[cs-image-system-tofu-roots](../tofu-roots/README.md#the-terraform-roots)
(`TofuInstanceBuilderBase`, `TofuStorageBuilderBase`), not the AWS
plugin's classes: the root's layout, the variables, the state binding and
the remote-state references, the module calls and outputs, the gated
plan, gate and apply sequence, the decommission whitelist, the ephemeral
sequence, the finalization hooks, the storage state machine and the
state query are the base's, and this package answers the base's hooks
with what is the daemon's own: the `docker` provider from
`kreuzwerker/docker` with an empty provider block, the module
directories `docker_container` and `docker_volume`, the resource type
`docker_container` a replacement names, the word `container`, the launch
script `launch-<label>.sh.tftpl` that is uploaded rather than passed as
user data, and the module arguments below. The entry point also
registers the library's `TofuVersionChecker` under `tofu-docker`, so a
tree whose only terraform roots are container roots still has its
`tofu` version checked; the registry takes the one class from several
plugins as one registration.

### Models

#### `TofuDockerInstanceBuilderModel` (`tofu-docker`)

The fields of every tofu instance builder: `runtime` (a `docker` runtime),
`executable` (the `cfg/executables.yml` entry for tofu), `state_configuration`
(the root's state manager; `default` inherits the runtime's, else the
default), `required_plugins` (the terraform providers; with none declared the
root requires `kreuzwerker/docker` unpinned). Nothing docker-specific is
declared on the builder: the daemon's address and the machine types live on
the runtime.

#### `TofuDockerVolumeStorageBuilderModel` (`tf-docker-volume`)

The same universal fields, plus `variables` (a `DockerVolumeVariables`):
`driver` (the volume driver; the daemon's `local` when unset), `driver_opts`
(its options) and `tags`, emitted as labels under the storage item's own.

#### The runtime builder the plugin reads

`host` or `context` (the daemon's address, which rides in the environment of
every tofu process the roots run, never in a `.tf` file), `networking.network`
(the network every container joins, by name), `machine_types` (a name to
`{cpus, memory}`; an instance's `machine_type` picks one, the runtime's
`default_machine_type` otherwise) and `repository` (where the floating tag
of a deferred image lives).

### The builder

#### `TofuDockerInstanceBuilder` (phase `instance-generation`)

One `module "instance_<label>"` call per instance against
`tfmodules/docker_container`:

- `name` is the instance's declared name (a container's name is unique on a
  daemon, and every instance hook finds the container by it); `hostname` is
  the canonical name `<name>-NNN` the launch parameters decide;
- `image` is the pinned build (an image id, `sha256:...`), else the resolved
  provider-specific image, else the per-instance variable `<label>_image`
  that finalization fills from the packer manifest, with `image_tag` (the
  series' floating tag) as the module's fallback through a `docker_image`
  data source;
- `cpus` and `memory` are the machine type's limits (`cpus` rendered with a
  decimal point, `1.0`, because that is how the provider reads it back;
  memory in MB from docker's own spelling, `4g`);
- `labels` carry the configuration id (`csis_config`), the instance
  (`csis_instance`) and its generation (`csis_generation`); the module adds
  `csis_build` from the image it resolved;
- `volumes` map each attached storage to `{volume_name, container_path}`,
  the name by remote-state reference to the storage root's outputs;
- `launch_script` is `templatefile` over `launch-<label>.sh.tftpl`, the same
  script `launch_params.user_data_template` renders for the clouds, with the
  group's gid by the group builder's expression (a posix group's gid is a
  number of the configuration). On this runtime the script sets no hostname
  (the container was created with it) and, for a volume, formats and mounts
  nothing: the daemon mounted it, and the script makes the group's subtree
  and sets its ownership and mode. That block is the volume builder's
  answer to the storage launch hooks, through the base's platform-mounted
  default: `launch_mount()` puts `platform_mounted: true` in the mount
  record (because `platform_mounts()` is true), `launch_script_lines()` is
  the header and `mkdir`, the mount mark (`csis-mount: <mount point>
  mounted`, which `verify instance` reads back) and the subtree lines,
  `launch_tasks()` is the directory task alone, and `launch_variables()`
  is empty (nothing is read by reference at launch).

The module declares `must_run = false`, `start = true`, `init = true`, the
restart policy `unless-stopped`, and ignores later changes to `image`,
`labels`, `upload` and `memory_swap` (the daemon computes the last from
`memory`). An upgrade is a `-replace` of `module.instance_<label>.docker_container.this`
through the gate, as on the clouds; a decommission destroys the module.

Every tofu process the root runs (`fmt`, `init`, `validate`, `plan`, `apply`)
carries the runtime's `DOCKER_HOST` or `DOCKER_CONTEXT` (and the TLS pair)
in its environment; the runner script renders them as an assignment prefix
on the line, an ENC `host` as a `cs-image-system decrypt` call. The
`provider "docker"` block is empty.

#### `TofuDockerVolumeStorageBuilder` (phase `storage-generation`)

One `module "storage_<label>"` call per live storage against
`tfmodules/docker_volume`: the volume's name (the storage's name as the
daemon allows it), the driver and its options when declared, and labels
(`csis_storage`, `csis_config`, one `csis_group_<group>` per allowed group,
the builder's and the item's tags). Capability type `volume`: many
containers may attach one, it is POSIX, it is not zonal (the zone comparison
has nothing to compare), and `platform_mounts` is true. A `destroyed` storage
is removed with its data (N19); the volume is not archivable yet (a volume
has no snapshot; a `tar` from a throwaway container is the obvious later
shape).

#### The instance hooks, on the runtime

The hooks the core calls after the apply are the docker runtime's
(`docker_runtime_builders.py`): the power state (`running`; `exited` and
`created` as stopped; `paused` as suspended; `restarting` as starting;
absent), `start_instance` and `stop_instance`, the identity (the container
id is the provider id, so a re-create is a new generation), the booted image
(`.Image`, the build id itself), `verify_instance` by exec (the launch
marker, each declared mount point in `/proc/mounts`, the booted image),
`run_session_command` (`docker exec -i -u root <name> bash -s`), no
`ssh_proxy_command` (login is by exec), `inventory` by the configuration's
label, and `instance_tags`/`retag_instance` (read; refuse to change).

### Emission

For an instance `docker-test` on builder `tofu-docker-local`, the root
`generated/instance-image/tofu-docker-local/instance-generation/` holds
`instance-generation.tf` (the `terraform` block requiring `kreuzwerker/docker`,
an empty aliased provider, the variables, the remote-state data sources, the
backend file beside it), `instance-docker-test.tf` (the module call) and
`launch-docker_test.sh.tftpl` (the script). The storage root
`generated/storage/<builder>/storage-generation/` holds the volume module
calls and one `output "storage_<label>"` per volume for the instance root
to read.

### Example configuration

```yaml
# cfg/instance-builders.yml
instance_builders:
  - name: tofu-docker
    type: tofu-docker
    runtime: docker-host
    executable: open-tofu-1
    state_configuration: local-dev
    required_plugins:
      - name: docker
        source: kreuzwerker/docker
        version: ">= 3.0.0"

# cfg/storage-builders.yml
storage_builders:
  - name: docker-volumes
    type: tf-docker-volume
    executable: open-tofu-1
    runtime: docker-host
    state_configuration: local-dev
    variables:
      tags:
        project: example

# storages/volumes.yaml
storages:
  - name: scratch
    type: docker-volumes
    runtime: docker-host
    mount_point: /mnt/scratch
    groups: [pxgroup]

# instances/containers.yaml
instances:
  - name: docker-test
    image: imgfile-docker          # a posix-owned image baked on docker-host
    runtime: docker-host
    type: tofu-docker
    machine_type: small            # one of the runtime's machine_types
    storages:
      - name: scratch
        mount_point: /mnt/scratch
```

The base image the instance image descends from declares `storage_types:
[volume]` (N4: a type must be declared to be attached), and the image's
group is a posix group (an OPA group on a docker runtime is refused at
validation).

## Prerequisites and integration

The package depends on the contract and on the SDK's three libraries
(the kit, `hashicorp-utils` and `tofu-roots`), each **by a range**
(`>=0.2,<0.3` for the SDK), and on nothing else of this system; its
`test` extra adds the command line with its test kit and the core
plugins its fixture declares. What the ranges promise, and how the
package is held to the SDK's declared surface, is in
[WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md), which uses
this package as its example.

### The runtime

- A daemon that speaks the Docker Engine API, reachable from the machine
  that runs the system: `docker version` against the runtime's `host` or
  `context` must answer (preflight says so in one line per daemon; the
  probe is this plugin's own `session_status` hook).
- The `docker` CLI, declared in `cfg/executables.yml` (`version: ">=24"`
  is the floor the system runs with); `--init` needs the daemon's
  `docker-init`, which every supported daemon ships.
- `packer` with the `docker` and `ansible` plugins (`required_plugins` of
  the image builder), and `ansible-playbook` on the machine that bakes:
  ansible's docker connection runs the local `docker` CLI against the same
  daemon.
- Podman's API service works as the daemon: Podman 5.8 or later, rootless
  on AlmaLinux 10 through `docker` over ssh is the proved shape, and the
  setup and what differs from Docker are in
  [docs/OPERATIONS.md](../../docs/OPERATIONS.md), "Podman as the daemon".
  A rootless Podman user needs `/etc/subuid` and `/etc/subgid` ranges.
  Podman Desktop's machine on macOS works too, rootful and beside
  OrbStack (`just test-podman-desktop-cycle` runs the cycle on it and
  skips when no machine runs). Podman 6 dropped Intel Macs, so an Intel
  host stays on Podman 5 and the proof there has an end date, kept in
  [REMINDERS.md](../../REMINDERS.md).
- The posix identity plugin for the groups an instance image activates; an
  OPA group is refused on this runtime.
- A tree whose only runtime is docker declares a `local` state manager; a
  tree with clouds may put the docker roots in its default manager, and
  then needs that cloud's session for them.

### The roots

- A `docker` runtime (the docker runtime plugin) whose daemon the operator's
  shell can reach, and the `docker` CLI it names in `cfg/executables.yml`.
- `tofu` in `cfg/executables.yml`, and the `kreuzwerker/docker` provider,
  which `tofu init` downloads (version 3.0.0 or later; 4.6.0 proved it).
- A state manager for the roots: the runtime's `state_configuration`, often
  `local` for a tree with no cloud.
- The modules `tfmodules/docker_container` and `tfmodules/docker_volume`
  beside the configuration root (`module_source_base`, or one of them where
  `module_sources` names it); `init-config` writes them from the
  docker-runtime plugin's package data.
- `bash` on the baked image (the session runs `bash -s`), which the docker
  runtime's settle step installs with `sudo` and `python3` where a vendor
  container lacks them.

The plugin depends on `cs-image-system-contract` and `cs-image-system-base`
(as every built-in plugin does), `cs-image-system-hashicorp-utils` (the
provider-neutral terraform roots this plugin subclasses, the collector
and the version checker), the runtime half of this package (the
names and the runtime's hooks) and `pydantic`
([pyproject.toml](pyproject.toml)). It does not depend on the AWS root
(`cs-image-system-tf-ebs-instance-plugin`) or on `aws-runtime-plugin`:
installing this plugin installs no AWS package and no `boto3`. The
proof is the neutral-root test,
[tests/test_neutral_tofu_root.py](../../tests/test_neutral_tofu_root.py),
which syncs an environment for this plugin and the GCE one alone and
imports, registers and constructs both there.

## Configuration reference

### The runtime

See [Models](#models) for every field of the runtime, and the image
builder's reference in the [packer plugin](../packer-plugin/README.md) for
`type: packer-docker`. An OS builder's `runtimes[]` entry on a docker
runtime takes the usual keys; its `query` may use `name`, `version`,
`publisher`, `architecture` and `native.image`, and its `image_id` is a
digest reference. `output_image_name` is the tag prefix.

### The roots

Builder entries (`cfg/instance-builders.yml`, `cfg/storage-builders.yml`):
`name`, `type` (`tofu-docker` | `tf-docker-volume`), `runtime` (a `docker`
runtime), `executable`, `state_configuration`, `required_plugins[]`
(`{name, source, version}`), `is_default`, `description`, `tags`; the volume
builder's `variables: {driver, driver_opts, tags}`.

The instance item (`instances/*.yaml`, `type:` a `tofu-docker` builder):
`name` (the container's name and the hostname label), `image`, `runtime`,
`machine_type` (one of the runtime's `machine_types`; empty = its default),
`storages[]` (`{name, mount_point}`), `image_policy`, `ephemeral`,
`on_failure`, `teardown_after`, `userdata` (lines appended to the launch
script), `tags` (labels, fixed at creation). `availability_zone` is accepted
and compares with nothing (a daemon has no zones).

The storage item (`storages/*.yaml`, `type:` a `tf-docker-volume` builder):
`name`, `runtime`, `mount_point`, `groups[]`, `share_mode`, `public_read`,
`state` (`active` | `destroyed`; `archived` is refused: not supported yet),
`tags`. `lifecycle` is refused (no data lifecycle on a volume).

Execution knobs read through the base: `config.apply_instances` and
`config.apply_storage` (a bool, or the roots that may apply, by builder name
or runtime), `config.use_state_backends`, `config.module_source_base`.

## What it tests and verifies

The package's own suite ([tests/](tests/)) needs nothing else of this
repository: unit tests that run with only the contract, the SDK and the
package; and pipeline tests that drive a whole stubbed run over the
package's own fixture ([tests/fixture/](tests/fixture)) and compare it
with the package's own golden ([tests/golden/](tests/golden)), through
the published test kit and the stubs this package ships
([testing.py](src/cs_image_system/docker_runtime/testing.py)). `just
test-docker-alone` runs it in an empty environment at both ends of the
SDK range, and `just test-docker-install` installs
`cs-image-system[docker]` alone and validates and dry-runs the starter.
[WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md) explains each
of these.

### The runtime

- `validate` version-checks the `docker` executable and refuses a query key
  the daemon cannot answer, a label key it cannot carry, a build name longer
  than a tag, a `default_machine_type` that names no declared machine type,
  and a runtime that declares both `host` and `context`.
- `preflight` prints whether each docker runtime's daemon answers. The
  probe is this plugin's: the builder class's `session_status` hook runs
  `docker version` with the declared executable's binary against the
  runtime's `host` or `context` (`probe_daemon`), and answers the core
  with the engine and API versions or the first line of why not; a daemon
  that answers is present and judged, one that does not is absent, with
  the hint to start it or fix the address. The class also declares
  `DOCKER_*` as its credential prefix (set-but-empty is refused) and
  classifies `DockerUnreachable` into the one-line load failure below.
- The unit tests ([tests/unit/](tests/unit)) pin the names module (tags,
  repository names, movable tags), the query translation, the model's
  environment, the packer source and post-processor shapes, and the local
  target's CLI and its retried pull, without a daemon.
  [tests/pipeline/test_container_runtime.py](tests/pipeline/test_container_runtime.py)
  drives a dry `run --all` over this package's own fixture and checks the
  emitted docker sources, what validation refuses, the builder's answer
  for an unreachable daemon and its session hook. What the core and the
  other plugins do with a docker runtime beside every other provider (an
  identity plugin's objection, the preflight's line per session) is the
  system's [tests/test_container_runtime.py](../../tests/test_container_runtime.py).
- [tests/live/](tests/live) holds the one test that needs a real daemon:
  the modification tests of the fixture on this package's own stand-in.
  It is in no default path and no isolated run; `just test-docker-live`
  runs it, as a leg of `just full-test`, and without a daemon it fails.
- `just test-docker-bake`, a leg of `just full-test`, bakes an AlmaLinux 10
  and a Debian 12 base image and an instance image on the local daemon,
  checks the lineage and the tags, disposes them, and skips loudly without
  docker.
- The bootstrap section is tested without a daemon: its discovery and
  wanting, the reach rule (an `ssh://` host or none declared is reachable;
  a socket, a context, `tcp://` and a marker are not), the quiet interview
  of the `standard-docker` starter, the guard default in a tree with a
  runtime CI cannot reach, and that no address or marker reaches the
  generated README.

### The roots

- `packages/docker-plugin/tests/`: the module arguments from a resolved,
  a pinned and a deferred provider-specific image; the machine type's
  limits; the memory and cpus spellings; the volume's module arguments and
  labels; the launch-script template on a volume mount.
- [tests/pipeline/test_container_runtime.py](tests/pipeline/test_container_runtime.py):
  a dry run over this package's own fixture emits both roots, the module
  calls, the uploaded launch script and the environment prefix on every
  tofu line; an encrypted host stays a marker in the script; the launch
  parameters record the delivery and the platform mount; the hooks'
  answers over a stubbed daemon. The delivery of the launch script by the
  core's hook is the system's
  [tests/test_container_runtime.py](../../tests/test_container_runtime.py).
- `tests/test_docker_cycle_live.py` (`just test-docker-cycle`, a leg of
  `just full-test`): the cycle on the local daemon from nothing to nothing:
  bake, launch two containers on one volume, verify, reconcile accounts,
  stop one and show the next apply leaves it stopped, start it, upgrade one
  to a new build (a new generation), decommission, destroy the volume,
  dispose the images.
- The verification of a launched container (`verify instance`): the launch
  marker, each declared mount point, the booted image, and the image's
  declared post-bake tests over the session.

## When it fails

### The runtime

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

| Symptom | Cause | Remedy |
|---|---|---|
| `the configuration cannot load: docker runtime X: the daemon at ... cannot be reached` | The daemon is not running, or `host`/`context` names the wrong one. | Start it (OrbStack, Docker Desktop, the engine on the host) or fix the address; `preflight` shows which daemon answers. |
| `executable 'docker' is not declared in cfg/executables.yml` | The runtime's `executable` names no entry. | Declare `- name: docker` with its `binary`. |
| `image_id '...' is not a digest reference` | An entry pins a tag. | Pin `<repository>@sha256:<digest>` (`docker image inspect --format '{{index .RepoDigests 0}}'`). |
| `image ... is in use by container(s) ...` at disposal | A container stands on the build. | Decommission the container first; the image is never pulled from under it. |
| An ansible step cannot reach the container | The bake ran against a daemon other than the one the local `docker` CLI uses. | The runtime's `host`/`context` is what both read; check `DOCKER_HOST` is not also set in the shell to something else. |
| The bootstrap says `docker.runtime: ... -- no default can be derived` under `--quiet` | The tree declares no runtime of type `docker`, or the section was kept from an earlier interview of a tree that had one. | Declare the runtime, or answer `want_docker: no`. |
| `parent: lineage=<id> tag=series:<name>` in the state query on a Podman daemon | Podman spells `RepoTags` as `docker.io/<repository>:<tag>`, so a tag must be compared with its registry prefix stripped; a release that compares `RepoTags` as written reads every movable tag as missing ([the stage index](../../docs/CHANGES.md#s109) names the release that strips it). | Take a release that strips the prefix; nothing on the daemon needs repairing, the movable tags are there. |
| `a docker tag is at most 128 characters` at validate | A declared `output_image_name` is too long once the timestamp is appended. | Shorten it. |

### The roots

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

- `the daemon at ... cannot be reached`: the runtime's `host` or `context`
  does not answer; preflight says the same in one line.
- `machine_type 'x' is not one of runtime ...'s machine_types`: the instance
  names a type the runtime does not declare.
- `memory '...' is not a size docker understands`: a machine type's memory
  is not `512m`, `4g` or a number of MB.
- A plan that wants to replace a container the operator did not upgrade:
  a volume attachment changed (a detach on a container is a re-create, not
  an in-place detach as on the clouds), or `cpus`/`memory` of its machine
  type changed. The gate refuses the unwhitelisted destroy; an `upgrade
  instance` sanctions the replacement.
- `relabel: could not retag instance ...: a container's labels are fixed`:
  expected; the labels arrive with the next re-create.
- `verify ...: launch script: no completion marker`: the launch script did
  not run or failed; the next applying run delivers it again
  (`csis launch:` lines in the log say why).

## Related

- [docs/OPERATIONS.md](../../docs/OPERATIONS.md), [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)
- [packer-plugin](../packer-plugin/README.md) (`type: packer-docker`), [posix-identity-plugin](../posix-identity-plugin/README.md)
- [cs-image-system-tofu-roots](../tofu-roots/README.md#the-terraform-roots):
  the provider-neutral terraform roots this plugin subclasses, their
  hooks and the version checker.
- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md):
  the AWS root on the same bases, for comparison; not a dependency.
- `tfmodules/docker_container`, `tfmodules/docker_volume`: the modules.
- `docs/OPERATIONS.md`: the cycle, power states and generations.
