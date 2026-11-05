<!--
SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>

SPDX-License-Identifier: Apache-2.0
-->

# cs-image-system-docker-runtime-plugin

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
  a pattern" query; the tag is that query). A label is fixed when an image
  is built, so what the core stamps afterwards (the parent bound after the
  bake, the fingerprint, a release) is carried by tags that MOVE:
  `<repository>:<short id>--<key>--<value>`, one per key.
- **POSIX accounts only.** Access is through the daemon (`docker exec -u`);
  whoever can reach the daemon is root on the host. An OPA group on a docker
  runtime is refused at validation; enrolling `sftd` in a container is
  not yet supported.

## What it registers

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

## Models

### `DockerContainerBuilderModel`

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

## The builder

### The image query

The daemon answers the keys `name` (a repository), `version` (a tag),
`publisher` (a registry namespace; `library` is Docker Hub's and is
dropped), `architecture` (a platform, `x86_64` → `linux/amd64`) and
`native.image` (a reference verbatim). The release catalog's `docker` block
gives every family one (`almalinux:{version}`, `debian:{version}`, ...);
those blocks are this plugin's, shipped as package data in
[`data/image-sources.yml`](src/cs_image_system/docker_runtime/data/image-sources.yml)
and read by `DockerContainerBuilder.image_source_entries()`, so the
release catalog a tree sees carries a `docker` block exactly when this
plugin is installed. The query PULLS the reference and records its digest reference
(`<repository>@sha256:...`) as the identifier, so a vendor moving a tag shows
as a move. An entry's `image_id` pins a digest reference; a tag is refused
there, because a tag moves.

### Image query translation

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

### The local test target

The core's local modification tests (`cs-image-system test-mods`; the
harness is [`mod_tests.py`](../base/src/cs_image_system/base/mod_tests.py)
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

### Bakes

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

### Names

A build's final name is written as a tag: `image_name_as_made` replaces what
a tag cannot carry with `-`; `image_name_problem` refuses a name longer than
128 characters once made (the cut would fall where the timestamp is). A
label key carries no whitespace and no `=`.

### Images in the store

`query_images` lists every image labelled `csis_series`, its lineage facts
read from its labels as built with the movable tags' values on top;
`inventory` adds every container and volume, with the `csis_config` label
each carries. `dispose_image` removes a build and every tag with it, and is
REFUSED while a container was created from it. `retag_image` moves the
per-key tags; `release_commands` moves `<repository>:<series>--<model>`.

### Instances

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

## Example configuration

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

## Prerequisites and integration

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

## Configuration reference

See [Models](#models) for every field of the runtime, and the image
builder's reference in the [packer plugin](../packer-plugin/README.md) for
`type: packer-docker`. An OS builder's `runtimes[]` entry on a docker
runtime takes the usual keys; its `query` may use `name`, `version`,
`publisher`, `architecture` and `native.image`, and its `image_id` is a
digest reference. `output_image_name` is the tag prefix.

## What it tests and verifies

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
- The unit tests ([tests/](tests/)) pin the names module (tags, repository
  names, movable tags), the query translation, the model's environment and
  the packer source and post-processor shapes without a daemon; the
  system's [tests/test_v2_stage_103.py](../../tests/test_v2_stage_103.py)
  drives a dry `run --all` over an overlay of the frozen fixture and
  checks the emitted docker sources.
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

## When it fails

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

## Related

- [docs/OPERATIONS.md](../../docs/OPERATIONS.md), [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)
- [packer-plugin](../packer-plugin/README.md) (`type: packer-docker`), [posix-identity-plugin](../posix-identity-plugin/README.md)
