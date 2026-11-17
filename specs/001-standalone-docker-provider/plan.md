# Implementation Plan: A provider that stands alone (docker first)

**Branch**: `feature/001-standalone-docker-provider` | **Date**: 2026-11-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-standalone-docker-provider/spec.md`

**Users served**: a plugin author (primary); operators and an adopting
team.

## Summary

Make the docker family provable on its own, make the core provable
with no provider, give the SDK a declared surface and a version, close
the run-time channels through which one installed plugin can change or
break another, and prove that the usual install still delivers docker.

The approach, decided in [research.md](research.md):

1. Split the shared test harness. Its provider-neutral part becomes a
   published test kit inside the system package. Each provider ships
   its own stubs. The shared fixture, golden and tests stay whole as
   the every-provider suite.
2. Merge docker's two packages into one distribution that carries its
   own tests, fixture and golden, and run that suite in an empty
   environment built from wheels, in place and from a copy outside the
   workspace.
3. Give the core a small fixture and golden that use a test-double
   runtime, and run the core's suite in an empty environment with no
   extras.
4. Declare a surface for the kit and for each of the two shared
   Terraform libraries. Version the kit on one line and the two
   libraries on another, both from 0.2.0. Pin docker to ranges, refuse
   a release when a surface changed and the right number did not, and
   test docker at both ends of its ranges on every change.
5. Give the Terraform libraries the same boundary as a provider
   (FR-026): a range on the kit, the import check, and their own
   isolated run. They stay in this repository.
6. Treat every unusable plugin and every collision the same way:
   skipped, named in one line, and fatal only to a configuration that
   uses it.
7. Add the install check: `cs-image-system[docker]` from built wheels
   into an empty environment, then validate and dry-run a docker-only
   configuration.
8. Write one guide and correct what this makes false.

## Technical Context

**Language/Version**: Python 3.13 (`requires-python = ">=3.13"`)

**Primary Dependencies**: uv 0.12 (workspace, build, environments),
hatchling (build backend), pydantic 2, typer, bump-my-version, just.
External tools the product drives: OpenTofu, Packer, ansible-core, the
docker client.

**Storage**: files only. Configuration trees, emitted trees, goldens.

**Testing**: pytest through `just`. `just test` (lint, type check with
zero errors, tests) is the local acceptance bar; `just full-test`
before a release.

**Target Platform**: a developer's local machine (macOS or Linux) and
the CI runner image (AlmaLinux 10) with the container daemon's socket
mounted.

**Project Type**: a command-line tool with a plugin system, built as a
uv workspace of 23 packages plus the top-level package.

**Performance Goals**: the three isolated runs that join `just test`
add no more than seven minutes to it (estimate; `just test` takes about 25
minutes today).

**Constraints**:

- The shared golden stays byte-identical (FR-025, Constitution IV).
- The reference configuration's and the `standard-docker` starter's
  emission stay byte-identical (FR-022).
- AWS, Google Cloud and Okta plugin sources change only where a shared
  channel changes (spec, Assumptions).
- The contract package does not change, so its version does not.
- No Google Cloud cycle is needed: no Google Cloud code path changes
  beyond shared channels held by the golden.
- Nothing is committed to `main`; nothing is committed or pushed
  unless the operator asks.

**Scale/Scope**: 54,482 source lines, 1,939 tests in 234 files, a
shared golden of 148 files. This feature touches the engine's loader
and registry reporting, the kit, the two Terraform libraries, the
system package, both docker packages, the test harness, the Justfile,
one CI workflow, the release scripts and the documents.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
| --- | --- | --- |
| I. Purpose first | The spec names a plugin author, operators and an adopting team. | Pass |
| II. Acceptance is executable | Every story ends in a recipe that passes or fails; see [quickstart.md](quickstart.md). Each new recipe fails when zero tests ran or any was skipped. Story 5 is backed by the recipe the guide tells the reader to run. | Pass |
| III. Nothing irreversible by default | No apply is involved. Every run in this plan is a dry run or a stubbed run. | Pass |
| IV. The emission is the contract with the past | The shared golden does not move. Two new goldens are added (docker, core); each is read file by file when first recorded, and the docker one is compared with the shared golden's docker subtrees. | Pass |
| V. Public by construction | New fixtures use the existing synthetic personas and test identity. The public-safety gate runs unchanged. | Pass |
| VI. Layers and no interference | This feature is the implementation of the principle's second half. The test kit sits in the system package so the kit never imports the engine. | Pass |
| VII. A budget | Stated below. Growth carries reasons. | Pass |
| VIII. One source per fact | Hand-kept counts that this feature makes false are deleted, not updated. The surface declaration is a source, not a derived fact. | Pass |
| IX. Tests guard behaviour or architecture | New repository-level tests hold Principle VI only (the surface check, the baseline). The existing workflow-shape tests are edited for the new jobs, not extended. | Pass |
| X. What a change makes false | Listed below. | Pass |

**Re-check after design**: two places where the plan delivers less
than the spec's words are recorded under Complexity Tracking (FR-013
at the low end of the range; one exception to FR-020). No principle is
violated.

### Budget (Principle VII)

| Measure | Today | Expected | Actual, 2026-11-17 | Reason for any growth |
| --- | --- | --- | --- | --- |
| Source lines (`packages/*/src`, `src`) | 54,482 | +700 to +1,300 | 56,792 (+2,310) | About 400 are the harness's neutral part moving from `tests/` into the system package. New: three surface declarations, the import check, the baseline record and check, collision and skip reporting, the test-double runtime. |
| Test lines | 45,127 | −300 to +300 | 47,146 (+2,019) | The harness's neutral part leaves; new tests arrive. |
| Workspace packages | 23 | 22 | 22 | Docker's two packages become one. No package is added. |
| Contract protocol members | unchanged | 0 | 0 (unchanged) | The stand-in capability already exists (`local_test_target`). |
| Tests | 1,939 | +25 to +55 | 2,041 (+102) | New: surface and baseline, each collision and skip case, the stand-in cases, the isolation assertion, two goldens. Removed: the old import-rule file. |
| Golden files | 148 | +35 to +50 | 222 (+74) | The docker family's golden (about 26 files that duplicate the shared golden's docker subtrees, by the operator's decision of 2026-11-16) and the core's. |
| Repository-wide checks | n/a | 2 removed, 2 added | 2 removed, 2 added | Removed: the import-rule test, the assertion that a plugin reaches every kit module. (The cap on the import edge between docker's two halves stays: the analyser counts by import package, and those two names did not change.) Added: every workspace plugin and both Terraform libraries pass the surface check; no core module imports a Terraform library (FR-026). |

**Measured** on 2026-11-17 with one method for both columns, on the
commit the branch started at (`be648dbb`, which reproduces every figure
in the Today column) and on the working tree: lines of `*.py` under
`packages/*/src` and `src`; lines of `*.py` under `tests` and
`packages/*/tests`, fixtures and goldens left out; `pyproject.toml`
files under `packages/`; functions named `test_`; files under every
golden directory.

**Four figures are outside their expected range.** The reasons:

- **Source lines, +2,310 against +700 to +1,300.** The test kit is 764
  lines, not the 400 that moved: it gained the test-double runtime, the
  golden comparison, the isolation assertion and the broken neighbour.
  The kit's surface package is 663 lines (the declaration, the import
  check, the baseline record and its command line). Each provider's
  stubs now ship in its package and so count as source (docker,
  `tofu-roots`, `hashicorp-utils`: about 290 lines that were test
  code). The engine grew by 390 for skip-and-name discovery, the
  collisions and the stand-in rule. Nothing was added that a
  requirement did not ask for; the estimate was low.
- **Test lines, +2,019 against −300 to +300.** The estimate assumed the
  four docker test files would leave `tests/` for the family's suite;
  they have not (tasks T024 to T026 are open), so nothing left. What
  arrived: the family's suite, the core's suite, the surface and
  baseline tests for three libraries, the isolated-run tests, and a
  test for every skip and collision.
- **Tests, +102 against +25 to +55.** The same cause: every skip and
  collision case, each end of each SDK range and each failure of the
  isolated runs has a test of its own, and none of the docker tests
  moved out.
- **Golden files, +74 against +35 to +50.** The docker family's golden
  is 42 files (26 were expected: its fixture also declares identity
  and a release, which the estimate left out) and the core's is 32.

`scripts/isolated-run` (474 lines) is outside every measure above: it
is a script, not package source.

### Statements this change makes false (Principle X)

Corrected in the same work. Line numbers are those of `be648dbb`.

**"A plugin is written against the contract alone"** (the kit is the
SDK):

- [README.md](../../README.md) lines 67, 69, 76, 115
- [GOALS.md](../../GOALS.md) line 24
- [docs/DESIGN.md](../../docs/DESIGN.md) line 24
- [docs/DESCRIPTION.md](../../docs/DESCRIPTION.md) line 114
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) lines 2610, 2631, 2652
- [docs/PLUGINS.md](../../docs/PLUGINS.md) lines 27, 28, 60, 196
- [docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) lines 1291, 1408
- [packages/contract/README.md](../../packages/contract/README.md)
  lines 3, 240
- [packages/base/README.md](../../packages/base/README.md) lines 3,
  9 to 11, 18 to 20
- [packages/hashicorp-utils/README.md](../../packages/hashicorp-utils/README.md)
  lines 14, 38, 394

The contract example plugin really is written against the contract
alone and says so correctly; its statements stay.

**"Every package pins its siblings at the one shared version"**:

- [docs/PLUGINS.md](../../docs/PLUGINS.md) lines 10, 19 to 21
- [docs/PARITY.md](../../docs/PARITY.md) line 55
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) lines 2455 to 2459,
  2469
- [packages/contract/README.md](../../packages/contract/README.md)
  lines 135, 173 to 181
- [packages/engine/README.md](../../packages/engine/README.md) lines
  45, 662 to 665
- [packages/system/README.md](../../packages/system/README.md) line 12
- [packages/tofu-roots/README.md](../../packages/tofu-roots/README.md)
  line 515
- [packages/hashicorp-utils/README.md](../../packages/hashicorp-utils/README.md)
  line 392
- [pyproject.toml](../../pyproject.toml) comments at lines 16 to 20,
  37 to 38, 143
- the comments in `scripts/own-versions-current` and
  `scripts/dev-pin-resolves` that name the contract as the only
  package with its own version
- [tests/test_package_metadata.py](../../tests/test_package_metadata.py)
  and
  [tests/test_contract_version.py](../../tests/test_contract_version.py),
  which assert it

**How docker is tested, and where docker lives**:

- the two docker READMEs' test sections and dependency sections (they
  merge into one README)
- [tests/fixtures/config/README.md](../../tests/fixtures/config/README.md)
  lines 13 to 18
- [GOLDEN.md](../../GOLDEN.md) line 75, and its per-lifecycle table,
  which is already wrong and is deleted
- [docs/PLUGINS.md](../../docs/PLUGINS.md), wherever it lists the two
  docker packages

**Counts** (deleted, not updated):

- [README.md](../../README.md) lines 58, 60
- [docs/PLUGINS.md](../../docs/PLUGINS.md) lines 3, 31
- [docs/OPERATIONS.md](../../docs/OPERATIONS.md) lines 2386, 2451 to
  2471, 2544
- [docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) line 1231
- [packages/hashicorp-utils/README.md](../../packages/hashicorp-utils/README.md)
  line 26

**CI**:

- [.github/workflows/ci.yml](../../.github/workflows/ci.yml) line 8
  ("Three jobs")
- [tests/test_ci_workflow.py](../../tests/test_ci_workflow.py), which
  pins the job set

**The reference configuration and the starters**: nothing in them
becomes false. They name `cs-image-system[docker]`, which still works
(FR-021).

## Project Structure

### Documentation (this feature)

```text
specs/001-standalone-docker-provider/
├── spec.md
├── plan.md              # this file
├── research.md          # decisions R1 to R22
├── data-model.md        # the things this feature introduces
├── quickstart.md        # how to prove each story
├── contracts/
│   ├── sdk-surface.md   # the surface declaration, the check, the version rule
│   ├── test-kit.md      # what a provider's tests may rely on
│   └── commands.md      # recipes, CI jobs, and the messages they must print
├── checklists/
│   └── requirements.md
└── tasks.md             # written by /speckit-tasks, not by this command
```

### Source Code (repository root)

Only what is added, moved or materially changed.

```text
packages/
├── docker-plugin/                      # NEW: the docker family, one distribution
│   ├── pyproject.toml                  #   SDK pinned by range; test extra names the core
│   ├── README.md                       #   the two READMEs merged
│   ├── src/cs_image_system/
│   │   ├── docker_runtime/             #   moved from docker-runtime-plugin, names unchanged
│   │   │   ├── tfmodules/              #   docker_container, docker_volume (unchanged)
│   │   │   └── testing.py              #   NEW: docker's stubs for a stubbed run
│   │   └── tf_docker_plugin/           #   moved from tf-docker-plugin, names unchanged
│   └── tests/
│       ├── unit/                       #   need the SDK only; run at both ends of the range
│       ├── pipeline/                   #   need the core; golden, isolation, the moved docker tests
│       ├── fixture/                    #   a docker-only configuration
│       └── golden/                     #   its pinned emission
├── docker-runtime-plugin/              # REMOVED (merged)
├── tf-docker-plugin/                   # REMOVED (merged)
├── base/
│   ├── pyproject.toml                  # version 0.2.0, outside the workspace bump
│   ├── surface-baseline.txt            # NEW: the recorded surface of the 0.2 line
│   └── src/cs_image_system/base/
│       ├── surface.py                  # NEW: the declaration, the import check, the record
│       └── run_context.py              # plugin_state keys carry a namespace
├── hashicorp-utils/                    # own version line (0.2.0, with tofu-roots); surface.py;
│                                       #   baseline; scoped agreement check; tests ported off the harness
├── tofu-roots/                         # same version line; kit pinned by RANGE; surface.py (hooks
│                                       #   named); baseline; tests ported off the harness
├── engine/src/cs_image_system/engine/
│   ├── loader.py                       # refusals and duplicate names become skip-and-name
│   ├── commands/load_failures.py       # "installed but could not be used"; declared classes only
│   ├── bootstrap/sections.py           # section collisions reported
│   └── mod_tests.py                    # stand-in: one, several, none
└── system/
    ├── src/cs_image_system/system/
    │   ├── cli.py                      # commands entry points guarded; --stand-in
    │   └── testing/                    # NEW: the test kit
    │       ├── run.py                  #   the stubbed run, from tests/harness.py
    │       ├── golden.py               #   compare and regenerate, from tests/golden.py
    │       ├── double.py               #   the test-double runtime
    │       └── isolation.py            #   "leaves the process as it found it"
    └── tests/
        ├── core_fixture/               # NEW: a configuration with no provider
        ├── core_golden/                # NEW
        └── test_core_golden.py         # NEW

tests/                                  # the every-provider suite, unmoved
├── harness.py                          # becomes: test kit + docker's stubs + AWS, GCP, Okta stubs
├── golden.py                           # thin: the shared fixture and golden paths
├── fixtures/                           # UNCHANGED (FR-025)
├── test_plugin_imports.py              # REMOVED (replaced by the surface check)
└── test_container_runtime.py, test_mod_tests.py,
    test_mod_test_containers.py, test_bootstrap_docker.py   # MOVED to the docker family

src/cs_image_system/extras.py           # unchanged if namespaces are kept (R1)
pyproject.toml                          # [docker] extra names the one package; paths; bump excludes
.bumpversion-kit.toml                   # NEW: the kit's own bump configuration
.bumpversion-terraform.toml             # NEW: the Terraform libraries' own bump configuration
Justfile                                # test-core, test-docker-alone, test-terraform-alone,
                                        #   test-docker-install, sdk-bump, surface-record;
                                        #   `test` gains three
scripts/
├── isolated-run                        # NEW: wheels, empty environment, pytest, no-skip rule
├── own-versions-current                # reads the SDK members as it reads the contract
└── release.py                          # names the surface refusal
.github/workflows/ci.yml                # four new jobs
docs/WRITING_A_PROVIDER.md              # NEW: the one guide
```

**Structure Decision**: the workspace layout (`packages/*`) is kept,
because the bump configuration, the release scripts and many tests
assume it. The docker family is one package directory that holds
everything the family needs, so "the family's directory" (FR-003) is
`packages/docker-plugin`. The every-provider suite stays in `tests/`
without moving a file it does not have to. The core's fixture and
golden sit with the system package, which is the top of the core and
the home of the test kit.

## Delivery order

Each phase ends in a command that passes or fails. `/speckit-tasks`
breaks these down; the order here is the dependency order.

| Phase | Delivers | Serves | Done when |
| --- | --- | --- | --- |
| A. Baselines | The before-state recorded: the reference's `config-drift` result and the shared golden green. (The starter's "before" emission is made on the day of the final comparison, from the commit the branch started at, because it holds a vendor image's digest.) | FR-022, FR-025 | The recorded result exists and `just test` passes on the new branch before any change. |
| B. Test kit | `cs_image_system.system.testing`; `tests/harness.py` composed from it; docker's stubs in the docker runtime package. No behaviour change. | Story 1 | `just test` passes; the shared golden did not move. |
| C. Docker alone | The merge; the family's fixture, golden and suite; the four docker test files moved; `just test-docker-alone`, in place and from a copy. | Story 1 (P1), FR-001 to FR-004 | `just test-docker-alone` passes with no skip; the family golden's docker subtrees equal the shared golden's. |
| D. Core alone | The test-double runtime; the core fixture and golden; package tests triaged by rule 1 of R4; `just test-core`. | Story 2 (P2), FR-005, FR-006 | `just test-core` passes with no skip in an environment with no extras. |
| E. The SDK | Three surface declarations; the import check; baselines; the kit's version line and the Terraform libraries' version line, both at 0.2.0; docker's ranges; `just sdk-bump`; the release refusal; both ends in `just test-docker-alone`. | Story 3 (P3), FR-009 to FR-014 | The surface check passes for every workspace plugin; a deliberate surface removal without a middle-number bump fails `just test` and names the entry; both ends print their source. |
| E2. The Terraform libraries alone | `tofu-roots` pins the kit by a range and passes the import check; the three harness-bound test files ported or moved; the reverse-direction test; `just test-terraform-alone` (R22). | FR-026 | `just test-terraform-alone` passes with no skip; the reverse-direction test passes. |
| F. No interference | R13 to R17: skip-and-name, collisions, scoped agreement, declared-not-installed, process state, the stand-in. | Story 4 (P4), FR-007, FR-008, FR-015 to FR-020 | The new cases pass in the suite that owns each; a docker-only run with a broken extra plugin installed validates and completes a dry run. |
| G. Install check and CI | `just test-docker-install`; the four CI jobs; `just test` and `just full-test` composition. | FR-004, FR-021, FR-026 | The four jobs pass on the branch; removing the docker package from the `[docker]` extra makes the install job fail. |
| H. The guide | `docs/WRITING_A_PROVIDER.md`; every statement listed above corrected; counts deleted. | Story 5 (P5), FR-023 | The guide's own commands are the ones phases C and E proved; a search for "contract alone" finds only the contract example plugin. |
| I. Proof | Everything in [quickstart.md](quickstart.md), then `just full-test`. | all | Every step of the quickstart passes. |

Phases B to D deliver Story 1 and Story 2 and can be reviewed before E
starts. Phase E does not depend on D. Phase E2 depends on B and E.
Phase F depends on B only.

## Complexity Tracking

No constitution principle is violated. Two places where the plan
delivers less than the spec's words, and two costs, are recorded here
so they can be rejected.

| Item | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| FR-013 at the low end runs the family's unit tests and the import check, not its pipeline tests or golden (R11) | The engine pins the kit exactly, so an environment with the oldest kit has an older engine; that engine's emission is not this change's | Running everything against an older published core fails whenever the core's own part of the emission changed, for reasons the family cannot fix |
| FR-020 has one exception: the kit's opened-secret store stays shared by every run in the process, and docker adds to it when given an encrypted host (R16) | It is shared by a recorded safety decision: another run's entries can only make a run hide more | A store per run moves every reader into the safety path (Constitution V) for no guard gained |
| The docker family's emission is pinned in two goldens | FR-025 keeps the shared golden whole; FR-001 gives the family its own | Removing docker from the shared golden moves the frozen golden; decided against in clarification |
| The core, docker and Terraform-library isolated runs happen twice in CI (R12) | The local bar must predict CI, and Story 1 asks for a named job | Leaving them out of `just test` makes a local pass weaker than a CI pass |
