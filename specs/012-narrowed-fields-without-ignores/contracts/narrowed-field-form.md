# Contract: the narrowed-field form a plugin author writes

**Spec**: [../spec.md](../spec.md) | **Research**: [../research.md](../research.md) R2 to R4

This is the SDK interface the change publishes. It lives in the kit
(`cs-image-system-base`) and the Terraform library
(`cs-image-system-tofu-roots`). The kit's and the Terraform library's
READMEs state it, and their surface declarations name the two type
parameters. The contract package (`packages/contract`) does not change.

## The kit: a runtime's credentials

Declared by the kit:

```python
# cs_image_system.base.models.runtime   (declared on the kit's surface)
CredentialsT = TypeVar("CredentialsT", bound=CredentialsBase,
                       default=CredentialsBase, covariant=True)

class RuntimeBuilderModel(BuilderModel, RuntimeBuilderModelProtocol, Generic[CredentialsT]):
    credentials: CredentialsT = field(
        default_factory=cast("Callable[[], CredentialsT]", CredentialsBase))

class CloudBuilderModel(RuntimeBuilderModel[CredentialsT], CloudBuilderModelProtocol): ...
class ContainerBuilderModel(RuntimeBuilderModel[CredentialsT], ContainerBuilderModelProtocol): ...
```

Written by a plugin that narrows:

```python
class MyCredentials(CredentialsBase):
    role: str | None = None

class MyCloudModel(CloudBuilderModel[MyCredentials]):
    credentials: MyCredentials = field(default_factory=MyCredentials)
```

Written by a plugin that does not narrow (unchanged):

```python
class MyContainerModel(ContainerBuilderModel):   # credentials: CredentialsBase
    ...
```

## The Terraform library: a storage root's variables

```python
# cs_image_system.tofu_roots.tofu_models   (declared on the library's surface)
VariablesT = TypeVar("VariablesT", bound=ModuleVariables,
                     default=ModuleVariables, covariant=True)

class TofuStorageBuilderModelBase(StorageBuilderModel, Generic[VariablesT]):
    variables: VariablesT = field(
        default_factory=cast("Callable[[], VariablesT]", ModuleVariables))
```

A leaf narrows directly
(`TofuDockerVolumeStorageBuilderModel(TofuStorageBuilderModelBase[DockerVolumeVariables])`).
An intermediate shared by several leaves passes the parameter on, and
each leaf names its own class:

```python
class TofuStorageBuilderModel(TofuStorageBuilderModelBase[VariablesT]): ...   # tf-aws
class TofuEbsStorageBuilderModel(TofuStorageBuilderModel[EbsVariables]):
    variables: EbsVariables = field(default_factory=EbsVariables)
```

## What the plugin author can rely on

1. **No exception.** The narrowed field type-checks at zero errors in
   pyright's "standard" mode, with no `pyright: ignore`.
2. **The refusal holds.** An unknown key under the narrowed field is
   refused at load, at the same location as before
   (`('credentials', '<key>')`, `('variables', '<key>')`).
3. **The default is yours.** Declare the field again with your class's
   default factory. If you do not, an absent key gives the general
   class's instance.
4. **No argument, no change.** A subclass that names no argument
   keeps the general class and its default. Its declared surface
   entry is unchanged.
5. **Annotations keep working.** A function or a builder bound typed
   by the unparametrized base (`TofuStorageBuilderModelBase`,
   `RuntimeBuilderModel`) accepts every narrowed model, because the
   parameter is covariant.
6. **Version.** The form needs the kit and the Terraform library at
   the version that carries it (research R7). A plugin that adopts it
   raises its lower bound to that version.

## What this does not cover

- `OSBuilderBaseImageBuilderSubconfig.description` keeps its exception.
  It is deferred until the first new middle number (research R5).
- A field the kit has not made generic. The rule for one is to make the
  kit's field generic the same way, not to add an exception (the spec's
  edge cases).
