<!--
SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>

SPDX-License-Identifier: Apache-2.0
-->

# cs-image-system-tf-docker-plugin

The OpenTofu plugin for a container runtime (stage 103, branch 2): the
instance builder `tofu-docker` and the storage builder `tf-docker-volume`.
Each emits one terraform root on the `kreuzwerker/docker` provider against a
release-owned module (`tfmodules/docker_container`, `tfmodules/docker_volume`,
which every starter carries), exactly as the clouds' tofu plugins do against
theirs. The runtime is the `docker` runtime of
[cs-image-system-docker-runtime-plugin](../docker-runtime-plugin/README.md):
a durable host running a daemon that speaks the Docker Engine API.

Three things are different from a cloud, and each is a decision recorded in
the stage:

- **The power state is the operator's.** A container is declared with
  `must_run = false`, so the next apply leaves a stopped container stopped
  (proved against the provider before anything else in the branch), and
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

## What it registers

One entry point under `cs_image_system.plugins.instance`
(`tf-docker-plugin`), registering two `type:` keys:

| `type:` | Model | Builder | Classified as |
|---|---|---|---|
| `tofu-docker` | `TofuDockerInstanceBuilderModel` | `TofuDockerInstanceBuilder` | an instance builder |
| `tf-docker-volume` | `TofuDockerVolumeStorageBuilderModel` | `TofuDockerVolumeStorageBuilder` | a storage builder |

Both subclass the AWS plugin's tofu bases (`TofuInstanceBuilder`,
`TofuStorageBuilder`), so the apply gate, the decommission whitelist, the
ephemeral sequence, the storage state machine and the state query are the
shared machinery.

## Models

### `TofuDockerInstanceBuilderModel` (`tofu-docker`)

The fields of every tofu instance builder: `runtime` (a `docker` runtime),
`executable` (the `cfg/executables.yml` entry for tofu), `state_configuration`
(the root's state manager; `default` inherits the runtime's, else the
default), `required_plugins` (the terraform providers; with none declared the
root requires `kreuzwerker/docker` unpinned). Nothing docker-specific is
declared on the builder: the daemon's address and the machine types live on
the runtime.

### `TofuDockerVolumeStorageBuilderModel` (`tf-docker-volume`)

The same universal fields, plus `variables` (a `DockerVolumeVariables`):
`driver` (the volume driver; the daemon's `local` when unset), `driver_opts`
(its options) and `tags`, emitted as labels under the storage item's own.

### The runtime builder the plugin reads

`host` or `context` (the daemon's address, which rides in the environment of
every tofu process the roots run, never in a `.tf` file), `networking.network`
(the network every container joins, by name), `machine_types` (a name to
`{cpus, memory}`; an instance's `machine_type` picks one, the runtime's
`default_machine_type` otherwise) and `repository` (where the floating tag
of a deferred image lives).

## The builder

### `TofuDockerInstanceBuilder` (phase `instance-generation`)

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
  and sets its ownership and mode.

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

### `TofuDockerVolumeStorageBuilder` (phase `storage-generation`)

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

### The instance hooks, on the runtime

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

## Emission

For an instance `docker-test` on builder `tofu-docker-local`, the root
`generated/instance-image/tofu-docker-local/instance-generation/` holds
`instance-generation.tf` (the `terraform` block requiring `kreuzwerker/docker`,
an empty aliased provider, the variables, the remote-state data sources, the
backend file beside it), `instance-docker-test.tf` (the module call) and
`launch-docker_test.sh.tftpl` (the script). The storage root
`generated/storage/<builder>/storage-generation/` holds the volume module
calls and one `output "storage_<label>"` per volume for the instance root
to read.

## Example configuration

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

- A `docker` runtime (the docker runtime plugin) whose daemon the operator's
  shell can reach, and the `docker` CLI it names in `cfg/executables.yml`.
- `tofu` in `cfg/executables.yml`, and the `kreuzwerker/docker` provider,
  which `tofu init` downloads (version 3.0.0 or later; 4.6.0 proved it).
- A state manager for the roots: the runtime's `state_configuration`, often
  `local` for a tree with no cloud.
- The modules `tfmodules/docker_container` and `tfmodules/docker_volume`
  beside the configuration root (`module_source_base`); every starter carries
  them.
- `bash` on the baked image (the session runs `bash -s`), which the docker
  runtime's settle step installs with `sudo` and `python3` where a vendor
  container lacks them.

The plugin depends on `cs-image-system-tf-ebs-instance-plugin` (the tofu
bases) and `cs-image-system-docker-runtime-plugin` (the names and the
runtime's hooks).

## Configuration reference

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

- `packages/tf-docker-plugin/tests/`: the module arguments from a resolved,
  a pinned and a deferred provider-specific image; the machine type's
  limits; the memory and cpus spellings; the volume's module arguments and
  labels; the launch-script template on a volume mount.
- `tests/test_v2_stage_103_instances.py`: a dry run over an overlay of the
  frozen fixture emits both roots, the module calls, the uploaded launch
  script, the environment prefix on every tofu line and the gated apply
  sequence; the hooks' answers over a stubbed daemon; the fixture and the
  golden do not change.
- `tests/test_v2_docker_cycle_live.py` (`just test-docker-cycle`, a leg of
  `just full-test`): the cycle on the local daemon from nothing to nothing:
  bake, launch two containers on one volume, verify, reconcile accounts,
  stop one and show the next apply leaves it stopped, start it, upgrade one
  to a new build (a new generation), decommission, destroy the volume,
  dispose the images.
- The verification of a launched container (`verify instance`): the launch
  marker, each declared mount point, the booted image, and the image's
  declared post-bake tests over the session.

## When it fails

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

- [cs-image-system-docker-runtime-plugin](../docker-runtime-plugin/README.md):
  the runtime, the bake and the instance hooks.
- [cs-image-system-tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md):
  the tofu bases this plugin subclasses.
- `tfmodules/docker_container`, `tfmodules/docker_volume`: the modules.
- `docs/OPERATIONS.md`: the cycle, power states and generations.
