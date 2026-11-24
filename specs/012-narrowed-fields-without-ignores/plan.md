# Implementation Plan: A provider narrows its own fields with no type-check exception

**Branch**: `feature/012-narrowed-fields-without-ignores` (to be created from `develop` when implementation starts) | **Date**: 2026-11-24 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/012-narrowed-fields-without-ignores/spec.md`

**Users served**: a plugin author; maintainers.

## Summary

Five of the six `reportIncompatibleVariableOverride` exceptions in this
repository go: the AWS runtime's `credentials`, and the `variables` of
the docker volume and the EBS, EFS and S3 storage. Each base model
becomes generic over its field's type through a **covariant** type
parameter that is bound to the general class and defaults to it
(`CredentialsT` in the kit, `VariablesT` in the Terraform library). A
provider names its own class as the argument. A subclass that names no
argument keeps the general class and its default. The research is in
[research.md](research.md) R2 and R3, and the form is in
[contracts/narrowed-field-form.md](contracts/narrowed-field-form.md).

Probed on `develop` (`770ef2d8`) in a scratch worktree with the
form applied: pyright analyzed 557 files and reported 0 errors. The
loader's refusal of unknown keys is unchanged, the golden passed, and
the affected plugins' tests passed. One more change is needed to keep
the patch-only rule. The SDK's surface record writes a field typed by
a type parameter as the parameter's default, so every existing
baseline entry stays byte-identical. The two type parameters are
declared on the surfaces as additions (R4).

The sixth exception, the OS builder entry's `description`, is
**deferred** by the operator's decision of 2026-11-24 (**D1**,
[spec.md](spec.md) Clarifications). Removing it widens a declared
surface entry, and that needs a middle number the patch-only rule does
not allow (R5). The Google Cloud family's three exceptions are that
family's to remove (FR-008). A scratch copy proves they pass in this
form (R8).

## Technical Context

**Language/Version**: Python 3.13 (uv workspace). `typing.TypeVar`'s
`default=` is new in 3.13, the workspace's floor.

**Primary Dependencies**:

- the kit (`packages/base`): `RuntimeBuilderModel`, `CloudBuilderModel`,
  `ContainerBuilderModel`, the surface record and the declaration;
- the Terraform library (`packages/tofu-roots`): `TofuStorageBuilderModelBase`
  and the declaration;
- three plugins: `aws-runtime-plugin`, `tf-ebs-instance-plugin` and
  `docker-plugin`;
- pydantic 2.13.5 (validation through `TypeAdapter`, unchanged);
- pyright 1.1.411 in "standard" mode.

**Storage**: N/A.

**Testing**: pytest through `just test`. Lint, the type check (zero
errors), the tests, the core run, the Terraform libraries alone and
the docker family alone all block. Both goldens guard that nothing
moved, `just surface-check` guards the surfaces, and `just full-test`
loads the released Google Cloud family beside the new kit.

**Target Platform**: your local machine and the CI runners.

**Project Type**: a library (the plugin SDK) and the plugins in this
repository that use it.

**Performance Goals**: N/A. Validation is the same pydantic schema.

**Constraints**:

- no golden moves (Constitution IV);
- no existing surface entry changes, and versions move only their last
  number (the operator's rule of 2026-11-23; spec 010's D7);
- the contract does not change;
- the Google Cloud family's repository is not changed (FR-008);
- a test does not assert wording (Constitution IX);
- no cloud is touched.

**Scale/Scope**:

- five exceptions removed;
- two type parameters added;
- four kit or library class lines and five plugin class lines changed;
- one rendering rule and one entry kind in the surface record;
- one `just` target added;
- one range edit (docker).

No NEEDS CLARIFICATION remains. The one question this plan raised
(the description against the surface rule) was put to the operator and
answered: deferred.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves a plugin author and maintainers, named in the spec | Pass |
| II. Acceptance is executable | Every story ends in a command ([quickstart.md](quickstart.md) steps 1 to 8): a `git grep` count, `just typecheck`, `just test-one`, `just surface-check`, `just typecheck-path`, `just test` and `just full-test`. A skip fails. | Pass |
| III. Nothing irreversible by default | No apply, no plan gate and no identity touched | Pass |
| IV. The emission is the contract | No configuration key or emitted file changes. Both goldens must not move (probed: the shared golden passes). | Pass |
| V. Public by construction | No secret read or written. Credentials classes keep their fields. | Pass |
| VI. Layers and no interference | The kit and the Terraform library change, and the plugins follow. Nothing imports back. The two type parameters are declared surface, so the plugin surface check allows them. An unparametrized plugin (the released Google Cloud family) loads unchanged beside the new kit (step 8). | Pass |
| VII. Budget, subtraction | Below: about level on source. The exceptions and their comments go, and the parameters and the record's rule come. | Pass |
| VIII. One source per fact | The form is stated once, in the contract, and linked from the kit's and the Terraform library's READMEs. The covariance note is stated once, in the kit's README. | Pass |
| IX. Tests guard behaviour | The new tests assert refusal locations, default classes and recorded surface entries. None asserts wording. | Pass |
| X. What a change makes false | Listed below (research R6) | Pass |

**Re-check after design**: still passes. The design adds no package
and no contract member. On the declared surfaces it adds two names, as
additions. One judgment is recorded under Complexity Tracking so it
can be rejected: covariance on a mutable field.

### Budget (Principle VII)

Measured on `develop` at `770ef2d8` on 2026-11-24:

- source lines: `*.py` under `packages/*/src` and `src`;
- test lines: tracked `*.py` under `tests` and `packages/*/tests`,
  fixtures left out;
- tests: `pytest --collect-only -q` in a worktree of `develop`.

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 18 under `packages/` | 18 | none |
| Source lines | 51,039 | -5 to +25 | the parameters, imports and casts (about 10, probed at +6 net); the record's rule and the `typevar` entry kind (about 20); the two declarations (2); the nine "narrowed on purpose" comment lines and five exceptions go (about -10) |
| Test lines | 44,395 | +60 to +120 | refusal and default cases per narrowed field and for an unparametrized runtime (about 50); the record's two rules (about 30); a second-level narrowing case (about 15) |
| Tests | 2,496 | +5 to +9 | one or more per scenario of stories 1 and 2, the record's two rules, and the edge cases with behaviour |
| Contract protocol members | 0 changed | 0 | the contract does not change |
| Golden files | 117 shared, core unchanged | 117, unchanged | nothing moves |
| Justfile targets | n/a | +1 | `typecheck-path` (D4) |

### Statements this change makes false (Principle X)

These are corrected in the same work (research R6):

- [pyproject.toml](../../pyproject.toml), the `[tool.pyright]` comment
  on narrowed fields and their exceptions.
- [packages/base/README.md](../../packages/base/README.md), the
  `credentials` row of the runtime field table. It gets the form and
  the covariance note.
- [packages/tofu-roots/README.md](../../packages/tofu-roots/README.md),
  the models paragraph and step 1 of "Writing a new provider's root".
- The code comments: on `credentials` in `runtime.py`, the docstring of
  `TofuStorageBuilderModelBase`, the AWS intermediate's docstring, and
  the "narrowed on purpose" comments on the five fields.
- [REMINDERS.md](../../REMINDERS.md), "The nine variable-override
  ignores". It is narrowed to what is left (D1, D3).
- [specs/README.md](../README.md), 012's row: its state.

## Decisions

- **D1. The description is deferred. Taken (the operator,
  2026-11-24).** Story 3 and FR-006 wait for the first middle number
  after the patch-only rule ends. The exception and its comment stay.
  `REMINDERS.md` keeps one line. SC-001 reads "one remains".
- **D2. The release that carries it.** The default is the next one
  after this merges (the spec's assumption). Before 1.0 that is a
  TestPyPI release (spec 013's rule). The kit and the Terraform line
  ride their current numbers (0.2.2) if those are still unreleased at
  the merge. Otherwise each takes `just sdk-bump <line> last`
  (research R7). The docker plugin's lower bounds rise to that number.
  **YOUR DECISION at "do 012"**: release with the next release
  (default), or cut one for this.
- **D3. The order against spec 007.** If spec 007 moves the AWS family
  out first, its four exceptions travel with it. This spec then
  removes only the docker volume's, and the AWS family's four join the
  Google Cloud family's three as "that family's" in `REMINDERS.md`
  and in this spec's records. If this spec lands first (the default,
  and the spec's assumption), the AWS family moves without them.
- **D4. `just typecheck-path <path>`.** Quickstart step 6 type-checks a
  file outside the workspace's include list against the workspace. No
  target does that, and the standing rule is to add one rather than
  call pyright by hand. It is a few lines in the
  [Justfile](../../Justfile) and is usable for any scratch proof.
  **Taken** (it is the rule's own answer).

## Project Structure

### Documentation (this feature)

```text
specs/012-narrowed-fields-without-ignores/
├── spec.md              # amended 2026-11-24 (D1)
├── plan.md              # this file
├── research.md          # R1-R8
├── data-model.md        # the fields, the parameters, the record's rule
├── quickstart.md        # steps 1-8
├── contracts/
│   └── narrowed-field-form.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks (not yet)
```

### Source Code (repository root)

```text
packages/base/src/cs_image_system/base/
  models/runtime.py            # CredentialsT; RuntimeBuilderModel[CredentialsT]; the typed default
  models/cloud_builder.py      # CloudBuilderModel(RuntimeBuilderModel[CredentialsT], ...)
  models/container_builder.py  # ContainerBuilderModel(RuntimeBuilderModel[CredentialsT], ...)
  surface/record.py            # a type-parameter field recorded as its default; `typevar` entries
  surface/__init__.py          # the kit's declaration (NAMES): + CredentialsT
packages/base/surface-baseline.txt     # + the CredentialsT entry (just surface-record)
packages/base/README.md
packages/tofu-roots/src/cs_image_system/tofu_roots/
  tofu_models.py               # VariablesT; TofuStorageBuilderModelBase[VariablesT]
  surface.py                   # + VariablesT
packages/tofu-roots/surface-baseline.txt  # + the VariablesT entry
packages/tofu-roots/README.md
packages/aws-runtime-plugin/src/.../aws_runtime_models.py        # CloudBuilderModel[AwsCredentials]
packages/tf-ebs-instance-plugin/src/.../tf_storage_models.py     # intermediate[VariablesT]; three leaves
packages/docker-plugin/src/.../tf_docker_models.py               # TofuStorageBuilderModelBase[DockerVolumeVariables]
packages/docker-plugin/pyproject.toml                            # lower bounds (R7)
pyproject.toml                 # the pyright comment
Justfile                       # typecheck-path (D4)
REMINDERS.md
tests/, packages/*/tests/      # the new cases (tasks.md names them)
```

**Structure Decision**: no new package or module. Every change is in
an existing file of the kit, the Terraform library or the three
plugins that narrow. `os_builder_runtime_config.py` is not touched
(D1).

## Complexity Tracking

| Choice | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| A covariant type parameter on a mutable dataclass field | It is the only form that keeps every existing unparametrized annotation and builder bound valid (R2: invariance fails at `TofuStorageBuilderModelBase`'s builder bound and at every function typed by a base). It states what the exceptions state today: narrowed only, never widened. | Invariant or PEP 695 syntax needs `[Any]` on every annotation that names a base, across the kit, the engine and the plugins. Keeping the exceptions is what the spec replaces. |
| The surface record writes a type-parameter field as its default | It keeps every existing baseline entry byte-identical, so the patch-only rule holds and no dependent's range moves (SC-004) | A middle number breaks the operator's rule and every `<0.3` range. A hand edit is refused by the check itself. |
