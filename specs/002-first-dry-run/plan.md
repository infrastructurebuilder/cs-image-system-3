# Implementation Plan: Fifteen minutes to a first dry run

**Branch**: `feature/first-dry-run` (to be created from `develop` when the work starts) | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-first-dry-run/spec.md`

## Summary

A newcomer reaches a successful dry run of the docker starter by one
page, `docs/QUICKSTART.md`: seven commands in three boxes that install
the system and ansible-core with uv, write the starter into
`csis-quickstart` with `init-config`, validate it and dry-run every
lifecycle. They call the command directly, so the page needs neither
`just` nor `git`. Trial runs on your local machine (research R1) show
the starter dry-runs as written, placeholders and all, with no key and
no account, and that the dry run needs a daemon that answers, the
network, and the tools the starter declares.

CI runs the page itself: a script, `scripts/quickstart`, reads every
`sh` block of the page in order and runs it in one shell, naming the
command that fails, counting the commands and timing the page. A job in
a stock `ubuntu:24.04` container, with only the prerequisites installed
at their stated floors, runs it twice against the commit's own wheels on
every push and pull request, and `publish` needs it. The same recipe,
`just test-quickstart`, is a leg of `full-test` and of the release's gate
for both indexes, so a release cannot reach an index before the page ran
against its packages on your local machine. It replaces the install
check (`test-docker-install`, CI's `docker-install` job and
`isolated-run --install-check`), which proved the same path by commands
that were not the page's.

Three messages change so that each first-run failure is one line with
its remedy (research R12): an absent tool names where tools come from;
the docker runtime recognises the current CLI's "failed to connect"
wording, a defect found in the trial; and `init-config` ends a refused
refresh with one line saying how to start over. The front page leads to
the description first and the quickstart second; the starters and the
manuals link to the page and lose the three false statements FR-016
names.

### Questions for the operator

The spec has no Clarifications section, so these are open. Each has a
recommended default, and the documents are written for it.

- **D1, the limit of four prerequisites** (research R2). A first dry run
  needs uv, Docker, OpenTofu and Packer, and also bash 5, which Linux
  ships and macOS does not. **Recommended: A**, raise FR-002 and SC-004's
  limit to five and list bash 5 (one list for both systems, no code). B
  states four on Linux and five on macOS; C keeps four by making a dry
  run warn instead of refuse for tools it does not execute (a code
  change, and a later failure for the reader); D runs the page in a
  container (rejected in R2).
- **D2, the person outside the project** (SC-002, research R18).
  **Recommended**: a member of an adopting team, on their own macOS
  machine, after the next final release, recorded under the tasks.
- **D3, the older repository `cs-image-system-starter-tree`** (research
  R15), whose README's first command is the bare install. **Recommended**:
  a three-line README pointing at the quickstart and the five template
  repositories, then archive it.

## Technical Context

**Language/Version**: Python 3.13; bash for the page's commands

**Primary Dependencies**: uv (`uv tool install`, `uv build`); the
umbrella's `docker` extra; the docker starter; GitHub Actions; the
vendors' release archives for the prerequisites (uv, the docker CLI,
OpenTofu, Packer)

**Storage**: N/A (files: the page, the written tree in a temporary
directory, the job summary)

**Testing**: pytest with a stubbed shell for `scripts/quickstart` and for
the three messages; the page itself is proved by running it (the job and
`just test-quickstart`), not by a test

**Target Platform**: the reader's macOS or Linux machine, x86_64 or
arm64; CI on GitHub's `ubuntu-24.04` runners, in a stock `ubuntu:24.04`
container

**Project Type**: a compiler-like CLI; this feature adds a page, its
runner and a CI job, and changes three messages

**Performance Goals**: the page in 900 seconds or less on a cold
machine, the prerequisites' installation excluded (SC-001)

**Constraints**: no cloud account, login, identity provider or key
(FR-005); nothing applied; the reader types nothing (FR-003); the CI
machine holds only the prerequisites (the spec's Assumptions); your own
installed command is never touched by the recipe

**Scale/Scope**: one new page; one new script and three recipes; one CI
job replacing another; three messages; corrections in five starters'
READMEs, the skeleton, the root README and four manuals

**Unknowns**: none left as NEEDS CLARIFICATION. Two points are chosen
with a check at implementation (research R8, R11): that `UV_OVERRIDE`
pins the requested package itself (with a stated fallback), and uv's
exact floor (the oldest release the job passes on, from 0.8.0).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves an adopting team and operators new to the system, named in the spec | Pass |
| II. Acceptance is executable | The `quickstart` job and `just test-quickstart`: the page's commands pass or fail; a page with no box, more than ten commands, a fallback to the index or a run over 900 seconds fails; the job has no condition and no skip. SC-002 adds one recorded human run, which the spec names | Pass |
| III. Nothing irreversible by default | The page only dry-runs (the command's default); the job needs no secret and applies nothing; the one real run in the walk (quickstart step 8) is the operator's decision and takes itself down | Pass |
| IV. The emission is the contract | No generation changes; the golden does not move | Pass |
| V. Public by construction | The page and the job hold no secret; the trees are written in temporary directories and never committed | Pass |
| VI. Layers and no interference | The engine's new remedy names no tool or vendor (it names the daily driver's section); the docker wording stays in the docker plugin; the `init-config` line is the CLI's; no new import edge | Pass |
| VII. Budget, subtraction | Below: source grows by a few dozen lines for the messages; the install check and its tests are deleted; the new script and its tests carry the reason | Pass |
| VIII. One source per fact | The steps are written on the page alone (FR-015); its prerequisites table is generated from the starter's `cfg/executables.yml` and one constant (R11); where each tool comes from stays the daily driver's section 1.2 | Pass |
| IX. Tests guard behaviour | The runner's and the messages' tests are behaviour tests; one test of a document's order is deleted (R14); the ten-command count is the job's acceptance, not a test | Pass |
| X. What a change makes false | Listed below | Pass |

The spec itself has one requirement the system cannot meet as written:
four prerequisites on macOS (FR-002, SC-004). That is D1, a change to
the spec, not a violation of the constitution.

**Re-check after design**: still passes. The contracts add no protocol
member and no kit surface; the costs are recorded under Complexity
Tracking.

### Budget (Principle VII)

Measured on `develop` on 2026-11-21 by the method of spec 004's T002:
lines of `*.py` under `packages/*/src` and `src`; tracked `*.py` under
`tests` and `packages/*/tests`, fixtures left out. Tests are those
`pytest --collect-only -q` collects over the default test paths.

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 0 | none |
| Source lines | 54,249 | +20 to +45 | The absent-tool remedy (engine), the current docker CLI's wording and the run's remedy (docker plugin), the closing line of a refused refresh (CLI). Under D1 option C, about +40 more |
| Test lines | 46,069 | +120 to +250 | The runner's tests (about +220) and the three messages' (about +60), less the install check's tests (about -95) and the document-order test (-6) |
| Tests | 2,610 | +8 to +16 | About ten for the runner and four for the messages, less four to six for the install check and one for the document order |
| Contract protocol members | 0 change | 0 | none |

Outside the method: `scripts/quickstart` is new (about 250 to 350
lines, the runner, the table and `prepare`), and `scripts/isolated-run`
loses its install-check mode (about -105 lines). The reason for the
growth: the page must be executed to stay true (story 2), and the
runner is the only way to execute the page's own commands; it replaces
the install check rather than adding to it.

### Statements this change makes false (Principle X)

Corrected in the same work. From the reading of 2026-11-21 (research
R14, R15).

- **The front page**: [README.md](../../README.md), "Where to start"
  (the daily driver first) and the Justfile contract table's `release`
  and `full-test` rows (the install check).
- **The starters**: every README's install lines (`uv tool install
  cs-image-system`, no provider) and "Before the first run", which link
  to the page instead; the image builder's type shown as `packer-ebs`,
  `packer-gce`, `packer-docker` (standard-aws, standard-aws-posix,
  standard-gce, standard-docker); "the load reads the account's VPCs"
  (standard-aws, standard-aws-posix) and the runtime files' "(an SSO
  profile needs a live session)" comment, which becomes "for a real run
  and `validate --online`"; the docker starter's README gains "A first
  real run" (R13).
- **The skeleton**: [CI_SETUP.md](../../docs/examples/_skeleton/CI_SETUP.md)
  line 29 and the [Justfile](../../docs/examples/_skeleton/Justfile)
  lines 6, 35 (the bare install) and 50 ("validate (needs the sessions)").
- **The manuals**: [DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) (its
  opening and section 1.4a link to the page; section 1.9's first box
  moves to its top); [CONFIGURATION.md](../../docs/CONFIGURATION.md) lines
  442-446 ("A load therefore needs a live AWS session");
  [OPERATIONS.md](../../docs/OPERATIONS.md) lines 1767, 2125, 2722, 2792
  (`test-docker-install`, `docker-install`) and "Installing a release"
  (a link to the page); [WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md)
  line 291; the [docker plugin's README](../../packages/docker-plugin/README.md)
  line 654.
- **This repository's tooling**: the root [Justfile](../../Justfile)
  (lines 40-41, "dry runs never start tofu"; lines 72, 94, 207-208 and
  403-404, the install check); [scripts/isolated-run](../../scripts/isolated-run)
  (its docstring's second mode); [scripts/release.py](../../scripts/release.py)
  (lines 628, 692, 805); [ci.yml](../../.github/workflows/ci.yml) (its
  header comment, the `docker-install` job, `publish`'s `needs`).
- **Tests that hold the old shape**: `tests/test_docs_contract.py` (the
  document-order test deleted, the page added to its link list),
  `tests/test_ci_workflow.py` (the job set and `publish`'s needs),
  `tests/test_release_script.py` and `tests/test_release_probes.py` (the
  gate's command), `tests/test_isolated_run.py` (the install check's
  tests out).
- **Outside this repository**: the five template repositories, which the
  next final release regenerates (`just publish-starters`); the older
  `cs-image-system-starter-tree` (D3).
- **Specifications**: [specs/README.md](../README.md) row 002.

## Project Structure

### Documentation (this feature)

```text
specs/002-first-dry-run/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── quickstart-page.md
│   ├── quickstart-runner.md
│   └── first-run-messages.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
docs/QUICKSTART.md                                   # new: the page (contracts/quickstart-page.md)
scripts/quickstart                                   # new: run, prerequisites, prepare (contracts/quickstart-runner.md)
scripts/isolated-run                                 # the install-check mode removed
scripts/release.py                                   # the gate: test-quickstart in place of test-docker-install
Justfile                                             # test-quickstart, quickstart-prepare, quickstart-table; test-docker-install removed; full-test-legs
.github/workflows/ci.yml                             # job `quickstart` in place of `docker-install`; publish needs it
packages/engine/src/cs_image_system/engine/commands/validate.py                 # the absent tool's remedy
packages/docker-plugin/src/cs_image_system/docker_runtime/docker_runtime_builders.py   # the current CLI's wording; the run's remedy
packages/system/src/cs_image_system/system/starters.py                          # the closing line of a refused refresh
tests/test_quickstart_script.py                      # new: the runner's behaviour
tests/test_isolated_run.py, test_docs_contract.py, test_ci_workflow.py, test_release_script.py, test_release_probes.py
packages/engine/tests, packages/docker-plugin/tests/unit, packages/system/tests  # one test per new line
docs/examples/*/README.md, docs/examples/_skeleton/{Justfile,CI_SETUP.md}, docs/examples/standard-aws*/cfg/runtime-builders.yml
README.md, docs/{DAILY_DRIVER,CONFIGURATION,OPERATIONS,WRITING_A_PROVIDER}.md, packages/docker-plugin/README.md
```

**Structure Decision**: no package is added or moved. The page sits
with the other manuals under `docs/`; its runner sits with the other
repository scripts under `scripts/`, run by `uv run --no-sync python`
and wrapped by recipes, as `isolated-run` is.

### Release

The next final release (0.1.13, the operator's) carries the feature: its
gate is the first to run `just test-quickstart`, its tag's CI run the
first whose `publish` needs the `quickstart` job, and its
`publish-starters` the first to give the five template repositories the
corrected READMEs. SC-002's walk (D2) follows it.

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| `scripts/quickstart prepare` downloads four tools from their vendors, checked against published checksums | The clean machine must hold the prerequisites at exactly the floors the page states, read from the one source of those floors (R7, R11) | GitHub's setup actions carry their versions in the workflow, a second copy of the floors, and none exists for the docker CLI; the project's runner image holds every tool, which the spec rules out |
| A generated table between marker comments on a reader's page | Principle VIII: version numbers in a document come from the code | Floors written by hand drift; floors left off break FR-002 |
| The job runs in a container with the host's docker socket | The dry run needs a daemon that answers (R1), and a stock image has none | A runner with no container is not clean (R7) |

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- D1: the limit is five prerequisites (FR-002 and SC-004 amended).
- D2: a member of an adopting team walks the page on their own macOS machine, after the next final release.
- D3: `cs-image-system-starter-tree`'s README points onward in three lines, then the repository is archived.
- Releases: one final release carries specs 002, 003 and 006 together.
- Order: 008, then 003, then 007; 002 fits between.
