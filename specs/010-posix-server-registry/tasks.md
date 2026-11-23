# Tasks: Every machine and every id recorded once, by an identity the system ships

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md),
[data-model.md](data-model.md), [contracts/registry-and-ids.md](contracts/registry-and-ids.md),
[quickstart.md](quickstart.md)

**Tests**: requested. The specification ends in executable acceptance
(Constitution II) and its quickstart names the test files; each story's
tests are written first and must fail before its code.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US7)

## Working rules

- `HERE` is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-3`; `REF`
  is `/Volumes/MiniSSD/git/Work/Lynker/cs-image-system-testconfig`
  (its `develop`, caught up first; never `main`).
- **The branch's base, the operator's word of 2026-11-22 ("010 from 008's
  branch")**: this specification and specification 008's re-hosting (its
  T035, part 1) live on `feature/008-relocate-okta-plugin`, not yet on
  `develop`, so `feature/010-posix-server-registry` starts from that
  branch's tip. It is squash-merged into `develop` first, its squash
  message naming the specification 008 work it carries;
  `feature/008-relocate-okta-plugin` then takes `develop` and goes on.
- Run Python as `uv run --no-sync python`; iterate with `just test-one
  <paths>`; the acceptance tests are `just test` at every checkpoint.
- **Nothing is written to Okta or OPA** (D2), and no test reaches either:
  every Okta call a test makes is stubbed. Never echo a credential.
- **The golden is the tripwire.** `git status --short tests/fixtures`
  prints nothing after a task unless the task says the golden moves; a
  moved golden is read file by file and recorded (Constitution IV).
- **The contract has its own version.** Every change to
  `packages/contract` is in T005's 0.5.1 (planned as 0.6.0, plan D7); a later change needs its own
  bump.
- **Releases are the operator's.** A task marked **RELEASE** stops.
- A new file in a new folder needs `git add -N` before `just lint`.

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |
| T001 | 2026-11-22: `feature/010-posix-server-registry` started by `git flow feature start 010-posix-server-registry feature/008-relocate-okta-plugin` at `d926b52f` (spec 008's branch's tip: its phases 1 to 3, its T035 part 1, and this specification's plan) |
| T002 | Before-figures at `d926b52f`, by spec 005's method (tracked `.py` under `src/`, tests outside fixtures, `def test_` functions): source lines 54,308; test lines 47,106; test functions 2,040; shared golden files 117 (tree `023d09a5`, unchanged since spec 008's start); workspace packages 19. Contract 0.5.0: `GroupBuilderProtocol` 40 own members, `UserBuilderProtocol` 7, `MetaStateProtocol` 12 |
| T049 (branch) | 2026-11-22, in `cs-image-system-okta`: `cs-image-system-contract>=0.5,<0.7` (was `<0.6`); `just full-test` passed (190; the low end 71; `standard-aws` 1); squash-merged as `21fdfef`, branch `feature/010-contract-range` kept; CI [45080935746](https://github.com/infrastructurebuilder/cs-image-system-okta/actions/runs/45080935746) passed (190, pyright 0 errors, public-safe clean). The 0.2.1 release is T052's |
| T050 | 2026-11-22, in `cs-image-system-google-cloud`: the three packages take `>=0.5,<0.7`; trusted publishing ported from `cs-image-system-okta` (`.github/workflows/publish.yml` for the three, the tag checked against the runtime's version; `scripts/release` tagging without a token and refusing a version either index held for any of the three; `tests/tooling/test_publish_commands_parse.py` and the held-version tests; `docs/RELEASING.md` naming the three projects, the repository and a fork's steps; the README and Justfile pointing at it). `just test` 167 passed, `full-test` passed at both ends, public-safe clean; the dry form `just release patch pypi yes` plans 0.2.1, free on both indexes, published by the tag's push. Squash-merged as `8dfd79e`, branch `feature/010-contract-range` kept; CI [45081553767](https://github.com/infrastructurebuilder/cs-image-system-google-cloud/actions/runs/45081553767) passed (167, pyright 0 errors, public-safe clean) |
| T051 | 2026-11-23, by the operator: the trusted publishers for `cs-image-system-gcloud-runtime-plugin`, `cs-image-system-tf-gcp-plugin` and `cs-image-system-gcs-state-plugin` on pypi.org (`pypi`) and test.pypi.org (`testpypi`), and the two environments in `cs-image-system-google-cloud` |
| T049, T052 | **Released by the operator, by the tag's push, no upload token**: the Okta plugin 0.2.1 (tag `v0.2.1` on `2274f16`, Publish run [45082704132](https://github.com/infrastructurebuilder/cs-image-system-okta/actions/runs/45082704132), 2026-11-22) and the Google Cloud family 0.2.1 (tag `v0.2.1` on `53e01ad`, run [45162122991](https://github.com/infrastructurebuilder/cs-image-system-google-cloud/actions/runs/45162122991), 2026-11-23; its first-ever trusted publish). Both indexes hold each version's wheel and sdist, read from each version's own page and the simple index (the project pages lagged a few minutes). Every family released elsewhere now takes `cs-image-system-contract>=0.5,<0.7` |
| T004 | The contract's additions, by [contracts/registry-and-ids.md](contracts/registry-and-ids.md): `keeps_recorded_registry`, `record_aliases`, `id_pool` on `GroupBuilderProtocol`; `id_pool` on `UserBuilderProtocol`; `query_instance_identity`'s optional `address` (docstring); `Claim.identity` and `Claim.external`; six members on `MetaStateProtocol` ("eighteen members") |
| T005 | 2026-11-23, after T052: the contract at 0.6.0 (its README's version table and the dependents' range line), every workspace dependent's range `cs-image-system-contract>=0.6,<0.7` (18 manifests), the kit's README's range; `UV_REFRESH=1 uv lock` takes the Google Cloud family at 0.2.1; `just init` |
| T006 (code) | The kit's defaults: `keeps_recorded_registry` False, `record_aliases` None, `id_pool` None on `GroupBuilderBase`, `id_pool` None on `UserBuilderBase`; `just surface-record` (four entries added to the kit's baseline; the Terraform libraries' unchanged); the kit's and the Terraform libraries' LAST bumps follow in their own commit (`just sdk-bump` needs a clean tree) |
| T007 | `SERVERS` (`servers.yaml`) and `IDS` (`ids.yaml`) in `meta_ledgers.py` and `ALL_FILES`; the six members in the engine's `MetaState`: entries keyed by `instance_id`, sorted by hostname, address, id; an unreadable `servers.yaml` answers None and every write and retirement over it raises; `record_ids` refuses a changed id for a current or retired name, naming both |
| T008 | Three cases in `tests/test_meta_state.py`: record, replace by `instance_id`, aliases, retire by hostname; an unreadable registry is None and refuses writes and retirements; a recorded id never changes for a current or a retired name; 15 passed |
| T009 | `address` in both runtimes' `query_instance_identity`: AWS's `PrivateIpAddress`, docker's address on its network (`NetworkSettings.IPAddress`, else the first network's); `tests/test_instance_identity_address.py` (new, AWS) and the docker family's identity test; 18 passed. Lint clean, pyright 0 errors, `just surface-check` clean |
| T005 (again) | 2026-11-23, the operator's rule that versions move only their third number (plan D7; "make the contract 0.5.1 after the run"): the contract is 0.5.1, not 0.6.0, and the 18 dependents' ranges are back on `>=0.5,<0.6`; the contract README's 0.5.1 row says why, and a dated note suspends its MINOR rule while the patch-only rule holds. `uv lock` (contract 0.6.0 -> 0.5.1), `just init`; the contract, metadata, extras and records tests 164 passed. The checkpoint run on 0.6.0 had shown the code sound (2,624 passed, pyright 0 errors, the core and high-end isolated runs passed) and failed only at the Terraform libraries' low end, whose published 0.2.0 requires the contract below 0.6 |
| T006 (bumps) | `just sdk-bump kit last` (0.2.1 -> 0.2.2, `05e52da3`) and `just sdk-bump terraform last` (0.2.1 -> 0.2.2, `97e11821`), each with its exact pins: the kit's and the Terraform libraries' dependency on the contract changed, so their published 0.2.1 no longer match what the tree builds |
| T010 | 2026-11-23, on contract 0.5.1 (`5d5b68fa`): `just test` lint clean, pyright 0 errors, 2,624 passed, 23 skipped; the isolated runs each `0 skipped`: core 377; the Terraform libraries 6, 37 and 6 (the low end, which failed on 0.6.0, passes); docker 62, 62 and 38; `git status --short tests/fixtures` printed nothing |
| T011 | `tests/test_recorded_ids.py` (new): the eight scenarios as ten pure cases of `resolve_posix_ids` (the POSIX fallback and the external collisions each split in two), plus one through `validate`'s `check_posix_ids` over a fixture copy whose `meta-state/ids.yaml` records `pxgroup` as 3102 (refused, naming 3102, 3101 and "does not change"; no network). **Deviation**: the external identity is stood in for by claims marked `external=True`, not by a stub builder registered through the test kit; that builder is built with T022, whose "a second external identity joins with no core change" is where it matters. Run before T012: they failed |
| T012 | `posix_ids.py`: recorded ids first and never moved; an external id stands and the POSIX identity defers to it (`defers`), a different declared id is refused saying which it must be; two external identities that disagree, by name or by id, are a configuration error; a retired id is never another name's (its own name may take it back); the resolution also carries each name's `identities` and the `externals`. A side's identity is named when the two sides' identities differ; a user's private group is named as that user's. The resolver is split into one function per kind of side (`_resolve_external`, `_resolve_recorded`, `_resolve_declared`) and `_check_across_names` (ruff's complexity limit, 25 > 20). One existing expectation in `tests/test_posix_identity.py` (change3) now names its two identities, `posix-local` and `posix-users` |
| T013 | `check_posix_ids` passes `recorded=ctx.meta_state.recorded_ids()`; it reads only the tree's records |
| T014 | Every POSIX claim carries `identity=self.get_name()` (`external` keeps its default, False) |
| T015 | 2026-11-23: `just test-one tests/test_recorded_ids.py tests/test_posix_identity.py packages/posix-identity-plugin/tests` 74 passed; `just lint` clean; `just typecheck` 0 errors. `just test`: lint clean, pyright 0 errors, 2,633 passed, 23 skipped, 2 failed, both this phase's: the resolver's docstring named Okta in the core (`test_core_names_no_runtime`), and one new assertion pinned a sentence (`test_sentence_pins_only_fall`, 27 > 26). Both fixed (the docstring says "an identity whose provider assigns ids itself"; the assertion pins `names must`); those two files, `test_recorded_ids.py` and `test_posix_identity.py` then 67 passed, `just lint` clean. The whole run was not repeated for the two fixes |
| T016 | Fifteen cases in `tests/test_recorded_ids.py`: the lowest free id no name holds, claims or once held; a pooled id unchanged as names come, go and reorder (a retired name's id is never given again); a later matching declaration passes and another fails; an exhausted pool names its bounds; an identity with no pool is refused; a plain dry run records nothing, a `--commit` dry run and an applying run do (`records_ids`), and `settle_ids` over the fixture writes `ids.yaml` only when recording; an external identity's new group is an id to come and draws nothing; overlapping pools name both; two POSIX builders may share one pool; a recorded id a pool change leaves outside is kept and noted; a pool over another identity's recorded id and a declared id inside another identity's pool are refused; a user and its private group draw one id; a pool below the floor or upside down is refused at load. In `tests/test_posix_identity.py`, `pxgroup` without its `gid:` no longer fails: it draws 3000 and bakes and verifies it (the old "no side supplies its id" case is gone, rule 4 being the pool now) |
| T017 | `id_pool: tuple[int, int] = (3000, 59999)` on both POSIX models (`DEFAULT_ID_POOL`), refused at load unless `Group.MIN_GID <= min < max` (`checked_pool`); both builders answer it from `id_pool()` |
| T018 | `posix_ids.py`: `Pool` (identity, bounds, external); `resolve_posix_ids(..., pools=)` draws each undeclared name the lowest id of its identity's pool that no name holds, claims, recorded or retired, users first so a private group takes its user's id; `_check_pools` refuses pools below the floor, pools of two parties that overlap, a pool over another party's recorded id and a declared id inside another party's pool, and notes a recorded id outside its own pool. **Every builder that does not assign ids itself is one party, "the POSIX identity"**: the fixture's `posix-local` (groups) and `posix-users` (users) both take the default pool, and one pass draws for both, so their pools may coincide; only a pool of an external identity may overlap none. An identity with no pool cannot draw (refused, naming it). The resolution carries `hows`, `notes` and `private_groups`; `ids_document` builds the `ids.yaml` a recording run writes, and `drawn` the log lines |
| T019 | `run_lifecycles.py`: `records_ids(dry_run, commit)` (`commit or not dry_run`, D1) and `settle_ids` after validation, which logs each drawn id and, on a recording run, writes `ids.yaml` through `record_ids` when it changed. `validate.py` gathers the claims and pools once per run (`resolve_run_ids`), keeps the resolution in `ctx.plugin_state` and logs its notes |
| T020 | **Contract 0.5.2** (the operator: "go ahead with contract 0.5.2"): `IdentityServiceProtocol.resolved_id(kind, name)`, the id the run resolved, and its README row; the engine's `IdentityService` answers from the run's resolution. The POSIX builders read the declared id, else `resolved_id`, in `gid_expression`, `activation_commands`, `activation_verify_commands`, `accounts_script` and the proof user; `configuration_errors` no longer asks a member for a `uid:` (one may be drawn). `just lint` clean, `just typecheck` 0 errors, `just surface-check` clean (the SDK surfaces unchanged); the golden tests 14 passed with `tests/fixtures` unchanged |
| T021 | 2026-11-23. The first `just test`: lint clean, pyright 0 errors, 2,648 passed, 23 skipped, 2 failed, both this phase's: `id_pool` was missing from `docs/CONFIGURATION.md` (`test_docs_parity`), and `resolved_id` imported the validation module inside a function, the core's fourth such import where three are allowed (`test_import_closure`). Fixed: `id_pool` documented for both POSIX builders, with how an undeclared id is drawn and recorded; the run's claims, pools and resolution moved to `engine/run_ids.py`, imported at the top by `validate`, `run_lifecycles` and the identity service. The second `just test`: lint clean, pyright 0 errors, 2,650 passed, 23 skipped; the isolated runs: core 377, the Terraform libraries' high ends 6 and 37, each `0 skipped`; the Terraform libraries' low end failed before its tests ran, on a TLS handshake timeout reading the index (environmental), which stopped the docker legs too. Rerun: `just test-terraform-alone` 6, 37 and 6, `just test-docker-alone` 62, 62 and 38, each `0 skipped`. The shared golden did not move (the fixture's runs record no ids); `git status --short tests/fixtures` printed nothing |
| T022 | `tests/external_identity.py` (new): a test-local external identity, a group builder of the type `test-external` whose provider "assigned" each group the id the tree gives it (`holds`) and whose pool is its `id_pool`; its claims are `external`; `stub_external_identity` adds it to the plugins the loader replays for one test, as the test kit adds its double runtime (the stub builder T011 deferred). Four cases in `tests/test_recorded_ids.py`, through `check_posix_ids` and `settle_ids` over a fixture copy: an external group's id read first is recorded `how: read` with its pool (`how: read`), and afterwards no declared id may take it and a draw passes it by; a later read of another id is refused naming both and `ids.yaml` stays byte-for-byte; an external id read onto `pxgroup`'s recorded 3101 is refused naming both, the external id the one that cannot move; a second external identity whose id collides with the first's is a configuration error naming both, with no core change. Run first: the first failed (below) |
| T023 | Phase 4's code already recorded what an external identity reads (`how: read`), held an id to come out of the draws, and recorded an external pool `how: read` (`run_ids.posix_pools`). T022 found one gap: a declared id equal to the recorded id of a name no builder claims this run was not refused (FR-003). `resolve_posix_ids` now holds such a name's id as a retired one is (the next recording retires it), and the refusal says "id N is recorded for <name>, which no builder declares now" |
| T024 | 2026-11-23: `tests/test_recorded_ids.py` 30 passed; with `test_posix_identity`, the pin, core-words and import-closure checks 93 passed; `just lint` clean, `just typecheck` 0 errors. `just test`: lint clean, pyright 0 errors, 2,654 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `git status --short tests/fixtures` printed nothing. **What the Okta repository's specification 002 must answer** (D3): its group builder's `posix_id_claims()`, marked `external=True` and `identity=<builder name>`, one per configured group (the configured name, never an `sft_` name the agent makes on the machine), with the gid OPA holds once read and `DEFERRED` until then; its user claims, each the uid Okta assigns (the system never chooses one, FR-007); its `id_pool()`, the bounds OPA's attribute options note, read by an applying run or the record step (`how: read`), or declared in the Okta group builder's configuration where the service gives none; and the naming rules T003's look at an enrolled machine settles |
| T025 | `tests/test_posix_registry.py` (new), seven cases over a fixture copy whose instance `test` takes `imgfile-posix` (owned by `pxgroup` on `posix-local`), the runtime's report of the machine stubbed: an applying run registers the machine it launched with its provider id, canonical hostname and address; a machine launched before the registry is registered by the first applying run, and a second run rewrites nothing; a launch that never came up registers nothing; a second unlaunched machine under a registered name is refused naming the entry; two entries under a launched name are refused naming both; an unreadable `servers.yaml` is refused as unable to check, for every POSIX-owned instance (`test` and the fixture's own `container-test`); a dry run asks the runtime nothing and leaves `servers.yaml` byte-for-byte. Run first: all failed but the dry run's |
| T026 | `registry.py` (new) in the POSIX plugin, over the run's records (`meta_state.registered_servers`, `retire_servers`, `record_server_aliases`); `PosixGroupBuilder` answers `can_query_servers` and `keeps_recorded_registry` True, and `registered_servers`, `retire_servers_named` and `record_aliases` through it; `alias_registration_script` stays the kit's None. **The dry run** (story 4, scenario 5) keeps today's rule: the hostname check runs only on a launching, non-dry run, so a dry run of a POSIX tree neither reads the registry nor refuses (the conservative reading; the other would check from the records in dry runs too) |
| T027 | `register_launched_servers` in `launch_params.py`, registered after `record_detachments` (so before the alias pass): for every launched instance in the apply scope whose group's builder keeps a recorded registry, the runtime's `query_instance_identity` gives the entry, written through `meta_state.record_server` under the builder's name; an entry already as it would be written is left alone and keeps its aliases; no provider id, no runtime answer or an unreadable record is said, never raised; a dry run does nothing |
| T028 | 2026-11-23: `tests/test_posix_registry.py` 7 passed; with the hostname-claim, alias, capability and POSIX tests 136 passed; `just lint` clean, `just typecheck` 0 errors. `just test`: lint clean, pyright 0 errors, 2,661 passed, 23 skipped (23 m 45 s, no slower: the alias pass's wait never ran for the fixture's `container-test`); the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `just surface-check` clean; `git status --short tests/fixtures` printed nothing |
| T029 | Five cases in `tests/test_posix_registry.py` (`_world` gains `undeclare` and `ephemeral`): a decommission retires both entries under `test-001`, keeps another hostname's, forgets the launch record and says "retired 2 registration(s)"; a retirement over an unreadable `servers.yaml` is said NOT retired, naming `meta-state/servers.yaml` as the remedy, and the decommission stands; a replacement retires the old machine's entry (`mark_launched`) and registers the new one, one entry left; an ephemeral teardown retires its entry; a decommission leaves `ids.yaml` byte-for-byte and `check_posix_ids` clean. Run first: the ephemeral case failed (nothing retired it) and the replacement registered the new machine as `test-003` |
| T030 | `forget_ephemerals` retires the torn-down machine's registration through `_retire_registration` before its launch record goes (R3). `_retire_registration`'s lines name any registry ("registration", not "OPA registration"), name the group, and give the remedy for a registry kept in the records (remove the entry from `meta-state/servers.yaml`) or another (deregister it by hand). **A correction to T027**: `register_launched_servers` registers a machine under the hostname it booted with (its recorded launch hostname), falling back to the canonical hostname; the canonical hostname of a machine this run replaced is the next generation's, which registered the new machine as `test-003` |
| T031 | 2026-11-23: `tests/test_posix_registry.py` 12 passed; with the ephemeral, decommission, canonical-name and hostname-claim tests 69 passed; `just lint` clean, `just typecheck` 0 errors. `just test`: lint clean, pyright 0 errors, 2,665 passed, 23 skipped, 1 failed, this phase's: `_retire_registration`'s new docstring named Okta in the core (`test_core_names_no_runtime`); fixed ("an outside service's"), then that check, the registry and the narration tests 34 passed. The run had stopped at pytest, so the isolated runs were run on their own: core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `just surface-check` clean; `git status --short tests/fixtures` printed nothing. **The Okta behaviour that changes**: an ephemeral Okta-owned machine's OPA registration is now retired when the machine is torn down, as a decommission's always was; before, it outlived the machine and claimed its name. The retirement's log lines say "registration" for every registry |
| T032 | Six cases in `tests/test_posix_registry.py`: a registered machine's free aliases (`ip-10-0-0-5`, the bare `test`) land in its entry's `alt_names` and no session command runs; an alias another entry claims is skipped naming the claimant; a machine launched this run gets its aliases with the reachability wait forbidden; the state query reports `registered_as` `test-001` and `booted_as` `test-002` and notes the difference; `verify login` refuses two entries under the hostname and an unreadable registry before any login (both through `prove_login`, the machine reported running). Run first: the alias and login cases failed; the state query's already passed (its notes read any builder that can be asked for servers) |
| T033 | `provider_aliases.py`: for a builder that keeps a recorded registry, `_register_instance_aliases` skips the power-state check and the post-launch wait, and writes the final aliases with `_record_aliases` (the builder's `record_aliases`, a failure reported and never raised) in place of `_write_aliases`; the collision rules and the equality short-circuit are unchanged |
| T034 | `login_proof.py`: `prove_login` asks `_registration_refusal` before the identity plugin's checks; for a builder that can be asked for servers, a registry that cannot be asked or two entries under the hostname is a failed `one registration` check and no login is tried. Worded as the Okta plugin's own check ("has 2 registrations: s-1@10.0.0.1, ..."; "could not be asked (silence is not one server)"), so an Okta login proof's record is unchanged (`tests/test_login_proof.py` 15 passed); Okta's own check is now redundant and stays until its repository drops it (R12) |
| T035 | 2026-11-23: `tests/test_posix_registry.py` 18 passed; with the login-proof, alias, canonical-name, alias-pool and state-query tests 99 passed; the core-words check found a comment naming Okta in `login_proof.py`, fixed. `just test`: lint clean, pyright 0 errors, 2,672 passed, 23 skipped (26 m 53 s); the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `git status --short tests/fixtures` printed nothing |
| T036-T038 (the world) | `tests/posix_world.py` (new): the POSIX-owned world the story tests and the re-hosted cases share (`make_posix_owned`, `seed_servers`, `answer_identity`, `posix_world`, `launched`, `entry`), moved out of `tests/test_posix_registry.py`. Delegated to three agents, one per task, each over its own files (no `just test`; `just test-one`, lint and typecheck on its files), and read back here. A registry record is read once per run and kept, so a case seeds `servers.yaml` before its run is built, or writes through `meta_state.record_server` |
| T036 | `tests/test_hostname_claims.py`'s 8 registry cases on a seeded POSIX registry (`_opa` removed; a `posix` fixture and `_registry_calls`, which wraps the real `registered_servers`): no registry question unless a launch is possible; a free registry; a taken name refused naming `772d4058 at 10.26.35.236`; one registration fine and two refused (the second written through the records); silence refused for every POSIX-owned instance; and the three retirement cases, which read the record instead of a retirement journal (a decommission leaves the registry empty; a failed retirement over an unreadable record is said NOT retired and the forget stands; a dry run leaves `servers.yaml` byte-for-byte). `tests/test_capabilities.py::test_a_dry_run_never_asks_the_registry_for_a_hostname_claim` on a dry and a real POSIX run. `tests/test_login_proof.py`'s two registration cases on its POSIX world, through `login_proof` (now the core's check, T034; its pinned id is `i-0def@10.0.0.6`); its Okta cases and its module-level `sft_login` import stay until they leave with the plugin. 58 passed in the three files |
| T037 | `tests/test_provider_aliases.py`'s 14 hook cases on POSIX (a `world` factory over `posix_world`, `Seams` recording power-state questions and session commands, the entry `OWN` under the bare `test` so the one wanted alias is `ip-10-0-0-5`); every AltNames-script assertion is now one on the entry's `alt_names` plus "no session command". Re-expressed, with no POSIX analogue as written: a session command with no output (now: no session command runs, whatever it would answer, the aliases are recorded and nothing is logged at WARNING); the wait for a machine launched this run (now: no wait, the reachability wait forbidden); a machine that never enrols (now: a machine launched this run but not registered gets no alias, said as not listed); and a fourth the agent found, a machine that is off (now: its aliases are recorded, the power state never asked, since nothing is written on the machine, T033). The pure cases and the test of Okta's alias script are unchanged. 23 passed |
| T038 | `tests/test_canonical_names.py` 3 (the bare and the IP name both come back, now in `alt_names`; a name that did not take at boot noted; a replacement retires the replaced machine's entry, read from the record), `tests/test_alias_pool.py` 1 (the pool name lands in `alt_names`), `tests/test_generations.py` 1 (the report names the generation beside the identity, over an empty POSIX registry); none imports the Okta plugin. 42 passed in the three files. Story 6's own cases in `tests/test_posix_registry.py` duplicated these and T036's login cases, and were removed; its docstring names where story 6 is proven |
| T039 | 2026-11-23. The connection logger rebuilt as a pytest plugin (`-p conn_logger`, kept outside the repository: it records each name lookup or connection to a non-loopback address, with our frames that made it, and refuses it). Over the six files R13 named it found every one still leaking: all six looked up the AWS login portal (`portal.sso.us-east-1.amazonaws.com`) through the AWS runtime's own machine lookups (`_named_instance`, `_running_instance`, behind `query_instance_identity`, `query_instance_power_state` and `query_instance_boot_image`, from the alias pass, the generations, the state query, the finalizer's boot-image check and `verify instance`), and `test_alias_draws.py` and `test_decommission.py` also looked up the fixture's OPA host through `opa_gids` (the Okta plugin's `accounts_script` reading a group's gid). Closed in `tests/harness.py`'s `stub_environment` (`_no_network`): `aws_utils.ec2_client` answers a client that knows no machine and refuses any other call, unless the test installed its own fake first; `opa_gids._urllib_transport_full` refuses as unreachable, below the transport a test may fake. The six and five neighbours with their own fakes: 102 passed, no attempt. **The whole suite under the logger**: 2,666 passed, 23 skipped, **zero network attempts**; none beyond the six |
| T040 | 2026-11-23: `just test`: lint clean, pyright 0 errors, 2,666 passed, 23 skipped; the isolated runs core 377, the Terraform libraries 6, 37 and 6, docker 62, 62 and 38, each `0 skipped`; `git status --short tests/fixtures` printed nothing. Specification 008's T035, part 2, recorded done there, file by file |

---

## Phase 1: Setup

**Purpose**: the branch, the before-state, and the look D3 asks for.

- [X] T001 Start `feature/010-posix-server-registry` from the tip of `feature/008-relocate-okta-plugin` (Working rules: `git flow feature start 010-posix-server-registry feature/008-relocate-okta-plugin`, or `git switch -c` from it when git-flow refuses a feature base); record the base commit
- [X] T002 [P] Record the before-figures in the Records table of `specs/010-posix-server-registry/tasks.md`: source lines, tests, the contract's protocol members (`packages/contract/README.md`'s counts), and the shared golden's file count and tree id (`git rev-parse HEAD:tests/fixtures/golden`)
- [ ] T003 [P] **The operator's box (D3)**: on one running machine of an Okta group, read-only, `getent group 180007; getent group sft_coops_user; grep -E '^sft[_-]' /etc/group; grep -c '^sft' /etc/passwd`; record the output; it feeds the Okta repository's specification 002 (`REMINDERS.md`), not a task here

---

## Phase 2: Foundational (the contract and the records)

**Purpose**: the questions and the records every story reads. Blocks
every story.

- [X] T004 Add to the contract, per [contracts/registry-and-ids.md](contracts/registry-and-ids.md): `record_aliases(group, entry_id, names)`, `keeps_recorded_registry()` and `id_pool()` on `GroupBuilderProtocol` (`packages/contract/src/cs_image_system/contract/group.py`); `id_pool()` on `UserBuilderProtocol` (`user.py`); the optional `address` key of `query_instance_identity`'s answer in `runtime.py`'s docstring; `identity: str = ""` and `external: bool = False` on `Claim` (`identity_vocabulary.py`); on `MetaStateProtocol` (`context.py`) `registered_servers(identity, group)`, `record_server(identity, group, entry)`, `retire_servers(identity, group, hostname)`, `record_server_aliases(identity, group, entry_id, names)`, `recorded_ids()`, `record_ids(document)`
- [X] T049 **The families widen first** (the operator's word of 2026-11-22, "widen the families, with trusted publishing for Google Cloud"; plan D6). In `cs-image-system-okta`: a branch moving `cs-image-system-contract>=0.5,<0.6` to `>=0.5,<0.7` in `packages/okta-opa-plugin/pyproject.toml` (the plugin uses none of 0.6's members), its `full-test` at both ends of the ranges, squash-merged into its `develop`; then **RELEASE** (the operator's): `just release patch pypi` and the tag's push publish 0.2.1
- [X] T050 In `cs-image-system-google-cloud`: a branch moving the same range in its three packages' `pyproject.toml`, and trusted publishing as `cs-image-system-okta` has it (its `.github/workflows/publish.yml` for the three distributions, `scripts/release` with no token tagging and both indexes probed, `tests/tooling` for a held version on either index and every publish line parsing, `docs/RELEASING.md` with the three project names, the repository and a fork's steps, the README and Justfile pointing at it); `just test` and `just full-test`, squash-merged into its `develop`
- [X] T051 **The operator's setup**: trusted publishers for the three Google Cloud projects (`cs-image-system-gcloud-runtime-plugin`, `cs-image-system-tf-gcp-plugin`, `cs-image-system-gcs-state-plugin`) on pypi.org (environment `pypi`) and test.pypi.org (`testpypi`), and the two environments in `cs-image-system-google-cloud` (its `docs/RELEASING.md`)
- [X] T052 **RELEASE** (the operator's): the Google Cloud family 0.2.1 by `just release patch pypi` and the tag's push; record both families' 0.2.1 on both indexes; only then can this repository lock on contract 0.6 (T005)
- [X] T005 Move the contract to 0.6.0 (`packages/contract/pyproject.toml`), its README's version table and member counts ("Twelve members" of the records becomes eighteen), and every dependent's range to `cs-image-system-contract>=0.6,<0.7` in each workspace `pyproject.toml` that names it; `uv lock`; `just init`
- [X] T006 Give the kit's builders the defaults: `record_aliases` returns None (the builder writes aliases by its script), `keeps_recorded_registry` False, `id_pool` None, in `packages/base/src/cs_image_system/base/basic/builder_base_group.py` and `builder_base_user.py`; `just surface-record`; `just sdk-bump kit last`
- [X] T007 Add the two records: `SERVERS = "servers.yaml"` and `IDS = "ids.yaml"` in `packages/base/src/cs_image_system/base/meta_ledgers.py` and in `ALL_FILES`; implement the six members in `packages/engine/src/cs_image_system/engine/meta_state.py` by [data-model.md](data-model.md): entries keyed by `instance_id`, sorted by hostname, address, id; `registered_servers` answers None when `servers.yaml` cannot be read and `[]` only for a group with no entry; `retire_servers` returns the removed ids; `record_ids` refuses any change to a recorded id, naming both
- [X] T008 [P] Test the records in `tests/test_meta_state.py`: `ALL_FILES` names both; a missing file is an empty record, an unreadable one None; record, replace, retire, aliases; `record_ids` refuses a moved id
- [X] T009 [P] Make `query_instance_identity` also answer `address` in `packages/aws-runtime-plugin/src/cs_image_system/aws_runtime/aws_runtime_builders.py` (the private address) and `packages/docker-plugin/src/cs_image_system/docker_runtime/docker_runtime_builders.py` (the container's address on its network), each with a test beside its existing identity test
- [X] T010 Checkpoint: `just test` passes; `git status --short tests/fixtures` prints nothing; record it

---

## Phase 3: User Story 1 - A declared id that collides is refused at validation (Priority: P1) 🎯 MVP

**Goal**: every user and group has one id, and a declared id that
collides with any identity's is refused, naming both.

**Independent Test**: `tests/test_recorded_ids.py`'s story 1 cases
(quickstart step 1).

### Tests for User Story 1

- [X] T011 [US1] Write story 1's eight scenarios in `tests/test_recorded_ids.py` (new), with a test-local external identity (a stub group and user builder registered through the test kit, `external=True`, claiming fixed ids) standing in for Okta, whose own claims are the Okta repository's (D3): a POSIX group on an external group's id is refused naming both identities and saying the external id cannot move; a POSIX user on another identity's user id is refused; a recorded name declared with another id is refused naming the recorded id; another group on a user's private-group id is refused naming the user; a clean tree passes with one id each; the POSIX fallback (`abc`, 15001: undeclared takes 15001 and draws nothing; declared 15002 is refused saying it must be 15001); a POSIX name recorded first that an external identity later holds with another id is refused, neither moving; two external identities that collide are refused naming both. Run them: they fail

### Implementation for User Story 1

- [X] T012 [US1] Widen the rule in `packages/engine/src/cs_image_system/engine/posix_ids.py`: recorded ids resolve first and never move (FR-005); claims carry `identity` and `external`; a non-external (POSIX) claim that knows a name an external claim holds takes the external id, and a different declared id is a problem saying which id it must be (FR-004a); between external claims every clash is a configuration error (FR-004b); an id recorded or retired for one name is never another's (FR-004c); every problem names the id, both names and both identities; a user's private group is named as that user's
- [X] T013 [US1] Feed it the records in `packages/engine/src/cs_image_system/engine/commands/validate.py` `check_posix_ids`: the recorded ids (`ctx.meta_state.recorded_ids()`) as a side ranked first; no network call (FR-009a)
- [X] T014 [P] [US1] Make the POSIX claims carry `identity=<builder name>`, `external=False` in `packages/posix-identity-plugin/src/cs_image_system/posix_identity_plugin/posix_builders.py`
- [X] T015 [US1] Checkpoint: T011 passes; `tests/test_posix_identity.py` passes; record it

---

## Phase 4: User Story 2 - An undeclared id comes from the pool and never drifts (Priority: P1)

**Goal**: an undeclared name draws from its identity's pool, is recorded,
and keeps its id for good.

**Independent Test**: `tests/test_recorded_ids.py`'s story 2 cases.

### Tests for User Story 2

- [X] T016 [US2] Write story 2's scenarios in `tests/test_recorded_ids.py`: the lowest free id of the pool that no record, retired record or claim holds; unchanged across added, removed and reordered names; a later matching declaration passes and another fails; an exhausted pool fails naming its bounds; a plain dry run shows the ids and records nothing while a `--commit` dry run and an applying run record them (D1); an external identity's new group is an id to come until read (D2); overlapping pools fail naming both; a recorded id a pool change leaves outside is kept and reported; a pool moved over another identity's recorded id fails; a user and its private group draw one id. Run them: they fail

### Implementation for User Story 2

- [X] T017 [US2] Add `id_pool: tuple[int, int] = (3000, 59999)` to `PosixGroupBuilderModel` and `PosixUserBuilderModel` in `packages/posix-identity-plugin/src/cs_image_system/posix_identity_plugin/posix_models.py` (refused at load unless `1024 <= min < max`), answered by both builders' `id_pool()` (D4)
- [X] T018 [US2] Draw and check pools in `packages/engine/src/cs_image_system/engine/posix_ids.py`: the lowest free id per identity's pool, one pool for users and groups, never a recorded, retired or claimed id; pools that overlap and a pool over another identity's recorded id are problems; a recorded id outside its pool is a note; an exhausted pool is a problem naming the pool; rule 4 ("no side supplies an id") is removed
- [X] T019 [US2] Record the ids in `packages/engine/src/cs_image_system/engine/commands/run_lifecycles.py`: after validation, on an applying run or a run with `--commit`, write the resolved ids, the pools and the retired names to `meta-state/ids.yaml` through `record_ids` (a name no longer declared moves to `retired`); a plain dry run logs the ids it would give and writes nothing
- [X] T020 [US2] Let an undeclared POSIX group and user take their concrete id: `gid_expression`, `activation_commands` and `accounts_script` in `posix_builders.py` read the resolved id (recorded or drawn) where they read the declared one, and stop raising for an undeclared gid
- [X] T021 [US2] Checkpoint: T016 passes; `just test`; if the shared golden moves (a fixture run with `--commit` writing `ids.yaml`), regenerate it, read every file and record it; record the checkpoint

---

## Phase 5: User Story 3 - Okta and POSIX coexist on one machine (Priority: P1)

**Goal**: an external identity's ids are recorded when read and win; a
third identity joins with no core change.

**Independent Test**: `tests/test_recorded_ids.py`'s story 3 cases, on
the test-local external identity.

### Tests for User Story 3

- [X] T022 [US3] Write story 3's scenarios in `tests/test_recorded_ids.py`: an external group's id read for the first time is recorded (`how: read`) and no declared or pooled id may take it; a later read of another id is refused naming both, the record unchanged; an external id read onto a POSIX name's recorded id is refused naming both; a second test-local external identity's claims join the same check with no core change; the external identity's `id_pool()` is recorded (`how: read`). Run them: they fail

### Implementation for User Story 3

- [X] T023 [US3] Record what an external identity reads, in `posix_ids.py` and `run_lifecycles.py`: its claims with an id are recorded `how: read` on a recording run (T019's rule); a `DEFERRED` claim is an id to come, held against the pools; its `id_pool()` answer is recorded `how: read`
- [X] T024 [US3] Checkpoint: T022 passes; record it, naming what the Okta repository's specification 002 must answer (its claims, its pool from the attribute options)

---

## Phase 6: User Story 4 - One name, one machine, for a POSIX group (Priority: P2)

**Goal**: a launched POSIX-owned machine is registered; a second machine
under its name is refused.

**Independent Test**: the hostname-claim cases on POSIX (quickstart
step 2).

### Tests for User Story 4

- [X] T025 [US4] Write story 4's scenarios in `tests/test_posix_registry.py` (new), over a fixture copy whose instance `test` is POSIX-owned (`imgfile-posix`, `pxgroup`) with the runtime's identity stubbed: an applying run registers the machine with its provider id, canonical hostname and address; a second unlaunched instance of that hostname is refused naming the entry; two entries under a launched name are refused naming both; an unreadable `servers.yaml` is refused as unable to check; a dry run reads only the records and writes nothing; a machine launched before the change is registered by the first applying run that finds it; a launch that never came up registers nothing. Run them: they fail

### Implementation for User Story 4

- [X] T026 [US4] Write the POSIX registry in `packages/posix-identity-plugin/src/cs_image_system/posix_identity_plugin/registry.py` (new) and wire it into `PosixGroupBuilder`: `can_query_servers` True, `keeps_recorded_registry` True, `registered_servers`, `retire_servers_named` and `record_aliases` through the run's records (`self._get_context().meta_state`), `alias_registration_script` None
- [X] T027 [US4] Add `register_launched_servers` to `packages/base/src/cs_image_system/base/launch_params.py`, registered in `register()` after `record_detachments` (so before the alias pass): for each launched, in-scope instance whose group's builder keeps a recorded registry, ask `query_instance_identity` and record the entry when it gives a provider id
- [X] T028 [US4] Checkpoint: T025 passes; record it

---

## Phase 7: User Story 5 - A decommission leaves nothing behind (Priority: P2)

**Goal**: a decommissioned, replaced or torn-down POSIX machine's entries
are retired; ids stay.

**Independent Test**: the retirement cases on POSIX.

### Tests for User Story 5

- [X] T029 [US5] Write story 5's scenarios in `tests/test_posix_registry.py`: a decommission retires every entry under the hostname and says how many; a retirement that fails is said NOT retired with the remedy and the decommission stands; a replacement leaves one entry, the new machine's; an ephemeral teardown retires; the group's and users' recorded ids are unchanged. Run them: they fail

### Implementation for User Story 5

- [X] T030 [US5] Make `forget_ephemerals` in `launch_params.py` retire the torn-down machine's registration through `_retire_registration` (R3), and word `_retire_registration`'s log lines for any registry ("registration", not "OPA registration")
- [X] T031 [US5] Checkpoint: T029 passes; record it, naming the Okta behaviour that changes (an ephemeral Okta machine's OPA entry is now retired)

---

## Phase 8: User Story 6 - A POSIX-owned machine's alias and generation are visible (Priority: P3)

**Goal**: aliases are recorded in the entry, never written on the
machine; the state query reports registered and booted names.

**Independent Test**: the alias and state-query cases on POSIX.

### Tests for User Story 6

- [X] T032 [US6] Write story 6's scenarios in `tests/test_posix_registry.py`: a running, registered machine's free aliases land in its entry's `alt_names` and no session command runs; a claimed alias is skipped naming the claimant; a machine launched this run gets its alias without the 300-second wait; the state query reports `registered_as` and `booted_as` and notes a difference; `verify login` on a POSIX machine refuses a duplicate or silent registration before any login. Run them: they fail

### Implementation for User Story 6

- [X] T033 [US6] In `packages/engine/src/cs_image_system/engine/provider_aliases.py`: when the builder keeps a recorded registry, call `record_aliases` in place of `_write_aliases`, skip `_enrolled_after_launch`, and do not apply "a machine that is off is left off"; the collision rules and the equality short-circuit stay
- [X] T034 [US6] In `packages/engine/src/cs_image_system/engine/commands/login_proof.py` `prove_login`: before any login, for every builder that keeps a registry, refuse a group whose registry cannot be asked or holds two entries under the hostname (R12)
- [X] T035 [US6] Checkpoint: T032 passes; record it

---

## Phase 9: User Story 7 - The core's proofs no longer need Okta (Priority: P3)

**Goal**: the registry tests specification 008 left run on POSIX.

**Independent Test**: those files pass with no Okta registry stub
(quickstart step 2).

- [X] T036 [P] [US7] Re-host on POSIX's recorded registry, keeping what each asserts and dropping its `OktaTfGroupBuilder` monkeypatches: `tests/test_hostname_claims.py`'s 8 registry cases, `tests/test_capabilities.py::test_a_dry_run_never_asks_the_registry_for_a_hostname_claim`, `tests/test_login_proof.py`'s `test_a_duplicate_hostname_fails_before_any_login` and `test_a_silent_registry_is_a_failed_check_not_one_server` (now the core's check, T034)
- [X] T037 [P] [US7] Re-host `tests/test_provider_aliases.py`'s 14 hook cases on POSIX: an assertion on the AltNames session script becomes one on the entry's `alt_names`; the three with no POSIX analogue (a session command with no output, the wait for a machine launched this run, a machine that never enrols) are re-expressed for a recorded registry (no session command; no wait; an unregistered machine waits for a run that registers it), each recorded with what it now asserts
- [X] T038 [P] [US7] Re-host the registry cases of `tests/test_canonical_names.py` (3), `tests/test_alias_pool.py` (1) and `tests/test_generations.py` (1) on POSIX
- [X] T039 [US7] Close the stubs that let six tests reach the fixture's OPA host and the AWS login endpoint (R13: `test_alias_draws.py`, `test_decommission.py`, `test_lineage_pins.py`, `test_ephemeral.py`, `test_convergent_bakes.py`, `test_canonical_names.py`, and those the T035 rerun names): each call they make is answered in-process; check with the connection logger of 2026-11-22 that none remains; record each
- [X] T040 [US7] Checkpoint: `just test` passes; record in specification 008's `tasks.md` that its T035, part 2, is done by T036 to T038, file by file

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T041 [P] Correct what the change makes false (plan, "What the change makes false"): `docs/OPERATIONS.md` ("A canonical hostname is claimed once", "What a machine answers to"), `docs/DAILY_DRIVER.md` (the decommission's registration, the aliases), `packages/posix-identity-plugin/README.md`, `packages/base/README.md` (the registry hooks), `packages/engine/README.md` (aliases, retirement), the docstrings and log lines naming "OPA registration" in `launch_params.py`, `builder_base_group.py`, `provider_aliases.py` and `posix_builders.py`, and `tests/test_login_proof.py`'s "the posix plugin keeps none"
- [ ] T042 [P] Document the ids for an operator in `docs/CONFIGURATION.md` (the `id_pool` field of the POSIX builders) and `docs/OPERATIONS.md` (the two records, the fallback, why an id never moves), each stated once and linked from the other
- [ ] T043 Measure the budget with T002's method and add a Budget section with the actual figures beside the expected to `specs/010-posix-server-registry/plan.md`, with a reason for any figure outside its range
- [ ] T044 Run `/speckit-converge`; complete any task it appends
- [ ] T045 Walk `specs/010-posix-server-registry/quickstart.md` steps 1 to 3 and record each result
- [ ] T046 **RELEASE** (the operator's, D5): the batched release for specifications 002, 003 and 006 carries this one; record its version and runs
- [ ] T047 In REF: take T046's release (`just take`), run an applying run and `just record` (quickstart step 4); expect `meta-state/ids.yaml` with every id unchanged from what the machines hold and `meta-state/servers.yaml` with every launched POSIX-owned machine; `just config-drift` green; record it (SC-004, SC-009)
- [ ] T048 Bring the specification's files up to date: the status line of `spec.md` and the row for 010 in `specs/README.md`, with the date

---

## Dependencies & Execution Order

- **Phase 1** first; T003 is the operator's and blocks nothing here.
- **Phase 2** blocks every story (the contract, the records). Within it,
  T005 waits for T049 to T052: this repository's own lock takes the
  Google Cloud family from the index (the `gcloud` and `all` extras), and
  no lock resolves while a family released elsewhere pins the contract
  below 0.6.
- **US1 → US2 → US3** in order: each widens the same rule
  (`posix_ids.py`).
- **US4** needs Phase 2 only; **US5** and **US6** need US4's registry.
- **US7** needs US4 to US6.
- **Phase 10** after the stories; T046 and T047 are the operator's.
- Specification 008's T035, part 2, and everything after it there wait
  for T040.

## Parallel Opportunities

- T002 and T003; T008 and T009 (different packages).
- T014 beside T012 and T013 (a plugin file against engine files).
- US4 (the registry) beside US1 to US3 (the ids), once Phase 2 is done:
  different files but for `posix_builders.py`, which both touch (T014,
  T020, T026): sequence those three.
- T036, T037 and T038 (different test files).
- T041 and T042.

## Implementation Strategy

- **MVP**: Phases 1 to 3 (story 1): every collision refused at
  validation, with no record written yet beyond what Phase 2 adds.
- Then story 2 (the pools and the records written), story 3 (external
  ids recorded), stories 4 to 6 (the registry), story 7 (Okta's stubs
  gone), and the documents.
- Each checkpoint runs `just test` and records it.
