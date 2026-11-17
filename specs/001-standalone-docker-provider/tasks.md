---

description: "Task list for specification 001, a provider that stands alone (docker first)"
---

# Tasks: A provider that stands alone (docker first)

**Input**: Design documents from `specs/001-standalone-docker-provider/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: this feature's deliverables are checks, so test tasks are
part of the work and are not optional. A new check is written with the
behaviour it guards, in the same task or the one beside it.

**Organization**: tasks are grouped by user story. Two requirement
groups in the spec belong to no story (the shared Terraform libraries,
FR-026; the install check, FR-021) and have a phase each, with no
story label.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an
  unfinished task)
- **[Story]**: the user story a task belongs to (US1 to US5)
- Every path is relative to the repository root.

## Rules for whoever carries these out

- Work on `feature/001-standalone-docker-provider`. Never on `develop`
  or `main`.
- Commit only when the operator asks. A checkpoint is a good place to
  ask.
- Read [.specify/memory/constitution.md](../../.specify/memory/constitution.md)
  first. Run Python through `uv run python`. Verify through `just`,
  never by calling `pytest`, `ruff` or `pyright` directly.
- While iterating, prove one file with `just test-one <path>`. At a
  checkpoint the bar is `just test` (about 25 minutes today).
- **The shared golden is the tripwire.** After any task,
  `git status --short tests/fixtures` must print nothing. If it prints
  something, stop: FR-025 forbids moving the shared fixture or golden.
- A task that says "port, or move" follows rule 3 of research R4: a
  test moves to another fixture only if what it asserts does not have
  to change. Otherwise it stays in, or moves to, [tests/](../../tests),
  and the task's result is recorded under Records below.
- The tree is shared with other sessions. Never stage or commit a file
  this feature did not change (the rename of specification 003 in the
  working tree is not this feature's).

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |
| T002 | `just test` before any change: passed on 2026-11-16, lint clean, type check 0 errors, 2,497 tests passed and 29 skipped, 21 min 31 s |
| T003 | `just cli config-drift` exit status before any change: NOT YET TAKEN. The AWS session had expired (`just preflight`, 2026-11-16). Take it from the commit the branch started at (`git merge-base develop HEAD`) once a session is live |
| T011 | Phase 2 checkpoint: `just test` passed, 2,497 passed and 29 skipped (the same as T002), shared fixture and golden untouched |
| T019 | Shared golden after the merge (must be unmoved): UNMOVED. Full `just test` on 2026-11-16: lint clean, type check 0 errors, 2,491 passed, 29 skipped, 1 failed (`tests/test_module_sources.py`, an expectation naming the old distribution; corrected, and that file then passed alone, 18 tests). One value does derive from the distribution's name: the namespace a shipped Terraform module is listed and stamped under is now `docker`, was `docker-runtime`. It is not in any emission. A `.csis-module` stamp in a configuration changes only when that module's copy is next rewritten |
| T012 | Not yet done from this task: the package's `test` extra and its own pytest settings. They are added with T028 to T030, where they are first used |
| T022 | Family golden recorded on 2026-11-16 (42 files) and compared with the shared golden: `base-image/pckr-docker`, `instance-image/pckr-docker` and `storage/docker-volume` are byte-identical. `instance-image/tofu-docker` differs in two files, by additions on the shared side only: `tofu-docker-instance-generation.tf` carries five `terraform_remote_state` blocks (`aws_efs`, `aws_ebs`, `aws_s3`, `gcp_pd`, `gcp_gcs`) and the instance file carries `"ebs" = {}` and `"efs" = {}`. Cause: a docker instance root reads the state of every storage builder the configuration declares, whichever provider it belongs to, and the family's fixture declares only docker's. Nothing was changed about that behaviour |
| T024 to T026 | NOT DONE. The four docker test files still live in `tests/` and pass there. Moving them means porting 47 tests to the family's fixture one at a time |
| T012, T027 | The package's `test` extra names the command line (with its `testing` extra) and the six core plugins whose `type:` words the fixture declares, not the top-level package: naming `cs-image-system` makes a dependency cycle with its `docker` extra, which the release tooling refuses |
| T033 | Story 1 checkpoint, 2026-11-16: `just test` passed end to end (lint clean, type check 0 errors, 2,510 tests passed and 29 skipped, then `test-docker-alone`: 24 passed and 0 skipped in place, and the same from a copy outside the workspace), 22 min 20 s. Shared fixture and golden untouched. T024 to T026 are still open |
| T026 | `test_bootstrap_docker.py`: ported or left, and why: |
| T034 | Does the core's image builder emit with Packer's `null` source: |
| T037 | `test_ansible_only_modifications.py`: ported or moved: |
| T066 to T068 | Each Terraform-library test file: ported or moved: |
| T073 | Was the contract package changed, and its new version if so: |
| T101 | Budget actuals written into plan.md: |
| T102 to T104 | Quickstart steps 1 to 9, each result: |

---

## Phase 1: Setup

**Purpose**: the branch, and the before-state the proofs compare with.

- [X] T001 Start the branch. First check the shared tree: read
  `git reflog -10` and list the other sessions; if another session is
  mid-change on `develop`, stop and ask. Then run
  `git flow feature start 001-standalone-docker-provider` from
  `develop`. Uncommitted files ride along untouched.
- [X] T002 Run `just init` and then `just test` on the new branch
  before changing anything, and record the result and the duration in
  the Records table of
  `specs/001-standalone-docker-provider/tasks.md`. If it does not
  pass, stop and report: the feature must start from green.
- [ ] T003 Run `just cli config-drift` against the reference
  configuration checked out beside this repository
  (`../cs-image-system-testconfig`) and record its exit status in the
  Records table of `specs/001-standalone-docker-provider/tasks.md`.
  Expected 0. If it is not 0, stop and report: drift that exists
  before the work cannot be told from drift the work causes.
- [X] T004 Confirm the invariant used at every later checkpoint:
  `git status --short tests/fixtures` prints nothing and
  `find tests/fixtures/golden -type f | wc -l` prints 148.

---

## Phase 2: Foundational (the test kit)

**Purpose**: split the shared harness so a suite can run without every
provider. Nothing a user can observe changes in this phase.

**⚠️ CRITICAL**: no user story can start until this phase is complete.

Contract: [contracts/test-kit.md](contracts/test-kit.md). Decisions:
research R2, R3, R4.

- [X] T005 Create the test kit's stubbed run in
  `packages/system/src/cs_image_system/system/testing/__init__.py` and
  `packages/system/src/cs_image_system/system/testing/run.py`. Move
  into it, from `tests/harness.py`, everything that names no provider:
  `copy_config` (now taking the fixture's path as an argument),
  `module_path`, `modules_beside`, `modules_inside`, `plain`,
  `BareRun`, `bare_run`, `os_type_for_family`, `load_context`,
  `cli_context`, `drive_lifecycles`, `tree`, `command_lines`, the
  `FIXED_*` constants, and the neutral part of `stub_environment`
  (fixed user, the fixture's test identity, the fixed clock, the
  execute journal, the in-process runner, the executable-version
  answer). The run takes `stubs`, a list of functions that each take
  the test's `monkeypatch`, and applies each. The moved code must name
  no provider, in code or comment:
  `tests/test_core_names_no_runtime.py` scans this package.
- [X] T006 [P] Create
  `packages/system/src/cs_image_system/system/testing/golden.py` from
  `tests/golden.py`: compare an emitted tree with a golden directory
  byte for byte (ignoring `run-summary.json`, `runs.yaml` and
  `runtime-facts.yaml`, failing with a unified diff per file and the
  lists of missing and unexpected files), and regenerate a golden
  directory. Both take the fixture path and the golden path as
  arguments.
- [X] T007 Add the extra `testing = ["pytest>=8.3"]` to
  `packages/system/pyproject.toml`, and import `pytest` only inside
  the `testing` package so the command line never needs it.
- [X] T008 [P] Create docker's stubs in
  `packages/docker-runtime-plugin/src/cs_image_system/docker_runtime/testing.py`:
  one function taking `monkeypatch` that does what
  `tests/harness.py` lines 277 to 280 and 305 to 308 do today
  (`query_provider_image`, `query_images`, `run_session_command`,
  `retag_image` on `DockerContainerBuilder`), plus the fixed digest
  constant `DOCKER_DIGEST`.
- [X] T009 Rewrite `tests/harness.py` as a composition with the same
  public names, so no file that imports it changes: its
  `stub_environment` and `FixtureRun` call the test kit with docker's
  stub function from `cs_image_system.docker_runtime.testing` and with
  local stub functions for AWS, Google Cloud and Okta that keep what
  lines 240 to 322 do for those three. `record_network_facts`, `VPCS`,
  `VENDOR_AMI` and `docker_binary` stay here.
- [X] T010 Reduce `tests/golden.py` to the shared fixture path, the
  shared golden path and calls into the test kit's `golden`, keeping
  `current_output`, `regenerate`, `GOLDEN` and `IGNORED_FILES`
  importable for the tests that use them and for `just golden-regen`.
- [X] T011 Checkpoint: `just test` passes and
  `git status --short tests/fixtures` prints nothing.

**Checkpoint**: the every-provider suite runs on the test kit and
nothing moved.

---

## Phase 3: User Story 1 - The docker family proves itself alone (Priority: P1) 🎯 MVP

**Goal**: one docker distribution with its own tests, fixture and
golden, proven in an empty environment, in place and from a copy
outside the workspace, on every change.

**Independent Test**: `just test-docker-alone` passes with no test
skipped (quickstart steps 1 and 2).

Serves FR-001 to FR-004. Decisions: research R1, R4, R6, R12.

### The merge

- [X] T012 [US1] Create `packages/docker-plugin/pyproject.toml` for
  the distribution `cs-image-system-docker-plugin`: the union of the
  two docker packages' dependencies (the contract range, the kit,
  `hashicorp-utils`, `tofu-roots`, `python-hcl2`, `pydantic`, pins
  unchanged for now); every entry point of both packages under its
  present group and name (`cs_image_system.plugins.runtime` `docker`,
  `cs_image_system.bootstrap` `docker`, `cs_image_system.modules`
  `modules`, `cs_image_system.plugins.instance` `tf-docker-plugin`);
  an extra `test = ["cs-image-system==<workspace version>",
  "cs-image-system-system[testing]==<workspace version>"]`; and
  `[tool.pytest.ini_options]` with `testpaths = ["tests"]` and
  `addopts = "--import-mode=importlib"`. Copy `LICENSE`.
- [X] T013 [US1] Move the sources with `git mv`, names unchanged:
  `packages/docker-runtime-plugin/src/cs_image_system/docker_runtime`
  and
  `packages/tf-docker-plugin/src/cs_image_system/tf_docker_plugin`
  into `packages/docker-plugin/src/cs_image_system/`. Then remove the
  two old package directories.
- [X] T014 [US1] Keep the namespaces: pass
  `_namespace="docker-runtime"` in
  `packages/docker-plugin/src/cs_image_system/docker_runtime/main.py`
  and `_namespace="tf-docker"` in
  `packages/docker-plugin/src/cs_image_system/tf_docker_plugin/main.py`,
  so every qualified `type:` word resolves as before.
- [X] T015 [US1] Remove the private reach: replace
  `getattr(rtb, "_docker", None)` in
  `packages/docker-plugin/src/cs_image_system/tf_docker_plugin/tf_docker_storage_builder.py`
  (line 101) with a call to a method without a leading underscore on
  `DockerContainerBuilder` in
  `packages/docker-plugin/src/cs_image_system/docker_runtime/docker_runtime_builders.py`.
- [X] T016 [US1] Write `packages/docker-plugin/README.md` by merging
  the two packages' READMEs, keeping every section once. Leave the
  sections on testing and on dependencies marked for task T092.
- [X] T017 [US1] Point the workspace at the one package in
  `pyproject.toml`: the `docker` and `all` extras name
  `cs-image-system-docker-plugin`; `[tool.uv.sources]`; `testpaths`;
  `pythonpath`; pyright `extraPaths`. Make the same path change in
  `.vscode/settings.json` (`tests/test_editor_paths.py` holds the two
  equal). Run `uv lock`.
- [X] T018 [US1] Update what names the two old distributions:
  `tests/test_package_metadata.py` (the distribution lists near line
  60 and the counts near line 273), `tests/test_neutral_tofu_root.py`
  (lines 33 to 37, 114, 136), `tests/test_import_closure.py` (remove
  the `tf_docker_plugin->docker_runtime` edge at line 44),
  `tests/test_registration_namespaces.py` (line 135),
  `tests/test_docs_examples.py` (lines 61, 70) and
  `tests/test_extras.py` (which must pass unchanged in meaning: the
  namespaces did not move). Leave `src/cs_image_system/extras.py`
  as it is.
- [X] T019 [US1] Checkpoint for research R1: `just test` passes and
  `git status --short tests/fixtures` prints nothing. Record it. If
  any golden file moved, stop: something in the emission derives from
  a distribution's name; find it and keep its value stable instead of
  accepting the move.

### The family's own suite

- [X] T020 [US1] Create the docker-only fixture in
  `packages/docker-plugin/tests/fixture/`, taken from the docker
  entries of `tests/fixtures/config` with their names unchanged: the
  runtime `docker-fixture`, the image builder of type `packer-docker`,
  the instance builder of type `tofu-docker`, the storage builder of
  type `tf-docker-volume`, the OS builder `rh10-container`, the local
  state backend, POSIX groups only (no Okta), the mod builders, the
  executables it needs, `images/image5.yaml`,
  `storages/container.yaml`, the docker instances, the playbooks they
  use, and the test `.age-identity` and `.age-recipient`. Personas
  stay the synthetic ones on `example.invalid`.
- [X] T021 [US1] Create `packages/docker-plugin/tests/conftest.py`
  (plugin discovery at session start, and nothing that names another
  provider) and `packages/docker-plugin/tests/support.py` holding the
  fixture and golden paths.
- [X] T022 [US1] Create
  `packages/docker-plugin/tests/pipeline/test_golden.py` using the
  test kit and docker's stubs, record
  `packages/docker-plugin/tests/golden/`, and read every recorded file
  (Constitution IV). Then run the comparison of quickstart step 2
  against `tests/fixtures/golden/generated/` for
  `base-image/pckr-docker`, `instance-image/pckr-docker`,
  `instance-image/tofu-docker` and `storage/docker-volume`; explain
  any difference file by file in the change description.
- [X] T023 [P] [US1] Move the two existing package test files to
  `packages/docker-plugin/tests/unit/test_docker_runtime.py` and
  `packages/docker-plugin/tests/unit/test_docker_module_calls.py`.
  They must import only the contract, the kit, the two Terraform
  libraries and the family.
- [ ] T024 [P] [US1] Move `tests/test_container_runtime.py` to
  `packages/docker-plugin/tests/pipeline/test_container_runtime.py`,
  on the test kit, docker's stubs and the family's fixture. Port, or
  move.
- [ ] T025 [P] [US1] Move `tests/test_mod_tests.py` and
  `tests/test_mod_test_containers.py` to
  `packages/docker-plugin/tests/pipeline/`. Port, or move. The one
  test gated on `CSIS_DOCKER_TESTS` needs a daemon: keep it out of the
  isolated run by placing it in
  `packages/docker-plugin/tests/live/test_mod_tests_live.py`.
- [ ] T026 [P] [US1] Move `tests/test_bootstrap_docker.py` to
  `packages/docker-plugin/tests/pipeline/test_bootstrap_docker.py`
  without its imports from `tests.test_bootstrap`. If it cannot stand
  without them, leave it in `tests/` and record why.
- [X] T027 [US1] Add `[tool.pytest.ini_options]` handling so the live
  directory is not collected by default: `testpaths = ["tests/unit",
  "tests/pipeline"]` in `packages/docker-plugin/pyproject.toml`, and
  the matching entries in the root `pyproject.toml` `testpaths`.

### The isolated run

- [X] T028 [US1] Create `scripts/isolated-run` (Python, run with
  `uv run python`): build every workspace wheel into a fresh temporary
  directory; create an empty virtual environment outside the
  workspace's; install the named requirements from the built wheels
  with third-party packages from the index; print the installed
  distributions; run `pytest` on the named paths with the given root
  directory and with `-o pythonpath= -o testpaths= -p
  no:cacheprovider`; exit non-zero when zero tests were collected, any
  was skipped, or any failed, saying which of the three. An option
  copies a directory outside the workspace first and installs and
  tests from the copy.
- [X] T029 [US1] Test the script's verdict rule in
  `tests/test_isolated_run.py` with a stubbed shell, as
  `tests/test_release_script.py` tests the release script: zero
  collected fails, one skipped fails, one failed fails, all passed
  passes, and a step that could not start is reported as not run.
- [X] T030 [US1] Add the recipe `test-docker-alone` to `Justfile`,
  calling `scripts/isolated-run` twice: the family and its `test`
  extra with `packages/docker-plugin` as the root, in place; and the
  same from a copy outside the workspace. Give `golden-regen` an
  argument (`shared`, the default; `docker`; `core`). Keep
  `tests/test_justfile_contract.py` passing.
- [X] T031 [US1] Make `test` in `Justfile` run `test-docker-alone`
  after the unit tests, and update the recipe's comment and
  `tests/test_justfile_contract.py`.
- [X] T032 [US1] Add the job `docker-alone` to
  `.github/workflows/ci.yml`, running `just test-docker-alone` on
  every push and pull request, in the same container image and with
  no condition that can skip it. Update the job set in
  `tests/test_ci_workflow.py` (line 51) and keep
  `tests/test_ci_runner.py` passing. Correct the "Three jobs" comment
  at line 8.
- [X] T033 [US1] Checkpoint: `just test-docker-alone` passes with no
  skip, `just test` passes, and `git status --short tests/fixtures`
  prints nothing.

**Checkpoint**: Story 1 is complete and provable on its own.

---

## Phase 4: User Story 2 - The core proves itself with no provider (Priority: P2)

**Goal**: the core's tests pass with a plain install and no extras,
against a fixture and golden that need no provider; a core check that
needs a stand-in never passes without running.

**Independent Test**: `just test-core` passes with no test skipped,
and its list of installed distributions holds no docker, AWS, Google
Cloud or Okta plugin (quickstart step 3).

Serves FR-005 to FR-008. Decisions: research R4, R5, R17.

- [ ] T034 [US2] Settle research R5 before building on it: in a
  throwaway test, give the core's image builder a runtime whose
  `packer_source_type` is `null` and see whether a dry run emits.
  Record the answer in the Records table of
  `specs/001-standalone-docker-provider/tasks.md`. If it does not
  emit, the core fixture of T036 declares no image.
- [ ] T035 [US2] Create the test-double runtime in
  `packages/system/src/cs_image_system/system/testing/double.py`: a
  model and a `RuntimeBuilderBase` subclass that bake through Packer's
  `null` source and offer no instance, no storage and no stand-in,
  registered by the test kit for the length of one run and never as
  an installed entry point. It must name no provider.
- [ ] T036 [US2] Create the core fixture in
  `packages/system/tests/core_fixture/`: one runtime of the
  test-double's type, the local state backend, POSIX groups with the
  synthetic personas, one OS builder, the mod builders, and (if T034
  allows) one base image and one instance image. No provider-specific
  runtime and nothing that needs Okta.
- [ ] T037 [US2] Port, or move,
  `packages/ansible-plugin/tests/test_ansible_only_modifications.py`:
  onto the test kit and the core fixture if what it asserts survives,
  otherwise to `tests/`. Record which.
- [ ] T038 [US2] Create `packages/system/tests/test_core_golden.py`,
  record `packages/system/tests/core_golden/`, and read every recorded
  file.
- [ ] T039 [US2] Change stand-in selection in
  `packages/engine/src/cs_image_system/engine/mod_tests.py`
  (`stand_in_target_factory` near line 112, and the callers near lines
  297 to 338) and `stand_in_runtime_type` in
  `packages/base/src/cs_image_system/base/image_sources.py` (lines 190
  to 200): exactly one installed runtime class whose
  `local_test_target()` returns a factory is used and named; two or
  more is an error until one is named; none, or one whose daemon does
  not answer, is a failure. It must never pick by name or by order.
- [ ] T040 [US2] Add `--stand-in <runtime type>` and an explicit
  exclusion option to the `test-mods` command in
  `packages/system/src/cs_image_system/system/cli.py` (near lines 864
  to 879), printing exactly the lines given under "The stand-in" in
  `specs/001-standalone-docker-provider/contracts/commands.md`.
  "Did not run" exits non-zero unless the exclusion was asked for.
- [ ] T041 [US2] Test the stand-in in
  `packages/engine/tests/test_stand_in.py` with stand-in runtime
  classes defined in the test: one installed; two installed and none
  named; two installed and one named; none installed; one installed
  whose factory returns nothing; and each of the last two with the
  exclusion.
- [ ] T042 [US2] Add the recipe `test-core` to `Justfile`:
  `scripts/isolated-run` with a plain `cs-image-system` (no extras)
  and `cs-image-system-system[testing]`, on the `tests` directories of
  `packages/contract`, `packages/base`, `packages/engine`,
  `packages/system`, `packages/ansible-plugin`,
  `packages/bash-mod-plugin`, `packages/default-os-plugin`,
  `packages/packer-plugin`, `packages/local-state-plugin` and
  `packages/posix-identity-plugin`. Any file there that still imports
  `harness` or `golden` from `tests/` fails the run: port it, or move
  it to `tests/`.
- [ ] T043 [US2] Make `test` in `Justfile` run `test-core`, add the
  job `core-alone` to `.github/workflows/ci.yml` running
  `just test-core`, and update `tests/test_ci_workflow.py` and
  `tests/test_justfile_contract.py`.
- [ ] T044 [US2] Checkpoint: `just test-core` passes with no skip and
  lists no provider; `just test` passes; the shared golden is unmoved.

**Checkpoint**: Stories 1 and 2 each pass on their own.

---

## Phase 5: User Story 3 - The kit is an SDK a provider can pin (Priority: P3)

**Goal**: a declared surface for the kit and for each Terraform
library, two version lines, docker on ranges, a release refused when a
surface changed and the right number did not, and docker tested at
both ends of its ranges.

**Independent Test**: the surface check passes for every workspace
plugin; removing a surface entry without raising the middle number
fails `just test` and names the entry; `just test-docker-alone` prints
where each SDK library came from at both ends.

Serves FR-009 to FR-014 and FR-019. Contract:
[contracts/sdk-surface.md](contracts/sdk-surface.md). Decisions:
research R7 to R11.

### Surfaces and the import check

- [ ] T045 [US3] Create
  `packages/base/src/cs_image_system/base/surface.py` with the
  declaration's structure (per module, the names a plugin may import;
  per class, the underscore-prefixed hooks a subclass may override or
  call) and the kit's own declaration. Seed it from what every
  `packages/*/src` outside `base`, `engine`, `contract` and `system`
  imports from `cs_image_system.base` today and from the kit's
  underscore members they override or call (`_get_context` and
  `_model` among them), then read it and trim it by hand.
- [ ] T046 [P] [US3] Create
  `packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/surface.py`
  with that library's declaration, seeded the same way. It must import
  nothing of the kit: this library depends on the contract alone.
- [ ] T047 [P] [US3] Create
  `packages/tofu-roots/src/cs_image_system/tofu_roots/surface.py` with
  that library's declaration, naming as hooks every underscore member
  the roots plugins override or call (`_provider_name`,
  `_provider_source`, `_provider_config`, `_module_dirname`,
  `_module_resource`, `_instance_word`, `_root_header_lines`,
  `_launch_template_name`, `_module_args`, `_launch_args`, `_lookup`,
  `_runtime_builder`, `_image_var`, `_launch_template_variables`,
  `_storage_builder_name`, `_storage_outputs_reference`, and any other
  the seed finds).
- [ ] T048 [US3] Implement the import check in
  `packages/base/src/cs_image_system/base/surface.py`, runnable as
  `python -m cs_image_system.base.surface check <source directory>`
  and with `--tests`, and callable returning a list of findings. It
  reads source with `ast`, finds the three libraries' declarations in
  the installed SDK, and reports each finding as
  `<file>:<line>: <import or member> — <reason>` with exactly the four
  reasons in
  `specs/001-standalone-docker-provider/contracts/sdk-surface.md`.
  `--tests` also allows `cs_image_system.system.testing` and the
  plugin's own `testing` module.
- [ ] T049 [US3] Test the check in
  `packages/base/tests/test_surface_check.py` on small source trees
  written by the test: a listed name passes; an unlisted kit name
  fails with "not on the surface"; an unlisted underscore member fails
  with "private to"; an engine import fails; another plugin's import
  fails; the plugin's own modules pass; and `--tests` allows the test
  kit.
- [ ] T050 [US3] Replace `tests/test_plugin_imports.py` with
  `tests/test_plugins_keep_to_the_surface.py`: every plugin under
  `packages/*/src` and both Terraform libraries pass the check. Delete
  the old file, and delete the assertion in
  `tests/test_import_closure.py` (lines 84 to 94) that a plugin
  reaches every kit module.
- [ ] T051 [US3] Run the check with `--tests` on
  `packages/docker-plugin/tests` from
  `packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py`,
  and on `packages/docker-plugin/src` from the same file, so the
  family proves FR-002 and SC-004 about itself.

### Baselines and the two version lines

- [ ] T052 [US3] Add the surface record to
  `packages/base/src/cs_image_system/base/surface.py`: for each
  declared entry, what
  `specs/001-standalone-docker-provider/data-model.md` lists under
  "Surface entry and baseline" (a function's parameters, kinds,
  defaults and return annotation; a class's surface bases, public
  methods and declared hooks; a model's fields with annotation and
  whether required; a constant's type and value). Write the three
  baselines `packages/base/surface-baseline.txt`,
  `packages/hashicorp-utils/surface-baseline.txt` and
  `packages/tofu-roots/surface-baseline.txt`, each headed by its
  middle number.
- [ ] T053 [US3] Add the baseline check as a test in each library's
  own suite (`packages/base/tests/test_surface_baseline.py`,
  `packages/hashicorp-utils/tests/test_surface_baseline.py`,
  `packages/tofu-roots/tests/test_surface_baseline.py`) with the three
  failures and messages in
  `specs/001-standalone-docker-provider/contracts/sdk-surface.md`,
  and test the comparison itself on written-out examples in
  `packages/base/tests/test_surface_record.py`: an added entry passes;
  a removed entry fails naming it; a changed parameter, default,
  annotation, model field and constant value each fail naming the
  entry and both forms; a higher middle number asks for a re-record.
- [ ] T054 [US3] Add the recipe `surface-record` to `Justfile`,
  rewriting the three baselines and refusing when the middle number
  equals the baseline's and an entry would be removed or changed.
- [ ] T055 [US3] Open the two version lines. Set `version = "0.2.0"`
  in `packages/base/pyproject.toml`,
  `packages/hashicorp-utils/pyproject.toml` and
  `packages/tofu-roots/pyproject.toml`. Rewrite every exact pin on
  those three, in every `packages/*/pyproject.toml` and in
  `pyproject.toml`, to `==0.2.0`. Add the three manifests to both
  `glob_exclude` lists in `pyproject.toml` (near lines 175 and 181)
  and make sure the workspace bump's `==` pattern cannot rewrite a pin
  on them even when the two numbers happen to be equal. Create
  `.bumpversion-kit.toml` and `.bumpversion-terraform.toml`. Run
  `uv lock`.
- [ ] T056 [US3] Add the recipe `sdk-bump` to `Justfile`, taking
  `kit` or `terraform` and `last` or `middle`, behaving as
  `specs/001-standalone-docker-provider/contracts/commands.md` says.
- [ ] T057 [US3] Put docker on ranges in
  `packages/docker-plugin/pyproject.toml`:
  `cs-image-system-base>=0.2,<0.3`,
  `cs-image-system-hashicorp-utils>=0.2,<0.3`,
  `cs-image-system-tofu-roots>=0.2,<0.3`. Run `uv lock`.
- [ ] T058 [US3] Update the tests that assert one shared version and
  exact pins: `tests/test_package_metadata.py` (lines 215 to 239 and
  349 to 377) and `tests/test_contract_version.py` (lines 96 and 100).
  The new rule they hold: a package listed under `glob_exclude` has
  its own version; every pin on an SDK member is exact, at its line's
  version, except a provider's, which is a range covering one middle
  number.
- [ ] T059 [US3] Confirm the release scripts treat the three as they
  treat the contract, and correct the comments that name the contract
  as the only such package: `scripts/own-versions-current`,
  `scripts/publish-target-ready`, `scripts/dev-pin-resolves`. Extend
  `tests/test_own_version_builds_match_the_index.py` and
  `tests/test_publish_target.py` where they list own-versioned
  packages.
- [ ] T060 [US3] Make the release refusal say why: in
  `scripts/release.py`, beside `own_versions_or_refuse` (near line
  537), run the three baseline checks before anything is built and
  refuse naming the library and the entry. Test it in
  `tests/test_release_script.py`.

### Both ends of the range

- [ ] T061 [US3] Teach `scripts/isolated-run` the two ends: read the
  ranges from the family's manifest; for the low end install the
  lowest version of each SDK line and run only the named unit paths
  and the import check; for the high end install the highest and run
  everything; for each SDK library ask the index whether that version
  is published, install it from the index if so and from the built
  wheels if not, and print `<library> <version> from the index` or
  `<library> <version> from this repository's build (development
  install)`. When the two ends are the same version, say so and still
  run the low-end tests. Extend `tests/test_isolated_run.py`.
- [ ] T062 [US3] Add the low-end run to the `test-docker-alone` recipe
  in `Justfile`, on `packages/docker-plugin/tests/unit`.
- [ ] T063 [US3] Checkpoint: `just test-docker-alone` prints the
  source of each SDK library for three runs and passes; `just test`
  passes; the shared golden is unmoved.

**Checkpoint**: Stories 1 to 3 each pass on their own.

---

## Phase 6: The shared Terraform libraries alone (FR-026)

**Purpose**: give the two libraries the boundary a provider has, so a
later specification can move them. They stay in this repository.

**Independent Test**: `just test-terraform-alone` passes with no test
skipped (quickstart step 4), and the reverse-direction test passes.

Depends on Phases 2 and 5. Decision: research R22.

- [ ] T064 Pin the kit by a range in
  `packages/tofu-roots/pyproject.toml`
  (`cs-image-system-base>=0.2,<0.3`), keep its pin on
  `cs-image-system-hashicorp-utils` exact at the Terraform line's
  version, and run `uv lock`.
- [ ] T065 Make `packages/tofu-roots/src` pass the import check with
  no exception: each kit member it uses is either on the kit's surface
  in `packages/base/src/cs_image_system/base/surface.py` (as a named
  hook, for `_get_context`) or no longer used.
- [ ] T066 [P] Port, or move,
  `packages/hashicorp-utils/tests/test_terraform_collector.py` off
  `tests/harness.py`. Record which.
- [ ] T067 [P] Port, or move,
  `packages/hashicorp-utils/tests/test_packer_collector.py` off
  `tests/harness.py`. Record which.
- [ ] T068 [P] Port, or move, `packages/tofu-roots/tests/test_roots.py`
  off `tests/harness.py`. Record which.
- [ ] T069 Hold the reverse direction in `tests/test_contract.py`: no
  module under `packages/contract/src`, `packages/base/src`,
  `packages/engine/src`, `packages/system/src` or `src` imports
  `cs_image_system.hashicorp_utils` or `cs_image_system.tofu_roots`.
- [ ] T070 Add the recipe `test-terraform-alone` to `Justfile`:
  `scripts/isolated-run` with the two libraries and their declared
  dependencies only, at both ends of the kit range that `tofu-roots`
  declares, the whole of both packages' tests at the high end and
  their unit tests and the import check at the low end. Make `test`
  run it, add the job `terraform-alone` to
  `.github/workflows/ci.yml`, and update `tests/test_ci_workflow.py`
  and `tests/test_justfile_contract.py`.
- [ ] T071 Checkpoint: `just test-terraform-alone` passes with no
  skip and lists as installed only the two libraries, the kit, the
  contract and third-party packages; `just test` passes.

**Checkpoint**: FR-026 and SC-011 hold.

---

## Phase 7: User Story 4 - Another provider installed beside docker changes nothing (Priority: P4)

**Goal**: an unusable plugin or a collision is skipped and named, and
is fatal only to a configuration that uses it; installing a provider
beside docker changes nothing about a docker-only run.

**Independent Test**: with a deliberately broken extra plugin
installed, a docker-only configuration validates and completes a dry
run; each collision is reported with both plugins named.

Serves FR-015 to FR-020. Messages:
[contracts/commands.md](contracts/commands.md). Decisions: research
R13 to R16. Depends on Phase 2 only.

- [ ] T072 [US4] Add the unusable-plugin record to
  `packages/engine/src/cs_image_system/engine/loader.py`: for each
  plugin that could not be used, its entry-point name, its
  distribution, the cause (`failed to import`, `refused`, `collides`),
  for a collision the other plugin and what both claim, and the words
  it would have registered. Change the refusals at lines 219 to 223
  (namespace, conformance, group) from an exception that ends every
  command into a skip that logs one ERROR line in the form given in
  `specs/001-standalone-docker-provider/contracts/commands.md`.
- [ ] T073 [US4] Report silent replacements of enrollment kinds and
  field kinds (`packages/contract/src/cs_image_system/contract/enrollment.py`
  line 54, `field_kinds.py` line 93) as collisions that skip both
  plugins. Prefer detecting them in the loader, by comparing those
  registries before and after each plugin loads. If the contract
  package itself has to change, raise its version in the same task,
  update every range on it, and record that here and in plan.md, whose
  constraint "the contract does not change" then no longer holds.
- [ ] T074 [US4] In
  `packages/engine/src/cs_image_system/engine/loader.py` (lines 203 to
  206), treat two entry points with one name in one group as a
  collision: both skipped, one line naming both distributions.
- [ ] T075 [US4] Treat a registry key claimed by two plugins with
  different classes as a collision, in
  `packages/base/src/cs_image_system/base/registry.py` (lines 436 to
  447 and 707 to 711) and where `load_plugins` replays registrations
  in `packages/engine/src/cs_image_system/engine/loader.py`: both
  plugins skipped, neither registered, one line naming both. The same
  class registered by several plugins stays allowed.
- [ ] T076 [US4] Guard the commands entry points in
  `packages/system/src/cs_image_system/system/cli.py` (line 1585, run
  at import from line 1656): one that fails to load is skipped with
  one ERROR line and `--help` still works; two plugins mounting a
  different command under one name (lines 1640 to 1643) are both
  skipped and named.
- [ ] T077 [US4] Report bootstrap collisions in
  `packages/engine/src/cs_image_system/engine/bootstrap/sections.py`
  (line 34: a section name claimed twice skips both) and in
  `packages/engine/src/cs_image_system/engine/bootstrap/hcl.py` (lines
  79 to 87: two sections that declare one provider differently is an
  error naming both, not last-one-wins).
- [ ] T078 [US4] In
  `packages/base/src/cs_image_system/base/image_sources.py` (lines 148
  to 179), make an image-source block for a runtime type that another
  plugin registers a collision naming both, in place of the WARNING
  and first-by-name rule.
- [ ] T079 [US4] Make validation say the truth about a skipped plugin:
  when a configuration uses a word that an unusable plugin would have
  registered, `packages/engine/src/cs_image_system/engine/commands/load_failures.py`
  (lines 87 to 91) prints ` - <kind> type '<word>' is registered by
  <plugin>, which is installed but could not be used: <cause>` and not
  the "install the extra" advice of
  `src/cs_image_system/extras.py`, which stays for a plugin that
  really is absent.
- [ ] T080 [US4] Ask what is declared, not what is installed: failure
  classification in
  `packages/engine/src/cs_image_system/engine/commands/load_failures.py`
  (lines 68 to 76) and credential prefixes in
  `packages/engine/src/cs_image_system/engine/commands/preflight.py`
  (lines 118 to 133) consult only the classes the configuration
  declares.
- [ ] T081 [US4] Scope the provider agreement check in
  `packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py`
  (`validate_all`, lines 428 to 438, and its callers at lines 443,
  494, 506, 549; the Packer equivalent near lines 636 to 642): when a
  root is emitted, check only the providers that root declares,
  against the other roots that declare the same ones, and name the
  provider and every root in the disagreement. Test it in
  `packages/hashicorp-utils/tests/test_agreement_is_scoped.py`: two
  roots that disagree on a provider a third root does not declare
  leave the third root's emission working.
- [ ] T082 [US4] Namespace `plugin_state` keys in
  `packages/base/src/cs_image_system/base/run_context.py` (lines 421
  to 429) so two plugins using one key string hold separate state, and
  update its callers.
- [ ] T083 [US4] Create the isolation assertion in
  `packages/system/src/cs_image_system/system/testing/isolation.py`: a
  context manager that fails, naming what changed, if the process
  environment, the working directory, `sys.path`, or the root logger's
  level and handlers differ on exit, or if the kit's opened-secret
  store lost an entry. Use it around a load and a dry run in
  `packages/docker-plugin/tests/pipeline/test_leaves_the_process_alone.py`.
- [ ] T084 [US4] Test every skip and collision in
  `packages/engine/tests/test_unusable_plugins.py`, with entry points
  supplied by the test: a plugin that fails to import; one refused for
  each of namespace, conformance and group; a broken commands entry
  point; and a collision on each of a type, a command, a bootstrap
  section, an entry-point name, an enrollment kind, a field kind and
  an image-source block. Each asserts the plugin or pair is skipped,
  the one line names it, a configuration that does not use it loads,
  and a configuration that uses it fails validation with the cause.
- [ ] T085 [US4] Prove SC-006 in
  `packages/docker-plugin/tests/pipeline/test_broken_neighbour.py`:
  with a deliberately broken extra plugin supplied as an entry point,
  the family's fixture validates and completes a dry run, and the
  emission equals the family's golden.
- [ ] T086 [US4] Hold the two channels that already behave correctly,
  adding a test only where none exists: two distributions shipping a
  Terraform module directory of one name
  (`packages/engine/src/cs_image_system/engine/modules.py` lines 102
  to 106) in `packages/engine/tests/test_modules_collision.py`; and
  two plugins claiming one bare `type:` word, which
  `tests/test_registration_namespaces.py` already covers.
- [ ] T087 [US4] Checkpoint: `just test`, `just test-core` and
  `just test-docker-alone` pass; the shared golden is unmoved.

**Checkpoint**: Stories 1 to 4 each pass on their own.

---

## Phase 8: The usual install delivers docker (FR-021)

**Purpose**: prove that `cs-image-system[docker]`, installed from the
built packages into an empty environment, validates and dry-runs a
docker-only configuration.

**Independent Test**: `just test-docker-install` passes (quickstart
step 6).

Depends on Phase 3. Decision: research R18.

- [ ] T088 Add an install-check mode to `scripts/isolated-run`: install
  `cs-image-system[docker]` at the workspace version from the built
  wheels into an empty environment that holds nothing else; render the
  starter with the installed command
  (`cs-image-system init-config <dir> --from standard-docker`); run
  `validate`, then a dry `run --all`; report each of the three as ran
  and succeeded, ran and failed, or did not run; exit non-zero unless
  all three ran and succeeded. With `keep=<directory>`, leave the
  emitted `generated` tree there.
- [ ] T089 Extend `tests/test_isolated_run.py` for that mode with a
  stubbed shell: a failed install fails the run and reports the
  validation and the dry run as not run; a failed validation reports
  the dry run as not run; all three succeeding passes.
- [ ] T090 Add the recipe `test-docker-install` to `Justfile`. Add it
  to `full-test-legs` as a leg that fails, and does not skip, when the
  container daemon does not answer. Add the job `docker-install` to
  `.github/workflows/ci.yml` running `just test-docker-install`, and
  update `tests/test_ci_workflow.py` and
  `tests/test_justfile_contract.py`.
- [ ] T091 Checkpoint, on a machine with a container daemon:
  `just test-docker-install` reports the install, the validation and
  the dry run as each having run and succeeded.

**Checkpoint**: FR-021 and SC-010 hold.

---

## Phase 9: User Story 5 - One guide for writing a provider (Priority: P5)

**Goal**: one guide, with the docker family as its example, and every
statement this feature made false corrected.

**Independent Test**: a search for "contract alone" finds only the
contract example plugin (quickstart step 8), and the guide's commands
are the ones Phases 3 and 5 proved.

Serves FR-023. The list of statements is in
[plan.md](plan.md), "Statements this change makes false". Decision:
research R20.

- [ ] T092 [US5] Write `docs/WRITING_A_PROVIDER.md`, each point
  answered once with the docker family as the example: what a provider
  is made of; what it may import (the contract and the declared SDK
  surfaces) and how to check it; how it declares the kit and the
  Terraform libraries by range and what the version rule means for it;
  where its tests, fixture, golden, stubs and Terraform modules live;
  how to run its tests alone with `just test-docker-alone`; what the
  test kit gives it; and how a plugin that cannot be used shows itself
  to an operator. Finish the testing and dependency sections of
  `packages/docker-plugin/README.md` by linking to it.
- [ ] T093 [P] [US5] Correct `docs/PLUGINS.md`: the "contract alone"
  statements (lines 27, 28, 60, 196), the shared-version statements
  (lines 10, 19 to 21), the two docker packages wherever listed, the
  counts (lines 3, 31) deleted, and its how-to reduced to a link to
  the guide.
- [ ] T094 [P] [US5] Correct `docs/OPERATIONS.md`: "Writing a plugin"
  (lines 2608 to 2654) reduced to a link to the guide; the
  shared-version statements (lines 2455 to 2459, 2469); the counts
  (lines 2386, 2451 to 2471, 2544) deleted.
- [ ] T095 [P] [US5] Correct the other documents: `README.md` (lines
  58, 60, 67, 69, 76, 115), `GOALS.md` (line 24), `docs/DESIGN.md`
  (line 24), `docs/DESCRIPTION.md` (line 114), `docs/DAILY_DRIVER.md`
  (lines 1231, 1291, 1408), `docs/PARITY.md` (line 55), and
  `GOLDEN.md` (line 75, and its per-lifecycle table deleted).
- [ ] T096 [P] [US5] Correct the package READMEs:
  `packages/contract/README.md` (lines 3, 135, 173 to 181, 240, and
  "Writing a plugin" at 160 to 269 reduced to what is specific to the
  contract plus a link), `packages/base/README.md` (lines 3, 9 to 11,
  18 to 20), `packages/engine/README.md` (lines 45, 662 to 665),
  `packages/system/README.md` (line 12),
  `packages/hashicorp-utils/README.md` (lines 14, 26, 38, 392, 394),
  `packages/tofu-roots/README.md` (line 515) and
  `packages/dummy-plugin/README.md` (lines 17 to 20, which are already
  false, and 263 to 288).
- [ ] T097 [P] [US5] Correct the comments and docstrings:
  `pyproject.toml` (lines 16 to 20, 37 to 38, 143),
  `tests/fixtures/config/README.md` (lines 13 to 18, prose only: no
  fixture file changes), and the module docstrings of
  `tests/test_package_metadata.py` and
  `tests/test_contract_version.py`.
- [ ] T098 [US5] Run the documentation tests with `just test-one` on
  `tests/test_docs_contract.py`, `tests/test_docs_parity.py`,
  `tests/test_docs_examples.py` and
  `tests/test_sources_do_not_narrate.py`, then the search of
  quickstart step 8, which must print only `searched`.

**Checkpoint**: all five stories pass on their own.

---

## Phase 10: Polish and proof

**Purpose**: what crosses stories, and the acceptance run.

- [ ] T099 Give every new file its licence information: an SPDX header
  on each new source and script, and `REUSE.toml` entries for
  `packages/docker-plugin/tests/fixture/**`,
  `packages/docker-plugin/tests/golden/**`,
  `packages/system/tests/core_fixture/**`,
  `packages/system/tests/core_golden/**` and the three
  `surface-baseline.txt` files, none of which may carry a header. Then
  run `just headers`.
- [ ] T100 Run `just public-safe`. The new fixtures hold only the
  synthetic personas and the test identity.
- [ ] T101 Measure the budget and write the actual figures beside the
  expected ones in the Budget table of
  `specs/001-standalone-docker-provider/plan.md`: source lines, test
  lines, workspace packages, contract protocol members, tests, golden
  files, repository-wide checks. Any figure outside its expected range
  gets its reason written there.
- [ ] T102 Walk steps 1 to 6 and step 8 of
  `specs/001-standalone-docker-provider/quickstart.md` and record each
  result.
- [ ] T103 Prove FR-022 with step 7 of
  `specs/001-standalone-docker-provider/quickstart.md`:
  `just cli config-drift` exits with the status T003 recorded, and the
  `standard-docker` emission from the commit the branch started at
  equals the one `just test-docker-install keep=…` leaves, both made
  the same day.
- [ ] T104 Run `just full-test` (quickstart step 9). A leg that fails
  for an expired session or an unreachable service is reported as
  environmental, apart from a code failure.
- [ ] T105 Bring the specification's own files up to date: the status
  line of `specs/001-standalone-docker-provider/spec.md`; the note in
  `specs/001-standalone-docker-provider/checklists/requirements.md`
  that still says two planning choices are "bounded by FR-024"; and
  the row for 001 in `specs/README.md`.
- [ ] T106 Report to the operator what the first release after this
  feature does for the first time (research R21): it publishes the kit
  and the two Terraform libraries at 0.2.0 on their own version lines,
  and a new project on the index, `cs-image-system-docker-plugin`.
  This feature releases nothing.

---

## Dependencies & Execution Order

### Phase dependencies

| Phase | Depends on | Why |
| --- | --- | --- |
| 1. Setup | nothing | |
| 2. Test kit | 1 | |
| 3. Story 1 | 2 | The family's suite runs on the test kit and docker's stubs. |
| 4. Story 2 | 2, and T028 to T029 of Phase 3 | `test-core` uses `scripts/isolated-run`. |
| 5. Story 3 | 3 | The ranges go into the merged docker manifest; both ends extend `test-docker-alone`. |
| 6. Terraform libraries | 2, 5 | Needs the test kit, the surfaces and the version lines. |
| 7. Story 4 | 2; T083 and T085 need 3 | Loader and registry work is independent of the SDK. Two of its tests use the docker family's fixture. |
| 8. Install check | 3 | Needs the merged package and `scripts/isolated-run`. |
| 9. Story 5 | 3, 5, 6, 7 | The guide describes what was proven. |
| 10. Polish | all | |

### Story independence

- **Story 1** stands alone after the test kit. It is the MVP.
- **Story 2** shares only the isolated-run script with Story 1.
- **Story 3** builds on Story 1's merged package.
- **Story 4** is independent of Stories 2 and 3; two of its tests
  (T083, T085) use the docker family's fixture.
- **Story 5** comes last by design: it documents the others.

### Within a phase

- Tasks without **[P]** run in the order listed.
- A checkpoint task closes its phase. Do not start a phase that
  depends on it until it passes.

### Parallel opportunities

- Phase 2: T006 and T008 beside T005.
- Phase 3: T023 to T026 together, once T020 to T022 are done.
- Phase 5: T046 and T047 together, once T045 fixes the declaration's
  structure.
- Phase 6: T066 to T068 together.
- Phase 9: T093 to T097 together, once T092 exists to link to. Each
  touches different files.
- Phases 4, 7 and 8 can proceed beside Phase 5 once Phase 3 is done,
  with one caution: Phases 4, 6 and 8 each edit `Justfile`,
  `.github/workflows/ci.yml`, `tests/test_ci_workflow.py` and
  `tests/test_justfile_contract.py` (T043, T070, T090), so those four
  tasks are done one at a time.

---

## Parallel Example: User Story 1

```text
# After T022 (the family's fixture and golden exist), move the tests together:
Task T023: the two unit test files into packages/docker-plugin/tests/unit/
Task T024: tests/test_container_runtime.py into packages/docker-plugin/tests/pipeline/
Task T025: tests/test_mod_tests.py and tests/test_mod_test_containers.py
Task T026: tests/test_bootstrap_docker.py
```

## Parallel Example: User Story 5

```text
# After T092 (the guide exists), correct the documents together:
Task T093: docs/PLUGINS.md
Task T094: docs/OPERATIONS.md
Task T095: README.md, GOALS.md, docs/DESIGN.md, docs/DESCRIPTION.md,
           docs/DAILY_DRIVER.md, docs/PARITY.md, GOLDEN.md
Task T096: the package READMEs
Task T097: comments and docstrings
```

---

## Implementation Strategy

### MVP first (Story 1 only)

1. Phase 1: the branch and the before-state.
2. Phase 2: the test kit. Nothing observable changes; `just test` is
   the proof.
3. Phase 3: the merge, the family's suite, the isolated run.
4. **Stop and validate**: `just test-docker-alone` and `just test`
   pass, and the shared golden is unmoved. This is a reviewable,
   mergeable increment: the docker family proves itself alone.

### Incremental delivery

| After | What is true | Proof |
| --- | --- | --- |
| Phase 3 | Docker proves itself alone | `just test-docker-alone` |
| Phase 4 | The core proves itself with no provider | `just test-core` |
| Phase 5 | The SDK has surfaces, versions and a release refusal; docker is on ranges | `just test`, `just test-docker-alone` |
| Phase 6 | The Terraform libraries are separable | `just test-terraform-alone` |
| Phase 7 | No installed plugin can break or silently replace another | `just test` |
| Phase 8 | The usual install still delivers docker | `just test-docker-install` |
| Phase 9 | One guide; nothing left false | quickstart step 8 |
| Phase 10 | Everything, together | `just full-test` |

Each row leaves `just test` green and the shared golden unmoved, so
the work can stop after any of them.

### Where the risk is

- **T019**: the merge must not move the shared golden. If it does,
  the fallback in research R1 (keep two packages) is still open at
  that point and costs little, because nothing else has been built on
  the merge yet.
- **T034**: whether the core can emit an image without a provider
  decides how much the core golden covers.
- **T055**: the version lines touch every manifest. Do it in one task
  and run `just test` straight after.
- **T072 to T078**: each changes what happens when plugins load. The
  shared golden and the every-provider suite are the guard that
  ordinary loading did not change.

---

## Notes

- **[P]** tasks touch different files and depend on nothing
  unfinished.
- A story label ties a task to its user story; Phases 1, 2, 6, 8 and
  10 carry none, by the format's rule.
- Stop at any checkpoint to validate that story on its own.
- If a task turns out to need a change this list did not foresee, add
  the task here before doing it.
