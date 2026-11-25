# Tasks: Fifteen minutes to a first dry run

**Input**: [spec.md](spec.md), [plan.md](plan.md) (revised 2026-11-25),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/quickstart-page.md](contracts/quickstart-page.md),
[contracts/quickstart-runner.md](contracts/quickstart-runner.md),
[contracts/first-run-messages.md](contracts/first-run-messages.md),
[quickstart.md](quickstart.md)

**Tests**: requested. The page itself is proved by running it (the CI
job, the Publish job and `just test-quickstart`), not by a test; the
runner's behaviour and the three messages get behaviour tests
(contracts/quickstart-runner.md, contracts/first-run-messages.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US4)

## Working rules

- `HERE` is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`; `REF`
  is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig`;
  `TREE` is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-starter-tree`.
- The work is on `feature/002-first-dry-run`, from `develop`.
- **Nothing is applied** by a task here, except quickstart step 8's real
  run, which is the operator's decision. **Nothing is published**: a task
  marked **RELEASE** is the operator's and stops. Until 1.0 every release
  goes to TestPyPI alone (specification 013).
- **Every install from the index** in a command, a document or a test
  uses the one install form at the exact version (research R4): TestPyPI
  as the index, PyPI as the extra, `--index-strategy unsafe-first-match`.
  An unpinned install resolves to PyPI's older 0.1.12.
- Your own installed `cs-image-system` is never touched: every install a
  task makes goes into a temporary `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR`.
- Versions move only their third number.
- Run Python as `uv run --no-sync python`; iterate with `just test-one`;
  the acceptance tests are `just test` at every checkpoint.
- **Specification 003** (release gates) changes how the release's gates
  report; whichever lands second takes the other's gate list, and the
  quickstart leg never reports SKIPPED (research R17).

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |
| T001 | 2026-11-25: `feature/002-first-dry-run` started by `git flow feature start 002-first-dry-run` from `develop` at `845659fb`; its first commits the clarification (`6ac809b4`), the revised plan (`a4e85876`) and these tasks (`69fd796c`) |
| T002 | The before-state, 2026-11-25: the budget as the plan measured it (19 packages, 51,039 source lines, 44,727 test lines, 2,519 tests); `just test-docker-install` 41 s. Research R1 re-walked on 0.1.13.dev1 with the workspace's command in a scratch directory: `init-config --from standard-docker` wrote the tree (not a git repository), `validate` gave `Validation successful.` and a dry `run --all` `completed: identity, storage, base-image, instance-image, release, retention` and `"ok": true` in 26 s, with `CSIS_CONFIG_IDENTITY` unset; with only git and `/usr/bin:/bin` on `PATH`, `validate` refused in five lines (docker, packer, ansible-playbook, tofu not found; bash 3.2.57 below `>=5`). R1 holds |
| T003 | `tests/test_quickstart_script.py`, fourteen tests with a stubbed session, build and install check: page order, continuations, comments and `text` blocks; one session; a failing command named and the rest not run; no box; eleven commands; an install from an index; the time limit; two passes; `--wheels` building nothing; the umbrella's override carrying the page's extras; an installed package of the system from an index named; the prerequisites table and its check; `prepare` refusing a checksum that differs. Written before the script, so they failed on import until T004 |
| T004, T005 | `scripts/quickstart` (`run`, `prerequisites`, `prepare`), per contracts/quickstart-runner.md. **Research R8 settled** by a trial 2026-11-25: `UV_OVERRIDE` naming each built wheel makes `uv tool install` take every one of the system's packages from the build (their `direct_url.json` names the file), but an override of the umbrella replaces the page's requirement, extras and all, so the first trial installed no docker plugin; the override of the umbrella therefore carries the extras the page's install asks for (read from the page), and with it all 14 packages came from the build. No local-version fallback was needed. The check after the install is stronger than the plan's version check: every installed package of the system must have come from the build, since the version cannot tell a build from the index's copy of the same release. The session is one `bash` that each command runs in (`</dev/null`, its exit code on a line of its own), under `set -uo pipefail` with each command's exit checked by the runner rather than `-e`, so a failing command is named rather than ending the shell. `prepare`'s docker CLI has no published checksum (download.docker.com lists the archive alone): its digest, read from the vendor's 24.0.0 archive on 2026-11-25, is recorded in the script. OpenTofu's floor `>1,<2` names no release itself; its oldest, 1.6.0, is recorded as the one `prepare` installs. `just lint` clean, `just typecheck` 0 errors |
| T006 | The root `Justfile`: `test-quickstart *ARGS`, `quickstart-prepare dir`, `quickstart-table mode=""`, each with its comment and `[doc]` line, beside `test-docker-install` (which T015 removes) |
| T007 | `just test-one tests/test_quickstart_script.py tests/test_justfile_contract.py -q`: 45 passed |
| T008 | `docs/QUICKSTART.md`: three boxes, seven commands, command 1 the one install form at `cs-image-system[docker]==0.1.13.dev1`; the prerequisites table written by `just quickstart-table` (uv `>=0.8.0`, docker `>=24`, packer `>=1.14`, bash `>=5`, tofu `>1,<2`), `just quickstart-table check` passing; the systems covered, what was produced and kept, the test key, the network, nothing of proxies or mirrors, the three links (the docker starter's "A first real run", which T024 writes) |
| T009 | `pyproject.toml`'s `[tool.bumpversion]` moves `cs-image-system[docker]=={current_version}` in `docs/QUICKSTART.md`; `scripts/release.py`'s `bumped_files` (the files the release commit takes) gains the page, which it otherwise would have left moved and uncommitted; `tests/test_package_metadata.py`'s bump test copies the page and holds that its pin moves. That file and `tests/test_release_script.py`: 147 passed |
| T010 | Research R4's open point settled 2026-11-25 in a scratch tool directory: with 0.1.11 installed, the page's command 1 as written ends on 0.1.13.dev1, with `--upgrade` and without it. `--upgrade` is kept, harmless; nothing to change |
| T011 | 2026-11-25, `just test-quickstart --passes 2`: 19 wheels of 0.1.13.dev1 built in 4 s; both passes installed the build under test, every box's last line as the page says (the version, `Validation successful.`, `Run ... completed: identity, storage, base-image, instance-image, release, retention`), the second `init-config` keeping its own tree; the first pass 36 s (limit 900), the second 27 s; `passed -- 7 commands in 3 boxes, each ran and succeeded, twice`. On a warm machine: CI's clean machine gives the cold time (T018) |
| Phases 1 to 3 | 2026-11-25, the first `just test`: 3 failed, 2,507 passed, each this work's: the recipe catalogue in `docs/OPERATIONS.md` must name every recipe (the three new rows added there, ahead of T026's corrections), a source comment may not carry a date (`scripts/quickstart`'s digest comment), and the runner's tests pinned eight sentences of its output against the repository's ceiling of 26 (Principle IX: each now pins the exit code and one token). The three files: 85 passed. The second `just test`: lint clean, pyright 0 errors, 2,510 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped` |
| T012 | `.github/workflows/ci.yml`: the `quickstart` job in place of `docker-install`, in a stock `ubuntu:24.04` container with the host's socket; its own tools placed apart from the page's (certificates, curl and git by apt, a step named "Place the tools" as CI's other plumbing; just and uv by their setup actions; `just init` with `UV_PYTHON=3.13`, the job's own environment); `just quickstart-prepare /opt/quickstart`; `just test-quickstart --passes 2 --page-path /opt/quickstart/bin:/usr/bin:/bin` with `PACKER_GITHUB_API_TOKEN` from the job's token; `just quickstart-table check`; the header comment corrected. The runner gained `--page-path` (the session's starting `PATH`, so the job's uv and just are not the page's), with a test. **Rehearsed four times on your local machine** in the same stock container (2026-11-25), each run finding what CI would have: (1) with no Python on the machine uv took 3.15, for which `regex` (through the docker plugin's `python-hcl2`) has no built package, so the install tried to compile it with no compiler: the page's command 1 now names `--python 3.13`, the version the system is built and tested on (a newcomer's fresh machine meets the same), and the job's `just init` runs on 3.13; (2) `just hooks` needs a git repository (the rehearsal's copy had none; a checkout has); (3) macOS's `tar` had put AppleDouble `._*` files in the rehearsal's archive (an artifact of the rehearsal, not of the product); (4) **passed**: `prepare` 16 s, the page's first pass 48 s and the second 26 s, the table matching, the job 137 s in all |
| T013 | `.github/workflows/publish.yml`: a `quickstart` job after `build`, guarded to the repository, on the same clean machine, downloading the `dist` artifact and running `just test-quickstart --wheels dist --page-path ...` once; `testpypi` needs `[build, quickstart]`; the header says the upload waits on the page. The `--wheels` path walked here against the artifact's nested layout (`<dir>/01-cs-image-system/*.whl`): `19 wheels of 0.1.13.dev1 given ... (nothing built)`, the build under test installed, passed |
| T014 | `scripts/release.py`: the lighter check's pair is `just test`, `just test-quickstart` (and the module docstring, the docker probe's message, the gate's docstring and the dry plan's words); the root `Justfile`'s `full-test` leg runs `test-quickstart`, never SKIPPED, and its two comments say so |
| T015 | Deleted: the `test-docker-install` recipe, `scripts/isolated-run`'s `--install-check` mode (its docstring's second mode, its constants, `install_check`, its three arguments), and the install check's tests in `tests/test_isolated_run.py` (four tests and their shell) |
| T016 | `tests/test_ci_workflow.py` (the job set), `tests/test_publish_commands_parse.py` (the job set, `testpypi`'s needs, and a new test: the upload waits on the page against the tag's own files on a stock image), `tests/test_release_script.py` and `tests/test_release_probes.py` (the lighter check's command). With the runner's and `isolated-run`'s: 137 and 41 passed |
| T017 | uv's floor: 0.8.0, the oldest the plan considers, passes the rehearsed job (T012's fourth run, the page installing and running on uv 0.8.0), so `UV_FLOOR` stays 0.8.0 and the table is unchanged. No older release was tried: 0.8.0 is the plan's starting point |
| Quickstart step 5 | 2026-11-25, here: `just test-quickstart --page <a copy with run --al>`: `quickstart: FAILED at box 3 of 3: cs-image-system --root-dir csis-quickstart run --al (exit 2)` and a `FAILED --` verdict, exit 1. Its CI half waits for the push (T018) |
| T018 (first run) | 2026-11-25, `just test`: 1 failed, 2,503 passed: `tests/test_ci_runner.py` holds that every job of `ci.yml` runs in the runner image, which the `quickstart` job does not by design (research R7: the image holds every tool, so it could not prove the page's list is enough). The test now names that one job and holds its stock image and socket instead; `docs/CI_RUNNER.md`, which the plan's list of statements made false had missed, says the same beside the from-scratch path. Those and the documentation tests: 54 passed |
| T018 | 2026-11-25, the second `just test`: lint clean, pyright 0 errors, 2,504 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`. **Open**: the operator's push of the branch, then quickstart step 4 (CI's `quickstart` job) and step 5's CI half, each recorded here |

---

## Phase 1: Setup

- [X] T001 Record the start in the Records table of `specs/002-first-dry-run/tasks.md`: `feature/002-first-dry-run` was started 2026-11-25 by `git flow feature start 002-first-dry-run` from `develop` at `845659fb`; its first two commits are the clarification (`6ac809b4`) and the revised plan (`a4e85876`)
- [X] T002 [P] Record the before-state: the budget as the plan measured it (19 packages, 51,039 source lines, 44,727 test lines, 2,519 tests), `just test-docker-install`'s 41 seconds, and research R1 re-walked on the current release with the workspace's command in a scratch directory (`init-config <scratch>/t --from standard-docker`, `validate`, a dry `run --all`): every declared tool checked, a daemon that answers and the network needed, no key and no git, the placeholders no obstacle

---

## Phase 2: Foundational (the runner every story uses)

**Purpose**: `scripts/quickstart` and its recipes (contracts/quickstart-runner.md).
US1 needs it to prove the page; US2 to run it in CI and the Publish workflow.

- [X] T003 Write `tests/test_quickstart_script.py` first, with a stubbed shell as `tests/test_isolated_run.py` holds `isolated-run`: the commands are read in page order with `\` continuations joined and comment and blank lines skipped; only `sh` blocks run, `text` blocks never; one session carries an `export` into a later box; a failing command is named `quickstart: FAILED at box M of K: <the command> (exit N)` and later commands are reported as not run; a page with no box fails; a page with eleven commands fails; an install whose `--version` is not the build's fails; a run over `--limit` fails; `--wheels DIR` skips the build and names DIR's files to uv; exits 0 passed, 1 failed, 2 could not start; `prerequisites` gives the floors of a given `executables.yml` and `--check` names the first differing row. Expect them to fail before T004
- [X] T004 Implement `scripts/quickstart run [--page PATH] [--wheels DIR] [--passes N] [--limit SECONDS] [--keep DIR]` per contracts/quickstart-runner.md and research R6, R8, R10: build the workspace's wheels (`uv build --all-packages --wheel`) unless `--wheels`; a temporary working directory and tool directory; every `sh` block of the page (default `docs/QUICKSTART.md`) in one `bash` session under `set -euo pipefail`, with `UV_OVERRIDE` naming each workspace distribution as a direct reference to its built file; after command 1, `cs-image-system --version` must name the built version (if `UV_OVERRIDE` does not pin the requested package itself, the fallback of R8: wheels built under a local label `<version>+qs<short sha>` with `UV_FIND_LINKS`; record which held); the lines of "What `run` prints"; the 900-second limit on the first pass only; the time lines and the verdict also to `GITHUB_STEP_SUMMARY` when it is set
- [X] T005 Implement `scripts/quickstart prerequisites [--write | --check] [--page PATH]` (the table between the page's two marker comments, from the docker starter's `docs/examples/standard-docker/cfg/executables.yml` and one constant for uv's floor, each row's "Where it comes from" linking the daily driver's section 1.2; research R11) and `scripts/quickstart prepare --into DIR` (Linux x86_64 alone: uv, the static docker CLI, OpenTofu and Packer at exactly the floors `prerequisites` prints, from each vendor's release site, each checked against its published checksum, into `DIR/bin`; research R7)
- [X] T006 Add the recipes to the root `Justfile`: `test-quickstart *ARGS` (`scripts/quickstart run`, arguments passed through), `quickstart-prepare dir`, `quickstart-table mode=""` (`--write`, or `--check` with `check`), each with a comment and a `[doc(...)]` line as the file's other recipes have
- [X] T007 Checkpoint: `just test-one tests/test_quickstart_script.py -q` passes; record the count

---

## Phase 3: User Story 1 - From nothing to a dry run on one page (Priority: P1) 🎯 MVP

**Goal**: one page, seven commands in three boxes, reaches a successful
dry run of the docker starter with nothing to fill in.

**Independent Test**: `just test-quickstart --passes 2` (quickstart step 2).

- [X] T008 [US1] Write `docs/QUICKSTART.md` per contracts/quickstart-page.md and data-model.md "The quickstart page": the systems covered at the top (macOS and Linux, x86_64 and arm64; Windows not); the prerequisites table between its markers, written by `just quickstart-table`; box 1 (`uv tool install --upgrade --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \` then `--index-strategy unsafe-first-match 'cs-image-system[docker]==<the version pyproject.toml carries>'`, `uv tool install --upgrade 'ansible-core>=2.16'`, `export PATH="$(uv tool dir --bin):$PATH"`, `cs-image-system --version`), box 2 (`init-config csis-quickstart --from standard-docker`, `--root-dir csis-quickstart validate`), box 3 (`--root-dir csis-quickstart run --all`), each box headed `# step N -- box M of 3 -- v1` with its time comment; one short section on which commands need the network and which is slow, saying nothing of proxies or mirrors (research R16); after the run, a few sentences on what was produced, where, that nothing was applied, what the machine keeps (`almalinux:10`, the packer plugins) and the one command that removes the image, and that the tree's test key is unused and protects nothing (FR-007, research R5); `uv tool update-shell` named for a permanent `PATH`; the ending's three links (research R13)
- [X] T009 [US1] Add `docs/QUICKSTART.md` to `[tool.bumpversion]`'s file list in `pyproject.toml` with the search `cs-image-system[docker]=={current_version}` (research R4), and extend `tests/test_package_metadata.py`'s bump test (its `tree` fixture copies the page too) so a bump moves the page's pin with the rest
- [X] T010 [US1] Settle research R4's open point in a scratch tool directory: install `'cs-image-system[docker]==0.1.11'`, then run the page's command 1 as written; record whether it ends on the page's release; if it does not, change command 1 so it does (and contracts/first-run-messages.md's "an older release installed" row with it)
- [X] T011 [US1] Checkpoint: `just test-quickstart --passes 2` passes, the first pass under 900 seconds, and `just quickstart-table check` passes (quickstart steps 2 and 3); record the times and the verdicts

---

## Phase 4: User Story 2 - The page cannot go stale unnoticed (Priority: P2)

**Goal**: CI runs the page on a clean machine on every push, and every
release's packages run it before the tag and before the upload.

**Independent Test**: quickstart steps 4, 5 and 9.

- [X] T012 [US2] In `.github/workflows/ci.yml`, replace the `docker-install` job with `quickstart`, per data-model.md "The quickstart job": every push and pull request, no condition and no secret; a container from the stock `ubuntu:24.04` image with the host's docker socket mounted (research R7); install the job's own tools (git for the checkout, `just`) outside the page's `PATH`; `just quickstart-prepare <dir>`, timed apart; `just test-quickstart --passes 2` with `PATH` the prepared tools, the page's uv tool directory and `/usr/bin:/bin` alone; `just quickstart-table check`; `PACKER_GITHUB_API_TOKEN` from the job's own token; correct the header comment
- [X] T013 [US2] In `.github/workflows/publish.yml`, add a job `quickstart` per data-model.md "The Publish workflow's quickstart job": after `build`, guarded to the repository as the other jobs are, on the same machine as CI's job, downloading the `build` job's artifact and running `just test-quickstart --wheels <the downloaded files>` once; make `testpypi` need `[build, quickstart]`, so the upload waits on the page (decided 2026-11-25); correct the header comment
- [X] T014 [US2] In `scripts/release.py`, the lighter check runs `just test-quickstart` in place of `just test-docker-install` (the gate's pair at line 796, the module docstring at line 47, the docker probe's message at line 734, the probe docstring at line 777, the dry plan's gate words at line 936); in the root `Justfile`, `full-test`'s leg runs `test-quickstart` in place of `test-docker-install` (lines 187-188, never SKIPPED) and the comments at lines 72 and 99 say so
- [X] T015 [US2] Delete the install check it replaces (research R9): the `test-docker-install` recipe (`Justfile` line 383), `scripts/isolated-run`'s `--install-check` mode and its docstring's second mode, and their tests in `tests/test_isolated_run.py`
- [X] T016 [P] [US2] Correct the tests that hold the old shape: `tests/test_ci_workflow.py` (the job set: `quickstart` in place of `docker-install`), `tests/test_publish_commands_parse.py` (the `quickstart` job guarded to the repository; `testpypi` needs it), `tests/test_release_script.py` and `tests/test_release_probes.py` (the lighter check's command; these three are the tests that name `docker-install` or `test-docker-install` today); and `tests/test_workflow_names.py` for any action the two new jobs use
- [X] T017 [US2] Set uv's floor (research R11): the oldest uv release, from 0.8.0, on which `just test-quickstart` passes in the stock container; set the constant in `scripts/quickstart`, rewrite the page's table (`just quickstart-table`), and record the releases tried
- [ ] T018 [US2] Checkpoint: `just test`; record the counts. Then the operator's push of the branch, and quickstart step 4 (CI's `quickstart` job: two `the page took` lines, one `passed --`, no `FAILED`) and step 5 (`just test-quickstart --page <broken copy>` names the broken command; the CI half on a scratch branch holding the same change), each recorded

---

## Phase 5: User Story 3 - A first-run failure says what to do (Priority: P3)

**Goal**: each first-run failure of FR-013 is one line with its cause
and its remedy (contracts/first-run-messages.md).

**Independent Test**: quickstart step 6, boxes 1 to 6.

- [ ] T019 [P] [US3] In `packages/engine/src/cs_image_system/engine/commands/validate.py`, the absent binary's line gains, after a space, `-- install it (where each tool comes from: the daily driver, section 1.2)`; the engine names no tool or vendor (Principle VI); a behaviour test in `packages/engine/tests` with a declared binary that is not on `PATH`
- [ ] T020 [P] [US3] In `packages/docker-plugin/src/cs_image_system/docker_runtime/docker_runtime_builders.py`, the unreachable daemon's patterns gain the current CLI's `failed to connect to the docker API at` wording, and a run's failure for an unreachable daemon carries `DOCKER_REMEDY` as a load's does; a behaviour test in `packages/docker-plugin/tests/unit` with a stubbed CLI answering that wording
- [ ] T021 [P] [US3] In `packages/system/src/cs_image_system/system/starters.py`, after a refresh's `REFUSED <file>` lines, `init-config` prints one closing line: `init-config: <dest> already holds a configuration this release did not write; to start over remove it, or keep it and refresh the release's files with --force` (exit unchanged); a behaviour test in `packages/system/tests`
- [ ] T022 [US3] Checkpoint: `just test`; then quickstart step 6, boxes 1 to 6, each line recorded

---

## Phase 6: User Story 4 - What to do next is signposted (Priority: P4)

**Goal**: the front page leads to the description first and the page
second; the page's three routes each begin with a command that works;
no other document repeats the steps.

**Independent Test**: quickstart steps 7 and 8.

- [ ] T023 [US4] In `README.md`, "Where to start" lists `docs/DESCRIPTION.md` first, `docs/QUICKSTART.md` second and the daily driver third, its install lines link the page, and the Justfile contract table's `release` and `full-test` rows name `test-quickstart`; in `tests/test_docs_contract.py`, delete `test_the_daily_driver_is_the_first_place_to_start` (a test of a document's order, Principle IX; research R14) and add `docs/QUICKSTART.md` to the documents whose relative links resolve
- [ ] T024 [P] [US4] In the five starters' READMEs (`docs/examples/{complete,standard-aws,standard-aws-posix,standard-docker,standard-gce}/README.md`): the install lines and "Before the first run" link the page instead of repeating it; the image builder's type is `packer`, not `packer-ebs`, `packer-gce` or `packer-docker`; "the load reads the account's VPCs" goes (standard-aws, standard-aws-posix), and the runtime files' "(an SSO profile needs a live session)" comment in `docs/examples/standard-aws*/cfg/runtime-builders.yml` says "for a real run and `validate --online`"; a cloud starter's first box installs its extras by the one install form at the release's version; the docker starter's README gains "A first real run" (research R13: its first box the real run of the quickstart's tree, `--overlay overlays/launch.yaml --no-dry-run run --all`, its last the teardown)
- [ ] T025 [P] [US4] In the skeleton: `docs/examples/_skeleton/CI_SETUP.md` line 29 and `docs/examples/_skeleton/Justfile` lines 6, 35 (the bare install) and 50 ("validate (needs the sessions)") corrected (research R15)
- [ ] T026 [P] [US4] In the manuals: `docs/DAILY_DRIVER.md` (its opening and section 1.4a link the page; section 1.9's first box moves to its top); `docs/CONFIGURATION.md` lines 442-446 ("A load therefore needs a live AWS session"); `docs/OPERATIONS.md` (the install check at lines 1986, 2380, 2764 and 3219 becomes `test-quickstart`, "Releasing until 1.0"'s lighter check and the Publish workflow's jobs say the page runs before the tag and before the upload, and "Installing a release" links the page); `docs/WRITING_A_PROVIDER.md` line 291; `packages/docker-plugin/README.md` line 654; the root `Justfile`'s comment at lines 40-41 ("dry runs never start tofu")
- [ ] T027 [US4] Checkpoint: the documentation tests (`just test-one tests/test_docs_contract.py tests/test_docs_examples.py tests/test_docs_parity.py tests/test_package_metadata.py -q`); then quickstart step 7 and step 8's boxes 1 and 2; step 8's box 3, the first real local run, is **the operator's decision** (default yes; it bakes two images and stands a container and a volume, then takes them down); record each

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T028 Re-measure the budget by the plan's method and record it against the plan's expectations (source +20 to +45, tests +8 to +16, the install check's lines gone); a measure outside its range gets its reason in the record
- [ ] T029 Checkpoint: `just test`, then `just full-test` (the full proof: this changes the release's gate, the starters' workflows' neighbours and the Publish workflow); record both
- [ ] T030 Run `/speckit-converge`; complete any task it appends
- [ ] T031 In TREE (`cs-image-system-starter-tree`), the operator's decision D3 of 2026-11-21: its README replaced by three lines pointing at `docs/QUICKSTART.md` and the five template repositories; committing and pushing there, and archiving the repository on GitHub, are **the operator's** (outward-facing); record each
- [ ] T032 **RELEASE** (the operator's): the next release after the merge. Its lighter check runs `just test-quickstart` before the tag, and its Publish run's `quickstart` job passes before `testpypi` begins (quickstart step 9, SC-008); record the version and the runs. The five template repositories take the corrected READMEs at the next *final* release (a `.dev` release pushes none)
- [ ] T033 In REF: take T032's release (`just take <version>`) and run `just config-drift`; expect the refresh of the release-owned files, exit 0 and the reference's CI green; record it
- [ ] T034 SC-002 (quickstart step 10): someone who has never used the system follows the published `docs/QUICKSTART.md` unaided; open, with no date (decided 2026-11-25), in the end perhaps the operator on a clean account; the record gives the date, the machine, the minutes (15 or fewer passes) and every place they hesitated. Until it is recorded the specification stays merged, not complete
- [ ] T035 Bring the specification's files up to date: the status line of `spec.md` and the row for 002 in `specs/README.md`, with the date

---

## Dependencies & Execution Order

- **Phase 2** (the runner) blocks US1's checkpoint and all of US2.
- **US1** before US2: CI and the Publish workflow run the page US1 writes.
- **US3** depends only on Phase 1; its three tasks touch three packages
  and run in parallel.
- **US4** after US1 (it links the page) and after US2 for `docs/OPERATIONS.md`'s
  gate passages.
- **T032** (the release) needs every story merged; T033 and T034 follow it.

## Parallel Opportunities

- T002 beside T001.
- T019, T020 and T021 (three packages), beside Phases 2 to 4.
- T024, T025 and T026 (different documents).
- T016 beside T014 and T015 once their shapes are settled.

## Implementation Strategy

- **MVP**: Phases 1 to 3: the runner and the page, proved on your local
  machine.
- Then US2 (CI, the Publish job, the gate; the install check deleted),
  US3 (the three messages), US4 (the way in and the corrections), and
  the release that carries it.
