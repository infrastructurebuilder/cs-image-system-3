# What a CI runner needs

*Stage 92, 2026-10-16. Written for no CI system in particular: a GitHub
runner, a GitLab runner, an Azure DevOps agent or a machine of your own
is a cs-image-system CI runner when it meets this page. The image under
[ci/runner-image/](../ci/runner-image/) is one implementation of it, and
[.github/workflows/ci-from-scratch.yml](../.github/workflows/ci-from-scratch.yml)
is another; both are tested against this page.*

## 1. What the jobs do

A configuration repository's CI is three jobs, and every step of them is
a `just` target of the tree, so a runner that can run `just` in the
checkout runs the same thing a person does
([DAILY_DRIVER.md](../DAILY_DRIVER.md), 1.8). In the order the starter
workflow calls them:

| Job | Targets, in order | Needs |
| --- | --- | --- |
| `verify` | `just --list`, `just public-safe` | the release installed; no secret |
| `live` | `just validate`, `just config-drift`, `just state-query --strict`, `just test-mods --strict`, `just mirror-clean` | the read-only cloud identities, the OPA key pair, the age identity, a docker daemon |
| `perform` | `just record`, `just dry`, `just cloud-perform <runtime>`, `just ci-login-proof --runtime <runtime>`, `just record` again, `just state-query --strict`, `just mirror-clean` | the write identity for the performing step and the login proof, and push access to the repository |

The release itself is installed by the job from the index
(`uv tool install cs-image-system==<the content of .csis-version>`); a
development version comes from TestPyPI with PyPI as the extra index.

## 2. The machine

- **An OS the tools run on.** The image is AlmaLinux 10 (RHEL-family,
  binary-compatible with RHEL 10, supported to 2035), the family the
  system bakes; any Linux the tools below install on will do, and the
  from-scratch workflow proves Ubuntu 24.04. `bash` 5 is required;
  macOS's 3.2 is refused by `validate`.
- **A docker daemon the runner can reach.** The modification tests run
  every modification twice in a throwaway container (`test-mods`). The
  image carries the docker *client* alone and reaches the host's daemon
  through the mounted socket (`-v /var/run/docker.sock:/var/run/docker.sock`);
  a GitLab runner gives the same with the docker socket binding or a
  docker-in-docker service.
- **Federation by OIDC.** The read-only and write cloud identities are
  assumed from the job's OIDC token, never from a stored key: on GitHub
  the job holds `id-token: write`; GitLab's `id_tokens` and Azure
  DevOps's workload identity federation are the same mechanism. The
  OPA workload connection is proved the same way (`workload probe`).
- **The secrets the gate reads**, as the workflow names them
  ([CI_SETUP.md](examples/standard-aws/CI_SETUP.md), 3.7): the Okta API
  key, the OPA key pair, the age identity, the role ARNs or service
  account names. A job with none configured is skipped and says so; one
  with some missing fails by name.
- **The network it must reach:** the package indexes (PyPI and
  TestPyPI), the registries the tools come from (below) and Docker Hub
  for the test images, the clouds' APIs (AWS in the runtime's region,
  Google's, Okta's), and the repository to push the records back.
- **Write access to the repository** for the performing job alone, so
  the records it commits can be pushed.

## 3. The tools, their floors and their sources

The floors are what `cfg/executables.yml` in every starter pins and
`validate` checks ([CONFIGURATION.md](CONFIGURATION.md), section 3);
the versions are what the image carries (its `/etc/csis-ci/tools.txt`
is the same list, and the probe `csis-ci-probe` asks each tool). Where
the starters pin a path (`/usr/local/bin/<tool>`), the tool must answer
there.

| Tool | Floor | In the image | Source |
| --- | --- | --- | --- |
| `uv` | any current | 0.12.18 | the uv release archive (astral.sh) |
| `just` | 1.56+ | 1.56.0 | the just release archive (casey/just) |
| `tofu` (OpenTofu) | `>1,<2` | 1.12.6 | the OpenTofu release archive |
| `packer` | `>=1.14` | 1.14.3 | HashiCorp's release archive |
| `aws` (AWS CLI v2) | `>=2.32` | 2.37.1 | AWS's versioned installer archive |
| `session-manager-plugin` | any current | 1.2.835.0 | AWS's versioned rpm |
| `gcloud` (Google Cloud CLI) | `>=500` | 589.0.0 | Google's versioned archive, pinned by checksum (EL10 refuses Google's rpm key) |
| `sft` (Okta Privileged Access client) | 1.114 in use | 1.115.0 | Okta's EL10 repository (`scaleft-client-tools`) |
| `docker` (client) | `>=24` | 29.9.1 | Docker's EL10 repository (`docker-ce-cli`) |
| `ansible-playbook` (ansible-core) | `>=2.16` | 2.21.4 | a `uv tool` on the image's Python |
| `yq` | `>=4.5` | 4.53.6 | the yq release binary (mikefarah/yq) |
| `jq` | `>=1.7` | 1.8.2 | the jq release binary (AlmaLinux's own answers `jq --version` with no number) |
| `age`, `age-keygen` | any current | 1.3.2 | the age release archive |
| `python` (for the release) | 3.13+ | 3.13 | a uv-managed interpreter (AlmaLinux 10 ships 3.12) |
| `node` (for pyright, the bar's type-check) | 20+ | 22 | the distribution (`nodejs`), with `libatomic` for a node that pyright downloads |
| `bash` | `>=5` | 5.2 | the distribution |
| `git` | 2.18+ (the checkout action) | 2.52 | the distribution |

## 4. The implementations, and what moves

**The image**, `ghcr.io/infrastructurebuilder/csis-ci:alma10-<YYYYMMDD>`,
is built from [ci/runner-image/Dockerfile](../ci/runner-image/Dockerfile)
by the [Runner image](../.github/workflows/runner-image.yml) workflow.
A push that changes `ci/runner-image/`, or a dispatch, publishes the
tag the tree pins, the content of `ci/runner-image/TAG`; the monthly
schedule publishes today's date as a candidate, taken by moving `TAG`
and the workflows' lines (a test holds them equal). A published tag is
never rebuilt: a second image on one day is `alma10-<YYYYMMDD>.2` (the
first, 2026-10-16, lacked git's `safe.directory` for a checkout owned by
another user; the second lacked the `libatomic` that pyright's node
needs, so `.3` is the first that ran the bar).

**Who may pull the image is two settings, and both bit on the first
day.** The runner pulls the image with the job's own token before any
step runs. A job that declares a `permissions:` block gets only what
the block names, so a block without `packages: read` pulls as nobody;
every job of every workflow here carries that line, and a test holds
it (the second image was pulled by `verify`, which declares no block,
and refused to `live`, which does). The package itself is published
under the organisation (`ghcr.io/<owner>/csis-ci`) by the workflow's
token, and its visibility is the organisation's package setting on
GitHub, not the workflow's: the first publish on 2026-10-16 came out
PRIVATE, which another repository's token cannot read however its job
is written. The setting is "make the package public" in the
organisation's packages page; until it is, a configuration
repository's jobs fail at "Initialize containers" with `denied`
although the image exists. Check it once after the first publish, and
whenever a job of another repository cannot pull an image a job here
just built. The base is pinned by digest and every tool by version;
the probe runs at build time and `just runner-image` builds and probes
it locally (a leg of `just full-test`). A starter workflow pins one date tag on every
job (`container: image:`); `init-config --force` moves it with the
release's other lines, so a tree's CI changes only when the tree takes
a release. The image and the release move at different paces by
choice: a new image is not a new release, and a release does not need
a new image unless a tool's floor moved.

**The from-scratch path**, kept in this repository alone, is GitHub's
`ubuntu-24.04` image with every tool installed by a step, the way every
job ran before stage 92; it runs on `develop` weekly beside the image
path, so the list above stays true on a machine that holds nothing.

**Another CI system** builds its runner from this page: the table is the
list to install, section 2 is what the machine must be able to do, and
section 1 is the contract the jobs call. The Dockerfile is the shortest
way: a GitLab runner can use the same image as `image:` with the docker
socket bound.
