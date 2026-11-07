# cs-image-system-contract

The plugin contract: the one package a plugin is written against. It
carries the protocols a model and a builder satisfy, the constants and
field helpers a model is declared with, the lifecycle phases a hook keys
on, and the data carriers a hook returns. It depends on no other package of
the system -- `pydantic` and `packaging` only -- and the core
([base](../base/README.md)) depends on it, never the reverse: the contract
is upstream, the core conforms to it, and a new hook is a contract change
first. The core's base classes are the convenient implementation of the
contract, not the contract itself; a class that satisfies the protocols
structurally is a first-class plugin, and
[`testing.assert_conforms`](src/cs_image_system/contract/testing.py) is the
check that says so. Nothing in the package imports the registry, and a
plugin's `pyproject.toml` never needs the CLI host.

One module per kind of builder, over a shared core:

| Module | Carries |
| --- | --- |
| [`core`](src/cs_image_system/contract/core.py) | `PluginArtifactProtocol` (`csis_name`, `csis_classifier`), `NameTypedProtocol`, `PluginMetadataProtocol`, `BuilderModelProtocol` and `RuntimeEnabledBuilderModelProtocol` (what the core reads of any builder model), `BuilderProtocol` (the six universal hooks, the three finalize-phase hooks, `finalize`, the paths), and the three markers the orchestrator dispatches on: `SelfInjectedNameProtocol`, `SubItemOverrideProtocol`, `ParentPropertyHoldingProtocol`. |
| [`runtime`](src/cs_image_system/contract/runtime.py), [`operating_system`](src/cs_image_system/contract/operating_system.py), [`storage`](src/cs_image_system/contract/storage.py), [`image`](src/cs_image_system/contract/image.py), [`instance`](src/cs_image_system/contract/instance.py), [`modification`](src/cs_image_system/contract/modification.py), [`group`](src/cs_image_system/contract/group.py), [`user`](src/cs_image_system/contract/user.py), [`state`](src/cs_image_system/contract/state.py) | One `<Kind>BuilderModelProtocol` and one `<Kind>BuilderProtocol` per kind, with exactly the attributes and hooks a plugin calls on another's builder or model, or implements on its own ("The surface" below). `state` also carries the backend seam: `StateLocation`, `BackendRegistration`, `BackendKindProtocol` and `StateBackendModelProtocol`. `image` carries the provider-specific image's two enums. |
| [`metadata`](src/cs_image_system/contract/metadata.py) | `PluginMetadata`, the record a plugin's entry point returns. |
| [`modules`](src/cs_image_system/contract/modules.py) | `MODULES_ENTRY_POINT_GROUP` (`cs_image_system.modules`): the entry-point group a plugin declares its terraform modules directory in, one entry point whose value is `<package>:<dirname>`; the modules are package data inside the plugin, one directory per module, and the core lists and materialises them without importing the plugin. |
| [`constants`](src/cs_image_system/contract/constants.py) | `VCT` (the classifications), the sentinels (`DEFAULT`, `SELF`, `NONE`, `OOPS_DEFAULTS`), the field metadata keys, `PLUGIN_TYPES` (the entry-point groups), the collection names, the file names a run writes. |
| [`model_config`](src/cs_image_system/contract/model_config.py) | `CSIS_MODEL_CONFIG`, the one pydantic configuration every model is declared under (unknown keys are refused). |
| [`fields`](src/cs_image_system/contract/fields.py), [`field_kinds`](src/cs_image_system/contract/field_kinds.py) | `fk_field`, `templated_field`, `deferred_list_field`, `deferred_list_fk_field`, `parent_field`; the open registry of field kinds a plugin may extend. |
| [`lifecycle`](src/cs_image_system/contract/lifecycle.py), [`lifecycles`](src/cs_image_system/contract/lifecycles.py) | `ExecutionLifecyclePhase`; `Lifecycle`, `LifecycleSpec` and the phases and builder classifications each built-in lifecycle owns. |
| [`assets`](src/cs_image_system/contract/assets.py), [`executables`](src/cs_image_system/contract/executables.py) | `Asset`, `AssetSet` (what `generate_items_*` returns); `ExecutableProtocol`, `CFExecutables` (what `get_commands_to_run_*` returns). |
| [`names`](src/cs_image_system/contract/names.py), [`hcl`](src/cs_image_system/contract/hcl.py) | `safe_name`, `super_safe_name`; `HclRaw`, `hcl_expr`, `render_module_call`. |
| [`lineage_vocabulary`](src/cs_image_system/contract/lineage_vocabulary.py), [`launch_vocabulary`](src/cs_image_system/contract/launch_vocabulary.py), [`storage_vocabulary`](src/cs_image_system/contract/storage_vocabulary.py), [`identity_vocabulary`](src/cs_image_system/contract/identity_vocabulary.py) | The words a plugin reads and writes, constants and types only: the tag names and the fingerprint tag's length (`TAG_PREFIX`, `CONFIG_TAG`, `FINGERPRINT_TAG_LENGTH`); the enrollment variable, the mount mark, the launch script and marker paths and the verification failure policies (`ENROLLMENT_TOKEN_VARIABLE`, `MOUNT_MARK`, `LAUNCH_MARKER_PATH`, `ON_FAILURE_KEEP`, `ON_FAILURE_TEARDOWN`); the storage states and the attachment cardinalities; the gid policies and the id `Claim`. The functions that read lineage, compute launch parameters or reconcile ids are the core's. |
| [`power_state`](src/cs_image_system/contract/power_state.py) | The power states (`RUNNING`, `STOPPED`, `STOPPING`, `STARTING`, `SUSPENDED`, `ABSENT`, `UNKNOWN`), their groupings, and `is_off`, `is_on`, `exists`, `describe`. A runtime maps its provider's states onto these; "cannot answer" is `None`, never a state. |
| [`secrets`](src/cs_image_system/contract/secrets.py) | `EncryptedStr`, the type a model declares a secret field with; `Decrypted`, `is_marker` and the marker's shape. The decryption is the core's: it installs its decoder with `register_secret_decoder`, and a marker met with none is refused. |
| [`bootstrap`](src/cs_image_system/contract/bootstrap.py) | The bootstrap interview's question model a plugin's section is built from (`Question`, `Section`, `Rendered`, `Secret`, `Variable`, `Raw`, `Refused`, `Answers`, the coverage words `MADE`, `READ`, `ADOPTED`, `BY_HAND`) and `ENTRY_POINT_GROUP`, the group a section is registered in. The checkout's facts a default reads are the core's and reach the callables untyped. |
| [`errors`](src/cs_image_system/contract/errors.py) | `ContainerStartError`, the exception a local test target raises and the core catches by type. |
| [`hooks`](src/cs_image_system/contract/hooks.py) | The hook plugin's surface: `HOOK_ENTRY_POINT_GROUP`, `HookSet` and the four hook signatures (validators, lifecycle, summary, state bindings), typed on `RunContextProtocol`; a hook plugin imports nothing of the core for it. |
| [`enrollment`](src/cs_image_system/contract/enrollment.py) | The enrollment-kind registry an identity plugin registers its launch-time enrollment with (`register_enrollment_kind`, `enrollment_kind_for`, the script-line and task shapes). |
| [`image_sources`](src/cs_image_system/contract/image_sources.py) | The release-owned image-source catalog's words: the packaged catalog file name, the YAML key, and `container_reference(query)`; a runtime declares `image_source_package` and the core reads its catalog. |
| [`context`](src/cs_image_system/contract/context.py) | `RunContextProtocol`, `MetaStateProtocol`, the service protocols and `ServicesProtocol`: the run context as a plugin reads it, and the services it reaches through it. |
| [`testing`](src/cs_image_system/contract/testing.py) | `assert_conforms(cls, protocol)` and `conformance_problems`. |

### The surface

A kind protocol's own members are the ones at least one package outside
the core (a plugin, `hashicorp-utils`, `tofu-roots`) calls on a builder or
model it does not own, or implements or overrides, plus the ones the core
itself calls on a plugin's builder or model (the loader's wiring hooks,
the readers the lineage, validation and resolve code call on an OS
model), even where the kit's base class supplies the default body: the
contract names everything the core will call on the plugin's object. A
member only the core's base classes call on each other, or that nothing
outside its defining class reads, is a method or field of the kit's base
class (`cs_image_system.base.basic`, `base.models`) and not of the
protocol. The universal protocols in `core`
are the whole surface a structural plugin writes (the contract example
implements every member). The counts, own members only (the inherited
universal ones are not repeated), as measured over the sources:

| Protocol | Own members | Kept because |
| --- | --- | --- |
| `RuntimeBuilderModelProtocol` | 8 (`credentials`, `get_credentials`, `get_default_machine_type`, `update_networking`, `get_default_owners`, `retention_keep`, `on_failure`, `teardown_after`) | a terraform root reads the runtime's credentials and machine type; a cloud plugin redeclares its credentials type and overrides `update_networking`; the core reads the default owners (an OS builder's query inherits them) and the three retention/teardown knobs (lineage, retention, state query). `default_image_builder`, `default_machine_type`, `ephemeral` and the rest are the kit model's |
| `CloudBuilderModelProtocol` | 1 (`networking`) | every cloud plugin redeclares it with its own type; `region` and the rest are the kit model's |
| `ContainerBuilderModelProtocol` | 0 | `host`, `context`, `networking`, `machine_types` are read by the container plugin on its own model and by the core: the kit model's |
| `RuntimeBuilderProtocol` | 53 | the hooks the three runtime plugins override and the packer, terraform and identity plugins call, plus what the core calls on a runtime builder: `add_image_builder` and `add_instance_builder` (the image and instance builders wire themselves in at finalize) and `create_provider_specific_image_deferred` (resolve). `apply_specific_changes` is the kit's |
| `OsBuilderModelProtocol` | 22 | `families`, the six package-manager lines, `commands_for_policy` and `get_command_to_update` (the OS type's answers, which the default OS plugin implements and every baking plugin calls); and the thirteen readers the core calls on an OS builder's model: `get_owners`, `get_vendor_family`, `get_family_version`, `get_architecture`, `get_default_primary_disk_size`, `get_auto_update`, `get_query`, `get_runtimes` (the runtime subconfig, image names, validation, resolve), `effective_update_policy` (validation, lineage), `get_identity_types`, `get_storage_types`, `get_admin_user`, `get_admin_public_keys` (capabilities, lineage, validation). The fields themselves and the getters nothing outside the kit reads (`get_family`'s field, `get_modifications`, `get_osrtconfig_by_type`, `get_output_image_name`) are the kit model's |
| `OsBuilderProtocol` | 7 | `get_family` and `generate_items_for_os_update` (what the packer plugin asks an OS builder); `get_family_version`, `get_architecture`, `get_config_username`, `generate_resolved_image` and `get_configs_for_image_builders` (what the core's resolve, bake-user, mod-test and validate code ask one) |
| `StorageBuilderModelProtocol`, `InstanceBuilderModelProtocol`, `ModBuilderModelProtocol`, `GroupBuilderModelProtocol` | 0 | the universal fields; the plugin declares the rest |
| `ImageBuilderModelProtocol` | 1 (`get_default_machine_type`) | the OS builder's finalize reads it on the image builder's model; the field is the kit model's |
| `StorageBuilderProtocol` | 17 | the capability, lifecycle, launch and state hooks the terraform and identity plugins implement, and `add_storage`, which the loader calls to attach each storage item |
| `ImageBuilderProtocol` | 2 (`build_target_label`, `add_image`) | the packer plugin overrides the first; the loader and resolve call the second; the block paths and `get_images` are the kit's |
| `InstanceBuilderProtocol` | 1 (`add_instance`) | `tofu-roots` overrides it |
| `ModBuilderProtocol` | 3 | the three modification hooks the ansible and bash plugins implement and the packer plugin calls |
| `GroupBuilderProtocol` | 40 | the identity, bake, launch, state-query, login-proof and workload-access hooks the two identity plugins implement, and `add_group_to_builder`, which the loader calls; `add_user_to_builder`, `get_users_for_group`, `get_admins_for_group`, `get_users_for_builder` and `managed_groups` are the kit's |
| `UserBuilderModelProtocol` | 4 (`email_as_username`, `default_user_description_template`, `email_domain`, `get_user_email_template`) | the posix user model redeclares the first; the core's user item templates read the other three (`{{ builder.get_user_email_template() }}`); `default_user_email_template`, `get_user_description_template` and `get_email_domain` are the kit model's |
| `UserBuilderProtocol` | 7 | `default_managed`, `validate_user`, the attribute hooks, `posix_id_claims`, `get_users_for_builder`, and `add_user_to_builder`, which the loader calls |
| `StateBackendModelProtocol`, `StateBuilderProtocol`, `BackendKindProtocol` | 1, 1, 4 | every state plugin implements them |

The loader holds every class a plugin registers to the protocol of its
classification (`testing.protocol_for`), with `assert_conforms`, when it
discovers the installed plugins (once per process, as shipped): a builder
that lacks a hook, or answers it with the wrong parameters, is refused
with the plugin, the class, the protocol and the member named
(`PluginConformanceError`), never later with an `AttributeError`. The loader, the registry and the orchestrator decide what
kind of thing they hold by `isinstance` against the `runtime_checkable`
protocols of `core` (`PluginArtifactProtocol`, `NameTypedProtocol`,
`BuilderModelProtocol`, `RuntimeEnabledBuilderModelProtocol`,
`BuilderProtocol`, the markers), not by `hasattr` on a member's name.

### What the contract holds, and what the core keeps

The contract is the one home of every name in the table above: the core
has no path of its own for them (`cs_image_system.base.constants`,
`base.models.model_config`, `base.helpers.field_helpers`,
`base.helpers.field_kinds`, `base.lifecycle`, `base.basic.asset` and
`base.models.executable_adds` do not exist, and `base.lifecycles`,
`base.utils` and `base.models.provider_specific_image` hold only the
core's own registry, helpers and model), and `cs_image_system.base.protocols`
does not exist either. The core and every built-in plugin import the
contract directly ([the stage index](../../docs/CHANGES.md#s125) records the
commitment; the `s30-*` tags bracket the move of the bodies, as history).
The vocabulary modules are the exception by design: the
core keeps the paths a reader of the engine knows (`base.lineage` for the
tag words, `base.launch_params` for the enrollment variable,
`base.power_state`, `base.encryption`, `base.bootstrap.questions`,
`base.posix_ids`), each importing the words from here, so an engine module
reaches its vocabulary without naming the contract; a plugin imports the
contract module.

The protocols carry no implementation. Where a default body existed
(`global_id`, `get_classification`, `get_self_injected_name`, the parent
reference's registry lookup) it lives in the core's base classes and
mixins. The kind modules import `core` and only the kinds they declare they
read (`runtime` reads `image` for the provider-specific image's enums); the
vocabulary modules import nothing from the package.
[tests/test_contract.py](../../tests/test_contract.py) holds that
direction, holds the package to importing nothing from the core, and runs
`assert_conforms` over every base class and every built-in plugin's models
and builders; [tests/test_plugin_imports.py](../../tests/test_plugin_imports.py)
holds what a plugin may import of the core (the base classes, the models,
the two metadata abstractions) against a committed list of the remaining
exceptions, which can only shrink.

### Version

The contract carries a semantic version of its own, independent of the
workspace's: `0.4.0` now, and 0.x until the operator decides otherwise
(the decision of 2026-11-05). What a bump means: a PATCH is a change no
plugin can observe (a docstring, a test helper); a MINOR, while the
version is 0.x, is a change a plugin can observe, so a protocol member
added, renamed or removed, a constant's value changed, a module added or
removed, and it is the breaking step; from 1.0 a MINOR adds without
breaking and a MAJOR breaks. Every package that depends on the contract
pins the compatible series, `cs-image-system-contract>=0.4,<0.5`, and
`just release`, which moves every other package's version in lockstep,
leaves the contract's where it is (`bump-my-version` excludes its
manifest by name; the upload and the index probe read its version from
its own manifest). The contract's version moves only by hand, in the
stage that changes its surface, and
[tests/test_contract_version.py](../../tests/test_contract_version.py)
holds all of it: the version is its own and final, every dependent pins
the range, the bump excludes the manifest, the release tooling knows.

The versions so far:

| Version | What changed, and why it is the step it is |
| --- | --- |
| `0.1.0` | The first versioned contract: the protocols, constants and data carriers as the core's surface was settled ([the stage index](../../docs/CHANGES.md#s125)). |
| `0.2.0` | `PluginMetadata` and `PluginMetadataProtocol` gain `namespace` (optional, `None` by default), the override of the namespace the loader derives from the plugin's distribution. A member added is something a plugin can observe, so while the contract is 0.x it is a MINOR step, and every dependent's range moved from `>=0.1,<0.2` ([the stage index](../../docs/CHANGES.md#s131)). |
| `0.3.0` | A module added: `modules`, holding `MODULES_ENTRY_POINT_GROUP` (`cs_image_system.modules`), the entry-point group a plugin declares its terraform modules directory in, with the value `<package>:<dirname>`; the modules themselves are package data inside the plugin that owns them. A module added is something a plugin can observe, so while the contract is 0.x it is a MINOR step, and every dependent's range moved from `>=0.2,<0.3` ([the stage index](../../docs/CHANGES.md#s126)). |
| `0.4.0` | Two members removed from `LaunchServiceProtocol`: `hostname_problems` and `register_enrollment_kind`, both pure contract functions a plugin reaches without a run (`launch_vocabulary.hostname_problems`, `enrollment.register_enrollment_kind`) and none reached through the service; the core's adapter loses them too. A member removed is something a plugin can observe, so while the contract is 0.x it is a MINOR step, and every dependent's range moved from `>=0.3,<0.4` ([the stage index](../../docs/CHANGES.md#s130)). |

## Writing a plugin

A plugin is a Python distribution with an entry point in the group
`cs_image_system.plugins.<kind>` (`PLUGIN_TYPES` in `constants`: `runtime`,
`state`, `modification`, `storage`, `group`, `user`, `image`, `os`,
`instance`, `other`). The entry point loads to a zero-argument callable
that returns one `PluginMetadata` or a list of them. The kind is the one
the plugin is: at least one class it registers must carry that kind's
classification (a `runtime` plugin a runtime builder model, a `group`
plugin a group builder), or the loader refuses it naming the group that
fits; it may register more than its kind, and a plugin of no named kind
(a version checker alone, an injected model) declares `other`.

1. **Depend on the contract.** In `pyproject.toml`, `dependencies =
   ["cs-image-system-contract>=X"]`, with `X` the first release that
   carries the contract ([the stage index](../../docs/CHANGES.md#s30)
   names it; 0.1.3 and before do not): a floor, not a pin --
   the workspace's own packages pin each other at `==` because they
   release together, an external plugin does not. Add `cs-image-system-base` only
   if the plugin subclasses the core's base classes (every built-in plugin
   does; it is the convenient way, not the required one). Never depend on
   `cs-image-system-system`, the CLI host.
2. **Write the model**: a pydantic dataclass, `@dataclass(kw_only=True,
   config=CSIS_MODEL_CONFIG)`, that satisfies the kind's
   `<Kind>BuilderModelProtocol`. The universal fields are `name`, `type`
   (the field is `type_`, aliased `type`), `description`, `aliases`,
   `executable`, `is_default`, `config`, `gitignore`, `tags`, with the
   `get_*` readers and `finalize`; the kind's module says what more the
   core reads. The class methods `csis_name()` (the value a YAML `type:`
   names) and `csis_classifier()` (`VCT.<KIND>_BUILDER_MODEL`) are how the
   registry resolves a `type:` to the class. A foreign key to another
   builder is `fk_field(target=VCT....)`; a value the resolver renders is
   `templated_field(...)`; an item that belongs to a builder declares
   `_model_id = parent_field(VCT....)`.
3. **Write the builder**: a class that satisfies the kind's
   `<Kind>BuilderProtocol`: the universal surface in `BuilderProtocol`
   (`generate_items_{before,during,after}` return an `AssetSet`,
   `get_commands_to_run_{before,during,after}` a `CFExecutables`,
   `pre_finalize_phase`/`post_finalize_phase`/`post_failed_phase` fire
   around a phase's deferred commands, `finalize` once the configuration
   is complete) plus the kind's domain hooks, and the same two class
   methods, `csis_classifier()` returning `VCT.<KIND>_BUILDER`. The core's
   `BuilderBase` and `<Kind>BuilderBase` implement every hook with a
   default; subclass them to override only what the plugin does. A
   runtime builder also declares the keys of the system's image-query
   vocabulary it can translate (`supported_query_keys()`) and translates
   a query to its own words (`translate_image_query(query)`; "The image
   query" under Configuration reference): `validate` refuses a key the
   runtime cannot translate before any bake, and the runtime's README
   carries the translation table.
4. **Return the metadata**: `PluginMetadata(services={KEY: [Model,
   Builder]}, builders_for_models={Model: Builder})`, where `KEY` is the
   `csis_name`. Item models a plugin injects under a classification go in
   `injected_models`. Every class the record registers is keyed in the
   registry by its classification, the plugin's **namespace** and its
   `csis_name`, so a word another plugin already uses is not a collision:
   a tree names either by the qualified form `<namespace>/<name>`. The
   namespace is derived from the plugin's distribution name with the
   `cs-image-system-` prefix and the `-plugin` suffix dropped
   (`cs-image-system-aws-runtime-plugin` registers under `aws-runtime`,
   an outside `acme-roots` under `acme-roots`); `namespace="..."` on the
   record overrides the derivation, and a record with no distribution
   behind it (one a test builds in process) must name one, or the loader
   refuses the plugin with the field named. Only the same classification,
   namespace and name taken by a *different* class is the collision; the
   same class registered by several plugins (one version checker three
   root plugins carry) is one registration, and its bare word resolves.
   The reasoning is in [the stage index](../../docs/CHANGES.md#s131).
5. **Prove it.** In the plugin's tests, `assert_conforms(Model,
   <Kind>BuilderModelProtocol)` and `assert_conforms(Builder,
   <Kind>BuilderProtocol)`; then a dry `cs-image-system run --all` over a
   tree that declares the plugin's `type:`.

A state backend is the smallest kind: a model that answers
`to_backend_registration()` with a `BackendRegistration` naming its type's
`BackendKindProtocol` (where a workspace's state lives, the settings the
workspace's backend file carries, the settings a consumer's remote-state
data source carries), and a builder that emits nothing; the core hands
the registration to the terraform collector once the state backends are
loaded. The [contract example plugin](../contract-example-plugin/README.md)
is exactly that, written against this package alone with nothing of the
core, and the proof the bar runs; the
[local state plugin](../local-state-plugin/README.md) is the same kind
written the convenient way on the base classes; the
[dummy plugin](../dummy-plugin/README.md) is the template for a group or
user builder and for a hook plugin.

The run context is the contract's
([the stage index](../../docs/CHANGES.md#s125)):
[`context`](src/cs_image_system/contract/context.py) holds
`RunContextProtocol` (what a plugin may read of the run: the run id, the
paths, the builder collections typed by the kind protocols, the
provider-specific image, the meta-state and `services`), `MetaStateProtocol`
and the service protocols reached as `ctx.services.<name>` (`lineage`,
`launch`, `secrets`, `files`, `commands`, `images`, `identity`, `storage`,
`workspaces`, `scope`, `cli`, `lifecycles`, `meta_state`), each sized by
what plugins use. The loader binds the context to every builder that has
a `bind(ctx)` method; a base builder reaches it through `_get_context()`.
The hooks entry point is [`hooks`](src/cs_image_system/contract/hooks.py)
(`HookSet` and the hook signatures, typed on the context protocol), the
modules entry point is [`modules`](src/cs_image_system/contract/modules.py)
(a plugin that ships terraform modules declares its modules directory
under `cs_image_system.modules` as `<package>:<dirname>`, and the core
reads the directory as package data), the
bootstrap vocabulary and `FactsProtocol` are
[`bootstrap`](src/cs_image_system/contract/bootstrap.py), and the
enrollment-kind registry is
[`enrollment`](src/cs_image_system/contract/enrollment.py); a plugin
imports from the core only its base classes, its models and the two
metadata abstractions (`tests/test_plugin_imports.py` holds the rule).

## Prerequisites and integration

Nothing outside Python: the package needs Python 3.13 or later, `pydantic`
and `packaging`, and no account, tool, credential or network. A plugin
finds it by import (`cs_image_system.contract.<module>`); the core finds
it the same way and pins it at its own version.

## Configuration reference

The contract reads no YAML of its own. What it declares about every
builder's entry, read by the core through `BuilderModelProtocol`:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | str | required | The builder's name; `safe_name` normalises it, `display_name` keeps what was written. Not a word in `OOPS_DEFAULTS`. |
| `type` | str | required | The plugin's `csis_name`, which the registry resolves to the model class; an alias resolves to the canonical name. |
| `description` | str or null | null | Free text. |
| `aliases` | set of str | empty | Other names the builder answers to. |
| `executable` | str or null | null | The `executables:` entry the builder runs, version-checked at validation; null for none. |
| `is_default` | bool | false | The default builder of its classification; one per classification. |
| `config` | mapping | empty | The plugin's own settings. |
| `gitignore` | list of str | empty | Entries the builder adds to the emitted `.gitignore`. |
| `tags` | mapping of str | empty | Tags every resource the builder emits carries. |

The kind modules say what more each kind reads (a runtime's defaults and
credentials, an OS builder's family and query, a user builder's email
templates); the plugin's own README is the reference for the fields it
adds.

### The image query

`image.ImageQuery` is the system's own vocabulary for "which
vendor image": the image-source catalog, an OS builder's `query` and its
runtime entry's are all written in it, and a runtime plugin translates it
to its own words through two hooks on `runtime.RuntimeBuilderProtocol`,
`supported_query_keys()` (the keys it can translate) and
`translate_image_query(query)` (its native form, whatever its query path
and packer data source take). The keys, in the order a query is written
out (`image.QUERY_KEYS`):

| Key | Meaning |
| --- | --- |
| `name` | a glob over the vendor's image name |
| `family` | the vendor's own family token, where the runtime has one |
| `version` | the major version: a container runtime's tag; the clouds expand it into `name` or `family` |
| `architecture` | `x86_64` or `arm64` |
| `publisher` | who owns the image: an account, a project, a registry namespace |
| `state` | `available` |
| `virtualization`, `root_device` | the EC2 particulars (`hvm`, `ebs`) |
| `tags` | a tag or label per key (`tag:<k>` in YAML is read into it) |
| `newest` | take the latest match (the default); false refuses an ambiguous match |
| `native` | the one escape hatch: passed to the runtime verbatim, never translated |

The spellings are the system's, with EC2's kept where they were good
names (the system started on AWS and used its filter keys); the old
spellings still read through `image.QUERY_KEY_ALIASES` (`owners`,
`root_device_type`, `virtualization_type`, `most_recent`, the nested
`filters:` form). `ImageQuery.from_mapping` refuses any other key by
name; `merged(over)` lets a query land on another key by key (`name`
and `family`, two ways to say which image, displace each other);
`substituted(version=...)` fills the catalog's one placeholder. Each
runtime's README carries the translation table for its keys, and a docs
test holds the table to the hook. Unknown keys are refused by `CSIS_MODEL_CONFIG` (`extra="forbid"`).
The sentinels `default`, `self`, `none`, the empty string and null
(`OOPS_DEFAULTS`) mean "not set" wherever a value is read, so nothing may
be named after one of them. Variations: none; the contract behaves the same
under a dry run and a real one, on every runtime.

## What it tests and verifies

- `assert_conforms(cls, protocol)` (`testing`): every member the protocol
  declares exists on the class, every method takes the protocol's
  parameters by name and kind in order (an implementation may add
  parameters with defaults, or take `*args` and `**kwargs`), a property is
  a property or a dataclass field, a class method a class method.
  Annotations are not compared here; pyright does that where a class
  lists its protocol as a base (its override check,
  `reportIncompatibleMethodOverride`, is on as an error),
  and a protocol a class lists as a base is the question, not an answer,
  so its stubs never count. The core's
  [tests/test_contract.py](../../tests/test_contract.py) runs it
  over every base class and every built-in plugin's models and builders at
  `just test`; a plugin's own tests should run it over theirs. The verdict
  is an `AssertionError` naming every shortfall.
- The import direction, in the same test: the package's sources import
  nothing from `cs_image_system.base`, `.system` or `.hashicorp_utils`,
  and each kind module imports only `core` and the kinds it declares.
  [tests/test_package_metadata.py](../../tests/test_package_metadata.py)
  holds the same line from the manifest: the package declares exactly the
  third-party distributions it imports and reaches no sibling.
- At load, the loader checks what an entry point returned with
  `isinstance(..., PluginMetadataProtocol)` and logs an error for anything
  else; runs `assert_conforms` over every class the metadata registers,
  against the protocol of its classification, and refuses the plugin on a
  shortfall (`PluginConformanceError`); the registry refuses a `csis_name`
  registered twice under one classification (`Type Collision`).

## When it fails

Incidents that have happened, with their cause and fix, are recorded on
[INCIDENTS.md](../../docs/INCIDENTS.md); what follows keeps each
failure's symptom, its meaning and what to do.

- `AssertionError: <class> does not conform to <protocol>: <member>: ...`
  from `assert_conforms`: the class lacks a member or a method's
  parameters differ from the protocol's. Add the member or match the
  signature; the protocol is the specification. If the shortfall is in a
  core base class, the contract changed and the core did not follow: that
  is the test doing its job, and the fix is in `base`.
- `Plugin <name> is refused: <class> does not conform to <protocol>:
  <member>: ...` (`PluginConformanceError`) at load: the plugin registered
  a class that lacks a member of its kind's protocol or answers it with
  the wrong parameters. Fix the class; nothing of the plugin loads until
  it conforms.
- `Plugin <name> did not return a valid PluginMetadataProtocol instance`
  in the log at load, and the plugin's types unknown to every `type:`: the
  entry point returned something other than a `PluginMetadata` (or a list
  of them) -- a class instead of an instance, a dict, nothing.
- `Plugin <name> is refused: its entry point has no distribution to
  derive a namespace from, and its metadata names none; set
  PluginMetadata.namespace` (`PluginNamespaceError`) at discovery: the
  entry point was registered without a distribution behind it (a test's
  in-process entry point, a module put on the path by hand) and the
  record left `namespace` at `None`, so nothing could qualify its
  registrations. Name the namespace on the record, or install the plugin
  as a distribution.
- `Type Collision: <namespace>/<name> under <classification> is
  <module.Class>, and <module.Other> registers it too` (`ValueError`
  from the registry) at load: one plugin, or two plugins that derive the
  same namespace, registers two *different* classes under one
  classification and name. The same word in two plugins with different
  namespaces is not this: both load, and a tree names one by its
  qualified form. Rename one of the classes' `csis_name`, or give one
  plugin a `namespace` of its own.
- `type '<word>' is ambiguous under <classification>: N plugins register
  it; write one of <ns1>/<word>, <ns2>/<word>` (`AmbiguousTypeError`) at
  load, which `validate` prints as one configuration error under
  `Validation failed with 1 error(s).`: the tree wrote a bare `type:`
  word that different classes answer to. Write one of the qualified
  forms the line names.
- `BackendWithoutKind` (`state`): a `BackendRegistration` was built without
  its `kind`; the model's `to_backend_registration()` must name the type's
  `BackendKindProtocol` object.
- `<Model> ... Extra inputs are not permitted` at load: a YAML key the
  model does not declare (`CSIS_MODEL_CONFIG` refuses unknown keys); the
  plugin's README names the fields it reads.
- `ModuleNotFoundError: No module named 'cs_image_system.base.protocols'`
  (or `...base.constants`, `...base.lifecycle`, `...base.basic.asset`,
  `...base.helpers.field_helpers`) from a plugin written against an older
  core: the names live here and the core has no path for them; import
  them from the contract module the table above names
  (`cs_image_system.contract.core`, `.constants`, `.lifecycle`, `.assets`,
  `.fields`).

No failure of this package has been seen in the field.

## Related

- [docs/PLUGINS.md](../../docs/PLUGINS.md), the index of every package.
- [base](../base/README.md), the core that implements the contract.
