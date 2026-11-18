---

description: "Task list for spec 004: kinds a plugin declares, not kinds it registers on import"
---

# Tasks: Kinds a plugin declares, not kinds it registers on import

**Input**: Design documents from `specs/004-kinds-in-metadata/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md),
[research.md](research.md), [data-model.md](data-model.md),
[contracts/plugin-metadata.md](contracts/plugin-metadata.md),
[quickstart.md](quickstart.md)

**Tests**: requested. The specification ends every story in a test
(each story's Independent Test, FR-010, SC-001 to SC-003), so each
story's phase opens with its tests.

**Organization**: tasks are grouped by user story, so each story can be
built and checked on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, nothing unfinished it
  depends on)
- **[Story]**: the user story it serves (US1 to US4)

## Working rules

- Run Python as `uv run --no-sync python`; iterate with `just test-one
  <paths>`; the bar is `just test` at every checkpoint.
- **The shared golden is the tripwire.** After any task,
  `git status --short tests/fixtures` must print nothing (FR-003).
- A new file in a new folder needs `git add -N` before `just lint`, or
  the licensing check reads its `__pycache__`.
- Work on `feature/004-kinds-in-metadata` only. Never stage a file this
  feature did not change.
- "In every order" means the test builds the plugins as in-process
  entry points (as `packages/engine/tests/test_unusable_plugins.py`
  does) and runs discovery once per permutation of their names, since
  discovery reads by name.

## Records

Filled in as tasks complete.

| Task | Record |
| --- | --- |
| T001 | `just test` before any change: |
| T002 | Budget before any change (source lines, test lines, loader lines): |

---

## Phase 1: Setup

**Purpose**: the before-state the budget and the proofs compare with.

- [ ] T001 Run `just test` on `feature/004-kinds-in-metadata` before any change and record the counts (passed, skipped, each isolated run) in the Records table of `specs/004-kinds-in-metadata/tasks.md`
- [ ] T002 [P] Measure, with the method of spec 001's T101 (lines of `*.py` under `packages/*/src` and `src`; under `tests` and `packages/*/tests`, fixtures and goldens left out; `packages/engine/src/cs_image_system/engine/loader.py` alone), and record the three figures in the Records table of `specs/004-kinds-in-metadata/tasks.md`

---

## Phase 2: Foundational (blocks every story)

**Purpose**: the contract and the kit can carry declared kinds; nothing
uses them yet, and nothing is removed yet, so every test still passes.

- [ ] T003 Add `enrollment_kinds: tuple[EnrollmentKind, ...] = ()` and `field_kinds: Mapping[str, FieldKindHandler]` (empty by default) to `PluginMetadata` in `packages/contract/src/cs_image_system/contract/metadata.py`, and the two read-only members to `PluginMetadataProtocol` in `packages/contract/src/cs_image_system/contract/core.py`, with docstrings saying a plugin declares its kinds here and the loader registers them for an accepted plugin (data-model.md: an enrollment kind's `kind` is "Required, non-empty; unique within one plugin's declaration")
- [ ] T004 Add a private installer to `packages/contract/src/cs_image_system/contract/enrollment.py` (`_install(kind: EnrollmentKind)`) and to `packages/contract/src/cs_image_system/contract/field_kinds.py` (`_install(name, handler)`), each writing into its module's table, and add `SYSTEM_FIELD_KINDS = frozenset({FK, TEMPLATED, DEFERRED_LIST, DEFERRED_LIST_FK})` to `field_kinds.py`; keep the public `register_*` functions for now, as thin calls of `_install`
- [ ] T005 Make the resolver register the system's own field kinds through `field_kinds._install` in `packages/engine/src/cs_image_system/engine/orchestrator.py` (lines 1093 to 1094)
- [ ] T006 [P] Add the properties `enrollment_kinds` (returning `()`) and `field_kinds` (returning `{}`) to `AbstractPluginMetadata` in `packages/base/src/cs_image_system/base/basic/abstract_plugin_metadata.py`, documented as the ones a subclass overrides; then run `just surface-record` and confirm the only change to `packages/base/surface-baseline.txt` is the two added entries
- [ ] T007 Raise the contract to 0.5.0 in `packages/contract/pyproject.toml` and move every `cs-image-system-contract>=0.4,<0.5` to `>=0.5,<0.6` in the 21 manifests that carry it (find them with `grep -rln 'cs-image-system-contract>=0.4,<0.5' --include=pyproject.toml packages pyproject.toml`); refresh `uv.lock` with `uv lock`, run `just init`, and run `just test-one tests/test_contract_version.py tests/test_package_metadata.py packages/contract/tests`
- [ ] T008 Checkpoint: `just test` passes and the shared golden is unmoved; record it

**Checkpoint**: the contract and the kit can carry declared kinds.

---

## Phase 3: User Story 1 - A plugin declares its kinds and the system registers them (Priority: P1)

**Goal**: an accepted plugin's declared kinds are registered and used,
exactly as a registered kind is today; the Okta plugin declares its
kind; the emission does not move.

**Independent Test**: a plugin that declares an enrollment kind and a
field kind and registers neither; a configuration using both validates
and emits what the kinds render.

### Tests for User Story 1

- [ ] T009 [P] [US1] In `packages/engine/tests/test_declared_kinds.py` (new; `git add -N`), with in-process entry points: an accepted plugin's declared enrollment kind is in `enrollment.registered_kinds()` after discovery and `enrollment_kind_for` returns it; its declared field kind is returned by `field_kinds.get_field_kind_handler`; a plugin declaring none changes neither registry; and both registries hold the same after a second `discover()` in the process (FR-013)
- [ ] T010 [P] [US1] In `packages/engine/tests/test_declared_kinds.py`: a configuration field of a declared field kind is read through the kind's handler by the resolver (the pattern of `packages/engine/tests/test_field_kinds.py`, with the kind declared, not registered)

### Implementation for User Story 1

- [ ] T011 [US1] In `packages/engine/src/cs_image_system/engine/loader.py`, after `_Discovering.settled()` has decided the usable plugins, register the declared kinds of the usable plugins only, through the two `_install` functions, once per process (in the cached `_discovery()`, not in `load_plugins`); read each plugin's kinds from its metadata as `_register` reads its classes
- [ ] T012 [US1] Make the Okta plugin declare its kind: `OktaTypes` in `packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/main.py` overrides `enrollment_kinds` to return `(EnrollmentKind(SFTD_TOKEN, script_lines, ansible_tasks),)` from `sftd_launch`; remove the `register_enrollment_kind(...)` call at the end of `packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/sftd_launch.py` and correct its docstring; correct the comment at line 30 of `packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py`
- [ ] T013 [US1] Make `tests/test_posix_identity.py` stop relying on the import side effect (lines 38 to 64): it discovers the plugins, or declares the kind it needs on a plugin of its own, before rendering; keep what it asserts
- [ ] T014 [US1] Checkpoint: T009 and T010 pass; `just test-one tests/test_golden.py packages/docker-plugin/tests/pipeline/test_golden.py packages/system/tests/test_core_golden.py` passes and `git status --short tests/fixtures` prints nothing (FR-003, SC-004)

**Checkpoint**: declared kinds work, and the Okta plugin uses them.

---

## Phase 4: User Story 2 - A plugin that is not used leaves nothing behind (Priority: P2)

**Goal**: no kind of a skipped plugin is registered; a usable plugin
keeps every kind it declares, whatever it shares with a skipped one.

**Independent Test**: plugins declaring kinds that fail to load or are
skipped for a collision leave no kind registered; two plugins sharing a
library's kind object, one skipped, the other keeps it.

### Tests for User Story 2

- [ ] T015 [P] [US2] In `packages/engine/tests/test_declared_kinds.py`: a plugin that declares a kind and fails while its metadata is read registers none; a plugin skipped at settling for a collision over a builder type registers none of its declared kinds; a bystander's declared kinds stay (SC-002)
- [ ] T016 [P] [US2] In `packages/engine/tests/test_declared_kinds.py`: two plugins whose declarations hold one shared library's `EnrollmentKind` object (equal definitions), one of them skipped for an unrelated collision; the other is usable and the kind is registered (SC-003)

### Implementation for User Story 2

- [ ] T017 [US2] Confirm in `packages/engine/src/cs_image_system/engine/loader.py` that T011 registers kinds for usable plugins only and after every skip at settling (including `_loadable_together`); correct it if T015 or T016 fails

**Checkpoint**: Stories 1 and 2 pass on their own.

---

## Phase 5: User Story 3 - A collision over a kind is reported like any other (Priority: P3)

**Goal**: a kind declared twice differently is a two-sided collision,
named in one line, the same in every order; equal declarations are one
registration; a system field-kind name is refused.

**Independent Test**: each of the four cases recorded in spec 001 runs
in every order and gives the same outcome (SC-001).

### Tests for User Story 3

- [ ] T018 [P] [US3] In `packages/engine/tests/test_declared_kinds.py`, in every order: two plugins declaring one enrollment kind differently are both skipped, one line names both and the kind, and the kind is not registered; the same for a field kind; two declaring an equal definition both load and the kind is registered once (data-model.md: "equal when they are the same object or carry the same name and the same two renderers")
- [ ] T019 [P] [US3] In `packages/engine/tests/test_declared_kinds.py`, in every order: three plugins declaring one kind, two of them alike, are all skipped and every line names two that differ; a plugin declaring a field kind named in `SYSTEM_FIELD_KINDS` is skipped alone, its line saying the kind is the system's, and the system's handler is unchanged; a plugin declaring one kind twice is refused, naming the kind
- [ ] T020 [US3] In `packages/engine/tests/test_declared_kinds.py`, the four cases of spec 001 research R13 (tasks T140 to T143) as declared kinds, each in every order, each asserting the same accepted plugins, the same skipped and named plugins and the same registered kinds: (1) a plugin that fails while loading beside a usable plugin declaring the same kind; (2) two plugins colliding over a kind, with a third colliding with one of them over a builder type; (3) two entry points of one package declaring one equal kind, one of them skipped for another reason; (4) two plugins sharing a library's kind object, with a third declaring the kind differently (FR-010)

### Implementation for User Story 3

- [ ] T021 [US3] In `packages/engine/src/cs_image_system/engine/loader.py`, make each declared kind a registration key in `_Discovering._registrations` (or a sibling the settling reads), as `("enrollment kind", "", name)` and `("field kind", "", name)`, compared for equality as data-model.md defines; refuse in `_Discovering.load` a plugin that declares a field kind in `SYSTEM_FIELD_KINDS` or one kind twice; the messages in the forms of `specs/004-kinds-in-metadata/contracts/plugin-metadata.md`
- [ ] T022 [US3] Checkpoint: T018 to T020 pass; `just test-one packages/engine/tests tests/test_broken_plugin_is_skipped.py tests/test_registration_namespaces.py` passes

**Checkpoint**: Stories 1 to 3 pass on their own.

---

## Phase 6: User Story 4 - The loader is simpler, not cleverer (Priority: P4)

**Goal**: the inference spec 001 added for kinds registered on import
is gone, and no plugin can register a kind by a call.

**Independent Test**: quickstart steps 2 and 3 print only `searched`.

### Tests for User Story 4

- [ ] T023 [P] [US4] In `packages/base/tests/test_surface_check.py`: `from cs_image_system.contract.enrollment import _install` (and any underscore name from the contract) inside a plugin is a finding "private to the contract"; a public contract name still passes

### Implementation for User Story 4

- [ ] T024 [US4] Remove from `packages/engine/src/cs_image_system/engine/loader.py` the functions `_shared_kinds`, `_replaced`, `_restore`, `_defined_in`, `_own_package`, `_inside`, `_a_librarys`, `replaced_a_kind`, `_take_back_kinds`, and from `_Discovering` the snapshot taken around each import, `kind_owner`, `kind_claimant`, `collided_kinds` and the `contested` check, with the imports of `enrollment`, `field_kinds` and `functools` they alone needed; quickstart step 3 prints only `searched` (FR-009)
- [ ] T025 [US4] Remove from `packages/engine/tests/test_unusable_plugins.py` the tests of kinds registered by a call (the sections from the comment "kinds a plugin registers by a call of its own", "what is left behind, and who is named" as far as it tests kinds, and "a library two plugins share", with the `kinds`, `shared_library` and `two_libraries` fixtures and their helpers); T018 to T020 hold the behaviour now
- [ ] T026 [US4] Remove `register_enrollment_kind` from `packages/contract/src/cs_image_system/contract/enrollment.py` and `register_field_kind` from `packages/contract/src/cs_image_system/contract/field_kinds.py`; remove the re-exports of `register_enrollment_kind` and `_KINDS` from `packages/base/src/cs_image_system/base/launch_enrollment.py`; make `packages/engine/tests/test_field_kinds.py` (line 36) declare its kind on a plugin or install it through `field_kinds._install` with a comment that a test may; quickstart step 2 prints only `searched` (FR-002)
- [ ] T027 [US4] Add the rule to `packages/base/src/cs_image_system/base/surface/check.py`: an underscore-prefixed name imported from `cs_image_system.contract` is a finding whose reason is `private to the contract`; describe it in the module docstring; run `just surface-check`
- [ ] T028 [US4] Checkpoint: T023 passes; every test that used the removed functions is changed; `just test-one tests/test_plugins_keep_to_the_surface.py packages/engine/tests packages/base/tests` passes; the loader's line count is below T002's by at least 100 (SC-005)

**Checkpoint**: all four stories pass on their own.

---

## Phase 7: Polish and proof

**Purpose**: the documents, spec 001's record, the budget and the bar.

- [ ] T029 [P] Correct `packages/contract/README.md`: the `enrollment` and `field_kinds` rows of the module table (lines 31, 41), the range in the version rule (lines 140, 183) to `>=0.5,<0.6`, and a version-table row for 0.5.0 saying what changed and why it is the middle number
- [ ] T030 [P] Correct the contract's docstrings that this feature makes false: the module docstrings of `packages/contract/src/cs_image_system/contract/enrollment.py` and `field_kinds.py`, and line 131 of `packages/contract/src/cs_image_system/contract/context.py`
- [ ] T031 [P] Correct `packages/base/README.md` (line 488, field kinds by `register_field_kind`; line 1317, the contract's range) and the docstring of `packages/base/src/cs_image_system/base/launch_enrollment.py`
- [ ] T032 [P] Add to `docs/WRITING_A_PROVIDER.md` one place that says how a plugin brings an enrollment kind or a field kind (declared in its metadata, registered by the system for an accepted plugin), and correct the collision list near line 314 (SC-006)
- [ ] T033 Mark spec 001's limit superseded, without rewriting it: a note at the end of research R13's "Where this spec stops" paragraph in `specs/001-standalone-docker-provider/research.md`, a note on its row in the Complexity Tracking of `specs/001-standalone-docker-provider/plan.md`, and a note under the "is nobody's" line form in `specs/001-standalone-docker-provider/contracts/commands.md`, each pointing to `specs/004-kinds-in-metadata` (FR-012)
- [ ] T034 Measure the budget again with T002's method and write the actual figures beside the expected ones in the Budget table of `specs/004-kinds-in-metadata/plan.md`, with a reason for any figure outside its range
- [ ] T035 Walk `specs/004-kinds-in-metadata/quickstart.md` steps 1 to 4 and record each result in the Records table
- [ ] T036 Run `just cli config-drift` against the reference configuration and confirm exit 0 with no change of the tree's own (SC-004); record it
- [ ] T037 Bring the specification's files up to date: the status line of `specs/004-kinds-in-metadata/spec.md`, and the row for 004 in `specs/README.md`

---

## Dependencies & Execution Order

- **Phase 1** first; T001 and T002 can run together.
- **Phase 2** blocks every story: the members (T003), the installers
  (T004) and the kit's properties (T006) are what the stories use; the
  version (T007) touches every manifest and is done once.
- **US1 (Phase 3)** first among the stories: US2 and US3 test the
  registration US1 adds.
- **US2 (Phase 4)** and **US3 (Phase 5)** both depend on US1 and touch
  the same new test file and the loader; do them in order.
- **US4 (Phase 6)** depends on US1 to US3: the inference is removed only
  once declared kinds carry every case, and the public functions only
  once nothing calls them (T012, T013, T026).
- **Phase 7** after US4.

### Parallel opportunities

- T001 with T002.
- T006 with T003 to T005 (different packages).
- T009 with T010 (the same new file, different tests: write them in one
  sitting).
- T029 to T032 (different documents).

### Parallel example: Polish

```text
Task: T029 packages/contract/README.md
Task: T030 the contract's docstrings
Task: T031 packages/base/README.md and launch_enrollment.py
Task: T032 docs/WRITING_A_PROVIDER.md
```

## Implementation Strategy

### MVP first (User Story 1)

Phases 1 and 2, then Phase 3: kinds can be declared and the Okta plugin
uses them, with the golden unmoved. At that point the new path works
beside the old one; nothing has been removed yet.

### Incremental delivery

1. US1: declared kinds work (the MVP).
2. US2 and US3: the properties that the four recorded cases broke hold,
   in every order.
3. US4: the old path and its inference are removed; the loader shrinks.
4. Polish: the documents, spec 001's record, the budget, the bar.

### Where the risk is

- **T007** touches 21 manifests and the lock. Run `just test` straight
  after (T008).
- **T012** is the one change to an emitting plugin; the golden (T014)
  is the proof.
- **T024 to T026** delete. A test that still uses a removed name fails
  loudly; nothing can silently keep the old path.
