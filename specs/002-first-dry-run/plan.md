# Implementation Plan: Fifteen minutes to a first dry run

**Branch**: `feature/002-first-dry-run` (created 2026-11-25) | **Date**: 2026-11-21, revised 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-first-dry-run/spec.md`

> **Revised 2026-11-25**, after specification 013 (releases on TestPyPI
> until 1.0, published by the tag's push) and the spec's clarifications
> of that day. What changed: the page's first command is the one install
> form at the exact version, moved by each release's bump (R4); the page
> runs against a release's packages in two places, the release's own
> lighter check before the tag and a new job in the Publish workflow on
> a clean machine that the upload waits on (R8), since CI's `publish` job
> is gone; the page says nothing of proxies or mirrors (R16); SC-002's
> walk stays open with no date (R18). The trial runs of 2026-11-21 stand.

## Summary

A newcomer reaches a successful dry run of the docker starter by one
page, `docs/QUICKSTART.md`: seven commands in three boxes that install
the system (by the one install form, at the exact version the page
names) and ansible-core with uv, write the starter into
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
every push and pull request. The same recipe, `just test-quickstart`, is
in the release's lighter check (and so a leg of `full-test`, the full
proof), before the tag, on your local machine; and the Publish workflow
gains a `quickstart` job on the same kind of clean machine, against the
tag's built files, which its TestPyPI upload waits on. So a release
cannot reach the index before the page ran against its packages twice
over. It replaces the install
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

Decided: D1 to D3 on 2026-11-21, and four more on 2026-11-25; the
sections "Operator decisions" at the end say each. The text below is the
question as first put.

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
umbrella's `docker` extra, from TestPyPI by the one install form until
1.0 (specification 013); the docker starter; GitHub Actions (CI and the
Publish workflow); the
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
job replacing another and one Publish job added; the page's pin in the
bump's file list; three messages; corrections in five starters'
READMEs, the skeleton, the root README and four manuals

**Unknowns**: none left as NEEDS CLARIFICATION. Three points are
chosen with a check at implementation (research R4, R8, R11): that
`UV_OVERRIDE` pins the requested package itself (with a stated
fallback), that the pinned install replaces an older one (with
`--upgrade` kept for it), and uv's exact floor (the oldest release the
job passes on, from 0.8.0).

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
| VIII. One source per fact | The steps are written on the page alone (FR-015); its prerequisites table is generated from the starter's `cfg/executables.yml` and one constant (R11); the version its install names is the version line's, moved by the bump with every other pin (R4); where each tool comes from stays the daily driver's section 1.2 | Pass |
| IX. Tests guard behaviour | The runner's and the messages' tests are behaviour tests; one test of a document's order is deleted (R14); the ten-command count is the job's acceptance, not a test | Pass |
| X. What a change makes false | Listed below | Pass |

The spec itself has one requirement the system cannot meet as written:
four prerequisites on macOS (FR-002, SC-004). That is D1, a change to
the spec, not a violation of the constitution.

**Re-check after design**: still passes. The contracts add no protocol
member and no kit surface; the costs are recorded under Complexity
Tracking. Re-checked after the 2026-11-25 revision: still passes. The
Publish workflow's job needs no secret and applies nothing (III, V), and
the page's pin is moved by the bump, not by hand (VIII).

### Budget (Principle VII)

Measured on `develop` on 2026-11-25 (re-measured for the revision;
specification 008 moved the Okta plugin out since 2026-11-21) by the
method of spec 004's T002:
lines of `*.py` under `packages/*/src` and `src`; tracked `*.py` under
`tests` and `packages/*/tests`, fixtures left out. Tests are those
`pytest --collect-only -q` collects over the default test paths.

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 0 | none |
| Source lines | 51,039 | +20 to +45 | The absent-tool remedy (engine), the current docker CLI's wording and the run's remedy (docker plugin), the closing line of a refused refresh (CLI). Under D1 option C, about +40 more |
| Test lines | 44,727 | +120 to +250 | The runner's tests (about +220) and the three messages' (about +60), less the install check's tests (about -95) and the document-order test (-6) |
| Tests | 2,519 | +8 to +16 | About ten for the runner and four for the messages, less four to six for the install check and one for the document order |
| Contract protocol members | 0 change | 0 | none |

Outside the method: `scripts/quickstart` is new (about 250 to 350
lines, the runner, the table and `prepare`), and `scripts/isolated-run`
loses its install-check mode (about -105 lines). The reason for the
growth: the page must be executed to stay true (story 2), and the
runner is the only way to execute the page's own commands; it replaces
the install check rather than adding to it.

### Statements this change makes false (Principle X)

Corrected in the same work. From the reading of 2026-11-21 (research
R14, R15), with the tooling's lines read again on 2026-11-25.

- **The front page**: [README.md](../../README.md), "Where to start"
  (the daily driver first) and the Justfile contract table's `release`
  and `full-test` rows (the install check); its install lines take the
  page's link.
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
  (`test-docker-install`, `docker-install`; read again 2026-11-25 at
  lines 1986, 2380, 2764 and 3219, and "Releasing until 1.0"'s list of
  what the lighter check runs) and "Installing a release" (a link to the
  page); [WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md)
  line 291; the [docker plugin's README](../../packages/docker-plugin/README.md)
  line 654.
- **This repository's tooling**: the root [Justfile](../../Justfile)
  (lines 40-41, "dry runs never start tofu"; lines 72, 99, 187-188 and
  383, the install check); [scripts/isolated-run](../../scripts/isolated-run)
  (its docstring's second mode); [scripts/release.py](../../scripts/release.py)
  (the lighter check, lines 47, 734, 777, 796 and 936);
  [ci.yml](../../.github/workflows/ci.yml) (its header comment and the
  `docker-install` job, line 155); [publish.yml](../../.github/workflows/publish.yml)
  (its header: the upload now waits on the page);
  [pyproject.toml](../../pyproject.toml) (the bump's file list gains the
  page's pin).
- **Tests that hold the old shape**: `tests/test_docs_contract.py` (the
  document-order test deleted, the page added to its link list),
  `tests/test_ci_workflow.py` (the job set), `tests/test_publish_commands_parse.py`
  (the Publish workflow's jobs and what the upload needs),
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
scripts/release.py                                   # the lighter check: test-quickstart in place of test-docker-install
Justfile                                             # test-quickstart, quickstart-prepare, quickstart-table; test-docker-install removed; full-test-legs
.github/workflows/ci.yml                             # job `quickstart` in place of `docker-install`
.github/workflows/publish.yml                        # job `quickstart` on a clean machine against the built files; `testpypi` needs it
pyproject.toml                                       # [tool.bumpversion]: the page's `cs-image-system[docker]==<version>`
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

The next release after the merge (the operator's; TestPyPI alone and
patch-only until 1.0, specification 013) carries the feature: its
lighter check is the first to run `just test-quickstart`, and its tag's
Publish run the first whose upload waits on the `quickstart` job. The
next *final* release's `publish-starters` is the first to give the five
template repositories the corrected READMEs (a `.dev` release pushes no
starter). SC-002's walk stays open with no date (the 2026-11-25
decision), so the specification stays merged, not complete, until it is
recorded.

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| `scripts/quickstart prepare` downloads four tools from their vendors, checked against published checksums | The clean machine must hold the prerequisites at exactly the floors the page states, read from the one source of those floors (R7, R11) | GitHub's setup actions carry their versions in the workflow, a second copy of the floors, and none exists for the docker CLI; the project's runner image holds every tool, which the spec rules out |
| A generated table between marker comments on a reader's page | Principle VIII: version numbers in a document come from the code | Floors written by hand drift; floors left off break FR-002 |
| The job runs in a container with the host's docker socket | The dry run needs a daemon that answers (R1), and a stock image has none | A runner with no container is not clean (R7) |
| A second run of the page in the Publish workflow, about 3 to 5 minutes before every upload | The operator's answer of 2026-11-25: the upload waits on the page proven on a clean machine, beside the release's own gate on your local machine, which has every tool | The gate alone proves the page on a machine that is not clean; CI's job on the tag runs beside the upload, so nothing waits on it |

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- D1: the limit is five prerequisites (FR-002 and SC-004 amended).
- D2: a member of an adopting team walks the page on their own macOS machine, after the next final release.
- D3: `cs-image-system-starter-tree`'s README points onward in three lines, then the repository is archived.
- Releases: one final release carries specs 002, 003 and 006 together.
- Order: 008, then 003, then 007; 002 fits between.

## Operator decisions of 2026-11-25

The spec's clarifications of that day, after specification 013; each
supersedes the text above where they differ.

- The install: the one install form at the exact version, written in the
  page and moved by each release's bump (FR-004; research R4).
- Where the page runs against a release's packages: both in the
  release's own gate before the tag and in the Publish workflow on a
  clean machine, the upload waiting on it (FR-011, SC-008; research R8).
- Proxies and package mirrors: out of scope; the page says nothing of
  either (Edge Cases; research R16).
- SC-002: kept as written; the walk stays open, perhaps in the end the
  operator on a clean account; this replaces D2's timing (research R18).
