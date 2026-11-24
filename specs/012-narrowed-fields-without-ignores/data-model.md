# Data model: A provider narrows its own fields with no type-check exception

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

No configuration key, record or emitted file changes. What changes is
the type each model class declares for two fields, and how the SDK's
surface baseline records those types.

## Entities

### A type parameter (new, two of them)

| Name | Module | Bound | Default | Variance |
| --- | --- | --- | --- | --- |
| `CredentialsT` | `cs_image_system.base.models.runtime` | `CredentialsBase` | `CredentialsBase` | covariant |
| `VariablesT` | `cs_image_system.tofu_roots.tofu_models` | `ModuleVariables` | `ModuleVariables` | covariant |

Each one is declared on its library's surface (`NAMES`: the kit's
`surface/__init__.py`, the Terraform library's `surface.py`). Both are
additions.

### A narrowed field (rows 1 to 5 of research R1)

| Class (layer) | Field | Declared type | Default |
| --- | --- | --- | --- |
| `RuntimeBuilderModel[CredentialsT]` (kit) | `credentials` | `CredentialsT` | `CredentialsBase()` (typed by a cast, R3) |
| `CloudBuilderModel[CredentialsT]`, `ContainerBuilderModel[CredentialsT]` (kit) | inherited | `CredentialsT` | inherited |
| `AwsCloudBuilderModel` = `CloudBuilderModel[AwsCredentials]` (AWS runtime) | `credentials` | `AwsCredentials` | `AwsCredentials()` |
| `DockerContainerBuilderModel`, `DoubleRuntimeModel` (unparametrized) | inherited | `CredentialsBase` (the default) | `CredentialsBase()` |
| `TofuStorageBuilderModelBase[VariablesT]` (Terraform library) | `variables` | `VariablesT` | `ModuleVariables()` (typed by a cast) |
| `TofuStorageBuilderModel[VariablesT]` (AWS storage, `tf-aws`) | inherited | `VariablesT` | inherited |
| `TofuEbsStorageBuilderModel` = `TofuStorageBuilderModel[EbsVariables]` | `variables` | `EbsVariables` | `EbsVariables()` |
| `TofuEfsStorageBuilderModel` = `TofuStorageBuilderModel[EfsVariables]` | `variables` | `EfsVariables` | `EfsVariables()` |
| `TofuS3StorageBuilderModel` = `TofuStorageBuilderModel[S3Variables]` | `variables` | `S3Variables` | `S3Variables()` |
| `TofuDockerVolumeStorageBuilderModel` = `TofuStorageBuilderModelBase[DockerVolumeVariables]` | `variables` | `DockerVolumeVariables` | `DockerVolumeVariables()` |
| the Google Cloud family's three storage models (unparametrized until that family changes) | their own, with exceptions | unchanged | unchanged |

### Deferred (research R5)

| Class | Field | Stays |
| --- | --- | --- |
| `OSBuilderBaseImageBuilderSubconfig` | `description: str` over `NameTyped.description: str \| None` | its exception and comment, until the first middle number after the patch-only rule |

## Validation rules (unchanged, now held by the type argument)

- An unknown key under `credentials:` or `variables:` is refused at
  load. The error's location is the field path as today, for example
  `('variables', '<key>')` with type `unexpected_keyword_argument`.
- An absent `credentials:` or `variables:` gives the class's own
  default: the narrowed class for a parametrized model, the general
  class for an unparametrized one.
- A subclass that names no argument sees the general class (FR-002).
- A second level of narrowing names its own class as the argument and
  declares the field with its own default factory (edge case 2).

## The surface record (one rendering rule, one entry kind)

- A dataclass field whose annotation is a type parameter is recorded
  as the parameter's default. A string annotation gives the default's
  name as written. An evaluated annotation gives the default's
  qualified name. Existing entries stay byte-identical
  (`CloudBuilderModel#credentials = field CredentialsBase optional`,
  `TofuStorageBuilderModelBase#variables = field
  cs_image_system.base.models.module_variables.ModuleVariables
  optional`).
- A declared name that is a `TypeVar` is recorded as `typevar bound
  <B> default <D> covariant`. This is a new entry, added under the
  same middle number.

## State transitions

None.
