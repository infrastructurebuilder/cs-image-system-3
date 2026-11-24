# Research: A provider narrows its own fields with no type-check exception

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Date**: 2026-11-24

Every finding below was reproduced on 2026-11-24. The probes ran in a
detached worktree of `develop` at `770ef2d8`, under the scratchpad.
They type-checked with this repository's pyright (1.1.411, "standard",
the root `pyproject.toml`'s settings), validated with its pydantic
(2.13.5), on Python 3.13.0. The shared checkout was not touched.

## R1. Where the six exceptions are, and what they narrow

| # | Field | Declared generally in | Narrowed in |
| --- | --- | --- | --- |
| 1 | `credentials` | the kit, `RuntimeBuilderModel` ([runtime.py](../../packages/base/src/cs_image_system/base/models/runtime.py)), as `CredentialsBase` | the AWS runtime, `AwsCloudBuilderModel` ([aws_runtime_models.py](../../packages/aws-runtime-plugin/src/cs_image_system/aws_runtime/aws_runtime_models.py)), as `AwsCredentials` |
| 2 | `variables` | the Terraform library, `TofuStorageBuilderModelBase` ([tofu_models.py](../../packages/tofu-roots/src/cs_image_system/tofu_roots/tofu_models.py)), as `ModuleVariables` | the docker volume ([tf_docker_models.py](../../packages/docker-plugin/src/cs_image_system/tf_docker_plugin/tf_docker_models.py)), as `DockerVolumeVariables` |
| 3-5 | `variables` | the same | EBS, EFS and S3 ([tf_storage_models.py](../../packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_storage_models.py)), as `EbsVariables`, `EfsVariables`, `S3Variables`, under the intermediate `TofuStorageBuilderModel` (`type: tf-aws`) |
| 6 | `description` | the kit, `NameTyped` ([builder_model.py](../../packages/base/src/cs_image_system/base/models/builder_model.py)), as `str \| None` | the kit, `OSBuilderBaseImageBuilderSubconfig` ([os_builder_runtime_config.py](../../packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py)), as `str` |

The runtime chain has two kit classes between the base and a provider:
`CloudBuilderModel` and `ContainerBuilderModel`. The storage chain has
one plugin class between the base and EBS, EFS and S3: the AWS
intermediate. Two runtimes name no class of their own: the docker
runtime and the test double (`DoubleRuntimeModel`). They are this
repository's own unparametrized subclasses (story 2).

## R2. The form: a covariant type parameter with a default

**Decision.** Each general field is typed by a module-level type
parameter. The parameter is bound to the general class, defaults to
it, and is **covariant**:

```python
CredentialsT = TypeVar("CredentialsT", bound=CredentialsBase,
                       default=CredentialsBase, covariant=True)

class RuntimeBuilderModel(BuilderModel, RuntimeBuilderModelProtocol, Generic[CredentialsT]):
    credentials: CredentialsT = field(
        default_factory=cast("Callable[[], CredentialsT]", CredentialsBase))
```

Each intermediate class passes the parameter through
(`CloudBuilderModel(RuntimeBuilderModel[CredentialsT], ...)`). A
provider names its class as the argument and declares the field with
its own default factory:

```python
class AwsCloudBuilderModel(CloudBuilderModel[AwsCredentials]):
    credentials: AwsCredentials = field(default_factory=AwsCredentials)
```

The storage side has the same shape with `VariablesT` (bound to and
defaulting to `ModuleVariables`) on `TofuStorageBuilderModelBase`.
The full shape is in [contracts/narrowed-field-form.md](contracts/narrowed-field-form.md).

**Evidence.**

- *Invariant (the default variance) fails.* An unparametrized
  annotation (`TofuStorageBuilderModelBase`, `RuntimeBuilderModel`)
  means "the default argument". Under invariance a narrowed model is
  not assignable to it. Two errors appear in the probe: one at the
  builders' existing bound
  (`Q = TypeVar("Q", bound=TofuStorageBuilderModelBase)` in
  [tofu_storage_builder.py](../../packages/tofu-roots/src/cs_image_system/tofu_roots/tofu_storage_builder.py),
  `reportInvalidTypeArguments`) and one at every function parameter
  typed by the base (`reportArgumentType`). The fix would be `[Any]`
  on every such annotation in the kit, the engine and the plugins.
- *Covariant passes.* The same probe with `covariant=True` reports 0
  errors. That includes a builder bound to the base, a function typed
  by the base or by an intermediate, a second level of narrowing (an
  intermediate that passes the parameter on, then a leaf), and an
  unparametrized subclass.
- *On the real code.* The worktree had exactly this form for rows 1
  to 5: the five exceptions removed, the AWS intermediate passing the
  parameter on, and every other line as it is on `develop`. Pyright
  analyzed **557 files: 0 errors, 0 warnings**. No other annotation
  had to change.
- *Pydantic keeps the refusal.* For a narrowed leaf, an unknown key
  under the field is refused with location `('variables', 'bogus')`
  and type `unexpected_keyword_argument`, the same as today's
  `EbsVariables`. An absent field gives the narrowed class's default.
  For an unparametrized subclass, the field is the general class: a
  key only the narrowed class knows is refused, and an absent field
  gives the general default.
- *Tests on the real code.* With the worktree's sources first on the
  path, 73 tests passed and 1 failed. They were
  [tests/test_credentials.py](../../tests/test_credentials.py), the
  tf-ebs plugin's tests, the docker plugin's unit tests, the AWS
  runtime's tests and the kit's surface baseline test. The one failure
  is the surface baseline; R4 deals with it.
  [tests/test_golden.py](../../tests/test_golden.py) passed.

**Why covariant is sound here.** Covariance on a mutable field is what
the six exceptions say today: the field is only ever narrowed, never
reassigned to a wider value. Pyright checks variance only for
protocols and inferred (PEP 695) parameters. An explicitly covariant
`TypeVar` on a class is taken at its word. This is the one place the
plan relies on that, and it is stated once, in the kit's README
(R6).

**Alternatives considered.**

- *PEP 695 syntax* (`class RuntimeBuilderModel[C: CredentialsBase =
  CredentialsBase]`). It reads better and needs no import. But its
  variance is inferred, and a mutable field infers invariance, so it
  fails as above. Rejected. (A probe in this syntax passed, but it
  had no annotation naming the unparametrized base. The variance claim
  is pyright's documented inference, not probed separately.)
- *`[Any]` on every annotation that names a base.* This changes many
  lines across layers and loses the narrowed type where it is read.
  Rejected.
- *Keep the exceptions* (the 2026-11-12 decision). The spec exists to
  replace it.

## R3. The base's own default needs a typed factory, not an exception

`field(default_factory=CredentialsBase)` on a field typed
`CredentialsT` is `reportAssignmentType`: the general class is not the
parameter. Three forms were tried:

- `cast("Callable[[], CredentialsT]", CredentialsBase)` gives 0
  errors and 0 warnings, and it is one expression in the kit.
  **Chosen.** A cast is not a rule-silencing comment, and it says what
  is true: the general class is the parameter's default.
- A generic helper `def _general[T](factory) -> Callable[[], T]`
  gives `reportInvalidTypeVarUse` (a warning). Rejected.
- A factory typed to return `Any` passes, but it hides the type.
  Rejected.

A provider still declares its field with its own factory. Without
that, an absent `credentials:` would give the general class's
instance, and the provider's code reads attributes the narrowed class
adds. This is unchanged from today.

## R4. The surface baseline: a field typed by a type parameter is recorded as its default

**Finding.** With R2's form the kit's surface baseline test fails on
two entries:

```text
CloudBuilderModel#credentials changed; the middle number must rise
    was: field CredentialsBase optional
    now: field CredentialsT optional
```

`ContainerBuilderModel#credentials` fails the same way. The Terraform
library's `TofuStorageBuilderModelBase#variables` would read `~VariablesT`
for the same reason. Under spec 010's D7 (patch-only: "the contract
and the SDK only add") a changed entry cannot land.

**Decision.** The surface record
([record.py](../../packages/base/src/cs_image_system/base/surface/record.py))
records a field typed by a type parameter **as the parameter's
default, in the form its annotation takes**:

- a string annotation (a module with `from __future__ import
  annotations`) gives the default's name as written;
- an evaluated annotation gives the default's qualified name.

This is what a subclass that names no argument sees. That is every
plugin written against the published kit, which is the reader the
baseline exists for. Probed: with the rule in the worktree, the kit's
and the Terraform library's baseline comparisons both pass unchanged
(the kit's test and `python -m cs_image_system.base.surface baseline
cs_image_system.tofu_roots ...`, exit 0). The patched `record.py`
type-checks at 0 errors.

**The new names are declared.** The AWS intermediate passes
`VariablesT` on, so a plugin imports it. A name not in the library's
declaration (`NAMES`: the kit's `surface/__init__.py`, the Terraform library's `surface.py`) is a finding of
the plugin surface check. So `CredentialsT` joins the kit's
declaration and `VariablesT` joins the Terraform library's. Both are
**additions**, recorded by `just surface-record` under the same
middle number, which is allowed. Once declared, removing either later
is a guarded reshape. The record renders a declared `TypeVar` as
`typevar bound <B> default <D> covariant`.

**Alternatives considered.**

- *A new middle number* (0.3). This breaks the patch-only rule, and
  every `>=0.2,<0.3` range would have to move, which breaks SC-004.
  Rejected.
- *Hand-edit the baseline.* The baseline says "Never edited by hand",
  and the check would still refuse the change. Rejected.
- *Have the intermediate define its own type parameter* instead of
  importing `VariablesT`. That avoids one declaration, but a second
  plugin author would copy it, and nothing would guard the form.
  Rejected.

## R5. The description is deferred (the operator, 2026-11-24)

Removing row 6's exception means the subconfig's field is `str |
None`. Its surface entry
(`OSBuilderBaseImageBuilderSubconfig#description = field str
optional`) then changes. That is a real reshape: what a plugin reads
widens. No rendering rule makes it the same, so it would need a new
middle number. The operator chose to defer it
([spec.md](spec.md), Clarifications 2026-11-24). Story 3 and FR-006
wait for the first middle number after the patch-only rule ends. The
exception and its comment stay, and `REMINDERS.md` keeps one line for
it.

## R6. Statements the change makes false

- The root [pyproject.toml](../../pyproject.toml), `[tool.pyright]`
  comment: "A field a subclass narrows on purpose ... carries a
  rule-named `pyright: ignore[...]`". It becomes: a provider names its
  class as the base's type argument, and the one exception left is
  the description, deferred.
- [packages/base/README.md](../../packages/base/README.md), the
  runtime field table's `credentials` row: "each plugin narrows it to
  its own subclass". It becomes: by naming the subclass as the type
  argument (`CloudBuilderModel[AwsCredentials]`), once, with the
  covariance note from R2.
- [packages/tofu-roots/README.md](../../packages/tofu-roots/README.md):
  the models paragraph ("a `ModuleVariables` each provider narrows")
  and step 1 of "Writing a new provider's root" ("narrow `variables`
  to the module's tunables"). Both show the form:
  `TofuStorageBuilderModelBase[YourVariables]`.
- The comments in code: the "narrowed on purpose ... the invariance
  rule cannot express" comments on the docker, AWS and EBS fields;
  the kit's comment on `credentials` in `runtime.py` ("Each provider
  narrows this to its own subclass"); and the docstrings of
  `TofuStorageBuilderModelBase` and the AWS intermediate.
- [REMINDERS.md](../../REMINDERS.md), "The nine variable-override
  ignores". It becomes the four left: the description here (deferred
  with the patch-only rule), and the Google Cloud family's three,
  which are that family's to remove in its own repository (FR-008).
  If spec 007 has moved the AWS family first, its four are listed
  there too (D3).
- [specs/README.md](../README.md), the row for 012: the state.

No document in `docs/` names the exceptions or the narrowing form.
Checked by grep for `pyright: ignore`, `variable-override` and
`invariance` outside `/ATTIC` and `specs/`.

## R7. Versions and ranges

- On `develop` the kit is 0.2.2 and the Terraform line (`hashicorp-utils`,
  `tofu-roots`) is 0.2.2. No tag carries either one: `v0.1.12` carries
  0.2.1, and PyPI holds 0.2.1. The version rule is "a change that
  removes or alters nothing on a declared surface takes the last
  number". If a line's current number is still unreleased when this
  merges, the change rides that number. Otherwise it takes
  `just sdk-bump kit last` and `just sdk-bump terraform last`.
  `scripts/own-versions-current` is the check at the release.
- `aws-runtime-plugin` and `tf-ebs-instance-plugin` pin the SDK exactly
  (`==`). `sdk-bump` moves those pins.
- `docker-plugin` takes the SDK by range (`>=0.2,<0.3`). Its volume
  model now subscripts `TofuStorageBuilderModelBase`, and a kit
  without the parameter raises `TypeError` at import. So its lower
  bounds on `cs-image-system-base` and `cs-image-system-tofu-roots`
  rise to the number that carries this change. This is a range edit
  on a plugin this spec changes anyway. It does not count against
  SC-004, which is about plugins that do not change.
- The docker family's isolated low end then resolves the new number
  from this repository's build until it is published (the run says so
  by name; [scripts/isolated-run](../../scripts/isolated-run)). So
  story 2's proof that an unchanged plugin still works does not come
  from the docker volume. It comes from (a) the docker runtime and the
  test double, unparametrized subclasses that load and refuse keys as
  before, and (b) the released Google Cloud family (unparametrized,
  exceptions in place), loaded beside this workspace by
  `scripts/with-released-families` in `just full-test`'s
  reference-configuration run.
- The contract does not change. `RuntimeBuilderModelProtocol.credentials`
  is `Any`.

## R8. Story 4 is a scratch proof, not a change

The Google Cloud family's three fields are written in R2's form in a
scratch copy of that family's storage model, type-checked against the
workspace's kit and Terraform library, and then discarded. Nothing in
that repository changes (FR-008).
[quickstart.md](quickstart.md) step 6 gives the commands.

**Probed 2026-11-24.** The copy was the sibling clone's `develop`,
`packages/tf-gcp-plugin/src/cs_image_system/tf_gcp_plugin/tf_gcp_models.py`.
In the copy, the intermediate `TofuGcpStorageBuilderModel` became
`TofuStorageBuilderModelBase[VariablesT]`, the PD, Filestore and GCS
leaves became `TofuGcpStorageBuilderModel[GcpVariables]`, and the
three exceptions were removed. Placed under the worktree's
`packages/tofu-roots/tests/`, it type-checked at **0 errors**. All
three leaves narrow to the same `GcpVariables`, so that family could
declare the field once, on its intermediate
(`TofuStorageBuilderModelBase[GcpVariables]`). That choice is the
family's.

Running the copy needs a path outside the workspace's include list,
type-checked against the workspace. No `just` target does that today.
Tasks add `just typecheck-path <path>` (a few lines in the
[Justfile](../../Justfile)), so the step does not call pyright by
hand.
