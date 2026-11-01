<!--
SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>

SPDX-License-Identifier: Apache-2.0
-->

# cs-image-system-docker-runtime-plugin

The `docker` runtime type (stage 103): a durable host running a daemon that
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
  runtime is refused at validation; enrolling `sftd` in a container is a
  later stage.

## What it registers

| Class | `csis_name()` | `csis_classifier()` | Role |
|---|---|---|---|
| `DockerContainerBuilderModel` ([docker_runtime_models.py](src/cs_image_system/docker_runtime/docker_runtime_models.py)) | `docker` | `VCT.CONTAINER_BUILDER_MODEL` (folded into the runtime namespace by the loader) | The runtime's declaration: `host` or `context`, `repository`, `machine_types`, `networking`, `state_configuration`, `executable`. |
| `DockerContainerBuilder` ([docker_runtime_builders.py](src/cs_image_system/docker_runtime/docker_runtime_builders.py)) | `docker` | `VCT.RUNTIME_BUILDER` | Every runtime hook, answered against the daemon through the CLI. |
| `DockerCLIVersionChecker` (same file) | `docker` | `VCT.VERSION_CHECKER` | `docker --version` for the `docker` entry of `cfg/executables.yml`. |

Entry points: `cs_image_system.plugins.runtime` → `docker`, and (stage 103
item 15) `cs_image_system.bootstrap` → `docker`, the container-host section of
the bootstrap interview ([bootstrap.py](src/cs_image_system/docker_runtime/bootstrap.py)):

| Class / function | Role |
|---|---|
| `docker_section()` → `Section` | The interview's "Container host" section. Wanted where the tree declares a docker runtime. It reads the runtime from the raw `cfg/` (never loading it, never printing an address: a `host` may be an `ENC[age:...]` marker) and asks two questions, which runtime and *can CI reach its daemon* (default yes for an `ssh://` host or for none declared, no for a socket, a context, a `tcp://` host or a marker). |

The section has no terraform module, because a daemon is a host somebody runs.
Its render says what remains by hand (the daemon and its host, the network,
CI's ssh key and `known_hosts` line, or, when CI cannot reach the daemon, to
name the runtime in `GUARD_RUNTIME`) and its audit lines are all BY HAND or
READ. The two secrets it concerns, `DOCKER_HOST_SSH_KEY` and
`DOCKER_HOST_KNOWN_HOSTS`, are among the GitHub section's, set by its script
from files.

## Models

### `DockerContainerBuilderModel`

Extends the core's `ContainerBuilderModel` (`host`, `context`, `networking`,
`machine_types`) and the runtime model every runtime shares
(`default_machine_type`, `default_image_builder`, `credentials`, `ephemeral`,
`retention_keep`, ...).

| Field | Default | Meaning |
|---|---|---|
| `host` | none | The daemon's address as a `DOCKER_HOST` URL: `unix:///var/run/docker.sock`, `ssh://user@host`, `tcp://host:2376`. May be an `ENC[age:...]` marker when the address itself is private. Declare `host` or `context`, not both. |
| `context` | none | A docker context name (`docker context ls`), set as `DOCKER_CONTEXT`. |
| `executable` | `docker` | The `cfg/executables.yml` entry whose `binary` every docker call on this runtime runs through; `validate` version-checks it. |
| `repository` | `csis/<runtime name>` | Where this runtime's builds are tagged, made a valid repository name (lowercase). |
| `tls_cert_path`, `tls_verify` | none, false | `DOCKER_CERT_PATH` and `DOCKER_TLS_VERIFY` for a `tcp://` host: TLS material by PATH, never a value. |
| `networking.network` | `bridge` | The network the bake container (and, later, every instance) joins, by name; referenced, never created or changed. No subnets, no zones. |
| `machine_types` | `{}` | A map from a name to `{cpus, memory}` (`--cpus 2`, `--memory 4g`). When any are declared, `default_machine_type` must name one. |
| `state_configuration` | the default state manager | The state manager this runtime's roots use; a tree with no cloud declares `local`. |

Nothing in the model is a credential.

## The builder

### The image query

The daemon answers the keys `name` (a repository), `version` (a tag),
`publisher` (a registry namespace; `library` is Docker Hub's and is
dropped), `architecture` (a platform, `x86_64` → `linux/amd64`) and
`native.image` (a reference verbatim). The release catalog's `docker` block
gives every family one (`almalinux:{version}`, `debian:{version}`, ...). The
query PULLS the reference and records its digest reference
(`<repository>@sha256:...`) as the identifier, so a vendor moving a tag shows
as a move. An entry's `image_id` pins a digest reference; a tag is refused
there, because a tag moves.

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

The instance hooks (power state, identity, verification, sessions,
relabel) are the next branch of stage 103; on this branch they answer as the
core's defaults do ("cannot").

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
  `context` must answer (preflight says so in one line per daemon).
- The `docker` CLI, declared in `cfg/executables.yml` (`version: ">=24"`
  is the floor the system runs with); `--init` needs the daemon's
  `docker-init`, which every supported daemon ships.
- `packer` with the `docker` and `ansible` plugins (`required_plugins` of
  the image builder), and `ansible-playbook` on the machine that bakes:
  ansible's docker connection runs the local `docker` CLI against the same
  daemon.
- Podman's API service works as the daemon (proved 2026-11-01 against Podman
  5.8.2 rootless on AlmaLinux 10, through `docker` over ssh; the setup and what
  differed are in [docs/OPERATIONS.md](../../docs/OPERATIONS.md), "Podman as
  the daemon"). A rootless Podman user needs `/etc/subuid` and `/etc/subgid`
  ranges. Podman Desktop's machine on macOS works too, rootful and beside
  OrbStack (proved 2026-11-01 with Podman 5.8.9; `just
  test-podman-desktop-cycle`, which skips when no machine runs; Podman 6
  dropped Intel Macs, so on one the proof lasts until June 2027).
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
digest reference. `output_image_name` (stage 105) is the tag prefix.

## What it tests and verifies

- `validate` version-checks the `docker` executable and refuses a query key
  the daemon cannot answer, a label key it cannot carry, a build name longer
  than a tag, a `default_machine_type` that names no declared machine type,
  and a runtime that declares both `host` and `context`.
- `preflight` runs `docker version` against each docker runtime's daemon
  and prints whether it answers.
- The unit tests ([tests/](tests/)) pin the names module (tags, repository
  names, movable tags), the query translation, the model's environment and
  the packer source and post-processor shapes without a daemon; the
  system's stage 103 tests drive a dry `run --all` over an overlay of the
  frozen fixture and check the emitted docker sources.
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

| Symptom | Cause | Remedy |
|---|---|---|
| `the configuration cannot load: docker runtime X: the daemon at ... cannot be reached` | The daemon is not running, or `host`/`context` names the wrong one. | Start it (OrbStack, Docker Desktop, the engine on the host) or fix the address; `preflight` shows which daemon answers. |
| `executable 'docker' is not declared in cfg/executables.yml` | The runtime's `executable` names no entry. | Declare `- name: docker` with its `binary`. |
| `image_id '...' is not a digest reference` | An entry pins a tag. | Pin `<repository>@sha256:<digest>` (`docker image inspect --format '{{index .RepoDigests 0}}'`). |
| `image ... is in use by container(s) ...` at disposal | A container stands on the build. | Decommission the container first; the image is never pulled from under it. |
| An ansible step cannot reach the container | The bake ran against a daemon other than the one the local `docker` CLI uses. | The runtime's `host`/`context` is what both read; check `DOCKER_HOST` is not also set in the shell to something else. |
| The bootstrap says `docker.runtime: ... -- no default can be derived` under `--quiet` | The tree declares no runtime of type `docker`, or the section was kept from an earlier interview of a tree that had one. | Declare the runtime, or answer `want_docker: no`. |
| `parent: lineage=<id> tag=series:<name>` in the state query on a Podman daemon | A release before 2026-11-01 compared `RepoTags` as written; Podman spells them `docker.io/<repository>:<tag>`. | Take a later release; nothing on the daemon needs repairing, the movable tags were there. |
| `a docker tag is at most 128 characters` at validate | A declared `output_image_name` is too long once the timestamp is appended. | Shorten it. |

## Related

- [docs/OPERATIONS.md](../../docs/OPERATIONS.md), [docs/CONFIGURATION.md](../../docs/CONFIGURATION.md)
- [packer-plugin](../packer-plugin/README.md) (`type: packer-docker`), [posix-identity-plugin](../posix-identity-plugin/README.md)
