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
check that says so. Stage 30 made the package (2026-10-29); until then the
protocols lived inside `base`, imported the registry, and a plugin's
`pyproject.toml` depended on the CLI host.

One module per kind of builder, over a shared core:

| Module | Carries |
| --- | --- |
| [`core`](src/cs_image_system/contract/core.py) | `PluginArtifactProtocol` (`csis_name`, `csis_classifier`), `NameTypedProtocol`, `PluginMetadataProtocol`, `BuilderModelProtocol` and `RuntimeEnabledBuilderModelProtocol` (what the core reads of any builder model), `BuilderProtocol` (the six universal hooks, the three finalize-phase hooks, `finalize`, the paths), and the three markers the orchestrator dispatches on: `SelfInjectedNameProtocol`, `SubItemOverrideProtocol`, `ParentPropertyHoldingProtocol`. |
| [`runtime`](src/cs_image_system/contract/runtime.py), [`operating_system`](src/cs_image_system/contract/operating_system.py), [`storage`](src/cs_image_system/contract/storage.py), [`image`](src/cs_image_system/contract/image.py), [`instance`](src/cs_image_system/contract/instance.py), [`modification`](src/cs_image_system/contract/modification.py), [`group`](src/cs_image_system/contract/group.py), [`user`](src/cs_image_system/contract/user.py), [`state`](src/cs_image_system/contract/state.py) | One `<Kind>BuilderModelProtocol` and one `<Kind>BuilderProtocol` per kind, with exactly the attributes and hooks the core reads. `state` also carries the backend seam: `StateLocation`, `BackendRegistration`, `BackendKindProtocol` and `StateBackendModelProtocol`. `image` carries the provider-specific image's two enums. |
| [`metadata`](src/cs_image_system/contract/metadata.py) | `PluginMetadata`, the record a plugin's entry point returns. |
| [`constants`](src/cs_image_system/contract/constants.py) | `VCT` (the classifications), the sentinels (`DEFAULT`, `SELF`, `NONE`, `OOPS_DEFAULTS`), the field metadata keys, `PLUGIN_TYPES` (the entry-point groups), the collection names, the file names a run writes. |
| [`model_config`](src/cs_image_system/contract/model_config.py) | `CSIS_MODEL_CONFIG`, the one pydantic configuration every model is declared under (unknown keys are refused). |
| [`fields`](src/cs_image_system/contract/fields.py), [`field_kinds`](src/cs_image_system/contract/field_kinds.py) | `fk_field`, `templated_field`, `deferred_list_field`, `deferred_list_fk_field`, `parent_field`; the open registry of field kinds a plugin may extend. |
| [`lifecycle`](src/cs_image_system/contract/lifecycle.py), [`lifecycles`](src/cs_image_system/contract/lifecycles.py) | `ExecutionLifecyclePhase`; `Lifecycle`, `LifecycleSpec` and the phases and builder classifications each built-in lifecycle owns. |
| [`assets`](src/cs_image_system/contract/assets.py), [`executables`](src/cs_image_system/contract/executables.py) | `Asset`, `AssetSet` (what `generate_items_*` returns); `ExecutableProtocol`, `CFExecutables` (what `get_commands_to_run_*` returns). |
| [`names`](src/cs_image_system/contract/names.py), [`hcl`](src/cs_image_system/contract/hcl.py) | `safe_name`, `super_safe_name`; `HclRaw`, `hcl_expr`, `render_module_call`. |
| [`testing`](src/cs_image_system/contract/testing.py) | `assert_conforms(cls, protocol)` and `conformance_problems`. |

### What moved where

Stage 30 moved these from the core into the package. Every old path but
`cs_image_system.base.protocols` still resolves: the module that held a
name re-exports it from here (the shims), kept on purpose while the
package is provisional. Removing the shims is the commitment to the
contract, and is done together with moving the package to a repository
of its own; until then an undo of the stage is a swap of which side
holds the bodies, with no import rewritten anywhere.

| Was | Is now |
| --- | --- |
| `base.constants` (all of it: `VCT`, the sentinels, the field metadata keys, `PLUGIN_TYPES`, the collection and file names) | `contract.constants` |
| `base.models.model_config.CSIS_MODEL_CONFIG` | `contract.model_config` |
| `base.helpers.field_helpers` (`fk_field`, `templated_field`, `deferred_list_field`, `deferred_list_fk_field`, `lookup_dataclass_field`) | `contract.fields`, plus the new `parent_field` |
| `base.helpers.field_kinds` (the field-kind registry) | `contract.field_kinds` |
| `base.lifecycle.ExecutionLifecyclePhase` | `contract.lifecycle` |
| `base.lifecycles`: `Lifecycle`, `LifecycleSpec`, `LifecycleLike`, `LIFECYCLE_ORDER`, `LIFECYCLE_PHASES`, `LIFECYCLE_BUILDER_VCTS` (the registry functions stay in `base`) | `contract.lifecycles` |
| `base.basic.asset`: `Asset`, `AssetSet` (`sort_and_write` now takes the generation path) | `contract.assets` |
| `base.models.executable_adds.CFExecutables` (now generic over `ExecutableProtocol`) | `contract.executables` |
| `base.protocols.plugin_metadata`: `PluginArtifactProtocol`, `PluginMetadataProtocol`; `base.protocols.name_typed_protocol`: `NameTypedProtocol`, `SelfInjectedNameProtocol`, `SubItemOverrideProtocol`; `base.protocols.builder_model_protocol`: `BuilderModelProtocol`; `base.protocols.parent_property_holding_protocol`: `ParentPropertyHoldingProtocol` (deleted, no shim; their default bodies are `base.models.mixins` and the base classes) | `contract.core` |
| `base.protocols.state_management.StateManagementRootProtocol` (zero implementers) | deleted |
| `base.utils.safe_name`, `super_safe_name` | `contract.names` |
| `base.utils.HclRaw`, `hcl_expr`, `render_module_call` | `contract.hcl` |
| `base.models.provider_specific_image.PSIState`, `PSISourceKind`, `psi_key` | `contract.image` |
| `hashicorp_utils.collector.StateLocation`, `BackendRegistration`, the `BackendKind` protocol (still importable from the collector) | `contract.state` (`BackendKindProtocol`; `BackendWithoutKind` is new) |
| nothing: new | `contract.metadata.PluginMetadata`, the kind protocols, `contract.testing` |

The protocols carry no implementation. Where a default body existed
(`global_id`, `get_classification`, `get_self_injected_name`, the parent
reference's registry lookup) it lives in the core's base classes and
mixins. The kind modules import `core` and only the kinds they declare they
read (`runtime` reads `image` for the provider-specific image's enums);
[tests/test_v2_contract.py](../../tests/test_v2_contract.py) holds that
direction, holds the package to importing nothing from the core, and runs
`assert_conforms` over every base class and every built-in plugin's models
and builders.

## Writing a plugin

A plugin is a Python distribution with an entry point in the group
`cs_image_system.plugins.<kind>` (`PLUGIN_TYPES` in `constants`: `runtime`,
`state`, `modification`, `storage`, `group`, `user`, `image`, `os`,
`instance`, `other`). The entry point loads to a zero-argument callable
that returns one `PluginMetadata` or a list of them.

1. **Depend on the contract.** In `pyproject.toml`, `dependencies =
   ["cs-image-system-contract>=X"]`, with `X` the first release that
   carries the contract (0.1.3 and before do not): a floor, not a pin --
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
   `injected_models`.
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

Not in the contract yet, so a plugin that needs them depends on `base`:
the run context (`GlobalTypeContext`, reached today through a base
builder's `_get_context()`; its protocol is a later stage), the
`cs_image_system.plugins.hooks` entry point (`HookSet`, typed on the
context) and the `cs_image_system.bootstrap` entry point (the bootstrap's
sections).

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

`image.ImageQuery` (stage 106) is the system's own vocabulary for "which
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
name; `merged(over)` lets a query land on another key by key;
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
  `reportIncompatibleMethodOverride`, is on as an error since hygiene XIX),
  and a protocol a class lists as a base is the question, not an answer,
  so its stubs never count. The core's
  [tests/test_v2_contract.py](../../tests/test_v2_contract.py) runs it
  over every base class and every built-in plugin's models and builders at
  `just test`; a plugin's own tests should run it over theirs. The verdict
  is an `AssertionError` naming every shortfall.
- The import direction, in the same test: the package's sources import
  nothing from `cs_image_system.base`, `.system` or `.hashicorp_utils`,
  and each kind module imports only `core` and the kinds it declares.
  [tests/test_v2_package_metadata.py](../../tests/test_v2_package_metadata.py)
  holds the same line from the manifest: the package declares exactly the
  third-party distributions it imports and reaches no sibling.
- At load, the loader checks what an entry point returned with
  `isinstance(..., PluginMetadataProtocol)` and logs an error for anything
  else; the registry refuses a `csis_name` registered twice under one
  classification (`Type Collision`).

## When it fails

- `AssertionError: <class> does not conform to <protocol>: <member>: ...`
  from `assert_conforms`: the class lacks a member or a method's
  parameters differ from the protocol's. Add the member or match the
  signature; the protocol is the specification. If the shortfall is in a
  core base class, the contract changed and the core did not follow: that
  is the test doing its job, and the fix is in `base`.
- `Plugin <name> did not return a valid PluginMetadataProtocol instance`
  in the log at load, and the plugin's types unknown to every `type:`: the
  entry point returned something other than a `PluginMetadata` (or a list
  of them) -- a class instead of an instance, a dict, nothing.
- `Type Collision: <name>` at load: two plugins register one `csis_name`
  under one classification; rename one.
- `BackendWithoutKind` (`state`): a `BackendRegistration` was built without
  its `kind`; the model's `to_backend_registration()` must name the type's
  `BackendKindProtocol` object.
- `<Model> ... Extra inputs are not permitted` at load: a YAML key the
  model does not declare (`CSIS_MODEL_CONFIG` refuses unknown keys); the
  plugin's README names the fields it reads.
- `ModuleNotFoundError: No module named 'cs_image_system.base.protocols'`
  from a plugin written before stage 30 running on this tree: the
  protocols moved here, with no shim; import them from
  `cs_image_system.contract.core`.

No failure of this package has happened in the field yet (2026-10-29).

## Related

- [docs/PLUGINS.md](../../docs/PLUGINS.md), the index of every package.
- [base](../base/README.md), the core that implements the contract.
