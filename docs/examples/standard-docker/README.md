# standard-docker: the smallest configuration on a docker host

Its template repository is
[`infrastructurebuilder/cs-image-system-starter-standard-docker`](https://github.com/infrastructurebuilder/cs-image-system-starter-standard-docker):
"Use this template" there makes a repository of your own from this tree,
generated from it with each final release.

The smallest tree a team writes to get going on the **docker runtime**:
images baked into, and containers run on, the container daemon of a
host, with its people as **POSIX accounts** in them. No cloud,
no account, no Okta or OPA, no credential of any kind in the YAML. Copy it,
replace every `REPLACE-ME` value, and it is a configuration: `just init`,
then `just validate`. As it stands it works against the daemon of the
machine you run it on (Docker Desktop, OrbStack, colima, Docker Engine),
which is the way to try it; a durable host is named in the runtime when
the containers are meant to outlive your laptop.

**Read this first: whoever can reach a docker daemon is root on its
host.** Docker's API has no narrower grant. The system says so rather than
hiding it, and it does nothing to soften it; the daemon and its host are the
team's to secure (see CI_SETUP.md 3.4a before you give CI a key to one).

What changes, against [`standard-aws-posix`](../standard-aws-posix/README.md):

- **The runtime** is `docker`: it names a daemon (by `host:` or `context:`;
  here neither, so the caller's environment's), the repository images are
  tagged into, the limits a container runs under (`machine_types`) and a
  network by name. Nothing about subnets, zones, accounts or sessions.
- **The bake** is packer's `docker` source: the vendor image is pulled
  (pinned by digest from the catalog's `docker` block), the base and the
  modifications run inside it through the daemon as `root`, and the result is
  committed and tagged into the daemon's image store. There is no machine
  image and no cloud-init.
- **An instance** is a container: `docker run --init` with a keepalive,
  `restart: unless-stopped`, the image's build pinned by id. There is no
  init system, so the launch work (hostname, accounts, keys, the group's
  subtree on the volume) is delivered by `exec` once the container is up, and
  services are not supported.
- **Storage** is a docker volume, mounted by the platform and owned by the
  group like any other.
- **State** is `local`: a directory (`state/`) on the machine that runs the
  tool, never committed. One machine drives these roots; a team that needs
  more keeps the state in `s3` or `gcs` (the CONFIGURATION.md state-backend
  sections).
- **There is no login proof.** A container runs no sshd, so there is no ssh
  login for CI to prove. A person reaches a container with `docker exec -it
  -u <user> <name> bash`, and `cloud-verify` checks the accounts, the
  marker and the mount by `exec`.
- **CI** has no cloud federation. Its `live` job runs against the runner's
  own daemon unless CI is given a way to yours; `perform` records only
  against your host (CI_SETUP.md 3.4a).

What it declares (one of everything):

| Piece | File | Plugin (`type:`) |
| --- | --- | --- |
| the runtime | [`cfg/runtime-builders.yml`](cfg/runtime-builders.yml) | `docker` |
| the state backend | [`cfg/state-backends.yml`](cfg/state-backends.yml) | `local` |
| the base image (OS builder) | [`cfg/os-builders.yml`](cfg/os-builders.yml) | `rhel` (the family `alma-linux`, which the catalog says IS rhel) |
| the image sources | [`cfg/image-sources.yml`](cfg/image-sources.yml) | the tree's layer of the vendor-image catalog, empty: the release's catalog answers for `alma-linux` (CONFIGURATION 5a) |
| the image builder | [`cfg/image-builders.yml`](cfg/image-builders.yml) | `packer-docker` |
| the modification builders | [`cfg/mod-builders.yml`](cfg/mod-builders.yml) | `ansible`, `bash-remote` |
| the instance builder | [`cfg/instance-builders.yml`](cfg/instance-builders.yml) | `tofu-docker` |
| the storage builder | [`cfg/storage-builders.yml`](cfg/storage-builders.yml) | `tf-docker-volume` |
| the group and user builders | [`cfg/group-builders.yml`](cfg/group-builders.yml) | `posix` |
| the tools | [`cfg/executables.yml`](cfg/executables.yml) | |
| the global settings | [`cfg/_config.yml`](cfg/_config.yml) | |
| one group, two users | [`groups/groups.yaml`](groups/groups.yaml), [`groups/users.yaml`](groups/users.yaml) | |
| one storage | [`storages/storages.yaml`](storages/storages.yaml) | |
| one instance image | [`images/images.yaml`](images/images.yaml) | |
| one instance | [`instances/instances.yaml`](instances/instances.yaml) | |
| its playbook and script | [`playbooks/setup-node.yml`](playbooks/setup-node.yml), [`scripts/post-install.sh`](scripts/post-install.sh) | |
| one overlay | [`overlays/launch.yaml`](overlays/launch.yaml) | |

Every file opens with a comment saying what it declares and where
[CONFIGURATION.md](../../CONFIGURATION.md) documents it. Inside the files,
a `REPLACE-ME` value is a placeholder the team must replace (a project
label, a group's ids, a person's key); every other line that could have been
written differently carries a `DECISION` comment saying what was decided
and what the alternatives are.

## What is synthetic

- The two users are the frozen fixture's personas (`avery_alpha`,
  `casey_charlie`) with placeholder keys. Replace them with your people.
- The tree is encrypted to the TEST identity committed beside it
  (`.age-identity`, public key `.age-recipient`). Export it to load the
  tree as it stands: `CSIS_CONFIG_IDENTITY=<copy>/.age-identity`.
  Encrypting to a committed key protects nothing; replace the recipient in
  `cfg/_config.yml`, run `cs-image-system reencrypt`, and drop the
  `path:.age-identity` allowance.

## What travels with the tree

This tree is a whole configuration REPOSITORY, not only the YAML. The
release carries it: `cs-image-system init-config <dir> --from
standard-docker` writes it out, and every part a team needs is then there:

| Part | What it is |
| --- | --- |
| `Justfile` | the single entry point: the five contract targets (`init`, `build`, `test`, `full-test`, `release`) and every daily and cycle recipe, each wrapping the released `cs-image-system` command against this tree; the `cloud-*` recipes take the docker runtime as their argument |
| `CI_SETUP.md` | setting CI up from scratch (the same guide every starter carries; its cloud and OPA sections do not apply here, 3.4a is this tree's): the repository settings, every secret the workflow reads, the proofs in order, and what each first-setup failure means; GitHub in full, GitLab not yet written |
| `.github/workflows/ci.yml` | the repository's own CI: `verify` (no secrets), `live` (validate, drift, state, the modification tests), `perform` (on `main`, against your docker host, records pushed back); every `REPLACE-ME` in it is a team value |
| `.githooks/pre-commit` | the public-safe gate on every commit; `just init` installs it |
| `tfmodules/` | the terraform modules the emitted roots call, at `module_source_base: tfmodules`; the release's, byte for byte (`cs-image-system init-config` writes them, and refreshes them after an upgrade) |
| `scripts/` | the tree's own modification scripts |
| `.gitignore` | the shell's exports, every credential file, the private mirror, tool residue and `*.tfstate`; `generated/` and `meta-state/` ARE committed |
| `.csis-version` | the release that wrote the tree, which CI installs; `init-config` writes it (absent in this source copy) |

Before CI can run, most of what the guide's GitHub section describes can be
generated: `just bootstrap` interviews you (or takes every default with
`--quiet`), writes `bootstrap.yaml` at the root of this tree and
`generated/bootstrap/` from it. The docker section reads this tree's
runtime and asks one question, can CI reach the daemon over ssh; it
creates nothing, since a daemon is a host somebody runs. CI_SETUP.md
section 3.0 says what the bootstrap makes and what is still yours.

The system itself is installed from a release, never cloned beside the
tree: `uv tool install cs-image-system` puts the command on `PATH`, or a
`pyproject.toml` here that depends on it and `export CSIS="uv run
cs-image-system"`. [DAILY_DRIVER.md](../../DAILY_DRIVER.md) is the
narrative, from the first command on.

## Before the first run

- The released system: `uv tool install cs-image-system`, then `just init`
  (the hook, the plugin cache, a check that the command runs).
- A docker daemon the `docker` CLI reaches (`docker version` answers),
  plus `packer`, `ansible-playbook` and `tofu` at the floors
  `cfg/executables.yml` names. Nothing else is needed: there is no
  account, profile or session to hold.
- `CSIS_CONFIG_IDENTITY` pointing at an identity that opens the tree's
  `ENC[age:...]` values (`.age-identity` as it stands; your own after
  `reencrypt`).
- `tests/test_docs_examples.py` in the cs-image-system repository loads and
  validates this tree with every tool stubbed, and holds its `Justfile`,
  workflows, hook and modules to the release's, so it stays a working
  starter as the code moves.

The cloud twins are [`../standard-aws-posix/`](../standard-aws-posix/README.md)
(the same identity on AWS), [`../standard-aws/`](../standard-aws/README.md) and
[`../standard-gce/`](../standard-gce/README.md); every field and variation is
in [`../complete/`](../complete/README.md).
