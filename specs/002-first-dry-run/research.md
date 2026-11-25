# Research: Fifteen minutes to a first dry run

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision is marked with what it rests on: **read** (seen in the
code, or in a trial run on your local machine on 2026-11-21), **decided**
(the operator's answer in the spec's Clarifications), or **chosen** (this
plan's choice, with the alternatives). Written 2026-11-21, when the
questions for the operator were R2 (D1), R18 (D2) and R15 (D3); all three
were decided that day. Revised 2026-11-25 after specification 013 put
every release on TestPyPI until 1.0, published by the tag's push: R3,
R4, R8, R16, R17 and R18 carry that day's decisions, each marked.

The trial runs were made in the session's scratch directory with the
workspace's installed command (release 0.1.12 plus `develop`), against
the local daemon, and in an isolated uv tool directory for the install
commands. Nothing was installed into your own tool directory.

## R1. What a first dry run of the docker starter needs today

**Finding** (**read**):

- **Every declared tool must be present and at its floor before anything
  is generated.** `validate` and every run call
  `check_executables_exist_and_versions`
  ([validate.py](../../packages/engine/src/cs_image_system/engine/commands/validate.py)
  lines 211-229, called from `collect_validation_errors` at line 808),
  which checks each entry of `cfg/executables.yml` with
  `check_single_version` (lines 88-127). The docker starter declares five:
  `docker >=24`, `packer >=1.14`, `ansible-playbook >=2.16`, `bash >=5`
  and `tofu >1,<2`
  ([executables.yml](../../docs/examples/standard-docker/cfg/executables.yml)).
  With only `git` and `/usr/bin:/bin` on `PATH` (macOS), `validate`
  refused with five errors: four `binary '<x>' not found (declared in
  cfg/executables.yml; an absolute path, or a name on PATH)` and `bash
  3.2.57 does not meet its requirement >=5 (cfg/executables.yml)`.
- **A dry run executes three of them.** Each terraform root runs `tofu
  fmt`, `tofu init -backend=false` and `tofu validate`
  ([roots.py](../../packages/tofu-roots/src/cs_image_system/tofu_roots/roots.py)
  lines 112-113); each packer root runs `packer fmt`, `packer init` and
  `packer validate`
  ([packer_image_builder.py](../../packages/packer-plugin/src/cs_image_system/packer_plugin/packer_image_builder.py)
  line 423); the base image's source is resolved by `docker pull --quiet
  almalinux:10` and pinned by digest
  ([docker_runtime_builders.py](../../packages/docker-plugin/src/cs_image_system/docker_runtime/docker_runtime_builders.py)
  lines 250-256, 270-276). `ansible-playbook` and `bash` are only
  version-checked in a dry run. The trial's log shows all of these.
- **The dry run needs a daemon that answers and the network.** With
  `DOCKER_HOST` pointed at a socket that does not exist, `validate`
  passed, the run's state query reported the images and the volume
  `unavailable` and went on, and the base-image lifecycle failed at the
  pull. `packer init` fetches the docker and ansible packer plugins, and
  `tofu init` fetches the `kreuzwerker/docker` provider.
- **It needs no key, no account and no git.** The docker starter carries
  no `ENC[age:...]` value, and `validate` and a dry `run --all` passed
  with `CSIS_CONFIG_IDENTITY` unset. git is called only on the committing
  path ([meta_state.py](../../packages/engine/src/cs_image_system/engine/meta_state.py)
  lines 112-704) and by the drift copy; a dry run without `--commit`
  ran in a directory that is not a repository.
- **The placeholders do not stop it.** The starter as written (its
  `REPLACE-ME` id, tags, gid comments and placeholder keys) validated
  and dry-ran: `Run ... completed: identity, storage, base-image,
  instance-image, release, retention`, `"ok": true`, about 33 seconds on
  a warm machine.
- **A plain `init-config` writes the AWS starter.** The default starter
  is `standard-aws` ([docs/examples/DEFAULT](../../docs/examples/DEFAULT),
  read by [starters.py](../../packages/system/src/cs_image_system/system/starters.py)
  line 168), so the page names `--from standard-docker`.
- **The starter's `just init` needs git.** The skeleton's `init` recipe
  runs `git config core.hooksPath .githooks`
  ([Justfile](../../docs/examples/_skeleton/Justfile) line 36), which
  fails outside a repository.

## R2. The prerequisites, and the limit of four

**Finding** (**read**, from R1): a first dry run needs uv, a docker
daemon with its CLI at 24 or later, OpenTofu (`>1,<2`), Packer (`>=1.14`),
ansible-core (`>=2.16`) and bash 5 or later. ansible-core is a Python
package and the page can install it with uv (R4). The other five are
not. bash 5 ships with every current Linux distribution; macOS ships
bash 3.2, which the starter refuses by decision ("never the system's 3.2
on macOS", the starter's `executables.yml`). Neither `just` nor `git` is
needed if the page calls the command directly (R3).

So the page can state four prerequisites on Linux (uv, Docker, OpenTofu,
Packer) and five on macOS (those and bash 5). FR-002 and SC-004 say four
or fewer.

**D1, the operator's decision**: how to meet the limit. The options:

- **A. Five prerequisites, the limit raised to five** (FR-002, SC-004
  amended): uv, Docker, OpenTofu, Packer and bash 5, the last already
  present on Linux. One list for both systems; no code changes; the
  reader's first real run then needs nothing more. **Recommended.**
- **B. Four on Linux, five on macOS**: the same tools, the limit stated
  per system. The same work as A, with a weaker promise to the macOS
  reader.
- **C. Four everywhere, by code**: a dry run stops refusing a tool it
  does not execute (`ansible-playbook`, `bash`) and only warns, while
  `validate` and a real run still refuse. The page then needs no bash 5.
  The cost is a second meaning of "valid" and a first real run that
  fails on bash after the reader was told the system worked.
- **D. Four everywhere, by a container**: the page runs the command in a
  published image holding every tool, with the host's socket mounted.
  The reader needs only Docker, but the spec's install command (FR-004),
  its "older release installed" failure and its clean-machine rule all
  assume an install on the reader's machine, and the next step (a real
  local run) needs the tools on the host anyway.

The plan's documents are written for A. Under B the page's table gains
an "on macOS only" row and nothing else changes; under C one task is
added (the dry-run warning) and bash leaves the table.

## R3. The page: where it lives and what it runs

**Decision** (**chosen**): one page, `docs/QUICKSTART.md`, whose
commands are, in order:

1. `uv tool install --upgrade --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match 'cs-image-system[docker]==<version>'`
   (one command, written over two lines with `\`; `<version>` is the
   release, written in the page by the bump, R4)
2. `uv tool install --upgrade 'ansible-core>=2.16'`
3. `export PATH="$(uv tool dir --bin):$PATH"`
4. `cs-image-system --version`
5. `cs-image-system init-config csis-quickstart --from standard-docker`
6. `cs-image-system --root-dir csis-quickstart validate`
7. `cs-image-system --root-dir csis-quickstart run --all`

Seven commands in three boxes, every one runnable as written (FR-003,
FR-008); the boxes are in
[contracts/quickstart-page.md](contracts/quickstart-page.md). Command 4
is the check the first box ends on: it prints the release the reader now
has. The tree
is written into `csis-quickstart` under the directory the reader is in;
`--root-dir` on each command spares a `cd`. The command is called
directly rather than through the tree's `just` recipes, so neither
`just` nor `git` is a prerequisite (R1). A dry run is the command's
default (`--dry-run` is on unless `--no-dry-run` is given), so command 7
applies nothing.

**Alternatives considered**:

- *`just init`, `just validate`, `just dry` in the tree.* Rejected: adds
  `just` and `git` to the prerequisites and a `git init` to the
  commands (R1).
- *Change the default starter to `standard-docker`* so `--from` can go.
  Rejected: it changes what every team's `init-config` writes.
- *A section of the daily driver.* Rejected: FR-001 asks for one page,
  and the daily driver is the 1,641-line page the spec's Why describes.

## R4. The install command

**Finding** (**read**, in an isolated uv tool directory): with 0.1.11
installed, `uv tool install 'cs-image-system[docker]'` exits 0 and
leaves 0.1.11 in place; `uv tool install --upgrade
'cs-image-system[docker]'` moves it to 0.1.12. `uv tool install
--upgrade 'cs-image-system[docker]' --with-executables-from
'ansible-core>=2.16'` installs both and exposes `ansible-playbook`
(2.22.0) beside `cs-image-system`. uv warns when its tool directory is
not on `PATH`, and a fresh uv's often is not. `uv tool dir --bin` names
that directory and honours `UV_TOOL_BIN_DIR`. The umbrella requires
Python 3.13 ([pyproject.toml](../../pyproject.toml) line 13); uv fetches
a managed Python when none is present, so Python is not a prerequisite.

**Finding, 2026-11-25** (**read**): until 1.0 every release is on
TestPyPI alone (specification 013), and PyPI keeps 0.1.12. Resolved by
the one install form (TestPyPI as the index, PyPI as the extra,
`--index-strategy unsafe-first-match`, which asks PyPI first for each
name), `cs-image-system[docker]` unpinned gives 0.1.12, PyPI's, and
`cs-image-system[docker]==0.1.13.dev1` gives 0.1.13.dev1 with every one
of the system's names from TestPyPI (`uv pip compile`, 2026-11-25). An
unpinned install therefore lands on the old release without a word.

**Decision** (**decided** 2026-11-25, the spec's FR-004): command 1 is
the one install form with the exact version. The version is written in
the page and moved by each release's bump: `docs/QUICKSTART.md` joins
`[tool.bumpversion]`'s file list in [pyproject.toml](../../pyproject.toml)
with the search `cs-image-system[docker]=={current_version}`, so the
page on `develop` always names the last release, which the index holds,
and a release commit names its own, which its tag publishes. The reader
types nothing (FR-003). At 1.0 the form goes back to the plain install
with the decision's lifting (specification 013, FR-008), and the pin
can stay or go then.

`--upgrade` stays: with the exact pin it is harmless, and it makes an
older install end on the page's release (FR-013, story 3 scenario 4).
**To be confirmed at implementation**: that a pinned `uv tool install`
over an older install replaces it; the page's version line after
command 1 shows either way, and the runner's version check holds it.
ansible-core stays the plain install: it is not one of the system's
names, and the form would take it from PyPI anyway.

**Decision of 2026-11-21, kept for ansible-core and the rest**: commands
1 to 4 of R3, `--upgrade` harmless on a fresh machine. ansible-core is its own `uv tool`,
so its version floor is the starter's (`>=2.16`). `export PATH=...`
makes both reachable in the reader's shell without asking them to edit
a profile; the page says `uv tool update-shell` makes it permanent.

**Alternatives considered**:

- *One command with `--with-executables-from`.* Rejected: it raises uv's
  floor to the first release with that option, and an older uv answers
  with an argument error that names neither uv nor the version needed.
- *A `[quickstart]` extra that depends on ansible-core.* Rejected: uv
  exposes only the requested package's executables, so it still needs
  the option above.
- *No `--upgrade`, and a message when an older release is found.*
  Rejected: the command would have to be the system's, and the older
  release's command is the one that runs.

## R5. Placeholders and the test key

**Finding** (**read**, R1): the docker starter dry-runs as written; it has
no encrypted value, so its committed test identity is never read.

**Decision** (**chosen**): the page sets no `CSIS_CONFIG_IDENTITY` and
says the tree carries a test key that the quickstart does not use and
that protects nothing (the spec's Assumptions). No placeholder is filled
by the command that writes the example out: none needs it (FR-006).

## R6. How CI takes the commands from the page

**Decision** (**chosen**): a script, `scripts/quickstart`, reads the page
and runs it. Its contract is in
[contracts/quickstart-runner.md](contracts/quickstart-runner.md) and the
page format it reads in
[contracts/quickstart-page.md](contracts/quickstart-page.md). In short:

- every fenced block with the info string `sh` on the page is a box of
  commands, run in page order; a block meant only to be read uses `text`;
- one command is one line, after joining a trailing `\` continuation;
  comment lines and blank lines are not commands;
- all boxes run in one `bash` session (`set -euo pipefail`), so `export
  PATH=...` in one box holds for the next, in a working directory of the
  runner's making;
- before each command the runner prints `quickstart: box M of K: <the
  command>`; when a command fails it prints `quickstart: FAILED at box M
  of K: <the command> (exit N)` and exits 1, so the failure names the
  command (story 2 scenario 2);
- a page with no box, or more than ten commands, is a failure, not a pass
  (FR-008, SC-004, FR-011's "could not run").

**Alternatives considered**:

- *A second copy of the commands in the workflow.* Rejected by FR-010.
- *Mark the runnable blocks with a special info string.* Rejected: a
  block that is not run would then look the same as one that is; making
  every `sh` block run means the page cannot show a command that CI does
  not prove.
- *A pytest test that reads the page.* Rejected: running the page is the
  feature's acceptance, a CI job, not a test of a document (Principle
  IX); the runner's own behaviour is what the tests guard (R9).

## R7. The clean machine

**Decision** (**chosen**): the job runs in a container from the stock
`ubuntu:24.04` image with the host's docker socket mounted, not in the
project's runner image (the spec's Assumptions). Its first step installs
the prerequisites at exactly their floors into one directory
(`scripts/quickstart prepare`: uv, the static docker CLI, OpenTofu and
Packer release archives, from each vendor's download site, each checked
against the vendor's published checksum); the image's own bash is 5.2.
The page's commands then run with `PATH` set to that directory, the uv
tool directory the page adds, and `/usr/bin:/bin`, so nothing the setup
fetched with (curl, unzip) or the job used (`just`) is offered to the
page except through the base system. Installing at the floors proves the
floors the page states.

Linux x86_64 only: GitHub's macOS runners have no docker daemon. macOS is
proved by the release's local run (R8), which runs on your local machine.

`PACKER_GITHUB_API_TOKEN` is set from the job's own token: `packer init`
reads the plugins' releases from GitHub's API, whose anonymous limit a
shared runner can exhaust. It is an environment setting, not a page
command, and a reader is unlikely to meet the limit. Docker Hub's
anonymous pull limit is the other environmental risk; a refused pull
fails the job and its line says so.

**Alternatives considered**:

- *`runs-on: ubuntu-24.04` with no container.* Rejected: GitHub's image
  carries many tools beyond the prerequisites, so it is not clean.
- *The project's runner image.* Rejected by the spec's Assumptions.
- *A macOS job with colima.* Rejected: nested virtualisation on GitHub's
  macOS runners is not dependable, and the Intel runners are retiring.
- *GitHub's setup actions for uv, OpenTofu and Packer*, as
  [ci-from-scratch.yml](../../.github/workflows/ci-from-scratch.yml)
  uses. Rejected: each would carry its version in the workflow, a second
  copy of the floors the page states (Principle VIII), and there is no
  such action for the docker CLI; `prepare` reads the floors from the
  same source as the page's table (R11).

## R8. Running the page against a release's packages

**Finding** (**read**): `develop` carries the last released version
(0.1.12, [pyproject.toml](../../pyproject.toml) line 7) until a release
bumps it, so a wheel built from a `develop` commit has a version PyPI
already holds. An install that may choose between the two can silently
take PyPI's. The operator's `just release` uploads from your local
machine before it pushes the tag
([scripts/release.py](../../scripts/release.py), the gate at line 805),
so a CI job on the tag runs after the upload.

**Decision** (**chosen**):

- **Which packages.** The runner builds this workspace's wheels (`uv
  build --all-packages --wheel`) and runs the page with `UV_OVERRIDE`
  naming each of this workspace's distributions as a direct reference to
  its built wheel, so `uv tool install` takes exactly this commit's
  packages and the index only for third-party dependencies. The page's
  commands are unchanged; only the environment points uv at the build.
  After command 1 the runner checks that `cs-image-system --version`
  names the built version and fails otherwise.
- **Where it runs** (**decided** 2026-11-25, the spec's FR-011: both
  before the tag and before the upload). A recipe `just test-quickstart`
  (the runner, with an isolated `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` in a
  temporary directory, so your own installed command is never touched),
  run by:
  - the CI job on every push and pull request (R7), the tag's included;
  - the release's lighter check, where `test-docker-install` is today
    ([scripts/release.py](../../scripts/release.py) line 796, the gate's
    pair `just test`, `just test-docker-install`), and so `full-test`'s
    legs ([Justfile](../../Justfile) lines 187-188) under `--full`: on
    your local machine, before the tag, about a minute (it replaces the
    install check's 41 seconds); this is the macOS proof (R7);
  - a new job `quickstart` in the Publish workflow
    ([publish.yml](../../.github/workflows/publish.yml)), on the same
    clean machine as CI's job (R7), against the tag's own built files:
    it downloads the `build` job's artifact and runs the page with
    `UV_OVERRIDE` naming those files (`scripts/quickstart run --wheels
    DIR`, which skips the build), one pass. The `testpypi` job needs it,
    so the upload waits on it: about 3 to 5 minutes added to a Publish
    run of about 2 (the prerequisites' install at their floors, then the
    page).

  Since specification 013 the release uploads nothing from your local
  machine, and CI's `publish` job is gone: the tag's push runs the
  Publish workflow, whose upload no CI job can be needed by (another
  workflow's jobs cannot be). So the gate before the tag and the job
  before the upload are the two places that can hold a release back.

**To be confirmed at implementation**: that `UV_OVERRIDE` pins the
requested package itself as well as its dependencies. If it does not,
the fallback is to build the wheels under a local version label
(`<version>+qs<short sha>`), which no index ever holds, with
`UV_FIND_LINKS` pointing at them; the version check above catches either
failing.

**Alternatives considered**:

- *Run the page against TestPyPI after the upload*, exactly as written.
  Rejected by the operator (2026-11-25): the release would already be
  published when the page failed, and the next patch would have to
  replace it.
- *The release's gate alone.* Rejected by the operator (2026-11-25): your
  local machine holds every tool, so it does not prove the stated
  prerequisites are enough; CI's job on the tag proves that, but runs
  beside the upload, which does not wait for it.
- *The Publish job alone.* Rejected: the tag would be made, and pushed,
  before the page had run once against the release.
- *`UV_FIND_LINKS` alone.* Rejected: the same version on PyPI and in the
  build makes the choice the resolver's.

## R9. The install check is replaced, not kept beside

**Finding** (**read**): `just test-docker-install`
([Justfile](../../Justfile) lines 403-404), through `scripts/isolated-run
--install-check` (lines 54-66 and 430-509), already installs
`cs-image-system[docker]` from the built wheels into an empty
environment, writes the docker starter with the installed command, and
validates and dry-runs it; CI's `docker-install` job runs it and gates
`publish`. The quickstart job does the same, by the page's own commands,
on a clean machine.

**Decision** (**chosen**): the quickstart job and `just test-quickstart`
replace `docker-install`, `test-docker-install` and the install-check
mode of `isolated-run`, with their tests (Principle VII: deleting is a
first-class outcome). What the install check proved that the page does
not is its "no stray distribution" check; under `uv tool install` the
environment holds only what the resolver chose, so there is nothing
stray to find. The runner's own behaviour gets tests with a stubbed
shell, as `isolated-run`'s have: the commands are read in order, a
failing command is named, the session is shared, zero boxes or more than
ten commands fail, the version check fails a fallback to the index.

**Alternatives considered**: *keep both.* Rejected: two jobs proving one
path, and the older one by commands that are not the page's.

## R10. How long it took

**Decision** (**chosen**): the runner prints `quickstart: box M of K took
Ns` after each box and `quickstart: the page took Ns (limit 900)` at the
end, and in CI writes the same lines to the job summary (FR-012). The
page run fails when it took more than 900 seconds (SC-001), counted from
command 1; building the wheels and installing the prerequisites are
timed and reported separately and not counted (the spec's Assumptions
exclude installing the prerequisites). The job runs the page twice in
the same container and both passes must pass (story 1 scenario 5); the
limit applies to the first, cold one.

**Alternatives considered**: *record only.* Rejected: SC-001 is the
feature's promise, and Principle II wants it to pass or fail.

## R11. The prerequisites table is generated

**Decision** (**chosen**): the page's table of prerequisites, with their
floors, sits between two marker comments and is written by
`scripts/quickstart prerequisites --write`. Its source is the docker
starter's `cfg/executables.yml` for the tools the system checks, and one
constant in the runner for uv's floor (the system does not drive uv, so
no configuration names it). The job runs `scripts/quickstart
prerequisites --check`, which fails when the page's table is not what
the source gives, and `prepare` installs exactly those floors. Principle
VIII: a version number on the page comes from the code.

uv's floor is set at implementation as the oldest uv release on which
the job passes, starting from 0.8.0; the job installs exactly that
version, so the stated floor is proven.

**Alternatives considered**:

- *Write the floors by hand.* Rejected by Principle VIII.
- *Leave the floors off the page.* Rejected by FR-002.

## R12. The first-run failures

**Finding** (**read**) and **decision** (**chosen**), condition by
condition (FR-013, story 3). The lines are in
[contracts/first-run-messages.md](contracts/first-run-messages.md).

- **A prerequisite absent.** `validate` names the tool and that it is
  not on `PATH` (validate.py lines 95-99) but not where to get it.
  Chosen: the line gains its remedy, "install it (where each tool comes
  from: the daily driver, section 1.2)". The daily driver's section 1.2
  is the one place that says where every tool comes from
  ([DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) lines 189-233), so the
  message names it rather than any tool's vendor, and the core names no
  tool (Principle VI). uv absent is the one case no command of the
  system can report: the shell's `command not found: uv` names the tool,
  and the page's prerequisites table, above the first command, says
  where it comes from.
- **A prerequisite older than required.** `validate` already says `<tool>
  <found> does not meet its requirement <needed> (cfg/executables.yml)`
  (validate.py lines 121-123): tool, version found, version needed. No
  change. For uv, the job proves the floor the page states (R11).
- **The daemon not answering.** The docker runtime turns the CLI's
  "cannot connect" errors into one line with its remedy
  (`DockerUnreachable` and `DOCKER_REMEDY`, docker_runtime_builders.py
  lines 62-71 and 199-212), but its patterns (`Cannot connect to the
  Docker daemon`, `error during connect`, `connection refused`) miss the
  wording of the current CLI: docker 29.8 says `failed to connect to the
  docker API at unix:///...`, and the trial's dry run ended in a plain
  `RuntimeError` with no remedy. Chosen: the pattern list gains that
  wording, and the run's failure line for an unreachable daemon carries
  `DOCKER_REMEDY`, as a load failure already does (line 163). This is the
  edge case "no container daemon is running": the daemon is a stated
  prerequisite and its absence gets one line.
- **The system installed without the provider.** `validate` already says
  `runtime type 'docker' is ...: install the extra: uv tool install
  'cs-image-system[docker]'`, composed by the umbrella's table
  ([registry.py](../../packages/base/src/cs_image_system/base/registry.py)
  lines 183-198; [extras.py](../../src/cs_image_system/extras.py)). No
  change.
- **An older release installed.** Command 1's `--upgrade` ends on the
  current release (R4). No message is needed, because the condition no
  longer stops the page.
- **The command run where a configuration already exists.** Command 5
  writes into `csis-quickstart`. Three cases, read in
  [starters.py](../../packages/system/src/cs_image_system/system/starters.py)
  and tried: a directory that holds something other than a configuration
  is refused in one line naming the cause and the remedy (lines 567-578);
  the quickstart's own earlier tree, from the same release, is refreshed
  with every file "kept as it was" and the page goes on (story 1 scenario
  5); a tree from an earlier release, or one the reader edited, gets one
  `REFUSED <file>: it exists and differs from the release's; --force
  overwrites it` line per file (line 469) and exit 1. Chosen: after
  refused lines, init-config prints one closing line: `init-config:
  <dest> already holds a configuration this release did not write; to
  start over remove it, or keep it and refresh the release's files with
  --force`. That is the one line with cause and remedy.

## R13. The three routes onward (FR-008)

**Decision** (**chosen**): the page ends with three links, each to a
section whose first box is a command that works on the machine the
quickstart left:

- **A first real local run**: a new section of the docker starter's
  README, "A first real run", whose first box is the real run of the
  tree the quickstart wrote (from inside `csis-quickstart`: `cs-image-system
  --overlay overlays/launch.yaml --no-dry-run run --all`, the run the
  starter's [overlays/launch.yaml](../../docs/examples/standard-docker/overlays/launch.yaml)
  comment names) and whose last says how to take it down. The README
  travels with the tree, so the reader also has it at
  `csis-quickstart/README.md`.
- **The cloud starters**: the default cloud starter's README,
  [standard-aws](../../docs/examples/standard-aws/README.md), whose "Before
  the first run" opens with the install of its extras and its
  `init-config`, and which links its twins.
- **A team's own repository**: the daily driver's section 1.9, "The
  configuration repository, from scratch", whose first box (the
  `init-config` lines) moves to the top of the section.

**Alternatives considered**: *one new page per route.* Rejected: the
three pages exist, and new ones would repeat them (FR-015).

## R14. The way in (FR-014, FR-015)

**Decision** (**chosen**): the root README's "Where to start" lists
[docs/DESCRIPTION.md](../../docs/DESCRIPTION.md) first (its opening is
"The one-paragraph version"), the quickstart second and the daily driver
third. The daily driver's opening and its section 1.4a ("the way to try
it") link to the page; each starter README's "Before the first run"
links to it instead of carrying its own install line.

`tests/test_docs_contract.py::test_the_daily_driver_is_the_first_place_to_start`
asserts that the daily driver is the first item
([test_docs_contract.py](../../tests/test_docs_contract.py) lines 86-90).
It asserts the order of a document's list, which Principle IX does not
allow, and FR-014 makes it false. Chosen: it is deleted, not rewritten.
`docs/QUICKSTART.md` joins the list of documents whose relative links
that file's link test resolves (line 32).

## R15. The statements FR-016 names, and others found

**Finding** (**read**):

- **The install command that installs no provider**: `uv tool install
  cs-image-system` as the way to get the system, in every starter
  README's "What travels with the tree" and "Before the first run"
  (standard-aws lines 85 and 92, standard-aws-posix 110 and 117,
  standard-gce 80 and 87, standard-docker 119 and 126, complete 113 and
  120), the skeleton's [CI_SETUP.md](../../docs/examples/_skeleton/CI_SETUP.md)
  line 29 and its [Justfile](../../docs/examples/_skeleton/Justfile)
  lines 6 and 35. The bare package carries no runtime
  ([extras.py](../../src/cs_image_system/extras.py)).
- **The claim that loading needs a live cloud session**:
  [standard-aws/README.md](../../docs/examples/standard-aws/README.md)
  line 94 and [standard-aws-posix/README.md](../../docs/examples/standard-aws-posix/README.md)
  line 119 ("the load reads the account's VPCs and security groups"),
  [CONFIGURATION.md](../../docs/CONFIGURATION.md) lines 442-446 ("A load
  therefore needs a live AWS session"), and the skeleton Justfile line 50
  ("validate (needs the sessions)"). The load adopts
  `meta-state/runtime-facts.yaml` offline
  ([aws_runtime_builders.py](../../packages/aws-runtime-plugin/src/cs_image_system/aws_runtime/aws_runtime_builders.py)
  line 67; [builder_base_runtime.py](../../packages/base/src/cs_image_system/base/basic/builder_base_runtime.py)
  line 232); only `validate --online` and a real run ask the account, as
  [CONFIGURATION.md](../../docs/CONFIGURATION.md) line 2421 already says.
- **The name shown for the image builder's type**: the four standard
  starters' tables show `packer-ebs`, `packer-gce` and `packer-docker`
  in the column "Plugin (`type:`)" (standard-aws line 26,
  standard-aws-posix 51, standard-gce 21, standard-docker 61); those are
  the builders' names, and every starter's `type:` is `packer`.
- **Found beside them**: the root [Justfile](../../Justfile)'s comment at
  lines 40-41 says dry runs "never start tofu", but a dry run runs `tofu
  fmt`, `init -backend=false` and `validate` (R1).
- **The five template repositories** carry the starters' READMEs as
  generated at 0.1.12 (the docker template's README shows `packer-docker`
  and `uv tool install cs-image-system`, read through the GitHub API).
  They take no pull requests; the next final release regenerates them
  (`just publish-starters`).
- **The older public repository `cs-image-system-starter-tree`** (checked
  out beside this one) opens with `uv tool install cs-image-system` and
  `init-config my-config --from standard-aws # or standard-gce, complete`,
  and its CI guide links the daily driver on `develop`. It is not one of
  the five template repositories and nothing regenerates it.

**D3, the operator's decision**: what to do with
`cs-image-system-starter-tree`. **Recommended default**: replace its
README with three lines pointing at the quickstart and the five template
repositories, then archive it on GitHub, because a stranger who finds it
gets a stale first command. The alternative is to leave it, recorded
here as a stale statement outside this repository.

## R16. The network, the systems covered, a proxy, the slow step

**Finding** (**read**, the trial's log): the network is needed by
commands 1 and 2 (the package index, and a managed Python on a machine
without 3.13) and by command 7 (the vendor image from Docker Hub, the
packer plugins from GitHub, the OpenTofu provider from its registry).
Commands 3 to 6 work offline. The slow steps are command 1 on a cold
machine and command 7 the first time (the image pull and the plugin
downloads); a second dry run reuses all of it.

**Decision** (**chosen**): the page states this in one short section,
names macOS and Linux (x86_64 and arm64) as covered and Windows as not,
and says nothing of proxies or package mirrors (**decided** 2026-11-25:
out of scope; the TestPyPI-only install is for the development cycles
before 1.0, and no one but the operator uses the project yet). It also
says what the dry run
leaves on the machine besides `csis-quickstart`: the `almalinux:10`
image in the daemon's store and the packer plugins in packer's plugin
directory, and the one command that removes the image.

## R17. Interactions with the specifications planned beside this one

**Finding** (**read**, [specs/README.md](../README.md)):

- **003 (release gates)** changes how the release's gates report. This
  plan moves one leg of that gate (`test-docker-install` becomes
  `test-quickstart`, R8, R9). Whichever lands second takes the other's
  gate list; the quickstart leg must never report SKIPPED, which is
  003's rule too.
- **006 (qualified runtime words)** does not touch the docker starter's
  bare words. No interaction.
- **007 (the AWS family out)** and **008 (Okta out)** rewrite the AWS
  starters' READMEs and their install lines. The FR-016 corrections to
  `standard-aws` and `standard-aws-posix` (R15) and the cloud route's
  target (R13) are on the same lines; whichever lands second rebases
  onto the other. The quickstart itself uses only the docker family,
  which stays in this workspace. If the docker family later leaves, the
  runner's overrides (R8) take it from the index like any other
  dependency.

- **013 (TestPyPI until 1.0)**, merged 2026-11-24 and released in
  0.1.13.dev1 (**read** 2026-11-25): every release on TestPyPI alone, by
  the tag's push and the Publish workflow; the one install form; the
  lighter check and `--full`. This plan takes all three as they stand
  (R4, R8). The quickstart's pin is one more pin the bump moves; the
  page's install goes back to the plain one when 013's decision is
  lifted at 1.0.

## R18. The person outside the project (SC-002)

**Finding** (**read**): SC-002 needs one person who has never used the
system to complete the page unaided, on the first attempt, in fifteen
minutes or less, recorded. No command can stand in for it.

**D2, the operator's decision**: who walks it and on what machine.
**Recommended default**: one member of an adopting team, on their own
macOS machine (the system CI does not cover, R7), after the page is
merged and the next release is published, so they follow the released
page with nobody's help. The record is a dated note under the spec's
tasks with the time taken and every place they hesitated. If none is
available, the operator names someone outside the project who is.

**Decided** 2026-11-21 as above, then **replaced** 2026-11-25: SC-002
stays as written, and the specification stays incomplete until it is
walked. No one but the operator uses the project yet; the walker may in
the end be the operator on a clean account, but no date is set. The
record, when it comes, is as above.
