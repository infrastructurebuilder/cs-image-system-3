---

description: "Task list for spec 005: the Google Cloud provider in a repository of its own"
---

# Tasks: The Google Cloud provider in a repository of its own

**Input**: Design documents from `specs/005-relocate-gcp-provider/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/family-repository.md](contracts/family-repository.md),
[contracts/test-kit-strict.md](contracts/test-kit-strict.md),
[quickstart.md](quickstart.md)

**Tests**: requested. Every story ends in a command that passes or
fails (Constitution II); the moved and re-hosted tests keep what they
assert, and the strict session and the starter selection get tests of
their own.

**Organization**: tasks are grouped by user story. The plan's four
phases (research R1) map onto them: phase 1 (prepare here) is Phase 2
below; phase 2 (stand alone there) is US1; phase 3 (remove here) is US2
with US3's proofs; phase 4 (the reference) is in Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US4)

## Working rules

- Three repositories. `HERE` is
  `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`, on
  `feature/005-relocate-gcp-provider`. `THERE` is
  `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-google-cloud`, on a
  branch `feature/005-relocate-gcp-provider` from its `develop`. `REF`
  is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig`,
  whose `develop` is caught up first (`git fetch && git merge --ff-only
  origin/main`) and never `main`.
- Run Python as `uv run --no-sync python`; iterate with `just test-one
  <paths>`; the bar is `just test` at every checkpoint, in the
  repository the checkpoint names.
- **The shared golden is the tripwire until T052.** Before T052,
  `git status --short tests/fixtures` in HERE must print nothing after
  any task. From T052 on, every golden change is read file by file and
  recorded (Constitution IV).
- **Releases are the operator's** (research R2). A task marked
  **RELEASE** stops: it records what the release must carry and waits
  for the operator to cut it. Nothing is pushed, published or merged
  without the operator's word.
- **No Google Cloud spending.** No task runs a live cycle; the live
  tests in THERE run only if the operator decides (T068).
- A new file in a new folder needs `git add -N` before `just lint`.
- Never stage a file this feature did not change, in any repository.

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |

---

## Phase 1: Setup

**Purpose**: the before-state the budget, the golden comparison and the
proofs compare with.

- [ ] T001 Record HERE's `just test` before any change in the Records table of `specs/005-relocate-gcp-provider/tasks.md`: take it from the CI proof of `develop` at `f3c7472e` (both workflows passed on 2026-11-18) and the local bar of spec 004's T035, since the branch differs from it only in specification files; if it differs, run `just test`
- [ ] T002 [P] Record the budget's before-figures with the plan's method (source lines 57,214; test lines 48,141; tests 2,093; golden files 148; workspace packages 22) and the family's own (3,030 source lines; 26 package tests in 472 lines) in the Records table
- [ ] T003 [P] Keep the shared golden before the move as the comparison's left side: copy `tests/fixtures/golden` and `tests/fixtures/config` at `c273d854` to the scratchpad directory, and record the copy's path and `git rev-parse HEAD:tests/fixtures/golden` in the Records table (research R7)

---

## Phase 2: Foundational (prepare here, then release)

**Purpose**: the family ready to leave while still in HERE, and the SDK
and test kit it will range on published. Blocks every story.

- [ ] T004 [P] Write the strict session's tests in `packages/system/tests/test_strict_session.py` (new; `git add -N`): with `pytester`, a session that collects nothing fails with exit status 1; one that skips a test fails; one that passes everything passes; one that fails already fails without a second cause (contracts/test-kit-strict.md)
- [ ] T005 Add the strict session as `packages/system/src/cs_image_system/system/testing/strict.py` (new): a pytest plugin whose `pytest_sessionfinish` sets exit status 1 with the line `strict: no test was collected; the tests did not run` or `strict: <n> skipped; a skipped check is a failed check`, and a function `verdict(collected, skipped, failed)` that both the plugin and `scripts/isolated-run` use; export it from `packages/system/src/cs_image_system/system/testing/__init__.py`
- [ ] T006 Make `scripts/isolated-run` take its verdict from `cs_image_system.system.testing.strict.verdict` instead of its own `verdict` (lines 198-209), keeping its messages; run `just test-core test-docker-alone`
- [ ] T007 [P] Turn the family's exact SDK pins into ranges: `packages/gcloud-runtime-plugin/pyproject.toml` (`cs-image-system-base>=0.2,<0.3`, `cs-image-system-hashicorp-utils>=0.2,<0.3`), `packages/tf-gcp-plugin/pyproject.toml` (the same, and `cs-image-system-tofu-roots>=0.2,<0.3`), `packages/gcs-state-plugin/pyproject.toml` (`cs-image-system-base>=0.2,<0.3`); `uv lock`; `just init` (data-model.md: "Ranges only")
- [ ] T008 Move the Google Cloud stubs out of `tests/harness.py` (`_clouds()`, lines 183-232: the network map from the fixture's `gcloud` runtimes, `query_provider_image`, `query_images`, `run_session_command`, `retag_image`) into `packages/gcloud-runtime-plugin/src/cs_image_system/gcloud_runtime/testing.py` (new) as `stub(monkeypatch, ...)` in the shape of `cs_image_system.docker_runtime.testing.stub`; `tests/harness.py` calls it among its stubs, unchanged in behaviour (research R6)
- [ ] T009 [P] Move `stub_networks_from` (`tests/test_docs_examples.py`, lines 95-128) onto `cs_image_system.gcloud_runtime.testing`, and point its three users (`tests/test_a_load_enters_every_child_under_its_own_key.py`, `tests/test_registry_index_holds_current_ids_after_a_load.py`, `tests/test_bake_steps.py:364`) at the harness or the stub
- [ ] T010 [P] Move the helpers other test files import from Google Cloud test modules to where their users are: `private_plugin_cache` (`tests/test_gcp_runtime.py:451`, used by `test_bootstrap.py`, `test_bootstrap_aws.py`, `test_bootstrap_gcp.py`) into `tests/harness.py`; `_facts`, `_project`, `_tree` (`tests/test_bootstrap_gcp.py`, used by `test_bootstrap_coverage.py:189-190`) beside their user; `GCE_RT` and `_seed_converged` (`tests/test_convergent_bakes.py`, used by `test_bake_fingerprints.py:26-27`) beside their user; `prepared` and `_declare_ephemeral` (`tests/test_ephemeral.py`, used by `test_mount_verification.py:18`, `test_instance_roots.py:76`) beside their users (research R9)
- [ ] T011 [P] Make `packages/gcs-state-plugin/tests/test_gcs_backend.py` (lines 44-45) stop importing `tf_s3_state_plugin`, keeping what it asserts of the gcs backend; `local_state_plugin`, a core plugin, may stay
- [ ] T012 [P] Make `packages/tf-gcp-plugin/tests/test_gcp_only_storage.py` drive its run through the test kit (`kit.Run` with the family's stub) instead of `from harness import FixtureRun, copy_config`, against the shared fixture for now
- [ ] T013 Give each of the three packages a `[project.optional-dependencies] test` extra naming `cs-image-system-system[testing]` and the core plugins its tests need, and a `[tool.pytest.ini_options]` with its own `testpaths` and `--import-mode=importlib`, in the shape of `packages/docker-plugin/pyproject.toml` lines 26-43 and 76-78
- [ ] T014 Add to each of the three packages a surface self-check test (`tests/test_keeps_to_the_surface.py`, in the shape of `packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py`), with `own` naming its own import package and `family` naming `cs_image_system.gcloud_runtime` for `tf-gcp-plugin`; any finding is fixed in the package's source
- [ ] T015 Checkpoint: `just test` passes in HERE, the isolated runs each with `0 skipped`; `git status --short tests/fixtures` prints nothing; record it
- [ ] T016 **RELEASE** (the operator's; research R1, R2): HERE's next release publishes the contract 0.5.0, the kit 0.2.0, both Terraform libraries 0.2.0, `cs-image-system-docker-plugin` and the test kit with `strict`, with the family still inside on the workspace's number. Record in the Records table what it must carry and, once cut, its version and the index's answer for each SDK name; stop until it exists

**Checkpoint**: the SDK and the test kit are on the index; the family
ranges on them and keeps to their surfaces.

---

## Phase 3: User Story 1 - The family builds, tests and releases from its own repository (Priority: P1) 🎯 MVP

**Goal**: a fresh clone of THERE passes its bar against published
releases, with nothing skipped, and releases the family on its own.

**Independent Test**: quickstart steps 1 and 2.

### History and layout

- [ ] T017 [US1] In THERE, start `feature/005-relocate-gcp-provider` from `develop` (`ddb3533`); set aside the unpushed local `master` (`38c4bf5`) and the uncommitted `pyproject.toml` and `README.md` change as the operator's draft (copies in the scratchpad directory, nothing deleted), and record what each held (research R4)
- [ ] T018 [US1] In a fresh clone of HERE at T016's release commit, run `git filter-repo` keeping `packages/gcloud-runtime-plugin`, `packages/tf-gcp-plugin`, `packages/gcs-state-plugin`, `tests/test_gcp_runtime.py`, `tests/test_gce_cycle.py`, `tests/test_bootstrap_gcp.py`, `tests/test_mount_verification.py`, renaming the four test files under `tests/pipeline/`; merge the result into THERE's branch with `--allow-unrelated-histories`; record the filtered history's commit count and tip
- [ ] T019 [US1] Write THERE's `pyproject.toml` (the workspace of `packages/*`, no published umbrella, the dev group: pytest, ruff, pyright, reuse, bump-my-version; `[tool.uv.sources]` for the three packages only, never a path into HERE; the pytest and pyright settings for `packages/*/src`, `packages/*/tests` and `tests`, with `-p cs_image_system.system.testing.strict`), its `REUSE.toml`, `.gitignore` (from the operator's draft) and a family version line at 0.2.0 in all three manifests with `tf-gcp-plugin` pinning `cs-image-system-gcloud-runtime-plugin==0.2.0` (data-model.md: "one number for all three, on the family's own line from 0.2.0"; research R8)
- [ ] T020 [US1] Write THERE's `Justfile` with the five lifecycle targets as contracts/family-repository.md states them, plus `golden-regen`, `surface-check` (each package's self-check) and `public-safe`; `just init` resolves from the index alone

### The family's suite

- [ ] T021 [US1] Build THERE's fixture `tests/fixture/` from the Google Cloud declarations of T003's copy (research R7: `cfg/state-gcm.yml`, `storages/gce.yaml`, the three `overlays/gce-cycle-*`, and the GCP blocks of `cfg/runtime-builders.yml`, `image-builders.yml`, `instance-builders.yml`, `storage-builders.yml`, `os-builders.yml`, `executables.yml`, `base_images/base-images1.yaml`, `images/image1.yaml`, `instances/instances.yaml`), plus the core declarations they need (groups, users, the packer, ansible and default-os builders); bind every GCE root to the `gcs` backend instead of S3 (the operator's decision of 2026-11-19); copy the fixture's `.age-identity` handling from `packages/docker-plugin/tests/fixture`
- [ ] T022 [US1] Write `tests/pipeline/conftest.py` in THERE in the shape of `packages/docker-plugin/tests/pipeline/conftest.py`: `FIXTURE`, `GOLDEN`, `STUBS = (gcloud_testing.stub, roots_testing.stub)`, the `family_run`, `family_stubs` and `family_root` fixtures, the autouse logging isolation
- [ ] T023 [US1] Make the four moved tests (`tests/pipeline/test_gcp_runtime.py`, `test_gce_cycle.py`, `test_bootstrap_gcp.py`, `test_mount_verification.py`) run on the family's conftest and the test kit instead of HERE's `tests/harness.py`, keeping every assertion; `test_gce_cycle.py`'s `test_an_overlay_can_undeclare_a_tree_entry_for_one_invocation` stays with them (it is proven here too, by T046)
- [ ] T024 [US1] Carry to `tests/pipeline/` in THERE the Google Cloud cases of HERE's mixed and re-hosted files that prove the family's own behaviour, one test file per HERE file it came from, each named in the Records table with what it asserts: the GCE-specific ephemeral case (serial console) of `test_ephemeral.py`; the IAP case of `test_posix_identity.py`; the GCE cases of `test_power_state.py`, `test_state_query.py`, `test_configuration_ownership.py`; the three PD archive cases of `test_storage_semantics.py`; the gcs case of `test_state_locations.py`; the two relabel cases of `test_aws_parity.py`; `GCPCLIVersionChecker` of `test_version_checks.py`; the `gcp-service-account` secret pattern of `test_public_safe.py`; the gcloud rows of `test_image_sources.py` and `test_docs_image_sources.py`; the `tf-gcp` namespace of `test_registration_namespaces.py` (FR-004)
- [ ] T025 [US1] Add `tests/pipeline/test_golden.py` and `tests/regen_golden.py` to THERE in the shape of docker's (`kit.Run(...).run("all", apply=True)`, `kit.assert_matches(GOLDEN, kit.emitted(...), regenerate_with="just golden-regen")`), and generate `tests/golden/` once with `just golden-regen`
- [ ] T026 [US1] Compare THERE's golden with T003's copy, file by file: each of the 31 files under `generated/base-image/pckr-gce-ans`, `generated/instance-image/pckr-gce-ans`, `generated/instance-image/tofu-gce`, `generated/storage/gcp-gcs`, `generated/storage/gcp-pd` with the file of the same path, and the GCE lines of the 6 shared files (`generated/base-image/run-base-image.sh`, `generated/instance-image/run-instance-image.sh`, `generated/storage/run-storage.sh`, `meta-state/launch-params.yaml`, `meta-state/storage.yaml`, `meta-state/state-locations.yaml`) with the family's; read every difference; each must follow from the `gcs` backend (a root's backend block, its `state-locations` entry); record every file's result in the Records table; any other difference is a defect to fix, not to accept (research R7; SC-005)
- [ ] T027 [P] [US1] Add `tests/pipeline/test_broken_neighbour.py` and `tests/pipeline/test_leaves_the_process_alone.py` to THERE in the shape of docker's (the kit's `broken_neighbour` and isolation helpers)
- [ ] T028 [P] [US1] Add `tests/pipeline/test_qualified_words.py` to THERE: a configuration that writes `gcloud-runtime/gcloud`, `tf-gcp/tofu-gce` and `gcs-state/gcs` loads, and so does one that writes them bare (spec story 3, scenario 2)
- [ ] T029 [P] [US1] Add `tests/live/` to THERE with the cycle tests that need a Google Cloud session, excluded from `testpaths`, and a `just test-live` recipe that fails, never skips, without a session; it is not part of `just test` or `just full-test`

### Its bar, its documents, its CI

- [ ] T030 [US1] Make THERE's `just test` pass: lint, type check at zero errors, each package's self-check, the unit and pipeline tests and the golden, under the strict session; record the counts
- [ ] T031 [US1] Add THERE's `full-test` legs: the low end of the SDK ranges (`uv sync --resolution lowest-direct`, then the unit tests and self-checks, as docker's low end), and `standard-gce` and `complete` rendered with `init-config`, validated and dry-run with the system and the AWS and docker families from the index and the family from the checkout (research R11; spec story 3, scenario 4); a leg whose tool is absent fails
- [ ] T032 [P] [US1] Correct the three moved READMEs (`packages/*/README.md` in THERE): every relative link into HERE (`../../tests`, `../../docs`, `../<package>` outside the family) points to THERE's own file or to HERE by URL at `develop`; the install section says `uv tool install 'cs-image-system[gcloud]'` and links HERE's operations guide
- [ ] T033 [P] [US1] Move the field tables of the `gcloud` runtime (HERE `docs/CONFIGURATION.md` §4.4) and the `gcs` backend (§`gcs`) into THERE's `docs/CONFIGURATION.md`, the one source from now (Constitution VIII); HERE's sections are replaced by T060
- [ ] T034 [P] [US1] Write THERE's `README.md` (what the family is, how an operator installs it, how a plugin author builds and tests it, where its documents are), replacing "not yet implemented"
- [ ] T035 [US1] Add THERE's `.github/workflows/ci.yml`: on push to `develop` and every pull request, a fresh `ubuntu-latest` runner, `astral-sh/setup-uv`, OpenTofu with `tofu_wrapper: false`, `just init`, `just test`, `just public-safe`; the live tests only by `workflow_dispatch` with the operator's GCP identity (contracts/family-repository.md)
- [ ] T036 [US1] Add THERE's `release` target: moves the family's one number in the three manifests, runs `just full-test`, builds the three wheels, refuses a version the index ever held for any of the three names, and publishes them together to the index named; test its refusal in `tests/test_release_refuses_a_held_version.py` against a stubbed index answer (FR-010)
- [ ] T037 [US1] Checkpoint: quickstart steps 1 and 2 pass from a fresh clone of THERE's branch pushed to the remote (the operator's word to push); record each leg
- [ ] T038 [US1] **RELEASE** (the operator's): merge THERE's branch into its `develop` (squash, branch kept) and cut the family's 0.2.0 to TestPyPI, then PyPI; record the version and the index's answer for the three names; stop until it exists

**Checkpoint**: the family exists on the index at 0.2.0, released from
its own repository.

---

## Phase 4: User Story 2 - This repository no longer holds the family (Priority: P2)

**Goal**: HERE's bar passes with no Google Cloud package, tool or
identity, and nothing here imports the family.

**Independent Test**: quickstart steps 3 and 4.

### Tests re-hosted and trimmed

- [ ] T039 [US2] Re-host on the shared fixture's AWS runtime the core behaviours these files prove through GCE, keeping what each asserts (research R9): `tests/test_convergent_bakes.py`, `test_bake_fingerprints.py`, `test_bake_selection.py`, `test_decommission.py`, `test_detach.py`, `test_ephemeral.py` (its serial-console case went to THERE in T024), `test_retention.py`, `test_post_bake_tests.py`, `test_runtime_facts.py`, `test_ci_perform.py`, `test_vendor_images.py`; where a behaviour is a container's, docker; record each file's vehicle in the Records table
- [ ] T040 [US2] Re-host `tests/test_nested_run_in_this_process.py` (GCE as the ephemeral runtime, `gcp-pd` scratch storage) and `tests/test_two_runs_in_one_process_share_nothing.py` (the `gce-cycle-decommission.yaml` overlay, its comparison with the golden at line 204) on AWS, with an AWS overlay in `tests/fixtures/config/overlays/` in place of the GCE one
- [ ] T041 [US2] Remove the Google Cloud cases T024 carried to THERE from the mixed files they came from, and the Google Cloud part of every other mixed file (research R9's 50: among them `test_extras.py` lines 39-40 and 185-228, `test_package_metadata.py` lines 64-65 and 319, `test_docs_examples.py` `PLUGIN_TYPES` lines 56-70, `test_module_sources.py` line 30, `test_neutral_tofu_root.py` line 113 and `ROOTS`, `test_import_closure.py` line 46, `test_docs_parity.py` lines 45-47, `test_contract.py` lines 506 and 511, `test_bootstrap_docker.py` line 59, `test_bootstrap_okta.py` line 84, `test_workflow_names.py` lines 35-36), keeping each file's other assertions; a case dropped without a home in THERE is named in the Records table with its reason
- [ ] T042 [P] [US2] Correct the passing mentions (research R9's 14 files) where they become false; the guard regex of `tests/test_core_names_no_runtime.py` stays (research R13)
- [ ] T043 [P] [US2] Write `tests/test_starters_by_declaration.py`: the set of starters this workspace's tests render is the set whose declared `type:` words the installed plugins register, by the rule of `src/cs_image_system/extras.py`; with the family absent it excludes `standard-gce` and `complete` and includes the rest; nothing is skipped (research R11)
- [ ] T044 [US2] Make the starter-rendering tests (`tests/starter_support.py` and its users: `test_changes_since.py`, `test_starter_recipes.py`, `test_starter_tree.py`, `test_release_version.py`, `test_workload_probe.py`, `test_starter_skeleton.py`, `test_bootstrap.py` `TREES`, `test_ci_runner.py`, `test_committed_files.py` `TREES_WITH_OPA`, `test_bootstrap_aws.py:111`) take their starters from T043's selection, not a list that names `standard-gce` or `complete`

### The shared suite, the packages, the manifests

- [ ] T045 [US2] Remove the Google Cloud declarations from `tests/fixtures/config` (research R7's five whole files and the GCP blocks of eleven mixed files, and the fixture's README lines 10-11 and 33 and `overlays/README.md` lines 15-23)
- [ ] T046 [US2] Keep the overlay behaviour `test_gce_cycle.py` proved here (`test_an_overlay_can_undeclare_a_tree_entry_for_one_invocation`): a test of the same behaviour on an AWS overlay in `tests/test_overlays.py` (new, or the existing overlay test file if one holds it)
- [ ] T047 [US2] Remove the Google Cloud stubs from `tests/harness.py` (T008's call, `record_network_facts`' `"gcloud"`, the docstrings at lines 12, 23, 104-109, 122) and `cs_image_system.gcloud_runtime` from every remaining test import
- [ ] T048 [US2] Remove `packages/gcloud-runtime-plugin`, `packages/tf-gcp-plugin` and `packages/gcs-state-plugin` from HERE (`git rm -r`)
- [ ] T049 [US2] Correct the root `pyproject.toml`: the `gcloud` and `all` extras name the three by `>=0.2,<0.3` (research R8; the operator's answer: kept, by a range); remove their `[tool.uv.sources]` entries (lines 109, 115, 121), `testpaths` (203, 207, 212), `pythonpath` (233, 238, 241), pyright `extraPaths` (328, 329, 337); the description (line 8) keeps naming GCE as a target; `uv lock`; `just init`
- [ ] T050 [P] [US2] Correct `.vscode/settings.json` (lines 16, 17, 25) to match the pyright `extraPaths` (held equal by `tests/test_editor_paths.py`)
- [ ] T051 [P] [US2] Remove the Google Cloud identity from HERE's live jobs: `.github/workflows/ci.yml` (the `GCP_WORKLOAD_IDENTITY_PROVIDER`/`GCP_SERVICE_ACCOUNT` gate at lines 194-195, 207, 212; the step at 246-251) and `.github/workflows/ci-from-scratch.yml` (77-78, 90, 95; 129-134; `gcloud` in the tool list at 154-160); `fixture-live` in `Justfile` (lines 688-722) needs no GCP session; the `publish-starters` CI step installs `cs-image-system[gcloud]` from the index before it writes the starters (research R11, R12)
- [ ] T052 [US2] Regenerate the shared golden (`just golden-regen shared`) and read every change file by file against T003's copy: exactly the 31 GCE files gone and the GCE lines gone from the 6 shared files, nothing else; record each in the Records table (research R10; Constitution IV)
- [ ] T053 [US2] Checkpoint: quickstart steps 3 and 4 pass; `just test` passes with the isolated runs each `0 skipped`; `uv pip list` in HERE's environment names none of the three; record it

**Checkpoint**: HERE holds no Google Cloud code and passes without it.

---

## Phase 5: User Story 3 - An operator sees no difference (Priority: P3)

**Goal**: with the family installed from its release, every command
behaves and emits as before.

**Independent Test**: quickstart step 5, and the family's starter legs
(T031).

- [ ] T054 [US3] Test in `tests/test_extras.py` that the `gcloud` and `all` extras name the three distributions by `>=0.2,<0.3`, and that a release bump moves no range (the bump's `=={current_version}` rule); and in `tests/test_package_metadata.py` that no workspace manifest names the three by an exact pin
- [ ] T055 [US3] Test in `tests/test_load_failures.py` (or the file that holds the absent-plugin message today) that a configuration naming `type: gcloud` with the family not installed is told the runtime is not installed and which extra installs it (spec story 3, scenario 3; FR-013), on a fixture of its own under `tests/fixtures/`
- [ ] T056 [US3] With the family at 0.2.0 on the index (T038), install `cs-image-system[gcloud]` from HERE's built wheels with the family from the index into an empty environment, and render, validate and dry-run `standard-gce` (the install check of `scripts/isolated-run --install-check`, with the family allowed from the index); record it

---

## Phase 6: User Story 4 - Each repository releases on its own (Priority: P4)

**Goal**: neither repository's release builds, tests or publishes the
other's packages.

**Independent Test**: quickstart step 4 here; T036 there.

- [ ] T057 [US4] Test in `tests/test_release_whole.py` that the set of distributions `scripts/release.py` publishes (`published_members`) and `scripts/publish-target-ready` probes holds none of the three, and that `just build` writes no wheel for them (quickstart step 4; FR-011)
- [ ] T058 [US4] Make a release here refuse when the `gcloud` extra's range is satisfied by no published family release (a probe in `scripts/release.py` beside the existing ones, tested in `tests/test_release_probes.py`), so the umbrella never names a family that is not on the index (spec story 4, scenario 1)

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T059 [P] Correct HERE's `README.md` (lines 7, 63, 88-89, 107-108, 111-112, 138), `docs/PLUGINS.md` (11, 57, 66, 70, 86-89, 121, 128, 169), `docs/DESCRIPTION.md`, `docs/DESIGN.md` (links) and `GOLDEN.md`: the family lives in THERE, is installed by the `gcloud` extra, and the shared golden holds AWS and docker
- [ ] T060 [P] Correct `docs/CONFIGURATION.md`: §4.4 `gcloud` and §`gcs` keep a short description and link THERE's tables (T033); the links at lines 362, 857, 1257, 1311, 1558 point to THERE
- [ ] T061 [P] Correct `docs/DAILY_DRIVER.md` (97, 112, the GCP prerequisites, 467-497, 1179, 1313-1319, 1384-1401) and `docs/OPERATIONS.md` (2495, 2512 and every link into the family's files): installing the family is stated once, in the operations guide, and linked from the others (FR-009)
- [ ] T062 [P] Point the links of `docs/CHANGES.md` and `docs/INCIDENTS.md` into the family's files at THERE, changing no other word (research R13)
- [ ] T063 [P] Correct the other packages' READMEs that name the family as a neighbour: `packages/base/README.md` (1348-1355), `packages/tofu-roots/README.md` (24, 263, 545, 569), `packages/tf-s3-state-plugin/README.md` (181, 714-717), `packages/tf-ebs-instance-plugin/README.md` (31, 1340), `packages/hashicorp-utils/README.md` (29-35), `packages/aws-runtime-plugin/README.md` (1128), `packages/default-os-plugin/README.md` (438, 665), `packages/packer-plugin/README.md` (475, 912), `packages/system/README.md` (264, 1323)
- [ ] T064 [P] Add a note to spec 001 where it says the move is a later specification (`specs/001-standalone-docker-provider/spec.md` FR-024 and the Google Cloud line near 461-465) pointing to `specs/005-relocate-gcp-provider`, without rewriting it
- [ ] T065 Measure the budget again with T002's method and write the actual figures beside the expected ones in the Budget table of `specs/005-relocate-gcp-provider/plan.md`, with a reason for any figure outside its range
- [ ] T066 **RELEASE** (the operator's): HERE's release without the family (research R1, phase 3); T058's probe passes; record its version
- [ ] T067 In REF: take T066's release (`just take`), and run `just config-drift`; expect exit 0 with no change of the tree's own (quickstart step 5; SC-003); correct `CI_SETUP.md` (29-30, 49-62, 226-234) and `README.md` (38-40) where they say the family comes from HERE; record it
- [ ] T068 **YOUR DECISION** (the operator's; default: none): whether one live GCE cycle runs from THERE (`just test-live`) to prove the move; if it runs, record what it stood up and that it was torn down (SC-006; the Constitution's Google Cloud cost rule)
- [ ] T069 Walk `specs/005-relocate-gcp-provider/quickstart.md` steps 1 to 5 and record each result in the Records table
- [ ] T070 Bring the specification's files up to date: the status line of `specs/005-relocate-gcp-provider/spec.md`, and the row for 005 in `specs/README.md`

---

## Dependencies & Execution Order

- **Phase 1** first; T001 to T003 can run together.
- **Phase 2** blocks every story and ends in a release (T016): the
  family's tests in THERE need the SDK and the strict session on the
  index.
- **US1 (Phase 3)** after T016. It ends in the family's release (T038),
  which US2's extras (T049) and US3's install check (T056) name.
- **US2 (Phase 4)** after T038. Within it, the tests are re-hosted and
  trimmed (T039 to T044) before the fixture, harness and packages go
  (T045 to T048), and the golden is regenerated last (T052).
- **US3 (Phase 5)** with or after US2: T054 needs T049; T056 needs
  T038.
- **US4 (Phase 6)** after US2.
- **Phase 7** after US4; T066 before T067; T068 at any point after T038,
  only on the operator's word.

### Parallel opportunities

- T001, T002, T003.
- T004 with T007 (different packages); T009 to T012 (different files).
- T027, T028, T029 (new files in THERE); T032 to T034 (documents).
- T042, T043; T050, T051.
- T059 to T064 (different documents).

### Parallel example: Phase 2

```text
Task: T004 packages/system/tests/test_strict_session.py
Task: T007 the three packages' pyproject.toml
Task: T011 packages/gcs-state-plugin/tests/test_gcs_backend.py
Task: T012 packages/tf-gcp-plugin/tests/test_gcp_only_storage.py
```

### Parallel example: Polish

```text
Task: T059 README.md, docs/PLUGINS.md, docs/DESCRIPTION.md, docs/DESIGN.md, GOLDEN.md
Task: T060 docs/CONFIGURATION.md
Task: T061 docs/DAILY_DRIVER.md, docs/OPERATIONS.md
Task: T063 the other packages' READMEs
```

## Implementation Strategy

### MVP first

Phase 1, Phase 2 and its release, then US1 and the family's release:
the family stands alone and is on the index from its own repository
(quickstart steps 1 and 2). HERE still holds its copy until US2, so
nothing an operator uses changes before then.

### Incremental delivery

1. Phase 2 → T016: the SDK and the strict session published.
2. US1 → T038: the family released from THERE.
3. US2 with US3's tests → T053: HERE without the family.
4. US4, Polish → T066, T067: HERE released; the reference takes it.

### Notes

- **T018** carries history; run it in a fresh clone, never in HERE's
  working tree, which `git filter-repo` would rewrite.
- **T026 and T052** are the two golden readings; each records every
  file, and a difference that does not follow from the `gcs` backend
  (T026) or from the GCE declarations leaving (T052) is a defect.
- **T039 and T040** are the largest; each file keeps its assertions and
  changes its vehicle. Split them by file if they are delegated.
- Three tasks stop for a release (T016, T038, T066) and one for a
  decision (T068).
