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
| T003 | `just cli config-drift` exit status before any change: **0**, taken on 2026-11-17 with the code of the commit the branch started at (`be648dbb`, in a temporary worktree) against the reference configuration at its `develop`. Its message: the committed emission is current with the configuration; the vendor's newest image has moved under a base the tree has not baked (1 line), which is not a change of the tree's. 3 min 40 s. The after-reading (T103) must also be 0; the vendor-image line may differ by the day |
| Postponed | Found at T022 and postponed by the operator on 2026-11-17: a docker instance root carries remote-state blocks for every storage builder the configuration declares, whichever provider it belongs to. Not part of this specification; do not change it here |
| T011 | Phase 2 checkpoint: `just test` passed, 2,497 passed and 29 skipped (the same as T002), shared fixture and golden untouched |
| T019 | Shared golden after the merge (must be unmoved): UNMOVED. Full `just test` on 2026-11-16: lint clean, type check 0 errors, 2,491 passed, 29 skipped, 1 failed (`tests/test_module_sources.py`, an expectation naming the old distribution; corrected, and that file then passed alone, 18 tests). One value does derive from the distribution's name: the namespace a shipped Terraform module is listed and stamped under is now `docker`, was `docker-runtime`. It is not in any emission. A `.csis-module` stamp in a configuration changes only when that module's copy is next rewritten |
| T012 | Not yet done from this task: the package's `test` extra and its own pytest settings. They are added with T028 to T030, where they are first used |
| T022 | Family golden recorded on 2026-11-16 (42 files) and compared with the shared golden: `base-image/pckr-docker`, `instance-image/pckr-docker` and `storage/docker-volume` are byte-identical. `instance-image/tofu-docker` differs in two files, by additions on the shared side only: `tofu-docker-instance-generation.tf` carries five `terraform_remote_state` blocks (`aws_efs`, `aws_ebs`, `aws_s3`, `gcp_pd`, `gcp_gcs`) and the instance file carries `"ebs" = {}` and `"efs" = {}`. Cause: a docker instance root reads the state of every storage builder the configuration declares, whichever provider it belongs to, and the family's fixture declares only docker's. Nothing was changed about that behaviour |
| T024 to T026 | DONE on 2026-11-17, as a split and not a move of four files. The rule applied to each of the 47 tests: a test of what the docker package itself does goes to the package, on its own fixture, and may import only the contract, the SDK's surface, the package and the test kit; a test of what the core or another plugin does with a docker runtime needs the engine or another provider, which a provider's suite may not import, and stays in `tests/`, where every provider is installed. 25 tests are now in the package (17 pipeline, 7 unit, 1 live) and 30 remain in `tests/`, each file's description saying which half it holds |
| T012, T027 | The package's `test` extra names the command line (with its `testing` extra) and the six core plugins whose `type:` words the fixture declares, not the top-level package: naming `cs-image-system` makes a dependency cycle with its `docker` extra, which the release tooling refuses |
| T033 | Story 1 checkpoint, 2026-11-16: `just test` passed end to end (lint clean, type check 0 errors, 2,510 tests passed and 29 skipped, then `test-docker-alone`: 24 passed and 0 skipped in place, and the same from a copy outside the workspace), 22 min 20 s. Shared fixture and golden untouched. T024 to T026 are still open |
| T024 | `test_container_runtime.py`: 14 tests ported to `packages/docker-plugin/tests/pipeline/test_container_runtime.py` over the family's fixture (the emission, validation's refusals, the encrypted host, the launch parameters, the hooks over a stubbed daemon), with two new ones at the plugin's own seam (the builder's `classify_failure` and `session_status`). 15 stay in `tests/`: the okta builder's objection, the preflight's line per session with the state backends beside the daemon, the core's load-failure line, the packer plugin's manifest reading, the core's launch-script delivery and hook order, what the contract and the kit declare, and the documents, Justfile and workspace membership. The cross-provider assertions that rode on the ported tests (the clouds' emission untouched) are held by the shared golden |
| T025 | `test_mod_tests.py` and `test_mod_test_containers.py` test the CORE's modification-test harness and command with a fake target over the shared fixture's cloud images, so 8 of their 10 tests stay in `tests/`. Ported: the docker target's retried pull and its CLI choice, to `packages/docker-plugin/tests/unit/test_local_target.py` (the error is the contract's `ContainerStartError`); and the daemon-backed test, to `packages/docker-plugin/tests/live/test_mod_tests_live.py`, over the family's fixture. It is in no default path and no isolated run, it no longer skips (without a daemon it fails), and it passed against the local daemon. The test kit gained `run_mod_tests(ctx, ...)` for it, and `encrypted(config_root, plaintext)` for T024's encrypted host; the kit's surface was not widened |
| T026 | `test_bootstrap_docker.py`: LEFT in `tests/`, 7 of its 8 tests, and not only for its imports from `tests.test_bootstrap`: it drives the engine's interview, generator and public-safe scan over the starters under `docs/examples` and asserts the order of every provider's section, none of which a provider's suite may import or reach. What is the section's own was ported to `packages/docker-plugin/tests/unit/test_bootstrap_section.py` (when it is wanted, what it proposes by how the runtime names its daemon, that its render never prints an address), with a stand-in for the one thing the section reads of a checkout. Before this the package's own suite did not exercise its bootstrap section at all |
| T034 | Does the core's image builder emit with Packer's `null` source: YES (2026-11-17). With the test-double runtime a stubbed run emits a base image and an instance image with a shell and an ansible modification. The fixture must declare an image source for the double, since no catalog ships one |
| T037 | `test_ansible_only_modifications.py`: PORTED to the test kit and the core fixture; what it asserts did not change. Two more tests failed in the empty environment and were moved whole: the example plugin's conformance test to `packages/contract-example-plugin/tests/test_example_conforms.py`, and the local-state test that needs the S3 backend kind to `tests/test_state_locations.py`. A contract test now reads its manifest from beside the test file instead of beside the installed module |
| T036, T038 | The core's fixture and golden are `packages/system/tests/fixture` and `packages/system/tests/golden` (not `core_fixture` and `core_golden` as the plan named them), so one licence rule covers every package's own fixture and golden. Golden: 32 files |
| T039 to T041 | `test-mods` with no stand-in installed used to exit 0 with every result `unsupported`. It now says the tests did not run and exits 1 unless `--allow-not-run` is given. Every recipe here and in the starters already passes `--strict` |
| T044 | Story 2 checkpoint, 2026-11-17: `just test` passed end to end: lint clean, type check 0 errors, 2,526 passed and 29 skipped, then `test-core` 267 passed and 0 skipped, then `test-docker-alone` 24 passed and 0 skipped twice. 24 min 11 s. Shared fixture and golden untouched |
| After T044 | Verified 2026-11-17 by a full `just test` with the restore in place: lint clean, type check 0 errors, 2,532 passed and 29 skipped, `test-core` 269 passed and 0 skipped, `test-docker-alone` 26 passed and 0 skipped twice, 23 min 37 s, shared fixture and golden untouched. At the operator's request (2026-11-17): the root logger is restored after every test. The restore's body is `cs_image_system.system.testing.isolation.root_logger_restored`; `conftest.py` (root), `packages/conftest.py` and the docker suite's conftest make it a fixture. A two-test proof sits in `tests/`, `packages/system/tests/` and the docker suite. `scripts/isolated-run` now passes `--confcutdir` so the conftest at a run's root applies. One test that read a logged word (`tests/test_mod_test_containers.py`) now asserts what the target saw |
| T066 to T068 | `test_packer_collector.py`: PORTED (its run holder now comes from `cs_image_system.hashicorp_utils.testing`, moved there from the test kit, which may not import this library). `test_terraform_collector.py` (26 tests): MOVED whole to `tests/`; its sample backend throughout is the S3 plugin's backend kind. `test_roots.py`: SPLIT; three tests without a backend stay, three that need the S3 backend kind moved to `tests/test_roots_with_a_state_backend.py` |
| T065 | `tofu-roots` passed the import check as soon as the kit's declaration was seeded (it lists `_get_context` and the other members the roots use as hooks). The check's scan of a library's private members now leaves out the library's `testing` module: matching is by name, and a test helper's `_state` was being reported against plugins' own attributes |
| T070 | Three runs, all with the roots library and what it declares installed: the roots at the high end, the collectors at the high end, the roots at the low end. The collectors' suite needs the kit for its baseline test, so it runs in the pair's environment, not alone |
| T071 | FR-026 checkpoint, 2026-11-17: `just test` passed end to end: lint clean, type check 0 errors, 2,586 passed and 29 skipped, `test-core` 290, `test-terraform-alone` 4, 24 and 4, `test-docker-alone` 28, 28 and 24, all with 0 skipped. Shared fixture and golden untouched |
| T045 to T047 | The three declarations were seeded from what every plugin uses today and committed as seeded: the kit 55 names in 41 modules and 9 hook names; `hashicorp-utils` 18 names; `tofu-roots` 11 names and 32 hook names. Not yet read and trimmed by a person |
| T048 | The check also lets a plugin import a plugin it DECLARES as a dependency (read from the manifest beside its sources, or `--family`): the AWS and Google Cloud roots import their runtimes, and the spec leaves them alone. Its entry point is the module `cs_image_system.base.surface.cli`; `check` holds `findings`, `record` the baseline |
| T050 | Replacing `tests/test_plugin_imports.py` left a dead link in the contract's README, so the CONTRACT IS NOW 0.4.3 (a PATCH: its README names the new test; nothing a plugin observes changed). Five documents that named the old test were corrected |
| T052 to T054 | Baselines: `packages/base/surface-baseline.txt` (about 1,640 lines), `packages/hashicorp-utils/surface-baseline.txt` (115), `packages/tofu-roots/surface-baseline.txt` (256). A third recipe was added, `just surface-check`, which the release's probes run |
| T055, T056 | Both lines are at 0.2.0. `.bumpversion-kit.toml` and `.bumpversion-terraform.toml` name each exact pin, so neither line nor the workspace's bump can move another's. A test moves each line by `last` and by `middle` over a copy of the tree |
| T061, T062 | The docker suite's conftest moved to `tests/pipeline/conftest.py`: the low-end environment holds the package, the SDK and the contract only (5 distributions), with no test kit to import |
| T063 | Story 3 checkpoint, 2026-11-17: `just test` passed end to end: lint clean, type check 0 errors, 2,581 passed and 29 skipped, `test-core` 290 passed and 0 skipped, `test-docker-alone` 28 and 28 passed at the high end (in place, from the copy) and 24 at the low end, 0 skipped. 32 min 9 s (the suite itself took 30 min on this run). Shared fixture and golden untouched |
| T073 | Was the contract package changed, and its new version if so: NOT CHANGED by Phase 7 (still 0.4.3, from T050). Replacements of an enrollment kind or a field kind are detected in the loader, which reads the contract's two registries before and after each plugin loads and puts them back when a plugin is skipped. The contract's two docstrings that say a second registration "replaces" the first are corrected with the other documents, in T107 |
| T072, T074, T075 | One line per skipped plugin or colliding pair, in the wording of `contracts/commands.md` (`Plugin <name> (<distribution>) is skipped: <cause>: <detail>`; `Plugins <a> and <b> are both skipped: both register <what>`). Discovery is `loader.discover()`; what could not be used is `loader.unusable_plugins()` |
| T076 | A plugin's commands are mounted plugin by plugin. One that cannot be mounted whole (its entry point fails, it returns something that is no mount, it takes a built-in command's name, or it and another plugin mount different things under one name) is skipped whole with one ERROR line, and the command line still starts. `mount_plugin_commands(root, mounts)` with a caller's own list still raises, as its existing tests hold |
| T077 | A section entry point that fails was a WARNING and is now the same ERROR line as any skipped plugin. Two sections declaring one provider differently raise the contract's `Refused`; the `bootstrap` command now catches it around generation too (it caught it only around the interview) and keeps the answers |
| T078 | Two rules. Discovery skips both plugins when one ships an image-source block for a runtime type the other registers (today each plugin ships blocks for its own type only). The kit's merge no longer keeps the first of two differing blocks: neither is used, and one ERROR line names both parts. The WARNING and first-wins rule for what a family `is` and its description is unchanged: the task named the block only |
| T080 | Failure classification asks the classes of the `type:` words the configuration declares. A load that fails after its builder lists are read leaves those words in the typer context (`declared_types`); `validate --online` passes its loaded builders' words. A load that fails before the lists are read still asks every installed class, since nothing is known of the configuration then. An OS builder whose `type` was defaulted from its family is not among the words; no OS builder classifies a failure |
| T081 | `validate_all()` keeps its signature and meaning (run-wide), so the Terraform libraries' surface is unaltered and their version line did not move. Emission calls the new `validate_for(workspace)`; the baseline of `hashicorp-utils` was re-recorded with that one added entry, which the 0.2 line (not yet released) allows |
| T082 | The contract's `plugin_state(key, factory)` is unchanged. The kit's context refuses a key that is not `<namespace>/<name>`, and the three keys in use became `hashicorp-utils/terraform-collector`, `hashicorp-utils/packer-collector` and `base/alias-pool.draws`. The context cannot know who is calling, so it holds the form, not the ownership |
| T083, T085 | The test kit gained `isolation.process_unchanged()`, `broken_neighbour(monkeypatch)` and `validation_errors(ctx)`. The docker family's isolation test stands in the configuration's root first: the load's change of directory is the core's own and deliberate, undone by the command line. The family changed nothing: the test passed on its first run |
| T084 | The skips and collisions are tested where each lives, not all in one file: discovery (import failure; namespace, conformance and group refusals; registry key; entry-point name; enrollment kind; field kind; image-source block) in `packages/engine/tests/test_unusable_plugins.py`; bootstrap sections and providers in `packages/engine/tests/test_bootstrap_collisions.py`; commands in `packages/system/tests/test_plugin_commands_are_guarded.py`, because an engine test may not import the command line; a whole run beside a broken plugin, and the validation message, in `packages/system/tests/test_a_broken_neighbour.py` |
| T086 | `packages/engine/tests/test_modules_collision.py` added: no test held the module-name refusal before |
| T087 | Story 4 checkpoint, 2026-11-17: `just test` passed end to end: lint clean, type check 0 errors, 2,638 passed and 29 skipped, `test-core` 331 passed and 0 skipped, `test-terraform-alone` 4, 31 and 4, `test-docker-alone` 31, 31 and 24, every isolated run with 0 skipped; shared fixture and golden untouched; 33 min 21 s for the unit tests. A first run failed on one test, the ceiling on sentence assertions (38 against 37): three new assertions checked a phrase and now check the plugin's name and its cause |
| T088 to T091 | FR-021 checkpoint, 2026-11-17, on the operator's machine with its container daemon answering: `just test-docker-install` reported the install, the validation and the dry run each as ran and succeeded (14 distributions of this repository installed, all from the built wheels). The mode is `scripts/isolated-run --install-check`; rendering the starter is counted with the install, so a failed render reports the install as ran and failed. `--keep` refuses a directory that already holds a `generated` tree and replaces nothing. The recipe takes `keep=<directory>` or the directory alone. In `full-test-legs` the leg stands outside the daemon check, so it fails where the other docker legs report SKIPPED |
| T092 to T098, T107 | Story 5, 2026-11-17. `docs/WRITING_A_PROVIDER.md` written with the docker provider as its example; the four earlier how-to places keep what is theirs and link to it. The search of quickstart step 8 prints only `searched`: true statements that used the words (the Terraform library depends on nothing but the contract; the example plugin) were reworded, a history row in `docs/CHANGES.md` and one test docstring among them. THE CONTRACT IS NOW 0.4.4 (a PATCH: its README and three docstrings; no function, protocol or constant changed), and the lock file was refreshed. Counts of packages were deleted, not updated. Not changed, and why: `tests/fixtures/config/README.md`, because what it says of the shared fixture still holds and leaving it keeps `git status --short tests/fixtures` empty; the comments in `scripts/own-versions-current` and `scripts/dev-pin-resolves`, already corrected in Phase 6. The documentation tests, the metadata tests and the contract's version tests pass |
| After T081 | Left as it was: the collector's check of state locations (`validate_state_locations`) still runs run-wide beside the per-root provider check, so two roots that collide on one state location still stop the emission of a third. The task and decision R14 name provider agreement only; a state-location collision is a fault in the configuration's own bindings, not a disagreement between providers |
| T099, T100 | `just headers` changed no file and the licensing check passes (1,278 of 1,278 files). The core's fixture and golden are `packages/system/tests/fixture` and `golden`, covered by the `packages/*/tests/fixture/**` and `golden/**` entries (see T036). `just public-safe`: 1,320 files hold nothing that must not be public |
| After T026 | Checkpoint for T024 to T026, 2026-11-17: `just test` passed end to end: lint clean, type check 0 errors, 2,662 passed and 28 skipped (one fewer skip: the daemon-gated test left `tests/`), `test-core` 331, `test-terraform-alone` 4, 31 and 4, `test-docker-alone` 62, 63 and 38, each with 0 skipped; shared fixture and golden untouched. The 63 was a DEFECT that run exposed: the copy of the docker package counted one test more than the run in place. `scripts/isolated-run` left a suite's default paths to pytest, which applies `testpaths` only when started in the directory it takes for its root; a copy under the system's temporary directory is reached through a symbolic link, so pytest collected every directory of the copy, and the new `tests/live` test ran in an isolated run (and passed only because a daemon was answering). The script now reads the declared `testpaths` and names them itself, with a test. After the fix: `test-docker-alone` 62, 62 and 38, `test-terraform-alone` and `test-core` as before, the script's own tests, lint and the type check all pass; the unit suite was not run a third time, since only the script and its test file changed after it |
| T101 | Budget actuals written into plan.md on 2026-11-17: source lines 56,818 (+2,336), test lines 47,352 (+2,225), packages 22, contract protocol members unchanged, tests 2,049 (+110), golden files 222 (+74), re-measured after T024 to T026. Four are outside their expected range, each with its reason there |
| T103 | FR-022, 2026-11-17, both halves made the same day. The reference configuration: `just cli config-drift` exit **0**, as T003 recorded; the committed emission is current, with the one vendor-image line (`almalinux-10-v20261110` to `almalinux-10-v20261116`) that is not the tree's change. The `standard-docker` starter: the emission from the commit the branch started at (`be648dbb`, a temporary worktree, every provider installed) and the one `just test-docker-install keep=…` left (the built wheels, `cs-image-system[docker]` alone) are IDENTICAL over 41 files after the normalisation `config-drift` applies. A raw `diff -r`, which the quickstart first asked for, cannot be empty: two dry runs differ in their run id, the time stamp in image names, an absolute path in `run-summary.json` and what `tofu init` leaves behind, and in nothing else. Box 3 of step 7 is now v2 and compares the normalised trees |
| T106 | Reported to the operator on 2026-11-17: the first release after this feature publishes the kit and the two Terraform libraries at 0.2.0 on their own version lines for the first time, and one new project on the index, `cs-image-system-docker-plugin`; the contract goes out at 0.4.4. This feature releases nothing |
| T102, T104 | Quickstart walked on 2026-11-17. Step 2: the one expected difference, `instance-image/tofu-docker`. Step 6: all three steps ran and succeeded. Step 7: see T103. Step 8: only `searched`. Steps 1, 3, 4, 5 and 9 were one run of `just full-test`, with the project's environment loaded, on the tree committed as `f1fafcf5`: `full-test: passed`. Lint clean, type check 0 errors, 2,646 passed and 29 skipped in 27 min 24 s; `test-core` 331, `test-terraform-alone` 4, 31 and 4, `test-docker-alone` 31, 31 and 24, each with 0 skipped; then the legs: the development pin resolves; `test-docker-install` ran and succeeded in all three steps; `test-mods --strict` 5 tested, 0 failed; the posix accounts (14) and bake steps (6); the runner image built; the docker bake (1) and cycle (2) on the local daemon; the Podman Desktop cycle (2); the dry `run --all` and `state query --strict` over a copy of the reference. One leg reported SKIPPED, by its own rule: the Podman API service cycle, because `CSIS_PODMAN_HOST` names none. T024 to T026 were done after this run and are covered by the `just test` recorded below |

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
- [X] T003 Run `just cli config-drift` against the reference
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
- [X] T024 [P] [US1] Move `tests/test_container_runtime.py` to
  `packages/docker-plugin/tests/pipeline/test_container_runtime.py`,
  on the test kit, docker's stubs and the family's fixture. Port, or
  move.
- [X] T025 [P] [US1] Move `tests/test_mod_tests.py` and
  `tests/test_mod_test_containers.py` to
  `packages/docker-plugin/tests/pipeline/`. Port, or move. The one
  test gated on `CSIS_DOCKER_TESTS` needs a daemon: keep it out of the
  isolated run by placing it in
  `packages/docker-plugin/tests/live/test_mod_tests_live.py`.
- [X] T026 [P] [US1] Move `tests/test_bootstrap_docker.py` to
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

- [X] T034 [US2] Settle research R5 before building on it: in a
  throwaway test, give the core's image builder a runtime whose
  `packer_source_type` is `null` and see whether a dry run emits.
  Record the answer in the Records table of
  `specs/001-standalone-docker-provider/tasks.md`. If it does not
  emit, the core fixture of T036 declares no image.
- [X] T035 [US2] Create the test-double runtime in
  `packages/system/src/cs_image_system/system/testing/double.py`: a
  model and a `RuntimeBuilderBase` subclass that bake through Packer's
  `null` source and offer no instance, no storage and no stand-in,
  registered by the test kit for the length of one run and never as
  an installed entry point. It must name no provider.
- [X] T036 [US2] Create the core fixture in
  `packages/system/tests/core_fixture/`: one runtime of the
  test-double's type, the local state backend, POSIX groups with the
  synthetic personas, one OS builder, the mod builders, and (if T034
  allows) one base image and one instance image. No provider-specific
  runtime and nothing that needs Okta.
- [X] T037 [US2] Port, or move,
  `packages/ansible-plugin/tests/test_ansible_only_modifications.py`:
  onto the test kit and the core fixture if what it asserts survives,
  otherwise to `tests/`. Record which.
- [X] T038 [US2] Create `packages/system/tests/test_core_golden.py`,
  record `packages/system/tests/core_golden/`, and read every recorded
  file.
- [X] T039 [US2] Change stand-in selection in
  `packages/engine/src/cs_image_system/engine/mod_tests.py`
  (`stand_in_target_factory` near line 112, and the callers near lines
  297 to 338) and `stand_in_runtime_type` in
  `packages/base/src/cs_image_system/base/image_sources.py` (lines 190
  to 200): exactly one installed runtime class whose
  `local_test_target()` returns a factory is used and named; two or
  more is an error until one is named; none, or one whose daemon does
  not answer, is a failure. It must never pick by name or by order.
- [X] T040 [US2] Add `--stand-in <runtime type>` and an explicit
  exclusion option to the `test-mods` command in
  `packages/system/src/cs_image_system/system/cli.py` (near lines 864
  to 879), printing exactly the lines given under "The stand-in" in
  `specs/001-standalone-docker-provider/contracts/commands.md`.
  "Did not run" exits non-zero unless the exclusion was asked for.
- [X] T041 [US2] Test the stand-in in
  `packages/engine/tests/test_stand_in.py` with stand-in runtime
  classes defined in the test: one installed; two installed and none
  named; two installed and one named; none installed; one installed
  whose factory returns nothing; and each of the last two with the
  exclusion.
- [X] T042 [US2] Add the recipe `test-core` to `Justfile`:
  `scripts/isolated-run` with a plain `cs-image-system` (no extras)
  and `cs-image-system-system[testing]`, on the `tests` directories of
  `packages/contract`, `packages/base`, `packages/engine`,
  `packages/system`, `packages/ansible-plugin`,
  `packages/bash-mod-plugin`, `packages/default-os-plugin`,
  `packages/packer-plugin`, `packages/local-state-plugin` and
  `packages/posix-identity-plugin`. Any file there that still imports
  `harness` or `golden` from `tests/` fails the run: port it, or move
  it to `tests/`.
- [X] T043 [US2] Make `test` in `Justfile` run `test-core`, add the
  job `core-alone` to `.github/workflows/ci.yml` running
  `just test-core`, and update `tests/test_ci_workflow.py` and
  `tests/test_justfile_contract.py`.
- [X] T044 [US2] Checkpoint: `just test-core` passes with no skip and
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

- [X] T045 [US3] Create
  `packages/base/src/cs_image_system/base/surface.py` with the
  declaration's structure (per module, the names a plugin may import;
  per class, the underscore-prefixed hooks a subclass may override or
  call) and the kit's own declaration. Seed it from what every
  `packages/*/src` outside `base`, `engine`, `contract` and `system`
  imports from `cs_image_system.base` today and from the kit's
  underscore members they override or call (`_get_context` and
  `_model` among them), then read it and trim it by hand.
- [X] T046 [P] [US3] Create
  `packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/surface.py`
  with that library's declaration, seeded the same way. It must import
  nothing of the kit: this library depends on the contract alone.
- [X] T047 [P] [US3] Create
  `packages/tofu-roots/src/cs_image_system/tofu_roots/surface.py` with
  that library's declaration, naming as hooks every underscore member
  the roots plugins override or call (`_provider_name`,
  `_provider_source`, `_provider_config`, `_module_dirname`,
  `_module_resource`, `_instance_word`, `_root_header_lines`,
  `_launch_template_name`, `_module_args`, `_launch_args`, `_lookup`,
  `_runtime_builder`, `_image_var`, `_launch_template_variables`,
  `_storage_builder_name`, `_storage_outputs_reference`, and any other
  the seed finds).
- [X] T048 [US3] Implement the import check in
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
- [X] T049 [US3] Test the check in
  `packages/base/tests/test_surface_check.py` on small source trees
  written by the test: a listed name passes; an unlisted kit name
  fails with "not on the surface"; an unlisted underscore member fails
  with "private to"; an engine import fails; another plugin's import
  fails; the plugin's own modules pass; and `--tests` allows the test
  kit.
- [X] T050 [US3] Replace `tests/test_plugin_imports.py` with
  `tests/test_plugins_keep_to_the_surface.py`: every plugin under
  `packages/*/src` and both Terraform libraries pass the check. Delete
  the old file, and delete the assertion in
  `tests/test_import_closure.py` (lines 84 to 94) that a plugin
  reaches every kit module.
- [X] T051 [US3] Run the check with `--tests` on
  `packages/docker-plugin/tests` from
  `packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py`,
  and on `packages/docker-plugin/src` from the same file, so the
  family proves FR-002 and SC-004 about itself.

### Baselines and the two version lines

- [X] T052 [US3] Add the surface record to
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
- [X] T053 [US3] Add the baseline check as a test in each library's
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
- [X] T054 [US3] Add the recipe `surface-record` to `Justfile`,
  rewriting the three baselines and refusing when the middle number
  equals the baseline's and an entry would be removed or changed.
- [X] T055 [US3] Open the two version lines. Set `version = "0.2.0"`
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
- [X] T056 [US3] Add the recipe `sdk-bump` to `Justfile`, taking
  `kit` or `terraform` and `last` or `middle`, behaving as
  `specs/001-standalone-docker-provider/contracts/commands.md` says.
- [X] T057 [US3] Put docker on ranges in
  `packages/docker-plugin/pyproject.toml`:
  `cs-image-system-base>=0.2,<0.3`,
  `cs-image-system-hashicorp-utils>=0.2,<0.3`,
  `cs-image-system-tofu-roots>=0.2,<0.3`. Run `uv lock`.
- [X] T058 [US3] Update the tests that assert one shared version and
  exact pins: `tests/test_package_metadata.py` (lines 215 to 239 and
  349 to 377) and `tests/test_contract_version.py` (lines 96 and 100).
  The new rule they hold: a package listed under `glob_exclude` has
  its own version; every pin on an SDK member is exact, at its line's
  version, except a provider's, which is a range covering one middle
  number.
- [X] T059 [US3] Confirm the release scripts treat the three as they
  treat the contract, and correct the comments that name the contract
  as the only such package: `scripts/own-versions-current`,
  `scripts/publish-target-ready`, `scripts/dev-pin-resolves`. Extend
  `tests/test_own_version_builds_match_the_index.py` and
  `tests/test_publish_target.py` where they list own-versioned
  packages.
- [X] T060 [US3] Make the release refusal say why: in
  `scripts/release.py`, beside `own_versions_or_refuse` (near line
  537), run the three baseline checks before anything is built and
  refuse naming the library and the entry. Test it in
  `tests/test_release_script.py`.

### Both ends of the range

- [X] T061 [US3] Teach `scripts/isolated-run` the two ends: read the
  ranges from the family's manifest; for the low end install the
  lowest version of each SDK line and run only the named unit paths
  and the import check; for the high end install the highest and run
  everything; for each SDK library ask the index whether that version
  is published, install it from the index if so and from the built
  wheels if not, and print `<library> <version> from the index` or
  `<library> <version> from this repository's build (development
  install)`. When the two ends are the same version, say so and still
  run the low-end tests. Extend `tests/test_isolated_run.py`.
- [X] T062 [US3] Add the low-end run to the `test-docker-alone` recipe
  in `Justfile`, on `packages/docker-plugin/tests/unit`.
- [X] T063 [US3] Checkpoint: `just test-docker-alone` prints the
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

- [X] T064 Pin the kit by a range in
  `packages/tofu-roots/pyproject.toml`
  (`cs-image-system-base>=0.2,<0.3`), keep its pin on
  `cs-image-system-hashicorp-utils` exact at the Terraform line's
  version, and run `uv lock`.
- [X] T065 Make `packages/tofu-roots/src` pass the import check with
  no exception: each kit member it uses is either on the kit's surface
  in `packages/base/src/cs_image_system/base/surface.py` (as a named
  hook, for `_get_context`) or no longer used.
- [X] T066 [P] Port, or move,
  `packages/hashicorp-utils/tests/test_terraform_collector.py` off
  `tests/harness.py`. Record which.
- [X] T067 [P] Port, or move,
  `packages/hashicorp-utils/tests/test_packer_collector.py` off
  `tests/harness.py`. Record which.
- [X] T068 [P] Port, or move, `packages/tofu-roots/tests/test_roots.py`
  off `tests/harness.py`. Record which.
- [X] T069 Hold the reverse direction in `tests/test_contract.py`: no
  module under `packages/contract/src`, `packages/base/src`,
  `packages/engine/src`, `packages/system/src` or `src` imports
  `cs_image_system.hashicorp_utils` or `cs_image_system.tofu_roots`.
- [X] T070 Add the recipe `test-terraform-alone` to `Justfile`:
  `scripts/isolated-run` with the two libraries and their declared
  dependencies only, at both ends of the kit range that `tofu-roots`
  declares, the whole of both packages' tests at the high end and
  their unit tests and the import check at the low end. Make `test`
  run it, add the job `terraform-alone` to
  `.github/workflows/ci.yml`, and update `tests/test_ci_workflow.py`
  and `tests/test_justfile_contract.py`.
- [X] T071 Checkpoint: `just test-terraform-alone` passes with no
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

- [X] T072 [US4] Add the unusable-plugin record to
  `packages/engine/src/cs_image_system/engine/loader.py`: for each
  plugin that could not be used, its entry-point name, its
  distribution, the cause (`failed to import`, `refused`, `collides`),
  for a collision the other plugin and what both claim, and the words
  it would have registered. Change the refusals at lines 219 to 223
  (namespace, conformance, group) from an exception that ends every
  command into a skip that logs one ERROR line in the form given in
  `specs/001-standalone-docker-provider/contracts/commands.md`.
- [X] T073 [US4] Report silent replacements of enrollment kinds and
  field kinds (`packages/contract/src/cs_image_system/contract/enrollment.py`
  line 54, `field_kinds.py` line 93) as collisions that skip both
  plugins. Prefer detecting them in the loader, by comparing those
  registries before and after each plugin loads. If the contract
  package itself has to change, raise its version in the same task,
  update every range on it, and record that here and in plan.md, whose
  constraint "the contract does not change" then no longer holds.
- [X] T074 [US4] In
  `packages/engine/src/cs_image_system/engine/loader.py` (lines 203 to
  206), treat two entry points with one name in one group as a
  collision: both skipped, one line naming both distributions.
- [X] T075 [US4] Treat a registry key claimed by two plugins with
  different classes as a collision, in
  `packages/base/src/cs_image_system/base/registry.py` (lines 436 to
  447 and 707 to 711) and where `load_plugins` replays registrations
  in `packages/engine/src/cs_image_system/engine/loader.py`: both
  plugins skipped, neither registered, one line naming both. The same
  class registered by several plugins stays allowed.
- [X] T076 [US4] Guard the commands entry points in
  `packages/system/src/cs_image_system/system/cli.py` (line 1585, run
  at import from line 1656): one that fails to load is skipped with
  one ERROR line and `--help` still works; two plugins mounting a
  different command under one name (lines 1640 to 1643) are both
  skipped and named.
- [X] T077 [US4] Report bootstrap collisions in
  `packages/engine/src/cs_image_system/engine/bootstrap/sections.py`
  (line 34: a section name claimed twice skips both) and in
  `packages/engine/src/cs_image_system/engine/bootstrap/hcl.py` (lines
  79 to 87: two sections that declare one provider differently is an
  error naming both, not last-one-wins).
- [X] T078 [US4] In
  `packages/base/src/cs_image_system/base/image_sources.py` (lines 148
  to 179), make an image-source block for a runtime type that another
  plugin registers a collision naming both, in place of the WARNING
  and first-by-name rule.
- [X] T079 [US4] Make validation say the truth about a skipped plugin:
  when a configuration uses a word that an unusable plugin would have
  registered, `packages/engine/src/cs_image_system/engine/commands/load_failures.py`
  (lines 87 to 91) prints ` - <kind> type '<word>' is registered by
  <plugin>, which is installed but could not be used: <cause>` and not
  the "install the extra" advice of
  `src/cs_image_system/extras.py`, which stays for a plugin that
  really is absent.
- [X] T080 [US4] Ask what is declared, not what is installed: failure
  classification in
  `packages/engine/src/cs_image_system/engine/commands/load_failures.py`
  (lines 68 to 76) and credential prefixes in
  `packages/engine/src/cs_image_system/engine/commands/preflight.py`
  (lines 118 to 133) consult only the classes the configuration
  declares.
- [X] T081 [US4] Scope the provider agreement check in
  `packages/hashicorp-utils/src/cs_image_system/hashicorp_utils/collector.py`
  (`validate_all`, lines 428 to 438, and its callers at lines 443,
  494, 506, 549; the Packer equivalent near lines 636 to 642): when a
  root is emitted, check only the providers that root declares,
  against the other roots that declare the same ones, and name the
  provider and every root in the disagreement. Test it in
  `packages/hashicorp-utils/tests/test_agreement_is_scoped.py`: two
  roots that disagree on a provider a third root does not declare
  leave the third root's emission working.
- [X] T082 [US4] Namespace `plugin_state` keys in
  `packages/base/src/cs_image_system/base/run_context.py` (lines 421
  to 429) so two plugins using one key string hold separate state, and
  update its callers.
- [X] T083 [US4] Create the isolation assertion in
  `packages/system/src/cs_image_system/system/testing/isolation.py`: a
  context manager that fails, naming what changed, if the process
  environment, the working directory, `sys.path`, or the root logger's
  level and handlers differ on exit, or if the kit's opened-secret
  store lost an entry. Use it around a load and a dry run in
  `packages/docker-plugin/tests/pipeline/test_leaves_the_process_alone.py`.
- [X] T084 [US4] Test every skip and collision in
  `packages/engine/tests/test_unusable_plugins.py`, with entry points
  supplied by the test: a plugin that fails to import; one refused for
  each of namespace, conformance and group; a broken commands entry
  point; and a collision on each of a type, a command, a bootstrap
  section, an entry-point name, an enrollment kind, a field kind and
  an image-source block. Each asserts the plugin or pair is skipped,
  the one line names it, a configuration that does not use it loads,
  and a configuration that uses it fails validation with the cause.
- [X] T085 [US4] Prove SC-006 in
  `packages/docker-plugin/tests/pipeline/test_broken_neighbour.py`:
  with a deliberately broken extra plugin supplied as an entry point,
  the family's fixture validates and completes a dry run, and the
  emission equals the family's golden.
- [X] T086 [US4] Hold the two channels that already behave correctly,
  adding a test only where none exists: two distributions shipping a
  Terraform module directory of one name
  (`packages/engine/src/cs_image_system/engine/modules.py` lines 102
  to 106) in `packages/engine/tests/test_modules_collision.py`; and
  two plugins claiming one bare `type:` word, which
  `tests/test_registration_namespaces.py` already covers.
- [X] T087 [US4] Checkpoint: `just test`, `just test-core` and
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

- [X] T088 Add an install-check mode to `scripts/isolated-run`: install
  `cs-image-system[docker]` at the workspace version from the built
  wheels into an empty environment that holds nothing else; render the
  starter with the installed command
  (`cs-image-system init-config <dir> --from standard-docker`); run
  `validate`, then a dry `run --all`; report each of the three as ran
  and succeeded, ran and failed, or did not run; exit non-zero unless
  all three ran and succeeded. With `keep=<directory>`, leave the
  emitted `generated` tree there.
- [X] T089 Extend `tests/test_isolated_run.py` for that mode with a
  stubbed shell: a failed install fails the run and reports the
  validation and the dry run as not run; a failed validation reports
  the dry run as not run; all three succeeding passes.
- [X] T090 Add the recipe `test-docker-install` to `Justfile`. Add it
  to `full-test-legs` as a leg that fails, and does not skip, when the
  container daemon does not answer. Add the job `docker-install` to
  `.github/workflows/ci.yml` running `just test-docker-install`, and
  update `tests/test_ci_workflow.py` and
  `tests/test_justfile_contract.py`.
- [X] T091 Checkpoint, on a machine with a container daemon:
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

- [X] T092 [US5] Write `docs/WRITING_A_PROVIDER.md`, each point
  answered once with the docker family as the example: what a provider
  is made of; what it may import (the contract and the declared SDK
  surfaces) and how to check it; how it declares the kit and the
  Terraform libraries by range and what the version rule means for it;
  where its tests, fixture, golden, stubs and Terraform modules live;
  how to run its tests alone with `just test-docker-alone`; what the
  test kit gives it; and how a plugin that cannot be used shows itself
  to an operator. Finish the testing and dependency sections of
  `packages/docker-plugin/README.md` by linking to it.
- [X] T093 [P] [US5] Correct `docs/PLUGINS.md`: the "contract alone"
  statements (lines 27, 28, 60, 196), the shared-version statements
  (lines 10, 19 to 21), the two docker packages wherever listed, the
  counts (lines 3, 31) deleted, and its how-to reduced to a link to
  the guide.
- [X] T094 [P] [US5] Correct `docs/OPERATIONS.md`: "Writing a plugin"
  (lines 2608 to 2654) reduced to a link to the guide; the
  shared-version statements (lines 2455 to 2459, 2469); the counts
  (lines 2386, 2451 to 2471, 2544) deleted.
- [X] T095 [P] [US5] Correct the other documents: `README.md` (lines
  58, 60, 67, 69, 76, 115), `GOALS.md` (line 24), `docs/DESIGN.md`
  (line 24), `docs/DESCRIPTION.md` (line 114), `docs/DAILY_DRIVER.md`
  (lines 1231, 1291, 1408), `docs/PARITY.md` (line 55), and
  `GOLDEN.md` (line 75, and its per-lifecycle table deleted).
- [X] T096 [P] [US5] Correct the package READMEs:
  `packages/contract/README.md` (lines 3, 135, 173 to 181, 240, and
  "Writing a plugin" at 160 to 269 reduced to what is specific to the
  contract plus a link), `packages/base/README.md` (lines 3, 9 to 11,
  18 to 20), `packages/engine/README.md` (lines 45, 662 to 665),
  `packages/system/README.md` (line 12),
  `packages/hashicorp-utils/README.md` (lines 14, 26, 38, 392, 394),
  `packages/tofu-roots/README.md` (line 515) and
  `packages/dummy-plugin/README.md` (lines 17 to 20, which are already
  false, and 263 to 288).
- [X] T097 [P] [US5] Correct the comments and docstrings:
  `pyproject.toml` (lines 16 to 20, 37 to 38, 143),
  `tests/fixtures/config/README.md` (lines 13 to 18, prose only: no
  fixture file changes), and the module docstrings of
  `tests/test_package_metadata.py` and
  `tests/test_contract_version.py`.
- [X] T107 [US5] Correct the statements Phase 7 made false, found
  after this list was written (the contract's README among them, so
  the contract's version rises once more, with every range on it, in
  this task). A plugin that is refused is now skipped and named, not
  the end of every command: `docs/PLUGINS.md` (line 83, and "a
  packaging error" at line 259), `docs/OPERATIONS.md` (line 2668),
  `packages/contract/README.md` (lines 84, 225, 367 to 368, 384, 394),
  `packages/base/README.md` (lines 132, 292) and
  `packages/engine/README.md` (line 1144). Emission checks provider
  agreement per root with `validate_for`, not run-wide with
  `validate_all`: `packages/hashicorp-utils/README.md` (lines 137,
  286, 513), `packages/gcs-state-plugin/README.md` (line 316) and
  `packages/tf-s3-state-plugin/README.md` (line 639). Credential
  prefixes and failure classification ask the declared classes:
  `packages/engine/README.md` (line 739). The two docstrings in the
  contract that say a second registration replaces the first
  (`enrollment.py` line 52, `field_kinds.py` line 92) now describe
  what the loader reports as a collision.
- [X] T098 [US5] Run the documentation tests with `just test-one` on
  `tests/test_docs_contract.py`, `tests/test_docs_parity.py`,
  `tests/test_docs_examples.py` and
  `tests/test_sources_do_not_narrate.py`, then the search of
  quickstart step 8, which must print only `searched`.

**Checkpoint**: all five stories pass on their own.

---

## Phase 10: Polish and proof

**Purpose**: what crosses stories, and the acceptance run.

- [X] T099 Give every new file its licence information: an SPDX header
  on each new source and script, and `REUSE.toml` entries for
  `packages/docker-plugin/tests/fixture/**`,
  `packages/docker-plugin/tests/golden/**`,
  `packages/system/tests/core_fixture/**`,
  `packages/system/tests/core_golden/**` and the three
  `surface-baseline.txt` files, none of which may carry a header. Then
  run `just headers`.
- [X] T100 Run `just public-safe`. The new fixtures hold only the
  synthetic personas and the test identity.
- [X] T101 Measure the budget and write the actual figures beside the
  expected ones in the Budget table of
  `specs/001-standalone-docker-provider/plan.md`: source lines, test
  lines, workspace packages, contract protocol members, tests, golden
  files, repository-wide checks. Any figure outside its expected range
  gets its reason written there.
- [X] T102 Walk steps 1 to 6 and step 8 of
  `specs/001-standalone-docker-provider/quickstart.md` and record each
  result.
- [X] T103 Prove FR-022 with step 7 of
  `specs/001-standalone-docker-provider/quickstart.md`:
  `just cli config-drift` exits with the status T003 recorded, and the
  `standard-docker` emission from the commit the branch started at
  equals the one `just test-docker-install keep=…` leaves, both made
  the same day.
- [X] T104 Run `just full-test` (quickstart step 9). A leg that fails
  for an expired session or an unreachable service is reported as
  environmental, apart from a code failure.
- [X] T105 Bring the specification's own files up to date: the status
  line of `specs/001-standalone-docker-provider/spec.md`; the note in
  `specs/001-standalone-docker-provider/checklists/requirements.md`
  that still says two planning choices are "bounded by FR-024"; and
  the row for 001 in `specs/README.md`.
- [X] T106 Report to the operator what the first release after this
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
