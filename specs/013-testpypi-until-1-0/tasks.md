# Tasks: Releases go to TestPyPI until 1.0

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/release-and-install.md](contracts/release-and-install.md),
[quickstart.md](quickstart.md)

**Tests**: requested (the acceptance is executable; the quickstart names
the lock check and the release's refusals).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US5)

## Working rules

- `HERE` is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`; `OKTA`
  is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-okta`; `GCLOUD`
  is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-google-cloud`;
  `REF` is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig`.
- **Nothing is published** by a task here; a task marked **RELEASE** is
  the operator's and stops. Nothing goes to PyPI, ever, until 1.0.
- **No third-party name from TestPyPI.** Every resolution a task changes
  is checked for it (the lock checks, `dev-pin-resolves`).
- Versions move only their third number.
- Run Python as `uv run --no-sync python`; iterate with `just test-one`;
  the acceptance tests are `just test` at every checkpoint.
- In OKTA and GCLOUD, unset `VIRTUAL_ENV` before `uv` or `just`.

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |
| T001 | 2026-11-24: `feature/013-testpypi-until-1-0` started by `git flow feature start 013-testpypi-until-1-0` from `develop` at `770ef2d8` (specification 008's squash; this specification's own files arrived on `develop` with specification 010's, `6bd23ee7`). The base is `develop`: it carries the specification and both merges it builds on |
| T002 | The before-state, 2026-11-24. **Indexes**: every one of the system's names holds the same newest version on PyPI and TestPyPI: the system and its plugins 0.1.12, the kit and the Terraform libraries 0.2.1, the contract 0.5.0, the Okta plugin and the Google Cloud family 0.2.1. **Locks**: every lock takes every one of the system's names from PyPI: this repository 4 (the Google Cloud family's three and the Okta plugin; 19 workspace members), the Okta repository 15, the Google Cloud repository 12; third-party names 79, 67 and 72, all from PyPI. **Install lines**: about 30 files carry one (`docs/OPERATIONS.md` 19 lines, each starter's CI workflow 9 and its README 2, `docs/DAILY_DRIVER.md` 8, the skeleton's `Justfile` 6 and `CI_SETUP.md` 5, the three `opa-workload-probe.yml` 3 each, `src/cs_image_system/extras.py` 2, `README.md`, `docs/PLUGINS.md` and `docs/CI_RUNNER.md` 1 each); one uses the TestPyPI form, for a `.dev` pin. 17 projects publish here (the root and 16 packages; the Okta plugin's copy left with specification 008) |
| T003 | **Done by specification 008**: `packages/okta-opa-plugin` is no longer in this repository (its T040), so nothing here can publish it again, and the tests that list the published projects already count 16 packages (its T036) |
| T004 | The root `pyproject.toml` pins `cs-image-system-contract==0.5.2`, the contract's own version (the contract has no bump configuration; its version is moved by hand). Held, not bumped: `tests/test_contract_version.py` requires the root's pin to equal the contract's version and every other dependent to pin its series range, and `tests/test_package_metadata.py`'s rule says the same; a bump of the workspace leaves it alone |
| T005 | `scripts/with-released-families --newest test` prints `<name>==<version>` for the newest release inside each released-elsewhere range (today all four at 0.2.1), refusing one no release meets (exit 1) or an index it could not ask (2). `scripts/release.py`: after the bump, `pin_released_families` writes those exact pins into the root's extras and relocks, so the release commit, its tag and the files built from it name every one of the system's names exactly; after the tag, `restore_released_ranges` puts the ranges back in a commit of its own ("after release <v>: the released families back on their ranges"); the dry form says both. Tests: `tests/test_release_script.py::test_a_release_pins_the_released_families_exactly_then_restores_their_ranges`, `tests/test_with_released_families.py::test_newest_names_the_newest_release_inside_each_range_and_refuses_one_unmet` |
| T006 | `[tool.uv.sources]` pins `cs-image-system-gcloud-runtime-plugin`, `-tf-gcp-plugin`, `-gcs-state-plugin` and `-okta-opa-plugin` to the explicit `testpypi` index. `uv lock` (by hand: no Justfile target locks alone) takes all four from `https://test.pypi.org/simple/` and every one of the 79 third-party names from PyPI; `just init` |
| T007 | `tests/test_index_pins.py`: every `cs-image-system*` registry entry of `uv.lock` is at TestPyPI, and every other at PyPI; with T004's and T005's changes, the contract, metadata, extras and released-families tests 83 and 93 passed; `just lint` clean, `just typecheck` 0 errors |
| T008 | 2026-11-24: `just test`: lint clean, pyright 0 errors, 2,477 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped` |
| T016 (the publishers) | 2026-11-24, at the operator's word ("fill the publishers in my browser"), through Claude in Chrome in the operator's signed-in TestPyPI session: a GitHub trusted publisher (`infrastructurebuilder/cs-image-system-3`, workflow `publish.yml`, environment `testpypi`) on each of the 17 projects this repository publishes (the umbrella and 16 packages: 17, not the plan's 18, the Okta plugin's copy having left with specification 008), each read back from its page; none had one before. PyPI and TestPyPI give no API for it. **Open**: the repository's `testpypi` environment, and removing the `TEST_PYPI_TOKEN` and `PYPI_TOKEN` secrets once T013's workflow has published |

---

## Phase 1: Setup

- [X] T001 Start `feature/013-testpypi-until-1-0` in HERE (its base: `develop`, or the branch carrying the specification, named by the operator); record the base commit
- [X] T002 [P] Record the before-state in the Records table of `specs/013-testpypi-until-1-0/tasks.md`: every install line (file and line) naming PyPI or the TestPyPI form, the newest version of each of the system's names on both indexes, and which repository's lock takes each from which index

---

## Phase 2: Foundational (the pins every consumer reads)

- [X] T003 Mark `packages/okta-opa-plugin` `Private :: Do Not Upload` in its `pyproject.toml` (D3), so `scripts/publish-dist` and the new workflow skip it; correct the tests that list the published projects (`tests/test_release_whole.py`, `tests/test_package_metadata.py`)
- [X] T004 Pin the contract exactly in the released umbrella's dependencies in HERE's root `pyproject.toml` (`cs-image-system-contract==<the tree's version>`), held by the version bump (`.bumpversion-*.toml` or the contract's own line) so it moves with the contract (R3, data-model: "the contract `==` the tree's version (was a range)")
- [X] T005 Pin each family extra (`gcloud`, and `okta` once specification 008's T041 points it at the Okta repository's line) exactly at the release, in `scripts/release.py`: before the bump, read the newest TestPyPI release inside each extra's range (`scripts/with-released-families --check test` already finds it) and write `==<it>` into the released umbrella's extras; the tree's own extras keep their ranges between releases (D1)
- [X] T006 In HERE's root `pyproject.toml`, pin the families' names to TestPyPI: `[tool.uv.sources]` with `index = "testpypi"` for `cs-image-system-gcloud-runtime-plugin`, `-tf-gcp-plugin`, `-gcs-state-plugin` (and the Okta plugin after specification 008's T041); `uv lock`; `just init` (R4)
- [X] T007 [P] Write `tests/test_index_pins.py`: every `cs-image-system*` registry entry of `uv.lock` is at `https://test.pypi.org/simple/`, and no other entry is (R4, data-model)
- [X] T008 Checkpoint: `just test`; record it

---

## Phase 3: User Story 1 - A release is published to TestPyPI only, proven enough for what it carries (Priority: P1) 🎯 MVP

**Goal**: an interim release runs the lighter check, advises when a full
proof is probably needed, refuses PyPI, and publishes by its tag's push.

**Independent Test**: quickstart step 2.

### Tests for User Story 1

- [ ] T009 [US1] Extend `tests/test_release_script.py` and `tests/test_release_probes.py`: `pypi` is refused naming the standing decision with nothing changed; the default gate is the lighter check (`just test`, the install check, the probes, the families released elsewhere asked of TestPyPI); `--full` runs `just full-test`, the session probes and the evidence, and its tag message carries `fully proven: full-test`; the advisory prints its line when a changed path since the newest fully proven tag is in its list and stays silent otherwise, and never refuses; the release never uploads. Run them: they fail

### Implementation for User Story 1

- [ ] T010 [US1] In `scripts/release.py`: refuse `pypi` in `index_name()`; make the `test` gate the lighter check and point `released_elsewhere_or_refuse` at TestPyPI; add `--full` (the PyPI gate and probes against TestPyPI; the evidence commit; the tag message line); remove the local upload, `release-finish` and the token probe; the closing line names the push that publishes (R1, R7)
- [ ] T011 [US1] Add the advisory to `scripts/release.py`: the paths changed since the newest tag whose message carries `fully proven: full-test`, against one constant listing the runtimes' and identity plugins' sources, the release and take tooling, the starters' workflows, the contract and the SDK (R2); printed before anything changes, never a refusal
- [ ] T012 [US1] In `Justfile`: `release <part|version> [--full] [yes]` (no index argument; `pypi` refused), `release-take` waits for TestPyPI to list the version through `scripts/index-knows` before it takes, `release-finish` and the local `publish` removed; the comments say what each does
- [ ] T013 [US1] Add `.github/workflows/publish.yml` to HERE (on a pushed `v*` tag, guarded to `infrastructurebuilder/cs-image-system-3`; the tag must equal the workspace's version; build every public project; environment `testpypi`, `id-token: write`; `uv publish --trusted-publishing always --index testpypi` for each project, skipping what the index holds; then `just publish-starters`), and remove the `publish` job and its token secrets from `.github/workflows/ci.yml`; `tests/tooling`-style parse test for its `uv publish` lines in `tests/test_publish_commands_parse.py` (R7)
- [ ] T014 [US1] Make `scripts/release-watch` read TestPyPI for every version and check the templates for every release (R8)
- [ ] T015 [US1] Write the setup for the 18 publishers into `docs/OPERATIONS.md` ("Publishing a release": the 18 project names, the repository, `publish.yml`, `testpypi`; the GitHub environment; a fork's steps), as the families' `docs/RELEASING.md` has it
- [ ] T016 [US1] **The operator's setup**: a TestPyPI publisher on each of the 18 projects for `infrastructurebuilder/cs-image-system-3`, `publish.yml`, environment `testpypi`; the `testpypi` environment in the repository; then the `TEST_PYPI_TOKEN` and `PYPI_TOKEN` secrets may go
- [ ] T017 [US1] Checkpoint: T009 passes; `just test`; quickstart step 2; record it

---

## Phase 4: User Story 2 - Every consumer takes the system's packages from TestPyPI, and only those (Priority: P1)

**Goal**: the reference, the starters and a clean install use the one
install form for every version.

**Independent Test**: `scripts/dev-pin-resolves` on the newest release
tag; the take recipe and the starters' install lines.

- [ ] T018 [US2] Make the one install form (contracts: `--index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ --index-strategy unsafe-first-match`) apply to every version, not only `.dev`, in `docs/examples/_skeleton/Justfile` (the take recipe, its install of the old version), `docs/examples/_skeleton/CI_SETUP.md`, and every starter workflow (`docs/examples/{complete,standard-aws,standard-aws-posix,standard-docker,standard-gce}/.github/workflows/ci.yml`, the three `opa-workload-probe.yml`), the `CSIS_VERSION_FILE` comments saying TestPyPI
- [ ] T019 [US2] Make `scripts/dev-pin-resolves` prove the newest release tag, final or `.dev` (`git tag --list 'v*'`, newest by version), keeping its check that every one of the system's names comes from TestPyPI and none other does
- [ ] T020 [US2] Make `scripts/with-released-families` emit exact `--with=<name>==<newest on TestPyPI inside the range>` with the install form's index options, and its `--check` default to TestPyPI (R5)
- [ ] T021 [US2] Make `scripts/isolated-run` read TestPyPI's JSON for the SDK's published versions and digests and install its exact pins with the install form's index options (R5)
- [ ] T022 [US2] Update the tests that pin today's split: `tests/test_dev_pin_install.py`, `tests/test_take_recipe.py`, `tests/test_starter_recipes.py`, `tests/test_with_released_families.py`, `tests/test_docs_examples.py`, `tests/test_ci_workflow.py`, `tests/test_isolated_run.py`, `tests/test_publish_dist.py`, `tests/test_publish_target.py`, `tests/test_release_watch.py`, `tests/test_release_on_main.py`
- [ ] T023 [US2] Checkpoint: `just test`; `just full-test` (the advisory's own case: this changes the release and take tooling); record it

---

## Phase 5: User Story 3 - A plugin is tested against the system it will run beside (Priority: P2)

**Goal**: both families lock, test and low-end-test the system's names
from TestPyPI, test against the newest, and stop publishing at TestPyPI.

**Independent Test**: each family's `just test`, `full-test` and the new
CI job, with every system name from TestPyPI.

- [ ] T024 [P] [US3] In OKTA: `[tool.uv.sources]` `index = "testpypi"` for every system name it reaches (contract, base, hashicorp-utils, tofu-roots, system, engine, packer, ansible, bash-mod, default-os, local-state, posix-identity, aws-runtime, tf-ebs-instance, tf-s3-state) and an `index-pins` group for each not a direct dependency; `uv lock`; `tests/test_index_pins.py` as T007's; `scripts/full-test-legs`' low end through `--group pyproject.toml:index-pins`; `.github/workflows/ci.yml` gains a job re-locking the system's names to TestPyPI's newest and running `just test` (D2); `.github/workflows/publish.yml` loses its `pypi` job and `final` output; `scripts/release` refuses `pypi` naming the decision, with a test in `tests/tooling/test_release_refuses_a_held_version.py`; `README.md`, `docs/RELEASING.md` and the plugin README say TestPyPI until 1.0
- [ ] T025 [P] [US3] In GCLOUD: the same as T024 for its names (contract, base, hashicorp-utils, tofu-roots, system, engine, packer, ansible, bash-mod, default-os, local-state, posix-identity)
- [ ] T026 [US3] Checkpoint: in OKTA and GCLOUD, `just test` and `just full-test`; record each, with the lock check's count of names from TestPyPI and of third-party names (zero)

---

## Phase 6: User Story 4 - The documents say how to install a TestPyPI release, and what it risks (Priority: P2)

- [ ] T027 [US4] Write `docs/OPERATIONS.md` "Installing a release": the one install form for every version and extra, why it is safe (PyPI first per name; every one of ours exact), and TestPyPI's limits (it has been wiped before, its rate limits and outages; a lost version is never re-cut, the next patch replaces it); the one statement every other document links
- [ ] T028 [P] [US4] Correct every other install line to the form, each linking T027's section: `README.md`, `docs/DAILY_DRIVER.md`, `docs/CI_RUNNER.md`, `docs/PLUGINS.md`, the five starters' `README.md`, the skeleton's `Justfile` init message, and the install hint in `src/cs_image_system/extras.py`
- [ ] T029 [P] [US4] Correct the release walk and the publishing sections in `docs/OPERATIONS.md` and `docs/DAILY_DRIVER.md` (no token secrets; trusted publishing; `--full` and the advisory; the starters on every release; lifting the decision at 1.0 as one named change)

---

## Phase 7: User Story 5 - The starter repositories follow the releases (Priority: P3)

- [ ] T030 [US5] Make `just publish-starters` (in `Justfile`) accept every release tag (no `.dev` refusal; the message says the templates name a TestPyPI release), run from T013's workflow after the upload with `STARTER_PUSH_TOKEN`; correct `tests/test_starter_recipes.py`
- [ ] T031 [US5] Checkpoint: `just test`; record it

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T032 Run `/speckit-converge`; complete any task it appends
- [ ] T033 **RELEASE** (the operator's): the first TestPyPI-only release, the batched one (specifications 002, 003, 006 and 010), with `--full` (the advisory names it: the contract, the SDK and the release tooling changed); walk quickstart steps 3 and 4 and record each result; PyPI's newest versions unchanged (SC-001)
- [ ] T034 In REF, after T033's take: its `Justfile`, CI workflows and `CI_SETUP.md` carry the one install form (the take's refresh); `just config-drift` green; record it
- [ ] T035 Bring the specification's files up to date: the status line of `spec.md` and the row for 013 in `specs/README.md`, with the date

---

## Dependencies & Execution Order

- **Phase 2** blocks every story: the pins every consumer reads.
- **US1** before **US2**'s checkpoint (the take waits on the new
  publishing); **US2** and **US3** in parallel (different repositories).
- **US4** after US1 and US2 (the documents describe them); **US5** after
  T013.
- **T033** needs T016 (the publishers) and every story.
- Specification 010's and 008's release tasks wait for T033.

## Parallel Opportunities

- T002 beside T003 to T006; T007 beside T006.
- T024 and T025 (two repositories).
- T028 and T029 (different documents).

## Implementation Strategy

- **MVP**: Phases 1 to 3: the pins, and a release that refuses PyPI,
  advises, and publishes by its tag.
- Then the consumers (US2), the families (US3), the documents (US4), the
  starters (US5), and the first release.
