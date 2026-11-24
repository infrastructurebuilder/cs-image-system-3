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
| T001 | 2026-11-21, on `feature/008-relocate-okta-plugin` at its start (`0e73dedc`), by spec 005's method: source lines 54,249; test lines 46,069; tests 2,007; shared golden files 117; workspace packages 19. The Okta plugin's own: 4,152 source lines; 11 test files, 1,313 lines, 71 tests |
| T002 | The comparison's left side is the tree at `0e73dedc`: `tests/fixtures/golden` is tree `023d09a506206a18a0aefac5277744a2e39ed18b` (117 files), `tests/fixtures/config` tree `9d862ccfc3d0816568cd0a6887d19c14a257ce37`; recoverable with `git archive 0e73dedc tests/fixtures/golden tests/fixtures/config` |
| T003 | 2026-11-21: **presence only**, no call to Okta or OPA at a load or under `validate` / `validate --online`. The oktapam provider's `_require_tfvar` (`okta_opa_plugin/okta_tf_workspace.py:193-208`) refuses the load (exit 2, `OPA_REMEDY`) when `TF_VAR_<team>_key` or `_secret` is UNSET and the builder leaves `key`/`secret` at the default (an empty string passes); the okta provider's `okta_credentials_present` (:57-60) only warns and skips `plan` when no `OKTA_API_*` key is set (:221-228). `--online` asks only runtimes with a `network_facts` hook; the plugin has none. The API is reached only from the state query (never fatal, recorded "unavailable"), `identity-attributes --probe`, terraform's `data \"external\"` at plan or apply, and the launch, alias and decommission paths. **So T043 takes the presence branch**: once the frozen fixture is POSIX, `fixture-live` needs none of the triple, and the starters' check already supplies dummies in-process; the triple can leave both workflows. (Spec 003's research and `Justfile:68-69`'s comment say the identity roots only warn and skip; true for `OKTA_API_*` alone, a missing team pair fails the load) |
| T004 | 2026-11-21, by a read-only search (`okta`, `sftd`, `opa` as a word): 77 test files and `tests/harness.py` name Okta, 28 import the plugin. **Okta-only, 8 files, 37 tests** (move whole); **mixed, 31 files, 377 tests** (about 58 Okta-specific tests move with T020/T036; about 107 core-through-Okta tests are re-hosted by T035); **passing mention, 38 files, 342 tests** (T037). Five files T004 named Okta-only are mixed (`test_identity_roots`, `test_login_proof`, `test_membership_removal`, `test_stale_attachments`, `test_state_query_verdicts`). The file-by-file table, the seam each mixed file proves and whether POSIX can carry it, is [test-classification.md](test-classification.md). **Found**: about 30 of the core-through-Okta tests need a group builder that keeps a server registry (hostname claims, provider aliases, the alias pool, canonical names, generations, a dry run asking the registry); neither the POSIX plugin nor the test kit has one (the operator's decision of 2026-11-21, below). The shared fixture also puts `stofs` and `secofs` on the Okta builder (T038's list lacked them), and the golden holds 39 files with Okta content, the `oktagroups` root 9 (not 8) |
| T005 | `packages/okta-opa-plugin/pyproject.toml` ranges on the kit and both Terraform libraries (`>=0.2,<0.3`; they were `==0.2.1`); `tests/test_package_metadata.py`'s `SDK_BY_RANGE` names the plugin; `uv lock`, `just init` |
| T006 | `cs_image_system.okta_opa_plugin.testing` (new): `credentials(monkeypatch, teams)` (the API key and each team's `TF_VAR_<team>_key`/`_secret`, dummies) and `stub(monkeypatch, retirements)` (groups present, the server registry empty and free, retirements journaled); `tests/harness.py` calls both, its fixture's team named once (`FIXTURE_TEAM`), its docstring saying the plugin ships its own stubs |
| T007 | The four tests import `bare_run` from `cs_image_system.hashicorp_utils.testing` |
| T008 | The plugin's `test` extra names `cs-image-system-system[testing]==0.1.12` (the Terraform library's `bare_run` comes with its own dependency), and its `[tool.pytest.ini_options]` has `testpaths = ["tests"]` and `--import-mode=importlib` |
| T009 | `packages/okta-opa-plugin/tests/test_keeps_to_the_surface.py` (new): the sources keep to the SDK's surfaces; the tests did not: two cases of `test_opa_gid_shim.py` imported the engine (`identity_gids`), so they moved to `tests/test_okta_identity_gids.py` (Okta-only, T013 takes it). No surface addition to the SDK is needed. The plugin's own tests: 73 passed |
| T010 | 2026-11-22: `just test` lint clean, type check 0 errors, 2,588 passed, 23 skipped, 1 failed: `tests/test_release_probes.py::test_pypi_without_a_live_configuration_or_a_session_is_refused_by_name` timed out at its 300-second limit under the full run's load; alone it passed in 161 seconds (the session probe now loads the reference with the Google Cloud family layered in from the index, spec 005, which makes the case slow: the case's empty home held an empty uv cache, so every run downloaded and built the family afresh. Fixed 2026-11-22 at the operator's word: `tests/test_release_probes.py` keeps the real uv cache (`UV_CACHE_DIR`) beside its empty home; the case went from 139 to 20 seconds, the file's 9 cases 42 seconds). The isolated runs, not reached by the failed run, then passed: `test-core` 377, `test-terraform-alone` 6, 37 and 6, `test-docker-alone` 62, 62 and 38, each 0 skipped; `git status --short tests/fixtures` printed nothing |
| T011 | Not needed: the SDK on the index (contract 0.5.0, the kit and both Terraform libraries 0.2.1, the test kit 0.1.12) carries every surface the plugin uses (T009) |
| T012 | 2026-11-22, in OKTA: `feature/008-relocate-okta-plugin` started by `git flow feature start` (git-flow-next 2.1.0) from the local `develop` at `e3d3f0a` (`Initial commit`, level with `origin/main`; `develop` is not on the remote). The operator's untracked `.gitignore` draft is kept in the working tree and copied to OKTA's `.git/csis-drafts-2026-11-22/gitignore`, out of git's view; T014 takes its lines. OKTA had no email of its own and would have committed under the global address: its local `user.email` is set to the noreply address, as THERE's is |
| T013 | 2026-11-22: a fresh clone of HERE at `f4e53e33` (T010's commit), its tags dropped, filtered by `uvx git-filter-repo` (a40bce548d2c) to `packages/okta-opa-plugin` and the eight Okta-only files of T004, renamed under `tests/instance/`: 88 commits, tip `a7d9486` ("Spec 008 phases 1 and 2"), every author and committer the noreply address. Merged into OKTA's branch with `--allow-unrelated-histories` as `11db2c9`. Not pushed |
| T014 | OKTA's `pyproject.toml`: a workspace of `packages/*` (never published, `Private :: Do Not Upload`); the `dev` group (the plugin's `[test]`, `cs-image-system-system[testing]>=0.1.11,<0.2`, the core plugins its fixture declares: packer, ansible, bash-mod, default-os, local-state, posix-identity, each `>=0.1.11,<0.2`; pytest, ruff, pyright, reuse, bump-my-version); the `instance` group naming the AWS family alone (`aws-runtime-plugin`, `tf-ebs-instance-plugin`, `tf-s3-state-plugin`, each `>=0.1.11,<0.3`), both groups installed by default (`default-groups`); `[tool.uv.sources]` for the plugin only; pytest's strict session and `--import-mode=importlib`, pyright standard. `REUSE.toml`, `LICENSES/Apache-2.0.txt`, `LICENSE`; `.gitignore` is the operator's draft unchanged (it equals THERE's). The plugin at 0.2.0, its `test` extra by range (`>=0.1.11,<0.2`), its URLs naming OKTA. `uv lock`: 84 packages, every system distribution from the index (0.1.12; the SDK 0.2.1, contract 0.5.0) |
| T015 | OKTA's `Justfile`: `init`, `build`, `test` (lint, typecheck, surface-check, pytest), `full-test` (`test`, then `scripts/full-test-legs`), `release` (`scripts/release`), and `lint-fix`, `typecheck`, `surface-check`, `pytest`, `golden-regen`, `public-safe`, in the Google Cloud family's shape. `just init` resolves from the index alone (`uv sync --locked`) |
| T016 | **Deviation, by reason**: the fixture `tests/instance/fixture/` is T002's copy whole, less its docker parts (the `docker-fixture` runtime, the `tofu-docker` instance builder, the `docker-volume` storage builder, the `pckr-docker` image builder, the `rh10-container` OS builder, `images/image5.yaml`, `storages/container.yaml`, the `container-test` instance, the `docker` executable), not the one-image, one-instance tree the task describes: the moved tests assert on the fixture's groups (`coops`, `tcmet`, `stofs`, `secofs`, `readers`), its two instances and its POSIX delegate, and the smaller tree would have rewritten their assertions (T019's rule: keep every assertion). Two AWS runtimes, the `local-dev` and s3 backends, `posix-local` and `pxgroup` stay. Personas synthetic as they were; the `.age-identity` committed on purpose as there; the README says what it is |
| T017 | `tests/instance/aws_stubs.py`: HERE's `_clouds` stubs (networking discovery, the vendor image query, image listing, retagging, the session command), `VPCS`, `VENDOR_AMI` and `record_network_facts`, its docstring naming it temporary until spec 007's phase 1 publishes `cs_image_system.aws_runtime.testing` |
| T018 | `tests/instance/conftest.py` (`FIXTURE`, `GOLDEN`, `STUBS = (aws_stubs.stub, okta_testing.credentials, okta_testing.stub, roots_testing.stub)`, the `okta_run`, `okta_root`, `fixture_dir` and `golden_dir` fixtures, the autouse logging isolation) and `tests/instance/harness.py`, which keeps HERE's harness names (`FixtureRun`, `copy_config`, `stub_environment`, ...) so each moved test reads as it did; a whole stubbed run of the fixture passes |
| T019 | The moved files import `harness` and `test_stale_attachments` instead of `tests.harness` and `tests.test_stale_attachments`; `test_bootstrap_okta.py` takes `_starter_copy` from `tests/instance/starter_support.py` (the installed system's `standard-aws` starter, rendered once per process). Two changes beyond imports: `test_bootstrap_okta.py`'s discovered sections are `github, aws, okta` here (no docker family is installed), and `test_workload_probe.py` leaves its fourth case (the starters' `opa-workload-probe` recipe) in HERE, by T004. The plugin's `test_module_objects.py` reads OKTA's golden. Each passes |
| T020 | 2026-11-22: 65 tests carried into 14 files under OKTA's `tests/instance/`, one per HERE file, each test body identical to HERE's (an AST comparison) but for imports: `test_identity_roots.py` 10 (the gid outputs through the shim, the structural read-model, the gated runner, a vanished group fails, an unmanaged group leaves state, the read-only builder, OPA paging, the 404 and missing-key refusals); `test_login_proof.py` 5 (the `sft` login: an expired session named, the client without a token, the team and address handed over, workload facts from the builder); `test_membership_removal.py` 5 (the sanctioned-removals file and its one reader); `test_stale_attachments.py` 5 and its helpers; `test_state_query_verdicts.py` 2 (the builder's real `query_state`: a 404 against an error, the module objects); `test_provider_aliases.py` 1 (the `AltNames` script); `test_identity_attributes.py` 3 (the read-only user builder refuses `managed: true`, the `managed` default, the probe step); `test_identity_leaves_core.py` 4 (the `workload` and `verify login` commands, the `OktaUser` profile fields, the workload-drift words); `test_posix_identity.py` 14 (the `sftd-token` renderer, the gid reference, the `posix:` delegate, the login hook, the accounts script in account names); `test_os_types.py` 1 (alpine refused); `test_emit_by_reference.py` 2; `test_bootstrap_coverage.py` 1 (the Okta section's BY HAND rows); `test_release_whole.py` 4 (the workload token) and its helpers; `test_load_failures.py` 1 (the plugin's `classify_failure`, counted in no group by T004, carried because nothing else in OKTA proves it). **Not carried, staying in HERE**: `test_container_runtime.py`'s Okta case (it needs the docker runtime); the sftd lines of `test_capabilities.py`, `test_image_tests.py` and `test_launch_playbook.py` (core seams by T004; OKTA holds that content through its byte-exact golden); every core, dummy, docker or starter case of the carried files. Two names imported privately from the kit (`power_state.RUNNING`, `launch_enrollment.registered_kinds`) are imported from the contract that defines them, the type check on installed packages refusing the re-export; nothing else changed. Open for T035/T036: the Okta builder's container objection has no test in OKTA without docker |
| T021 | `tests/instance/test_golden.py` (the emission against the golden; the fixture is Okta on AWS and nothing else) and `tests/regen_golden.py`; `just golden-regen` wrote 91 files |
| T022 | 2026-11-22, OKTA's golden (91 files) against T002's (117), file by file: **the 17 identity files are byte-identical** (`oktagroups` 9, `okta-tf-users` 3, `okta-groups-ro` 3, `run-identity.sh`, `.gitignore`), and so is `meta-state/identity.yaml`. 26 files are only in T002's: the `pckr-docker` bakes, the `tofu-docker` and `docker-volume` roots. Seven differ, each only by lines removed, every one the docker parts': `run-base-image.sh` (the `pckr-docker` bake line), `open-tofu-instance-generation.tf` (the `docker_volume` remote state), `run-instance-image.sh` and `run-storage.sh` (the docker roots' lines), `launch-params.yaml` (`container-test`), `state-locations.yaml` (`docker-volume`, `tofu-docker`), `storage.yaml` (`container_data`). No other difference |
| T023 | `tests/instance/test_broken_neighbour.py` and `tests/instance/test_leaves_the_process_alone.py`, in the Google Cloud family's shape; both pass |
| T024 | `tests/instance/test_qualified_words.py`: `okta-opa/okta-tf` and `okta-opa/okta-tf-ro` (the namespace HERE's `tests/test_registration_namespaces.py` names) load as their bare words do, for the two group builders and the user builder |
| T025 | `tests/test_aws_only_in_instance.py`: no file under `packages/` and no test outside `tests/instance/` imports the AWS family; the plugin's dependencies and `test` extra name none of its distributions; only the `instance` group names them |
| T026 | 2026-11-22, OKTA's `just test`: ruff clean, `reuse lint` compliant, pyright 0 errors, the surface check ("keeps to the surface"), **186 passed** under the strict session (71 the plugin's own, 115 instance, tooling and scope tests), the golden matching. The `standard-aws` leg moved to `tests/instance/starter/` (it uses the AWS family, which T025 holds to `tests/instance/`), and `norecursedirs` leaves it out of `just test`. `just full-test` passed: the low end of the ranges (the kit and both Terraform libraries 0.2.0, contract 0.5.0, the system and engine 0.1.11) 71 passed; `standard-aws` 1 passed |
| T027 | `scripts/full-test-legs`: the low end of the SDK ranges (the plugin from the checkout with its `test` extra, everything else `--resolution lowest-direct`, then its own tests), and `standard-aws` (`tests/instance/starter/test_standard_aws.py`, outside `just test`): rendered by the installed system's `init-config --from standard-aws`, loaded with the tree's own networks stubbed and dummy team credentials (T003), validated with no error and dry-run through every lifecycle, its identity roots emitted; it passed alone |
| T028 | The plugin's README: links into HERE's documents and packages point to HERE by URL at `develop`; the fixture and golden links to OKTA's; the configuration anchors to OKTA's `docs/CONFIGURATION.md`; an "Installing" section says `uv tool install 'cs-image-system[okta]'` and links HERE's operations guide |
| T029 | OKTA's `docs/CONFIGURATION.md`: HERE's section 9 Okta tables (the workspace, the `okta-tf` and `okta-tf-ro` group and user builders, the example), the one source from now; the example now carries the `posix:` field `okta-tf` requires, which HERE's example lacked. HERE's section 9 is replaced at T051 |
| T030 | OKTA's `README.md`: what the plugin is, how an operator installs it, how a plugin author builds and tests it, why the instance suite needs the AWS family and that it may change, how it releases |
| T031 | `.github/workflows/ci.yml`: on push to `develop` and every pull request, `ubuntu-24.04`, `extractions/setup-just@v4`, `astral-sh/setup-uv@v7`, OpenTofu (`tofu_wrapper: false`), `just init`, `just test`, `just public-safe`; a `lookup` job only on `workflow_dispatch` with `lookup: true`: `scripts/opa-lookup`, a read-only listing of the OPA team's resource groups that says their count and prints no credential, token or name, with the team's key pair from the secrets `TF_VAR_NOS_KEY` and `TF_VAR_NOS_SECRET` |
| T032 | `scripts/release`, from the Google Cloud family's: the probes (a clean checkout, the version, no tag, no version the index ever listed for `cs-image-system-okta-opa-plugin`, the token), the dry form, the bump, `uv lock`, `just full-test`, the build, the upload, then a commit only when something changed and the tag either way. `tests/tooling/test_release_refuses_a_held_version.py`: every 0.1.x the index lists is refused, 0.2.0 is free, an index that cannot be asked refuses; 3 passed |
| T033 | 2026-11-22, at the operator's word ("commit and push the Okta branch"): OKTA's branch committed as `0a85083` (177 files, the noreply address; `just public-safe` clean, 218 files), `develop` pushed to the remote first (`e3d3f0a`, level with `main`), then `feature/008-relocate-okta-plugin`. A fresh clone of the pushed branch from GitHub: `just init` exit 0 (every system distribution from the index), `just test` ruff clean, REUSE compliant, pyright 0 errors, the surface check passed, **186 passed** under the strict session. The quickstart's box clones `develop`, which holds the plugin only after T034's squash-merge; the branch is the same tree. CI runs on pushes to `develop` and on pull requests, so the branch push started no run |
| T034 | 2026-11-22, at the operator's word ("merge the Okta branch"): OKTA's branch squash-merged into its `develop` by `git flow feature finish --squash --keep --push` as `127bb13` (`git diff develop feature/008-relocate-okta-plugin` empty; the branch kept, local and remote). git-flow's own push timed out on GitHub's SSH port (environmental) and the retry pushed `develop`. OKTA's first CI run, [45031195914](https://github.com/infrastructurebuilder/cs-image-system-okta/actions/runs/45031195914), passed on a fresh `ubuntu-24.04`: REUSE compliant, pyright 0 errors, the surface check, **186 passed**, public-safe clean over 218 files; the dispatch-only `lookup` job skipped as it should; no Node.js 20 note. **Released 2026-11-22: 0.2.0 on TestPyPI, then PyPI**, each the wheel and the sdist. There was no upload token, so the operator chose trusted publishing, built in OKTA as its spec 001 (Spec Kit set up there the same day): a pushed `v<version>` tag runs OKTA's `Publish` workflow, which uploads to TestPyPI and then, for a final version, PyPI, with no token stored anywhere (OKTA's `docs/RELEASING.md`). The first tag on `314c4e5` failed before reaching an index (`uv publish` refuses `--index` with `--check-url`); with neither index holding 0.2.0, the tag was deleted and re-cut by `just release 0.2.0 pypi` (full-test passed) on the fixed `2b740f8`. Its run, [45041902604](https://github.com/infrastructurebuilder/cs-image-system-okta/actions/runs/45041902604), stopped once at TestPyPI's publisher entry (`invalid-publisher`), which the operator corrected; rerun, its `build`, `testpypi` and `pypi` jobs passed |
| T035 (part 1 of 2) | 2026-11-22, the operator's choice ("re-host the 77 now"): the core cases that need no server registry, re-hosted by three agents over 28 files, none importing the plugin or leaning on an Okta builder. **Vehicles**: POSIX (`pxgroup`, `imgfile-posix`, the `posix-local` and `posix-users` builders, a private copy where a subject must be POSIX now): the in-bake prerequisites and verification, the instance activation, the literal gid reaching the roots, group drift (`test_state_query.py`, all 16, its `world` stub on `PosixGroupBuilder`), the read model, a lost group, an unmanaged group, the login proof over `ssh_login`, a container runtime accepting a POSIX group; the dummy plugin (its user root for the runner's gating, its group builder for written-type parenting and the container objection); a test-declared enrollment kind (`loader.register_declared_kinds`, as spec 004's tests do) for launch parameters by reference and both launch forms; a test-local provider stub for identity attributes; the AWS and docker roots for state locations, backend binding, the flag-off refusal and root init arguments; the core gate functions alone for sanctioned removals. `test_committed_files.py`, `test_load_failures.py`, the pure cases of `test_hostname_claims.py` and `test_provider_aliases.py`, and `test_os_types.py`/`test_release_whole.py` needed nothing. **Waiting for spec 010 (part 2)**: 25 registry cases (`test_capabilities.py` 1, `test_hostname_claims.py` 8, `test_provider_aliases.py` 14, `test_login_proof.py` 2). **No vehicle, dropped when the plugin leaves**: `test_storage_state_machine.py::test_storage_root_consumes_gids_by_reference_only` (only an identity root that binds a state backend gives a gid by remote state; its literal half is held on POSIX), and the gated identity runner of `test_identity_roots.py` (POSIX and dummy emit no identity root; the Okta repository holds it). **For T036**: the Okta halves of four mixed tests have no copy in the Okta repository and are dropped by name (`test_runner_gating.py:161`, `test_state_backends.py:154`, `test_state_locations.py:54-66` and `:92`), each with its new core test beside it; the module-level Okta imports of `test_login_proof.py`, `test_membership_removal.py` and `test_state_query_verdicts.py` go with their Okta cases. **For T038**: if the POSIX fixture makes `posix-local` the default group builder, two parenting tests need other subjects. **Found**: the harness's Okta stub leaves `attribute_conflicts` unstubbed, so a test running the attributes probe reached the fixture's OPA host with the dummy credentials (HTTP 400, nothing changed); the new test stubs it |
| (registry) | **The operator's decision of 2026-11-22** (T004's finding): the core tests that need a group builder with a server registry are carried by the POSIX identity plugin, which gains a server registry. That is a feature of a shipping plugin, beyond this specification; it is specified on its own, and T035 waits for it |
| T035 (part 2 of 2) | 2026-11-23, by specification 010's T036 to T038, on the POSIX identity's recorded server registry (`meta-state/servers.yaml`, seeded through `tests/posix_world.py`), no Okta stub: `test_hostname_claims.py` 8 (the claim checks and the three retirements, read from the record), `test_capabilities.py` 1 (a dry run never asks the registry), `test_login_proof.py` 2 (the duplicate and silent registrations, now the core's check), `test_provider_aliases.py` 14 (the alias-pass hooks; the AltNames script's assertions read the entry's `alt_names`; four re-expressed for a registry kept in the records: no session command, no wait, an unregistered machine said not listed, a stopped machine's aliases recorded), and five more the re-hosting found leaning on Okta's registry: `test_canonical_names.py` 3, `test_alias_pool.py` 1, `test_generations.py` 1. 30 in all. None imports the plugin; `test_login_proof.py`'s Okta cases and its module-level `sft_login` import, and the pure test of Okta's alias script in `test_provider_aliases.py`, remain, and leave with the plugin (T036 onward) |
| T036 | 2026-11-23. The tests the Okta repository carries, found by name in its `tests/instance/` (an AST comparison) and removed here: 8 files whole (`test_bootstrap_okta`, `test_first_apply`, `test_group_release`, `test_identity_plan_in_mirror`, `test_new_group_gid`, `test_okta_identity_gids`, `test_workload_access`, and `test_login_proof`, whose four remaining Okta-world cases each have a POSIX twin in `test_login_proof_posix.py`) and 56 cases from 14 mixed files, 93 tests in all; the helpers they alone used went with them (one autouse fixture, `_identity` of `test_emit_by_reference.py`, mistaken for an orphan and restored). Then, with the plugin gone, four agents (one per group of files, none touching the fixture, the harness or core code) fixed the 118 failures of 49 files: bootstrap 46 passed, documents and tooling 333, runs and roots 198, identity 222. **Cases dropped without a home here**, each the plugin's own and carried in OKTA or re-hosted beside: in `test_identity_attributes.py` five (Okta's attribute rules and the three OPA-probe cases; the core path is the stub provider's case), in `test_identity_leaves_core.py` four (each with a re-hosted twin), `test_emit_by_reference.py`'s Okta user root case (the base-image case carries the rule), `test_capabilities.py`'s Okta launch parameters (the declared-kind case carries it), `test_container_runtime.py`'s OPA group on docker (the dummy builder's case carries it); and two assertions with no root left to host them: `test_in_process_steps.py`'s prune-attachments step and the generation-time `materialize .` (only the Okta user root emitted it), and `test_storage_state_machine.py`'s "no literal gid in storage IaC" (false by design now; it also never matched the quoted form). Two more stale expectations the checkpoint found (`test_portable_run_scripts.py`'s identity script, `test_state_encryption.py`'s nine backend files) were corrected |
| T037 | The passing mentions that became false, corrected with T036's fixes: the documents' links into the plugin's files point at OKTA's `develop` (checked to exist there), the operations guide states once that the plugin comes from its own repository, the local and S3 state plugins' READMEs show the docker roots' emission; the guard of `tests/test_core_names_no_runtime.py` is unchanged. The rest (the plugin named as a neighbour in package READMEs, CONFIGURATION.md's three links) are T049 to T052 |
| T038 | `tests/fixtures/config` is POSIX: `cfg/group-builders.yml` holds `posix-local` and `posix-users`, both the defaults; the groups `basic` (root, gid 3100), `coops` 3102, `stofs` 3103, `tcmet` 3104, `secofs` 3105 beside `pxgroup` 3101; `groups/group-lookup.yaml` removed; the base images declare `identity_types: [posix]`; the Okta agent's repository check (`os-builders.yml`) and `okta_gateway_selector` (`_config.yml`) gone; the comments describing live OPA state gone (two named what looked like real accounts). The users keep their ciphertexts: checked without printing them, all 19 names decrypt to their synthetic personas and all 10 addresses to example domains; they draw uids from the pool (3000 to 3018). The fixture's README follows. The AWS security group named OKTA-GATEWAY is the account's own and stays |
| T039 | `tests/harness.py`: no Okta stub, credential or OPA seam; its docstring names no Okta; `cs_image_system.okta_opa_plugin` is imported by no test (`grep -rln okta_opa_plugin` over packages, src, tests and scripts prints nothing) |
| T040 | `packages/okta-opa-plugin` removed (`git rm -r`); only ignored caches remain on disk, untracked |
| T041 | The root `pyproject.toml`: the `okta` and `all` extras name `cs-image-system-okta-opa-plugin>=0.2,<0.3`; its source entry, testpaths, pythonpath and pyright `extraPaths` removed; `extras.py`'s words keep the `okta` extra. Every sync is `uv sync --all-extras --no-extra gcloud --no-extra okta --no-extra all` (the Justfile's `init` and comments, `scripts/release.py`, the two guides, the release script's test: 28 spellings), and `scripts/with-released-families` lists `okta` beside `gcloud`. `uv lock` (run by hand: no Justfile target only locks) takes the plugin at 0.2.1 from the index for the extra alone; `just init` leaves it out |
| T042 | `.vscode/settings.json` lost the plugin's path (`tests/test_editor_paths.py` now counts a package root only when it has its own `pyproject.toml`) |
| T043 | By T003 (presence only): both workflows' live jobs gate on `AWS_ROLE_ARN` alone, and `just fixture-live` gets no Okta environment; `tests/test_ci_workflow.py` holds that no Okta credential appears in the job; the Justfile's comment on identity credentials removed. The starters that declare Okta (`standard-aws`, `complete`) are no longer rendered here; their check with the plugin from the index and dummy credentials is T047's |
| T044 | `just golden-regen shared`, read file by file against the copy kept before: 16 files removed (the 15 of the three Okta identity roots, `oktagroups` 9, `okta-groups-ro` 3, `okta-tf-users` 3, and `generated/identity/run-identity.sh`), 25 changed: the storage roots take literal gids (`coops` 3102, `stofs` 3103) and drop the `oktagroups` remote state; the instance roots take gid 3102 and an empty enrollment token, their user-data losing the agent's enrollment block; the bakes lose the Okta agent (its repository, install, dormant prerequisites, `tx.group` activation) and the POSIX login hook its `posix:` delegate needed, and gain the POSIX activation (each owning group made with its gid, a conflicting gid refused, the shadow tools checked), their fingerprints and assertion counts moving with them; `meta-state/identity.yaml` puts every group on `posix-local` (`config-time`), `readers` and the Okta user builder gone; `launch-params.yaml` carries no enrollment kind and the `posix` identity type; `state-locations.yaml` loses the three Okta workspaces. Nothing else moved (Constitution IV) |
| T045 | 2026-11-23. Quickstart step 2, box 1: `searched` alone. `just test`: lint clean, pyright 0 errors, 2,468 passed, 23 skipped, 2 failed (the two stale expectations of T036's last line, then fixed: those files 17 passed); the run stopped at pytest, so the isolated runs ran on their own: core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`. The whole run was not repeated for the two one-line fixes. `uv pip list` names no Okta package |
| T046 | `tests/test_extras.py::test_the_okta_and_all_extras_take_the_okta_plugin_by_its_series_range` (both extras name `cs-image-system-okta-opa-plugin` by `>=0.2,<0.3`) and `tests/test_package_metadata.py::test_no_manifest_pins_the_okta_plugin_exactly`; that a release bump moves no range was already held by `test_a_bump_moves_every_version_line_and_every_pin_at_once` (each pin equals its rule's, and a released-elsewhere distribution's rule is its range, Phase 4's change). 76 passed |
| T047 | `just test-cloud-starters` already takes its packages from `scripts/with-released-families`, which lists `okta` since T041, so the Okta plugin comes from the index there. `tests/cloud_starters/test_complete_starter.py`: `standard-aws` (its groups on Okta's builders) validates and dry-runs every lifecycle with the plugin from the index, emitting its `identity` root (`test_the_okta_starter_validates_and_dry_runs_every_lifecycle`), and `complete` carries an Okta group builder; the credentials are dummy ones (`stub_opa_credentials_from`), all T003 says a load needs. Under the strict session: 8 passed, none skipped |
| T048 | The release's released-elsewhere probe runs `with-released-families --check`, which reads every released-elsewhere extra, the `okta` one included since T041. `tests/test_release_probes.py::test_a_release_refuses_when_no_published_okta_plugin_meets_its_range`: an index holding the Google Cloud family's releases and none of the plugin inside its range refuses (exit 1), naming the plugin; one inside it passes. Which index the probe asks is specification 013's to move to TestPyPI (its R1) |
| (Phase 5, checkpoint) | 2026-11-23: `just test`: lint clean, pyright 0 errors, 2,473 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `just test-cloud-starters` (not a leg of `just test`) 8 passed, none skipped |
| T055 | `specs/007-relocate-aws-provider/research.md` R7 gains a "Landed" paragraph: the plugin is out of this repository, every fixture image is owned by a POSIX group, so `check_container_runtimes` holds none of them to AWS, and spec 007's phase 3 may now remove the cloud runtime the plugin's proofs rode on here (its order (a) holds once this specification is merged) |
| T056 | `plan.md` gains a Budget section by T001's method at three points (`0e73dedc`, `6bd23ee7`, `673dc6dd`): phases 4 and 5 took workspace packages 19 to 18 and source lines down by 4,203 (expected about 4,150), test functions by 177, test lines by 3,758, the shared golden by 16 files; the reasons are given there |
| T059 (steps 1 and 2) | 2026-11-23. **Step 1**: a fresh clone of OKTA's `develop` (at `262ab26`, "release 0.2.1") into the session's scratch directory, `just init` and `just test`: 190 passed. **Step 2**: T045's (box 1 `searched`; `just test` as recorded there and again at phase 5's checkpoint: 2,473 passed, every isolated run `0 skipped`). **Step 3** is the reference's `just config-drift`, after T057's release: T058's, the operator's |
| T049 to T054 | 2026-11-23, delegated to one agent (documents only) and read back here; every link into the Okta repository was checked against its `develop` tree. Installing the plugin is stated once, in `docs/OPERATIONS.md` ("Installing a release", the paragraph "The Okta identity plugin comes from its own repository too", which also says a tree that declares Okta still needs its credentials where it is validated or run), linked from `README.md`, `docs/PLUGINS.md`, `docs/DESCRIPTION.md`, `docs/DAILY_DRIVER.md` (1.1 and 9), `docs/CI_RUNNER.md`, `docs/CONFIGURATION.md` 9 and the POSIX plugin's README (FR-009). **T049**: README, PLUGINS, DESCRIPTION, DESIGN (N7, 3D, N20 qualified: a POSIX gid is the declared literal), GLOSSARY, WRITING_A_PROVIDER (`OktaTypes` linked in the Okta repository). **T050**: DAILY_DRIVER, OPERATIONS (the fixture POSIX, the live job asks no Okta credential), CI_RUNNER (the Okta credentials scoped to a tree that declares Okta). **T051**: CONFIGURATION 9 keeps a short description of each Okta builder and links sections 1 to 4 of the Okta repository's `docs/CONFIGURATION.md`; the fixture quotes in 2.4, 5.4, 9.4, 10 and 11.5 follow the POSIX fixture. **T052**: the POSIX plugin, tofu-roots, hashicorp-utils, tf-ebs-instance, packer and dummy plugins' READMEs (system, engine, base already right; aws-runtime, tf-s3-state, default-os, local-state had nothing false). **T053**: `docs/examples/_skeleton/CI_SETUP.md` 3.5 and 3.7: the Okta secrets serve a tree that declares Okta groups (`standard-aws`, `standard-gce`, `complete`), never this repository's CI. **T054**: `docs/INCIDENTS.md`'s 15 links point at the Okta repository, no other word changed; `docs/CHANGES.md` had none. The docs tests 144 passed, three more files reading the guides 19, `just lint` clean. **Found, and fixed in this phase** (the operator: "fix the found issues before we move on"; see the row below): `docs/OPERATIONS.md`'s `full-test` paragraph saying identity credentials are not gated (T003 found a missing `TF_VAR_<team>_*` pair fails the load); the starters' YAML comments citing CONFIGURATION 9 for Okta fields (it now links onward); and a code comment the storage and instance roots emit, "gids by remote-state reference", above what is now a literal POSIX gid |
| T060 | `spec.md`'s status line and `specs/README.md`'s row say in progress: phases 1 to 6 implemented, phases 4 to 6 not merged; T057 and T058 the operator's |
| (the found issues) | 2026-11-23, fixed in phase 6 at the operator's word, no later specification. (1) The storage roots stamped every module call "(gids by remote-state reference)" whatever the gid was: `TofuStorageBuilderBase.gid_note` now says what each allowed group's gid is ("gids literal", "gids by remote-state reference", or both), read from the group builder's own expression; `just surface-record` holds the new member (an addition; the Terraform libraries stay 0.2.2, unreleased). The instance user-data's and the Ansible subtree task's "(gid by reference)" now say "(gid from the template's group_gid)" and "(gid from group_gid)", true whichever identity supplies the number. Both goldens regenerated and read: the shared one and the docker family's changed only in those comment lines and the user-data hashes that cover them. (2) `docs/OPERATIONS.md`'s `full-test` paragraph says what T003 found: without `TF_VAR_<team>_key` or `_secret` the Okta plugin refuses a load that declares Okta (exit 2), without `OKTA_API_*` it warns and skips its user root's plan. (3) The `standard-aws`, `standard-gce` and `complete` starters' headers point at the Okta repository's `docs/CONFIGURATION.md` for the Okta builders' fields; their inline 9.1 to 9.3 markers still resolve to CONFIGURATION.md's kept headings. The Okta repository's own byte-exact golden will take the user-data comment when it next takes this repository's release |
| (Phase 6, checkpoint) | 2026-11-23, after T049 to T056, T060 and the found issues: `just test`: lint clean, pyright 0 errors, 2,473 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `just surface-check` clean |

---

## Phase 1: Setup

**Purpose**: the before-state, and the one open point of the plan.

- [X] T001 Record HERE's before-figures in the Records table of `specs/008-relocate-okta-plugin/tasks.md` with spec 005's method (its T002): source lines, test lines, tests, shared golden files, workspace packages; and the plugin's own (source lines, the 11 test files under `packages/okta-opa-plugin/tests` and their test count)
- [X] T002 [P] Keep the shared golden before the move as the comparison's left side: record the branch's start commit and `git rev-parse <commit>:tests/fixtures/golden` and `<commit>:tests/fixtures/config` in the Records table, recoverable with `git archive <commit> tests/fixtures/golden tests/fixtures/config`
- [X] T003 [P] Settle research R5's open point: read what `cs_image_system.okta_opa_plugin`'s workspace asserts at load and under `validate --online` (does it only read that `OKTA_API_PRIVATE_KEY`, `TF_VAR_<team>_key` and `_secret` are set, or does it call the OPA team?); record the answer and the lines it rests on in the Records table; it decides T043
- [X] T004 [P] Classify every test file in HERE that names Okta, in the Records table, as **Okta-only** (moves to OKTA; today among the 27 that import the plugin: `test_bootstrap_okta.py`, `test_identity_roots.py`, `test_login_proof.py`, `test_group_release.py`, `test_new_group_gid.py`, `test_stale_attachments.py`, `test_membership_removal.py`, `test_workload_access.py` and others), **mixed** (a core behaviour proven through Okta: re-hosted on POSIX by T035, its Okta cases carried by T020) or **passing mention** (T037); and for each mixed file, the core seam it proves (research R4)

---

## Phase 2: Foundational (prepare here)

**Purpose**: the plugin ready to leave while still in HERE. Blocks every
story.

- [X] T005 [P] Turn the plugin's exact SDK pins into ranges in `packages/okta-opa-plugin/pyproject.toml` (`cs-image-system-base>=0.2,<0.3`, `cs-image-system-hashicorp-utils>=0.2,<0.3`, `cs-image-system-tofu-roots>=0.2,<0.3`); `uv lock`; `just init` (data-model.md: "Ranges only")
- [X] T006 Move the Okta stubs out of `tests/harness.py` (`_credentials`' Okta lines, around 176-180; `_identity_provider`, around 216-228, with its retirement journal) into `packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/testing.py` (new) as `credentials(monkeypatch)` and `stub(monkeypatch, retirements)`, in the shape of `cs_image_system.gcloud_runtime.testing` before it left; `tests/harness.py` calls them, unchanged in behaviour
- [X] T007 [P] Make the plugin's four tests that import `from harness import bare_run` (`test_group_module_call.py`, `test_group_ro_builder_root.py`, `test_user_builder_root.py`, `test_user_ro_builder_root.py` under `packages/okta-opa-plugin/tests/`) import it from `cs_image_system.hashicorp_utils.testing`, where the harness takes it from
- [X] T008 Give `packages/okta-opa-plugin/pyproject.toml` a `[project.optional-dependencies] test` extra naming `cs-image-system-system[testing]` and the core plugins its tests need, and a `[tool.pytest.ini_options]` with its own `testpaths` and `--import-mode=importlib`, in the shape of `packages/docker-plugin/pyproject.toml`
- [X] T009 Add `packages/okta-opa-plugin/tests/test_keeps_to_the_surface.py` (in the shape of `packages/docker-plugin/tests/unit/test_keeps_to_the_surface.py`, `own` naming `cs_image_system.okta_opa_plugin`); fix any finding in the plugin's source; record whether a surface addition to the SDK is needed
- [X] T010 Checkpoint: `just test` passes in HERE, the isolated runs each with `0 skipped`; `git status --short tests/fixtures` prints nothing; record it
- [X] T011 **RELEASE**, only if T009 found a surface the published SDK lacks (the operator's): HERE's next release publishes it; otherwise record "not needed: the SDK on the index (contract 0.5.0, kit and Terraform libraries 0.2.0, test kit 0.1.11) carries every surface the plugin uses" and go on

**Checkpoint**: the plugin ranges on the published SDK and keeps to its
surfaces; its stubs are its own.

---

## Phase 3: User Story 1 - The Okta plugin builds, tests and releases from its own repository (Priority: P1) 🎯 MVP

**Goal**: a fresh clone of OKTA passes its acceptance tests against
published releases, with nothing skipped, and releases the plugin.

**Independent Test**: quickstart step 1.

### History and layout

- [X] T012 [US1] In OKTA, start `feature/008-relocate-okta-plugin` from the local `develop` (`e3d3f0a`, not on the remote; the remote holds `main` only); record both
- [X] T013 [US1] In a fresh clone of HERE at T010's commit (never HERE's working tree), run `uvx git-filter-repo` keeping `packages/okta-opa-plugin` and the Okta-only test files of T004, renaming those under `tests/instance/`; merge the result into OKTA's branch with `--allow-unrelated-histories`, under the noreply email set for OKTA (`git config user.email`, never `-c user.email`); record the filtered history's commit count and tip
- [X] T014 [US1] Write OKTA's `pyproject.toml`: a workspace of `packages/*`; the dev group (pytest, ruff, pyright, reuse, bump-my-version, `cs-image-system-system[testing]>=0.1.11,<0.2`, the core plugins the suites declare); a dependency group `instance` naming the AWS family alone (`cs-image-system-aws-runtime-plugin`, `cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin`, each `>=0.1.11,<0.3`); `[tool.uv.sources]` for the plugin only, never a path into HERE; pytest and pyright settings with `-p cs_image_system.system.testing.strict`; its `REUSE.toml`, `LICENSES/`, `.gitignore`; the plugin's version moved to 0.2.0 (data-model.md: "its own line from 0.2.0")
- [X] T015 [US1] Write OKTA's `Justfile` with the five lifecycle targets as contracts/okta-repository.md states them, plus `golden-regen`, `surface-check` and `public-safe`, in the shape of `cs-image-system-google-cloud`'s; `just init` resolves from the index alone

### The instance suite

- [X] T016 [US1] Build OKTA's fixture `tests/instance/fixture/` from T002's copy: one AWS runtime and the s3 backend the shared fixture binds the identity roots to, the Okta group builders (`oktagroups`, `okta-groups-ro`, `okta-tf-users` of `cfg/group-builders.yml`), `groups/test-group.yaml`, `groups/group-lookup.yaml` and the users they name, one image owned by an Okta group, one instance launched from it, and the core builders those need (packer, ansible, default-os); personas synthetic on `example.invalid`; the `.age-identity` handling of `packages/docker-plugin/tests/fixture`
- [X] T017 [US1] Add `tests/instance/aws_stubs.py` to OKTA: a copy of the AWS stubs of HERE's `tests/harness.py`, its docstring naming it temporary until spec 007's phase 1 publishes `cs_image_system.aws_runtime.testing`, which replaces it (research R3)
- [X] T018 [US1] Write `tests/instance/conftest.py` in OKTA in the shape of `cs-image-system-google-cloud/tests/pipeline/conftest.py`: `FIXTURE`, `GOLDEN`, `STUBS = (aws_stubs.stub, okta_testing.credentials, okta_testing.stub, roots_testing.stub)`, the run, stubs and root fixtures, the autouse logging isolation
- [X] T019 [US1] Make the moved Okta-only tests (`tests/instance/test_*.py` from T013) run on OKTA's conftest and the test kit instead of HERE's `tests/harness.py`, keeping every assertion
- [X] T020 [US1] Carry to `tests/instance/` the Okta cases of HERE's mixed files (T004) that prove the plugin's own behaviour, one test file per HERE file it came from, each named in the Records table with what it asserts: enrollment at launch (`sftd-token`), activation in the bake, the login proof, the server aliases, the gid shim, stale attachments (FR-004)
- [X] T021 [US1] Add `tests/instance/test_golden.py` and `tests/regen_golden.py` to OKTA in the shape of the Google Cloud family's, and generate `tests/instance/golden/` once with `just golden-regen`
- [X] T022 [US1] Compare OKTA's golden with T002's copy file by file: the 14 identity files (`generated/identity/oktagroups` 8, `okta-tf-users` 3, `okta-groups-ro` 3), `generated/identity/run-identity.sh` and `meta-state/identity.yaml` with the files of the same path, and the Okta lines of the bakes (`generated/*/pckr-ebs-ans/...`), the instance roots (`generated/instance-image/open-tofu/...`) and `meta-state/launch-params.yaml` and `state-locations.yaml` with the plugin's; each difference must follow from the smaller fixture (a group, image or instance it does not declare); record every file's result; any other difference is a defect to fix, not to accept (Constitution IV)
- [X] T023 [P] [US1] Add `tests/instance/test_broken_neighbour.py` and `tests/instance/test_leaves_the_process_alone.py` to OKTA in the shape of the Google Cloud family's
- [X] T024 [P] [US1] Add `tests/instance/test_qualified_words.py` to OKTA: a configuration that writes the plugin's words (`okta-tf`, `okta-tf-ro`) qualified by its namespace, as `tests/test_registration_namespaces.py` in HERE names it, loads, and so does one that writes them bare (spec story 3, scenario 2)
- [X] T025 [P] [US1] Add `tests/test_aws_only_in_instance.py` to OKTA: no file under `packages/` and no test outside `tests/instance/` imports `cs_image_system.aws_runtime`, `tf_ebs_instance_plugin` or `tf_s3_state_plugin`, and the plugin's `[project.dependencies]` and `test` extra name none of the AWS family's distributions (FR-004)

### Its acceptance tests, its documents, its CI

- [X] T026 [US1] Make OKTA's `just test` pass: lint, type check at zero errors, the surface check, `packages/okta-opa-plugin/tests` and `tests/instance` with the golden, under the strict session; record the counts
- [X] T027 [US1] Add OKTA's `full-test` legs: the low end of the SDK ranges (`uv sync --resolution lowest-direct`, then the plugin's own tests and the surface check), and `standard-aws` rendered with `init-config`, validated and dry-run with the system and the AWS family from the index and the plugin from the checkout, with the credentials T003 says a load needs; a leg whose tool is absent fails
- [X] T028 [P] [US1] Correct `packages/okta-opa-plugin/README.md` in OKTA: every relative link into HERE points to OKTA's own file or to HERE by URL at `develop`; the install section says `uv tool install 'cs-image-system[okta]'` and links HERE's operations guide
- [X] T029 [P] [US1] Move the Okta field tables (the `okta-tf` and `okta-tf-ro` group and user builders, their fields) from HERE's `docs/CONFIGURATION.md` into OKTA's `docs/CONFIGURATION.md`, the one source from now (Constitution VIII); HERE's sections are replaced by T051
- [X] T030 [P] [US1] Write OKTA's `README.md` (what the plugin is, how an operator installs it, how a plugin author builds and tests it, why the instance suite needs the AWS family and that it may change), replacing the stub
- [X] T031 [US1] Add OKTA's `.github/workflows/ci.yml`: on push to `develop` and every pull request, a fresh `ubuntu-latest` runner, `astral-sh/setup-uv`, OpenTofu with `tofu_wrapper: false`, `just init`, `just test`, `just public-safe`; a read-only lookup against the OPA team only by `workflow_dispatch`, with the Okta triple as secrets (contracts/okta-repository.md)
- [X] T032 [US1] Add OKTA's `release` target in the shape of the Google Cloud family's `scripts/release` (it commits only when there is a change, and tags either way): moves the plugin's version, runs `just full-test`, builds the wheel, refuses a version the index ever held for `cs-image-system-okta-opa-plugin` (every 0.1.x), publishes to the index named; test its refusal in `tests/test_release_refuses_a_held_version.py` against a stubbed index answer
- [X] T033 [US1] Checkpoint: quickstart step 1 passes from a fresh clone of OKTA's branch pushed to the remote (the operator's word to push; `develop` goes to the remote first); record each leg
- [X] T034 [US1] **RELEASE** (the operator's): squash-merge OKTA's branch into its `develop` (branch kept) and cut 0.2.0 to TestPyPI, then PyPI; record the version and the index's answer; stop until it exists

**Checkpoint**: the plugin is on the index at 0.2.0, released from its
own repository.

---

## Phase 4: User Story 2 - This repository no longer holds the Okta plugin (Priority: P2)

**Goal**: HERE's acceptance tests pass with no Okta package, credential
or OPA team, and nothing here imports the plugin.

**Independent Test**: quickstart step 2.

### Tests re-hosted and trimmed

- [X] T035 [US2] Re-host on the POSIX identity plugin (`packages/posix-identity-plugin`) or the test kit the core identity seams T004's mixed files prove through Okta, keeping what each asserts (research R4): the enrollment kinds a plugin declares (spec 004's tests), a group builder's launch parameters, a login proof a builder offers, group release, alias pools, hostname claims, canonical names, generations; record each file's vehicle in the Records table (spec story 2, scenario 2)
- [X] T036 [US2] Remove from HERE the Okta-only files T013 carried (`git rm`), and the Okta cases T020 carried and the Okta part of every other mixed file, keeping each file's other assertions; a case dropped without a home in OKTA is named in the Records table with its reason
- [X] T037 [P] [US2] Correct the passing mentions (T004) where they become false; the guard regex of `tests/test_core_names_no_runtime.py` stays

### The shared suite, the package, the manifests

- [X] T038 [US2] Make the shared fixture's identity POSIX in `tests/fixtures/config`: `cfg/group-builders.yml` loses `oktagroups`, `okta-groups-ro` and `okta-tf-users`; `groups/test-group.yaml`, `groups/group-tcmet.yaml` and `groups/users.yaml` become POSIX groups and users, each group with a gid and synthetic personas on `example.invalid`; `groups/group-lookup.yaml` is removed; the Okta lines of `cfg/_config.yml`, `cfg/os-builders.yml` and `cfg/runtime-builders.yml` go; the fixture's README follows (FR-006)
- [X] T039 [US2] Remove the Okta stubs' call and the Okta words of the docstrings from `tests/harness.py` (lines 13, 15-16, 23), and `cs_image_system.okta_opa_plugin` from every remaining test import
- [X] T040 [US2] Remove `packages/okta-opa-plugin` from HERE (`git rm -r`)
- [X] T041 [US2] Correct the root `pyproject.toml`: the `okta` and `all` extras name `cs-image-system-okta-opa-plugin>=0.2,<0.3` (lines 57-58, 68); remove its `[tool.uv.sources]` entry (107), `testpaths` (200), `pythonpath` (230) and pyright `extraPaths` (332); the WORDS table of `src/cs_image_system/extras.py` (lines 44, 94-96) keeps the `okta` extra; `uv lock`; `just init`
- [X] T042 [P] [US2] Correct `.vscode/settings.json` (line 20) to match the pyright `extraPaths` (held equal by `tests/test_editor_paths.py`)
- [X] T043 [US2] By T003's answer: if a load needs only the triple's presence, remove the Okta triple's gates and environment from `.github/workflows/ci.yml` (lines 196-198, 207, 212, 265-267) and `.github/workflows/ci-from-scratch.yml` (79-81, 90, 95, 169-171), and have the starters' check set dummy values; if it needs the real triple, keep them for the starters' check alone and correct the spec's edge case ("this repository's CI stops asking for the Okta secrets") to say so; in both cases `fixture-live` in `Justfile` (and its comment at line 69) no longer needs it
- [X] T044 [US2] Regenerate the shared golden (`just golden-regen shared`) and read every change file by file against T002's copy: the 14 identity files and `generated/identity/run-identity.sh` gone; `meta-state/identity.yaml` holding the POSIX groups; the Okta enrollment and activation lines of the bakes and instance roots replaced by the POSIX ones; nothing else; record each in the Records table (Constitution IV)
- [X] T045 [US2] Checkpoint: quickstart step 2 passes; `just test` passes with the isolated runs each `0 skipped`; `uv pip list` in HERE's environment does not name the plugin; record it

**Checkpoint**: HERE holds no Okta code and passes without it.

---

## Phase 5: User Story 3 - An operator sees no difference (Priority: P3)

**Goal**: with the plugin installed from its release, every command
behaves and emits as before.

**Independent Test**: quickstart step 3, and OKTA's starter leg (T027).

- [X] T046 [US3] Test in `tests/test_extras.py` that the `okta` and `all` extras name `cs-image-system-okta-opa-plugin` by `>=0.2,<0.3` and that a release bump moves no range; and in `tests/test_package_metadata.py` that no workspace manifest names it by an exact pin (FR-007)
- [X] T047 [US3] Extend spec 005's `just test-cloud-starters` (its T056) so the starters that declare Okta groups (`standard-aws`, `complete`) render, validate and dry-run with the plugin from the index, with the credentials T003 says they need; every step ran and succeeded, or the recipe fails; record it
- [X] T048 [US3] Make a release here refuse when the `okta` extra's range is satisfied by no published release of the plugin (beside spec 005's T058 probe in `scripts/release.py`, tested in `tests/test_release_probes.py`)

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T049 [P] Correct HERE's `README.md`, `docs/PLUGINS.md`, `docs/DESCRIPTION.md`, `docs/DESIGN.md`, `docs/GLOSSARY.md` and `docs/WRITING_A_PROVIDER.md`: the plugin lives in OKTA, is installed by the `okta` extra, and the shared golden's identity is POSIX
- [X] T050 [P] Correct `docs/DAILY_DRIVER.md`, `docs/OPERATIONS.md` and `docs/CI_RUNNER.md`: installing the plugin is stated once, in the operations guide, and linked from the others (FR-009)
- [X] T051 [P] Correct `docs/CONFIGURATION.md`: the Okta builders keep a short description and link OKTA's tables (T029)
- [X] T052 [P] Correct the other packages' READMEs that name the plugin as a neighbour: `packages/posix-identity-plugin/README.md` ("beside Okta"), `packages/system/README.md`, `packages/engine/README.md`, `packages/base/README.md`, `packages/tofu-roots/README.md`, `packages/hashicorp-utils/README.md`, `packages/aws-runtime-plugin/README.md`, `packages/tf-ebs-instance-plugin/README.md`, `packages/tf-s3-state-plugin/README.md`, `packages/default-os-plugin/README.md`, `packages/packer-plugin/README.md`, `packages/local-state-plugin/README.md`, `packages/dummy-plugin/README.md`
- [X] T053 [P] Correct `docs/examples/_skeleton/CI_SETUP.md` and the starters' CI setup where it says the Okta secrets serve this repository's CI (by T043's outcome)
- [X] T054 [P] Point the links of `docs/CHANGES.md` and `docs/INCIDENTS.md` into the plugin's files at OKTA, changing no other word
- [X] T055 [P] Add a note to spec 007 where its research R7 says the Okta plugin moves out, pointing to `specs/008-relocate-okta-plugin`, and record there that spec 007's phase 3 may now remove the cloud runtime the plugin's proofs rode on
- [X] T056 Measure the budget again with T001's method and add a Budget section to `specs/008-relocate-okta-plugin/plan.md` with the actual figures beside the expected ones (workspace packages −1; source lines about −4,150), with a reason for any figure outside its range
- [ ] T057 **RELEASE** (the operator's): HERE's release without the plugin; T048's probe passes; record its version
- [ ] T058 In REF: take T057's release (`just take`), and run `just config-drift`; expect exit 0 with no change of the tree's own and no identity root planning a change to any OPA group or user (quickstart step 3; SC-003); correct `CI_SETUP.md` and `README.md` where they say the plugin comes from HERE; record it
- [ ] T059 Walk `specs/008-relocate-okta-plugin/quickstart.md` steps 1 to 3 and record each result in the Records table
- [X] T060 Bring the specification's files up to date: the status line of `specs/008-relocate-okta-plugin/spec.md`, and the row for 008 in `specs/README.md`

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
