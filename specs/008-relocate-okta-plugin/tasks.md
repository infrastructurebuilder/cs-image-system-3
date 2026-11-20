---

description: "Task list for spec 008: the Okta identity plugin in a repository of its own"
---

# Tasks: The Okta identity plugin in a repository of its own

**Input**: Design documents from `specs/008-relocate-okta-plugin/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/okta-repository.md](contracts/okta-repository.md),
[quickstart.md](quickstart.md)

**Tests**: requested. Every story ends in a command that passes or
fails (Constitution II); moved tests keep what they assert, and the
confinement of the AWS family to the instance suite (FR-004) gets a
test of its own.

**Organization**: by user story, on spec 005's four phases (research
R2): phase 1 (prepare here) is Phase 2 below; phase 2 (stand alone
there) is US1; phase 3 (remove here) is US2; phase 4 (the reference) is
in Polish.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US3)

## Working rules

- Three repositories. `HERE` is
  `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`, on
  `feature/008-relocate-okta-plugin`, started from `develop` after spec
  005 is merged. `OKTA` is
  `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-okta`, on a branch
  `feature/008-relocate-okta-plugin` from its local `develop`. `REF` is
  `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig`, whose
  `develop` is caught up first (`git fetch && git merge --ff-only
  origin/main`) and never `main`.
- **Nothing live is touched** (research R7). No task applies an
  identity root or calls the OPA team's API to change anything; no OPA
  group or user is ever destroyed. Never echo an Okta credential.
- Run Python as `uv run --no-sync python`; iterate with `just test-one
  <paths>`; the acceptance tests are `just test` at every checkpoint, in
  the repository the checkpoint names.
- **The shared golden is the tripwire until T044.** Before T044,
  `git status --short tests/fixtures` in HERE must print nothing after
  any task. From T044 on, every golden change is read file by file and
  recorded (Constitution IV).
- **Releases are the operator's.** A task marked **RELEASE** stops: it
  records what the release must carry and waits for the operator. Nothing
  is pushed, published or merged without the operator's word.
- The AWS family appears only in OKTA's `instance` dependency group and
  `tests/instance/` (FR-004); T025 holds it there.
- A new file in a new folder needs `git add -N` before `just lint`.
- Never stage a file this feature did not change, in any repository.

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |

---

## Phase 1: Setup

**Purpose**: the before-state, and the one open point of the plan.

- [ ] T001 Record HERE's before-figures in the Records table of `specs/008-relocate-okta-plugin/tasks.md` with spec 005's method (its T002): source lines, test lines, tests, shared golden files, workspace packages; and the plugin's own (source lines, the 11 test files under `packages/okta-opa-plugin/tests` and their test count)
- [ ] T002 [P] Keep the shared golden before the move as the comparison's left side: record the branch's start commit and `git rev-parse <commit>:tests/fixtures/golden` and `<commit>:tests/fixtures/config` in the Records table, recoverable with `git archive <commit> tests/fixtures/golden tests/fixtures/config`
- [ ] T003 [P] Settle research R5's open point: read what `cs_image_system.okta_opa_plugin`'s workspace asserts at load and under `validate --online` (does it only read that `OKTA_API_PRIVATE_KEY`, `TF_VAR_<team>_key` and `_secret` are set, or does it call the OPA team?); record the answer and the lines it rests on in the Records table; it decides T043
- [ ] T004 [P] Classify every test file in HERE that names Okta, in the Records table, as **Okta-only** (moves to OKTA; today among the 27 that import the plugin: `test_bootstrap_okta.py`, `test_identity_roots.py`, `test_login_proof.py`, `test_group_release.py`, `test_new_group_gid.py`, `test_stale_attachments.py`, `test_membership_removal.py`, `test_workload_access.py` and others), **mixed** (a core behaviour proven through Okta: re-hosted on POSIX by T035, its Okta cases carried by T020) or **passing mention** (T037); and for each mixed file, the core seam it proves (research R4)

---

## Phase 2: Foundational (prepare here)

**Purpose**: the plugin ready to leave while still in HERE. Blocks every
story.

- [ ] T005 [P] Turn the plugin's exact SDK pins into ranges in `packages/okta-opa-plugin/pyproject.toml` (`cs-image-system-base>=0.2,<0.3`, `cs-image-system-hashicorp-utils>=0.2,<0.3`, `cs-image-system-tofu-roots>=0.2,<0.3`); `uv lock`; `just init` (data-model.md: "Ranges only")
- [ ] T006 Move the Okta stubs out of `tests/harness.py` (`_credentials`' Okta lines, around 176-180; `_identity_provider`, around 216-228, with its retirement journal) into `packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/testing.py` (new) as `credentials(monkeypatch)` and `stub(monkeypatch, retirements)`, in the shape of `cs_image_system.gcloud_runtime.testing` before it left; `tests/harness.py` calls them, unchanged in behaviour
- [ ] T007 [P] Make the plugin's four tests that import `from harness import bare_run` (`test_group_module_call.py`, `test_group_ro_builder_root.py`, `test_user_builder_root.py`, `test_user_ro_builder_root.py` under `packages/okta-opa-plugin/tests/`) import it from `cs_image_system.hashicorp_utils.testing`, where the harness takes it from
- [ ] T008 Give `packages/okta-opa-plugin/pyproject.toml` a `[project.optional-dependencies] test` extra naming `cs-image-system-system[testing]` and the core plugins its tests need, and a `[tool.pytest.ini_options]` with its own `testpaths` and `--import-mode=importlib`, in the shape of `packages/docker-plugin/pyproject.toml`
- [ ] T009 Add `packages/okta-opa-plugin/tests/test_keeps_to_the_surface.py` (in the shape of `packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py`, `own` naming `cs_image_system.okta_opa_plugin`); fix any finding in the plugin's source; record whether a surface addition to the SDK is needed
- [ ] T010 Checkpoint: `just test` passes in HERE, the isolated runs each with `0 skipped`; `git status --short tests/fixtures` prints nothing; record it
- [ ] T011 **RELEASE**, only if T009 found a surface the published SDK lacks (the operator's): HERE's next release publishes it; otherwise record "not needed: the SDK on the index (contract 0.5.0, kit and Terraform libraries 0.2.0, test kit 0.1.11) carries every surface the plugin uses" and go on

**Checkpoint**: the plugin ranges on the published SDK and keeps to its
surfaces; its stubs are its own.

---

## Phase 3: User Story 1 - The Okta plugin builds, tests and releases from its own repository (Priority: P1) 🎯 MVP

**Goal**: a fresh clone of OKTA passes its acceptance tests against
published releases, with nothing skipped, and releases the plugin.

**Independent Test**: quickstart step 1.

### History and layout

- [ ] T012 [US1] In OKTA, start `feature/008-relocate-okta-plugin` from the local `develop` (`e3d3f0a`, not on the remote; the remote holds `main` only); record both
- [ ] T013 [US1] In a fresh clone of HERE at T010's commit (never HERE's working tree), run `uvx git-filter-repo` keeping `packages/okta-opa-plugin` and the Okta-only test files of T004, renaming those under `tests/instance/`; merge the result into OKTA's branch with `--allow-unrelated-histories`, under the noreply email set for OKTA (`git config user.email`, never `-c user.email`); record the filtered history's commit count and tip
- [ ] T014 [US1] Write OKTA's `pyproject.toml`: a workspace of `packages/*`; the dev group (pytest, ruff, pyright, reuse, bump-my-version, `cs-image-system-system[testing]>=0.1.11,<0.2`, the core plugins the suites declare); a dependency group `instance` naming the AWS family alone (`cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin`, each `>=0.1.11,<0.3`); `[tool.uv.sources]` for the plugin only, never a path into HERE; pytest and pyright settings with `-p cs_image_system.system.testing.strict`; its `REUSE.toml`, `LICENSES/`, `.gitignore`; the plugin's version moved to 0.2.0 (data-model.md: "its own line from 0.2.0")
- [ ] T015 [US1] Write OKTA's `Justfile` with the five lifecycle targets as contracts/okta-repository.md states them, plus `golden-regen`, `surface-check` and `public-safe`, in the shape of `cs-image-system-google-cloud`'s; `just init` resolves from the index alone

### The instance suite

- [ ] T016 [US1] Build OKTA's fixture `tests/instance/fixture/` from T002's copy: one AWS runtime and the s3 backend the shared fixture binds the identity roots to, the Okta group builders (`oktagroups`, `okta-groups-ro`, `okta-tf-users` of `cfg/group-builders.yml`), `groups/test-group.yaml`, `groups/group-lookup.yaml` and the users they name, one image owned by an Okta group, one instance launched from it, and the core builders those need (packer, ansible, default-os); personas synthetic on `example.invalid`; the `.age-identity` handling of `packages/docker-plugin/tests/fixture`
- [ ] T017 [US1] Add `tests/instance/aws_stubs.py` to OKTA: a copy of the AWS stubs of HERE's `tests/harness.py`, its docstring naming it temporary until spec 007's phase 1 publishes `cs_image_system.aws_runtime.testing`, which replaces it (research R3)
- [ ] T018 [US1] Write `tests/instance/conftest.py` in OKTA in the shape of `cs-image-system-google-cloud/tests/pipeline/conftest.py`: `FIXTURE`, `GOLDEN`, `STUBS = (aws_stubs.stub, okta_testing.credentials, okta_testing.stub, roots_testing.stub)`, the run, stubs and root fixtures, the autouse logging isolation
- [ ] T019 [US1] Make the moved Okta-only tests (`tests/instance/test_*.py` from T013) run on OKTA's conftest and the test kit instead of HERE's `tests/harness.py`, keeping every assertion
- [ ] T020 [US1] Carry to `tests/instance/` the Okta cases of HERE's mixed files (T004) that prove the plugin's own behaviour, one test file per HERE file it came from, each named in the Records table with what it asserts: enrollment at launch (`sftd-token`), activation in the bake, the login proof, the server aliases, the gid shim, stale attachments (FR-004)
- [ ] T021 [US1] Add `tests/instance/test_golden.py` and `tests/regen_golden.py` to OKTA in the shape of the Google Cloud family's, and generate `tests/instance/golden/` once with `just golden-regen`
- [ ] T022 [US1] Compare OKTA's golden with T002's copy file by file: the 14 identity files (`generated/identity/oktagroups` 8, `okta-tf-users` 3, `okta-groups-ro` 3), `generated/identity/run-identity.sh` and `meta-state/identity.yaml` with the files of the same path, and the Okta lines of the bakes (`generated/*/pckr-ebs-ans/...`), the instance roots (`generated/instance-image/open-tofu/...`) and `meta-state/launch-params.yaml` and `state-locations.yaml` with the plugin's; each difference must follow from the smaller fixture (a group, image or instance it does not declare); record every file's result; any other difference is a defect to fix, not to accept (Constitution IV)
- [ ] T023 [P] [US1] Add `tests/instance/test_broken_neighbour.py` and `tests/instance/test_leaves_the_process_alone.py` to OKTA in the shape of the Google Cloud family's
- [ ] T024 [P] [US1] Add `tests/instance/test_qualified_words.py` to OKTA: a configuration that writes the plugin's words (`okta-tf`, `okta-tf-ro`) qualified by its namespace, as `tests/test_registration_namespaces.py` in HERE names it, loads, and so does one that writes them bare (spec story 3, scenario 2)
- [ ] T025 [P] [US1] Add `tests/test_aws_only_in_instance.py` to OKTA: no file under `packages/` and no test outside `tests/instance/` imports `cs_image_system.aws_runtime`, `tf_ebs_instance_plugin` or `tf_s3_state_plugin`, and the plugin's `[project.dependencies]` and `test` extra name none of the AWS family's distributions (FR-004)

### Its acceptance tests, its documents, its CI

- [ ] T026 [US1] Make OKTA's `just test` pass: lint, type check at zero errors, the surface check, `packages/okta-opa-plugin/tests` and `tests/instance` with the golden, under the strict session; record the counts
- [ ] T027 [US1] Add OKTA's `full-test` legs: the low end of the SDK ranges (`uv sync --resolution lowest-direct`, then the plugin's own tests and the surface check), and `standard-aws` rendered with `init-config`, validated and dry-run with the system and the AWS family from the index and the plugin from the checkout, with the credentials T003 says a load needs; a leg whose tool is absent fails
- [ ] T028 [P] [US1] Correct `packages/okta-opa-plugin/README.md` in OKTA: every relative link into HERE points to OKTA's own file or to HERE by URL at `develop`; the install section says `uv tool install 'cs-image-system[okta]'` and links HERE's operations guide
- [ ] T029 [P] [US1] Move the Okta field tables (the `okta-tf` and `okta-tf-ro` group and user builders, their fields) from HERE's `docs/CONFIGURATION.md` into OKTA's `docs/CONFIGURATION.md`, the one source from now (Constitution VIII); HERE's sections are replaced by T051
- [ ] T030 [P] [US1] Write OKTA's `README.md` (what the plugin is, how an operator installs it, how a plugin author builds and tests it, why the instance suite needs the AWS family and that it may change), replacing the stub
- [ ] T031 [US1] Add OKTA's `.github/workflows/ci.yml`: on push to `develop` and every pull request, a fresh `ubuntu-latest` runner, `astral-sh/setup-uv`, OpenTofu with `tofu_wrapper: false`, `just init`, `just test`, `just public-safe`; a read-only lookup against the OPA team only by `workflow_dispatch`, with the Okta triple as secrets (contracts/okta-repository.md)
- [ ] T032 [US1] Add OKTA's `release` target in the shape of the Google Cloud family's `scripts/release` (it commits only when there is a change, and tags either way): moves the plugin's version, runs `just full-test`, builds the wheel, refuses a version the index ever held for `cs-image-system-okta-opa-plugin` (every 0.1.x), publishes to the index named; test its refusal in `tests/test_release_refuses_a_held_version.py` against a stubbed index answer
- [ ] T033 [US1] Checkpoint: quickstart step 1 passes from a fresh clone of OKTA's branch pushed to the remote (the operator's word to push; `develop` goes to the remote first); record each leg
- [ ] T034 [US1] **RELEASE** (the operator's): squash-merge OKTA's branch into its `develop` (branch kept) and cut 0.2.0 to TestPyPI, then PyPI; record the version and the index's answer; stop until it exists

**Checkpoint**: the plugin is on the index at 0.2.0, released from its
own repository.

---

## Phase 4: User Story 2 - This repository no longer holds the Okta plugin (Priority: P2)

**Goal**: HERE's acceptance tests pass with no Okta package, credential
or OPA team, and nothing here imports the plugin.

**Independent Test**: quickstart step 2.

### Tests re-hosted and trimmed

- [ ] T035 [US2] Re-host on the POSIX identity plugin (`packages/posix-identity-plugin`) or the test kit the core identity seams T004's mixed files prove through Okta, keeping what each asserts (research R4): the enrollment kinds a plugin declares (spec 004's tests), a group builder's launch parameters, a login proof a builder offers, group release, alias pools, hostname claims, canonical names, generations; record each file's vehicle in the Records table (spec story 2, scenario 2)
- [ ] T036 [US2] Remove from HERE the Okta-only files T013 carried (`git rm`), and the Okta cases T020 carried and the Okta part of every other mixed file, keeping each file's other assertions; a case dropped without a home in OKTA is named in the Records table with its reason
- [ ] T037 [P] [US2] Correct the passing mentions (T004) where they become false; the guard regex of `tests/test_core_names_no_runtime.py` stays

### The shared suite, the package, the manifests

- [ ] T038 [US2] Make the shared fixture's identity POSIX in `tests/fixtures/config`: `cfg/group-builders.yml` loses `oktagroups`, `okta-groups-ro` and `okta-tf-users`; `groups/test-group.yaml`, `groups/group-tcmet.yaml` and `groups/users.yaml` become POSIX groups and users, each group with a gid and synthetic personas on `example.invalid`; `groups/group-lookup.yaml` is removed; the Okta lines of `cfg/_config.yml`, `cfg/os-builders.yml` and `cfg/runtime-builders.yml` go; the fixture's README follows (FR-006)
- [ ] T039 [US2] Remove the Okta stubs' call and the Okta words of the docstrings from `tests/harness.py` (lines 13, 15-16, 23), and `cs_image_system.okta_opa_plugin` from every remaining test import
- [ ] T040 [US2] Remove `packages/okta-opa-plugin` from HERE (`git rm -r`)
- [ ] T041 [US2] Correct the root `pyproject.toml`: the `okta` and `all` extras name `cs-image-system-okta-opa-plugin>=0.2,<0.3` (lines 57-58, 68); remove its `[tool.uv.sources]` entry (107), `testpaths` (200), `pythonpath` (230) and pyright `extraPaths` (332); the WORDS table of `src/cs_image_system/extras.py` (lines 44, 94-96) keeps the `okta` extra; `uv lock`; `just init`
- [ ] T042 [P] [US2] Correct `.vscode/settings.json` (line 20) to match the pyright `extraPaths` (held equal by `tests/test_editor_paths.py`)
- [ ] T043 [US2] By T003's answer: if a load needs only the triple's presence, remove the Okta triple's gates and environment from `.github/workflows/ci.yml` (lines 196-198, 207, 212, 265-267) and `.github/workflows/ci-from-scratch.yml` (79-81, 90, 95, 169-171), and have the starters' check set dummy values; if it needs the real triple, keep them for the starters' check alone and correct the spec's edge case ("this repository's CI stops asking for the Okta secrets") to say so; in both cases `fixture-live` in `Justfile` (and its comment at line 69) no longer needs it
- [ ] T044 [US2] Regenerate the shared golden (`just golden-regen shared`) and read every change file by file against T002's copy: the 14 identity files and `generated/identity/run-identity.sh` gone; `meta-state/identity.yaml` holding the POSIX groups; the Okta enrollment and activation lines of the bakes and instance roots replaced by the POSIX ones; nothing else; record each in the Records table (Constitution IV)
- [ ] T045 [US2] Checkpoint: quickstart step 2 passes; `just test` passes with the isolated runs each `0 skipped`; `uv pip list` in HERE's environment does not name the plugin; record it

**Checkpoint**: HERE holds no Okta code and passes without it.

---

## Phase 5: User Story 3 - An operator sees no difference (Priority: P3)

**Goal**: with the plugin installed from its release, every command
behaves and emits as before.

**Independent Test**: quickstart step 3, and OKTA's starter leg (T027).

- [ ] T046 [US3] Test in `tests/test_extras.py` that the `okta` and `all` extras name `cs-image-system-okta-opa-plugin` by `>=0.2,<0.3` and that a release bump moves no range; and in `tests/test_package_metadata.py` that no workspace manifest names it by an exact pin (FR-007)
- [ ] T047 [US3] Extend spec 005's `just test-cloud-starters` (its T056) so the starters that declare Okta groups (`standard-aws`, `complete`) render, validate and dry-run with the plugin from the index, with the credentials T003 says they need; every step ran and succeeded, or the recipe fails; record it
- [ ] T048 [US3] Make a release here refuse when the `okta` extra's range is satisfied by no published release of the plugin (beside spec 005's T058 probe in `scripts/release.py`, tested in `tests/test_release_probes.py`)

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T049 [P] Correct HERE's `README.md`, `docs/PLUGINS.md`, `docs/DESCRIPTION.md`, `docs/DESIGN.md`, `docs/GLOSSARY.md` and `docs/WRITING_A_PROVIDER.md`: the plugin lives in OKTA, is installed by the `okta` extra, and the shared golden's identity is POSIX
- [ ] T050 [P] Correct `docs/DAILY_DRIVER.md`, `docs/OPERATIONS.md` and `docs/CI_RUNNER.md`: installing the plugin is stated once, in the operations guide, and linked from the others (FR-009)
- [ ] T051 [P] Correct `docs/CONFIGURATION.md`: the Okta builders keep a short description and link OKTA's tables (T029)
- [ ] T052 [P] Correct the other packages' READMEs that name the plugin as a neighbour: `packages/posix-identity-plugin/README.md` ("beside Okta"), `packages/system/README.md`, `packages/engine/README.md`, `packages/base/README.md`, `packages/tofu-roots/README.md`, `packages/hashicorp-utils/README.md`, `packages/aws-runtime-plugin/README.md`, `packages/tf-ebs-instance-plugin/README.md`, `packages/tf-s3-state-plugin/README.md`, `packages/default-os-plugin/README.md`, `packages/packer-plugin/README.md`, `packages/local-state-plugin/README.md`, `packages/dummy-plugin/README.md`
- [ ] T053 [P] Correct `docs/examples/_skeleton/CI_SETUP.md` and the starters' CI setup where it says the Okta secrets serve this repository's CI (by T043's outcome)
- [ ] T054 [P] Point the links of `docs/CHANGES.md` and `docs/INCIDENTS.md` into the plugin's files at OKTA, changing no other word
- [ ] T055 [P] Add a note to spec 007 where its research R7 says the Okta plugin moves out, pointing to `specs/008-relocate-okta-plugin`, and record there that spec 007's phase 3 may now remove the cloud runtime the plugin's proofs rode on
- [ ] T056 Measure the budget again with T001's method and add a Budget section to `specs/008-relocate-okta-plugin/plan.md` with the actual figures beside the expected ones (workspace packages −1; source lines about −4,150), with a reason for any figure outside its range
- [ ] T057 **RELEASE** (the operator's): HERE's release without the plugin; T048's probe passes; record its version
- [ ] T058 In REF: take T057's release (`just take`), and run `just config-drift`; expect exit 0 with no change of the tree's own and no identity root planning a change to any OPA group or user (quickstart step 3; SC-003); correct `CI_SETUP.md` and `README.md` where they say the plugin comes from HERE; record it
- [ ] T059 Walk `specs/008-relocate-okta-plugin/quickstart.md` steps 1 to 3 and record each result in the Records table
- [ ] T060 Bring the specification's files up to date: the status line of `specs/008-relocate-okta-plugin/spec.md`, and the row for 008 in `specs/README.md`

---

## Dependencies & Execution Order

- **Spec 005 merged** before this begins (the branch starts from that
  `develop`); this must land before spec 007's phase 3.
- **Phase 1** first; T002 to T004 can run together. T003 decides T027,
  T043, T047.
- **Phase 2** blocks every story; T011 stops only if T009 found a
  missing surface.
- **US1 (Phase 3)** after Phase 2. It ends in the plugin's release
  (T034), which US2's extras (T041) and US3's starter check (T047) name.
- **US2 (Phase 4)** after T034. Within it, the tests are re-hosted and
  trimmed (T035 to T037) before the fixture, harness and package go
  (T038 to T040), and the golden is regenerated last (T044).
- **US3 (Phase 5)** with or after US2: T046 needs T041; T047 needs T034
  and spec 005's T056.
- **Phase 6** after US3; T057 before T058.

### Parallel opportunities

- T002, T003, T004.
- T005 with T007 (different files).
- T023, T024, T025 (new files in OKTA); T028 to T030 (documents).
- T037 with T042.
- T049 to T055 (different documents).

### Parallel example: User Story 1's new tests

```text
Task: T023 tests/instance/test_broken_neighbour.py, test_leaves_the_process_alone.py
Task: T024 tests/instance/test_qualified_words.py
Task: T025 tests/test_aws_only_in_instance.py
```

### Parallel example: Polish

```text
Task: T049 README.md, docs/PLUGINS.md, docs/DESCRIPTION.md, docs/DESIGN.md
Task: T050 docs/DAILY_DRIVER.md, docs/OPERATIONS.md, docs/CI_RUNNER.md
Task: T051 docs/CONFIGURATION.md
Task: T052 the other packages' READMEs
```

## Implementation Strategy

### MVP first

Phases 1 and 2, then US1 and the plugin's release: the plugin stands
alone and is on the index from its own repository (quickstart step 1).
HERE keeps its copy until US2, so nothing an operator uses changes
before then.

### Incremental delivery

1. Phase 2 → T010: the plugin ready to leave.
2. US1 → T034: the plugin released from OKTA.
3. US2 → T045: HERE without the plugin.
4. US3, Polish → T057, T058: HERE released; the reference takes it.

### Notes

- **T013** carries history; run it in a fresh clone, never in HERE's
  working tree, which `git filter-repo` would rewrite.
- **T022 and T044** are the two golden readings; each records every
  file.
- **T035 and T036** are the largest; split them by file if delegated.
- Two tasks always stop for a release (T034, T057); T011 stops only if
  needed.
