# TODO

One section per stage in flight. A landed stage's section is removed;
its squash commit is the record, and the history is in git and
[docs/history/](docs/history/README.md). **USER** marks a step only the
operator can take.

**Open**

- §30 landed in two branches (below). Standing: the core's re-export
  shims of the contract stay until the operator commits to it; a WEEKLY
  reminder to remove them stands until then, and removing them is done
  together with moving the package to a repository of its own (DESIGN
  §3P, "Reversibility"). Tier C, the run-context protocol, is a later
  stage and declares without injecting while the contract is
  provisional.
- §94, the F44 review: standing; next on or after 2026-11-09.
- §103, a container runtime (docker and the daemons that speak its
  API): planned 2026-10-29; eight questions wait for the operator's
  answers, then "do 103".
- No hygiene bundle is open; the next non-critical issue opens bundle
  XX.
- No documentation stage is open.

**Release**

- 0.1.4, the latest final release: PyPI and TestPyPI, tag `v0.1.4`
  (2480c76), 2026-10-29, cut straight from 0.1.3. Carries §30 (the
  contract package and its proof plugin: two new PyPI projects, now
  twenty), §101 and §102. Its tag published the four template
  repositories again (tag `v0.1.4`).
- The reference configuration runs 0.1.4 (take c837606, records to
  217b258); `perform` green on 2026-10-29, nothing baked. Its tag
  `v0.1.4-before` (b80b27e) marks the state before the move; the
  release tag is the after marker (the operator's rule since 0.1.4,
  so no `-after` tag).
- Last development release: 0.1.2.dev2.
- The §66 proof passed whole on 0.1.4 (2026-10-29): a private copy of
  `standard-aws`, its first push and a dispatched dry run green with
  `live` and `perform` SKIPPED, `uv tool install
  cs-image-system==0.1.4` from PyPI (the contract included), and `just
  init` naming the release (`init: cs-image-system 0.1.4 ready against
  ...`, §101). The copy was deleted afterwards.
- `STARTER_PUSH_TOKEN` (`cs-image-system-starter-repos-token`) expires
  2027-10-25: renew it before then.

**Landed since 2026-10-05** (newest first)

- §102, hygiene bundle XIX: 2026-10-29, its squash commit. pyright's
  override check (`reportIncompatibleMethodOverride`) is on as an error
  over the whole workspace, and the nineteen places it named are fixed;
  the terraform root mixin reaches the run context through the builder's
  accessor, so the okta builder tests stand alone.
- §30, the plugin contract package: 2026-10-29, two squashes. Branch 1
  (41f5f3a, tags `s30-1-before`/`s30-1-after`): `cs-image-system-contract`,
  one package with a module per kind, upstream of the core, which
  implements its protocols nominally; the old paths in `base` re-export
  it (the shims); the collector takes the declared state backends from
  the core at load; every plugin depends on the contract and `base`,
  none on `system`. Branch 2 (its squash, tags `s30-2-before`/
  `s30-2-after`): the proof, `cs-image-system-contract-example-plugin`,
  OpenTofu's `inmem` state backend written against the contract alone,
  loaded, structured and run in a dry `run --all`; the core's one
  nominal gate on builder models became the protocol's.
- §101, hygiene bundle XVIII: 2026-10-28, its squash commit. The CLI
  takes `--version` and prints the installed release before anything
  loads, so a starter's `just init` line names the release it found.
- §100, hygiene bundle XVII: 2026-10-28, its squash commit. CI's
  guard (`runtime-unchanged`) passes the vendor's newest image moving
  under a base with no build yet, as `config-drift` does, and names
  the move; a diff cut short is never read as one.
- §98, hygiene bundle XVI: 2026-10-27, its squash commit.
  `config-drift` says what it is doing as it goes and leaves the
  provider cache out of its copy, as every `full-test` copy now does
  too; an unconfigured copy of a starter skips `perform` on its first
  push to `main`.
- §99, a development pin installs from TestPyPI again: 2026-10-26, its
  squash commit (every install line names `--index-strategy
  unsafe-first-match`).
- §97, hygiene bundle XV: 2026-10-24, its squash commit. A tree
  `init-config` writes links out of the starter at the release's tag.
- §66, starter repositories on GitHub: 2026-10-24, its squash commit.
  Four public template repositories generated from `docs/examples/`
  per final release; every CI job reads its image from
  `vars.CSIS_RUNNER_IMAGE`; the runner image is public.
- §96, hygiene bundle XIV: 2026-10-23, its squash commit. A release
  resumes after a partial upload (`release-finish`), uploads one project
  at a time, reads PyPI's new-project limit as "not now" and proves its
  token; the strict query reads each group's OPA objects back.
- §83, a release asks its publish target first: bbb7ee4, 2026-10-17.
- §95, hygiene bundle XIII: 8cdc07c, 2026-10-17.
- §92, CI runs in the system's own AlmaLinux 10 image: 661270f and four
  follow-ups, 2026-10-16.
- §93, everything carries its configuration's id: 23bb441, 2026-10-16.
- §81, hygiene bundle XII: 64c3bc7 to ca7127d, item 33 b28d50b,
  2026-10-14.
- §65, the walk of the daily driver: 8afd4ef, 2026-10-14.
- §84 to §91, the walk's findings: 4fb338b, b0494fa, c6af4b2, 9655327,
  20206e8, 7eb5962, cdb80bf, e72cc1b, 2026-10-07 to 2026-10-14.
- §82, an image says which configuration owns it: 0d1850c, 2026-10-05.

**Standing decisions** (the operator's)

- Documents describe what is and carry no commit hash; a landed stage's
  record is its squash message.
- A non-critical issue goes into the open hygiene bundle (start one if
  none is open); large or blocking work gets its own stage.
- A stage is a plan until the operator says to execute it.
- A documentation stage changes no code; a code change it needs is a new
  stage.
- Documentation stays current: work that changes behaviour,
  configuration, tests or procedure and lands undocumented opens the
  rolling documentation stage, which lists what changed since the last
  update.
- Both repositories are public, each from one redacted commit. Account,
  project, network, image and bucket ids and the Okta org and team are
  public by decision; live rosters are encrypted to the four recipients;
  fixture people are synthetic.
- All terraform state stays on the S3 backend. Backends `s3`, `local`
  and `gcs` exist; `gcs` is declared and bound to nothing. Moving the
  GCE roots to GCS and per-runtime network checks are last, and not
  stages.
- GCP is the operator's money: no new GCP work unless a change could
  break the GCP code; then the GCE cycle runs on the operator's account
  and is torn down.
- `main` performs (stage 45): it records, bakes, releases and applies
  retention on AWS under the write role, then records again. GCE stays
  out of CI. A push to `main` is the operator's.
- Releases: `just release <part|version> [test|pypi]`, TestPyPI first; a
  deleted version is never re-cut; trusted publishing replaces the
  tokens once package names are stable.
- The plugin contract (§30) is provisional until the operator commits
  to it: the core's re-export shims stay, Tier C declares the context
  protocol without injecting it, and the stage may be undone by the
  soft route (DESIGN §3P). Removing the shims is the commitment, done
  together with moving the contract to its own repository.
- The bootstrap is ongoing work: a new release-owned part, runtime or
  secret owes it a section, module or question in the same stage.
  Keeping its state in GitHub is not built. The operator's words (§70):

  > Initially, the user must install the base application (generally using `uv`).
  > Then the user would fork and clone the starter repository.  This would give them
  > a place to land the bootstrapping code.  They would then start the bootstrapping
  > interview, and should end up with a runnable copy of the application, as well
  > as a configured set of dependencies, bootstrap code, and target locations for
  > state management (including, possibly, storing state in github [not recommended]).
  >
  > Once landed, the §70 work should be considered part of the ongoing updates of the application
  > and the starter repository, such that any new items are part of the process.

---

## 94. A verification starts a machine its operator switched off: KEPT, and reviewed monthly

**Status: OPEN 2026-10-15 as a stage of its own, moved here from hygiene
XII (item 25) when the bundle closed; the bundle's thirty-three items
landed in §82, §86, §88, §91, §93 (a plan) and the seven groups and item
33 of 2026-10-14/15. Nothing here runs: it is a standing review. USER,
on or after each date: keep the behaviour, or make it a stage (a
verification SKIPS a machine that is off unless it is asked to start
it). Each review is written below with its date and its outcome.**

**The finding.** The walk's F44 (2026-10-09, stage 14f; seen in the
machine's own boot log and in CloudTrail). `verify instance` on a
stopped machine starts it, checks it and stops it again (stage 57's
bounded exception); the daily driver's failure table said the opposite.
The operator's decision that day: "let's keep the behavior for F44 but
make a very prominent note about it somewhere. We should revisit that
question at least once a month for the next 4 months." The note is made:
`DAILY_DRIVER.md` 3.5 in capitals, and the section 6 row corrected.

**The reviews.**

- 2026-11-09: (open)
- 2026-12-09: (open)
- 2027-01-09: (open)
- 2027-02-09: (open)

## 103. A container runtime: docker and the daemons that speak its API

**Status: planned 2026-10-29. Nothing is built. The eight questions
below want the operator's answers first; the work then waits for "do
103".**

**Why**: every runtime today is a cloud. A durable host running a
container daemon is a third kind: cheaper than either cloud, local to a
team, and the first target the system can prove end to end without
spending money. The core already has the seams for it, and a scatter of
container pieces that nothing uses (below). The operator's assumptions
(2026-10-29), taken as given:

- the target platform is durable: a container started there is still
  known to the daemon after it stops, until something removes it;
- the system reaches it through a control daemon and standard container
  tooling (the Docker Engine API, the `docker` CLI, `DOCKER_HOST` and
  docker contexts), never through a cloud API;
- instances are POSIX: Linux first; BSD and other Unix-likes are allowed
  by the shape but not built; Windows containers only if trivial (they
  are not: see "Out of scope").

**What exists and belongs to nothing** (surveyed 2026-10-29)

- `ContainerSourceConfig` and `DockerSourceModel` in default-os-plugin's
  [docker_os_source_types.py](packages/default-os-plugin/src/cs_image_system/default_os_plugin/docker_os_source_types.py)
  (fields `tag` and `version="latest"`), and the `SourceModel` they
  extend: no service list names them and no fixture or test uses them;
  the package README says so. An OS already picks its source per
  runtime through its `runtimes:` entries (`image_id`, `owners`,
  `query`), which the runtime's `query_provider_image` resolves; these
  classes are a second, unfinished route to the same thing.
- In `base`: `ContainerBuilderModel` with `ContainerNetworkingModel`
  (`network_id="local"`), `Container`, and an empty
  `ContainerBuilderBase`; `VCT.CONTAINER_BUILDER_MODEL` and
  `CONTAINER_BUILDER`, which the loader and the registry fold into the
  runtime namespace. No plugin subclasses any of it. Three defects:
  `ContainerBuilderModel` does not return its own classifier
  (`CloudBuilderModel` does, and a contract test's comment says both
  do); `ContainerNetworkingModel` inherits the demand for a subnet list
  with a default subnet, which a container network does not have; and
  `CONTAINER_PROVIDER_TYPE` is `"container_provider"` in the contract
  but `"container"` in `base`.
- A commented-out `docker` and `docker-swarm` runtime in the frozen
  fixture's `cfg/runtime-builders.yml`, naming an image builder
  (`packer-docker-ansible`) that does not exist.
- [ansible_launch.py](packages/base/src/cs_image_system/base/ansible_launch.py):
  the launch parameters rendered as an inventory and a playbook "for
  targets that have no user-data"; DESIGN §3H says it waits for a metal
  or container target.
- Working prior art: the modification tests
  ([mod_tests.py](packages/base/src/cs_image_system/base/mod_tests.py):
  `docker run -d ... sleep infinity`, `exec`, `cp`, `diff`, ansible with
  `-c docker`, and a family-to-image table that is exactly an OS's
  default container source), and the posix accounts script, proved on
  almalinux:10 and debian:12 under docker. Both hard-code the binary
  `docker` and ignore the `docker` entry in `executables.yml`.
- The ansible builder's `ansible_connection` field, documented for the
  packer docker case and set by nothing.

**What a runtime is today**: a runtime plugin writes no files of its
own. The packer, instance, verify, power, generation, release, disposal,
relabel and accounts code calls hooks on `RuntimeBuilderBase` (declared
in `contract.runtime`), each defaulting to "cannot". So most of a
container runtime is those hooks implemented against the daemon. These
parts are NOT behind the seam and must be taught:

- preflight knows only the provider names `aws` and `gc`/`google`, and
  reads runtimes only, never the state backend's session;
- load failures classify only botocore errors;
- the packer source type falls back to `amazon-ebs`, and the bake waits
  on `cloud-init status`;
- the launch script goes in as user data (EC2) or a startup script
  (GCE), and uses `hostnamectl`, block devices, fstab and NFS;
- `launch_params` and `ansible_launch` hard-code the storage kinds
  (`ebs`, `pd`, `efs`, `filestore`, `s3`, `gcs`);
- the bootstrap's runtime facts prefer `aws` by name, the GitHub section
  hard-codes AWS and GCP secrets, and the four starters are all cloud;
- terraform state: a container runtime's roots resolve to the default
  backend, S3 in the reference, so a docker-only tree still needs an
  AWS session under the standing decision, and preflight would not
  check it.

**Questions for the operator** (each with the proposed default; the
answers become this section's Decisions before "do 103")

1. **Which daemons.** Default: any daemon speaking the Docker Engine
   API, addressed by a `DOCKER_HOST` URL or a docker context
   (`unix://`, `ssh://`, or `tcp://` with TLS): Docker Engine, Docker
   Desktop, OrbStack, colima, and Podman's API service. The `type:` key
   is `docker`; a workalike is proved, not keyed separately. containerd
   with nerdctl has no Docker API and is out. The proofs run on the
   local machine's OrbStack (Docker API 29.8, there today) and on
   Podman, which is not installed here.
2. **What PID 1 is.** Default: no init system. A container runs the
   image's keepalive under `--init`; the launch work is run by `exec`
   after the container is created; services that need systemd are not
   supported on this runtime, and image tests that check enabled
   services answer "not applicable". The alternative is systemd as PID
   1 (Podman's `--systemd=always`; Docker needs a writable cgroup and
   more privilege): service parity with the clouds, at the price of a
   privileged container.
3. **Identity.** Default: POSIX accounts only (the posix identity
   plugin, already proved in containers), with access through the
   daemon (`docker exec -u <user>`). Whoever can reach the daemon is
   root on the host, and the docs say so. An OPA (`sftd`) group on a
   docker runtime is refused at validation with one clear sentence.
   Enrolling sftd in a container needs systemd or a supervisor, sshd,
   a reachable access address, and an identity other than the instance
   id sftd reads from the cloud's metadata service, which a bridged
   container either lacks or shares with the host. That is a later
   stage.
4. **Where images live.** Default: in the daemon's own image store,
   which the durable-host assumption makes as lasting as an AMI. A
   build is an image id plus the tag `<repository>:<final-name>`.
   Release and relabel move tags, because an image's labels are fixed
   when it is built. Pushing released builds to a registry is a later
   option on the runtime.
5. **Terraform state.** Default: unchanged, the standing decision ("all
   terraform state stays on the S3 backend"). A docker runtime in the
   reference then needs an AWS session, as the GCE roots do, and
   preflight learns to check the session of every state backend a run
   reaches. `local` stays available for a tree that wants no cloud at
   all.
6. **Starters and the reference.** Default: a fifth starter,
   `standard-docker`, with `local` state, published by the next
   release. The reference configuration gains a docker runtime aimed at
   a durable host. **YOUR DECISION: which host**; the local machine's
   OrbStack does not survive a reinstall. CI never performs on it,
   because GitHub's runners have no durable daemon: the runtime is
   guarded in CI as the GCE one is.
7. **The orphan source classes.** Default: removed. The docker runtime
   resolves an OS's `runtimes:` entry as the clouds do: `image_id` pins
   `repository@sha256:...`; `query` names `repository` and `tag`; with
   neither, the OS's family and version give the image through the
   table the modification tests use. The resolved digest is recorded,
   so a vendor moving a tag shows as a move.
8. **Machine types.** Default: a `machine_types:` map on the runtime,
   from a name to `{cpus, memory}`, with `default_machine_type` naming
   one; an instance's `machine_type` picks its limits. The contract's
   `default_machine_type` stays required.

**Branch 1, `feature/container-runtime`** (the runtime and the bake,
about five days)

1. The contract first. `contract.runtime` gains a
   `ContainerBuilderModelProtocol` (`host`, `context`, `networking`,
   `machine_types`) beside the cloud one. Any new hook the later steps
   need (for example a post-create launch delivery, if `exec` through
   `run_session_command` is not enough) is declared there before `base`
   implements it. The contract stays provisional (§30).
2. The core's scaffolding fixed, not added to: `ContainerBuilderModel`
   classifies as `CONTAINER_BUILDER_MODEL` and dispatches as a runtime;
   `ContainerNetworkingModel` names a network (default `bridge`) and
   requires no subnets; one `CONTAINER_PROVIDER_TYPE`; the contract
   test's comment made true. Networks are referenced by name and never
   created or changed (the network rule of stage 1).
3. `packages/docker-runtime-plugin` (`cs_image_system.docker_runtime`,
   `type: docker`, entry point `cs_image_system.plugins.runtime`), on
   the core's bases like the two clouds:
   - the model: `host` or `context`, never a credential in YAML (TLS
     material by path or ENC marker), `state_configuration`,
     `machine_types`, networking;
   - a version checker on the `docker` executable;
   - the image hooks: `query_provider_image` and `_by_id` (pull and
     inspect, recording the digest), `query_images` (by the
     configuration's label, §93), `build_id_from_artifact`,
     `retag_image` (tags), `dispose_image` (`docker image rm`, refused
     while a container uses the image), `release_commands`,
     `label_key_problem` (docker's label rules),
     `bake_settle_commands` (none: no cloud-init), `default_bake_user`
     (root), `session_mechanism` (`exec`).
4. The bake. packer-plugin gains `packer-docker` (a subclass, as
   `packer-gce` is), and the runtime emits `source "docker"` from
   HashiCorp's docker plugin: `image` by digest, `commit = true`,
   `changes` for the labels and the keepalive command, and a
   `run_command` with `--init`; then a `docker-tag` post-processor and
   the manifest. The ansible builder sets `ansible_connection = docker`
   for this source, as its own comment documents. The bake's steps skip
   the cloud-init wait. Lineage, pins and the release model work
   unchanged through the hooks.
5. What is not behind the seam, for images: preflight learns `docker`
   (`docker version` against the host, in one line) and the state
   backend's session; load failures classify an unreachable daemon in
   one line; the packer fallback stays, but a docker runtime never
   reaches it. The modification tests and the posix container test
   read the `docker` executable from `executables.yml` instead of the
   literal.
6. default-os-plugin: the orphan source classes go (question 7), and
   its README's "present but not registered" paragraph changes with
   them.
7. Tests and proof. An overlay on a copy of the frozen fixture declares
   a docker runtime, a `packer-docker` image builder, a base image and
   an instance image; the fixture itself and the golden do not change.
   A dry `run --all` over it emits the docker sources. A new
   `full-test` leg bakes the overlay's AlmaLinux 10 and Debian 12 base
   and instance images on the local daemon, checks the lineage and the
   tags, disposes the images, and skips loudly without docker.

**Branch 2, `feature/container-instances`** (instances and storage,
about five days)

8. `packages/tf-docker-plugin` (entry point
   `cs_image_system.plugins.instance`): the instance builder
   `tofu-docker` and the storage builder `tf-docker-volume`. They emit
   roots on OpenTofu's `kreuzwerker/docker` provider, pinned in
   `required_plugins` like the clouds' providers, against two new
   release-owned modules, `tfmodules/docker_container` and
   `tfmodules/docker_volume`, which every starter then carries. Each
   container gets the hostname `<name>-NNN`; labels for the
   configuration id, the build and the generation; its network by
   name; the limits of its machine type; its volumes at their mount
   points; and the restart policy `unless-stopped`.
9. The power state stays the operator's. A container is declared so
   that the next apply does NOT start or replace a stopped container
   (`must_run = false`). This is proved against the provider before
   anything else in the branch; if the provider cannot leave a stopped
   container alone, the branch stops and asks.
10. Launching without user data. After the apply, the same launch
    script the clouds run is delivered by `exec`, as accounts are
    today, minus what a container cannot do: the hostname comes from
    the container, and the daemon mounts each volume, so the script
    only makes the group's subtree and sets its ownership.
    `launch_params` gains one daemon-mounted storage kind instead of a
    new hard-coded branch per kind. The marker
    `/var/lib/csis/launch-applied` is written as on the clouds.
    `ansible_launch` stays a prototype unless the operator chooses it
    as the delivery instead.
11. The instance hooks:
    - `query_instance_power_state`: running; exited or created as
      stopped; paused as suspended; restarting as starting; absent;
    - `start_instance` and `stop_instance`;
    - `query_instance_identity`: the container id is the provider id,
      so a re-create is a new generation, as the ledger expects;
    - `query_instance_boot_image`;
    - `verify_instance` by `exec`: the marker, the mounts, the booted
      image;
    - `run_session_command`;
    - `ssh_proxy_command`: none, because login is by `exec`;
    - `inventory` by the configuration's label, so `cloud-empty`
      works;
    - `instance_tags` and `retag_instance`: labels are fixed when the
      container is created, so relabel reports what a re-create would
      change and does not re-create.
12. Storage: `tf-docker-volume` makes a named volume. Its capability
    type allows several attachments, is not zonal, and is POSIX.
    Archive is a later item: a volume has no snapshot, and a `tar` of
    the volume from a throwaway container is the obvious shape.
    Validation skips its zone comparison for a runtime with no zones.
13. Accounts and verification: `reconcile_accounts`, `verify
    instance`, the post-bake tests and the strict query run unchanged
    through the hooks. An OPA group on a docker instance is refused at
    validation (question 3).
14. Proof: a `full-test` leg runs the docker cycle on the local daemon
    from nothing to nothing. It bakes, launches two instances on one
    volume, verifies, reconciles accounts, stops one and shows that
    the next apply leaves it stopped, starts it, upgrades it to a new
    build (a new generation), decommissions, and disposes. It skips
    loudly without docker.

**Branch 3, `feature/container-operations`** (the system around it,
about three days)

15. The bootstrap section, owed by the standing decision: it asks for
    the daemon's host or context and whether CI can reach it. The
    GitHub section stops assuming a cloud, and `first_runtime_name`
    stops preferring `aws` by name.
16. The starter and the reference's docker runtime (question 6); the
    reference's CI guards that runtime. The `cloud-*` recipes take the
    docker runtime by argument unchanged, and their names stay.
17. The docs, as one rolling item:
    - DESIGN: §1's table, §3E, the launch and identity sections, and
      §3H, which loses "container images";
    - CONFIGURATION: a §4 entry for `docker` and §8 entries for the two
      builders;
    - PLUGINS.md, and DAILY_DRIVER (the tools table, a "container host"
      setup section, chapter 7);
    - OPERATIONS: power, generations, inventory, credentials, the
      cycle, and a "Container hosts" part of the rules;
    - DESCRIPTION's runtimes and known limits, the README of every
      package touched, and CI_RUNNER if the runner image needs the
      docker CLI.
    The two new members owe the workspace touch points listed for §30
    (pins, sources, testpaths and the counts, which become 21 packages
    and 22 projects).
18. A Podman leg: the branch 2 cycle against Podman's API service, on
    a host or runner image that has it, recording what differs.

**Out of scope, recorded** (each would be a stage of its own):

- Windows containers: a Windows daemon, no POSIX, and no tooling shared
  with this stage, so not trivial.
- BSD containers: FreeBSD's OCI support runs under Podman with ocijail
  on a FreeBSD host, and the system has no FreeBSD OS family; each is a
  stage of its own.
- Swarm, Kubernetes and other orchestrators. The fixture's commented
  `docker-swarm` entry stays, because the frozen fixture does not
  change.
- OPA enrollment in containers (question 3), registry push (question
  4), and volume archive (item 12).

**Acceptance at every branch**: golden byte-identical; bar green;
pyright at 0 errors; the conformance test green over the new plugins;
the docs tests green; the `just full-test` legs green, the docker ones
included. Two new PyPI projects mean the first release after this one
is held to PyPI's new-project rate (§96). Records: each branch's squash
message; this section goes when the last branch lands.
