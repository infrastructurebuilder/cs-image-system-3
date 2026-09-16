# cs-image-system-base

The core library of cs-image-system. It defines the configuration models,
the plugin contract, the registry, the lifecycle runner, the cross-run
meta-state, value encryption, the public-safe gate, and the lineage,
release, retention, launch-parameter and capability rules that every plugin
and the command-line host build on.

It contains no cloud code. Clouds, identity providers, packer and terraform
live in plugins that register through the contract described here. The
package is licensed under Apache-2.0 and requires Python 3.13 or later.

Declared dependencies: `Jinja2`, `PyYAML`, `cattrs`, `multipledispatch`,
`age`. The models are pydantic dataclasses; `packaging` is used for version
specifiers.

The package registers itself as a plugin too: the entry point
`cs_image_system.plugins.base` (`cs_image_system.base.init:initialize`)
injects the `StorageMapping` item model as the default
`STORAGE_MAPPING_ITEM_MODEL`.

## Contents

- [The plugin contract](#the-plugin-contract)
- [The configuration tree](#the-configuration-tree)
- [How YAML becomes models](#how-yaml-becomes-models)
- [The base models](#the-base-models)
- [`cfg/_config.yml` key by key](#cfg_configyml-key-by-key)
- [Lifecycles and phases](#lifecycles-and-phases)
- [A run: generation, finalization, dry run, commit](#a-run-generation-finalization-dry-run-commit)
- [The run context](#the-run-context)
- [Meta-state](#meta-state)
- [Encryption](#encryption)
- [The public-safe gate](#the-public-safe-gate)
- [Lineage](#lineage)
- [Releases](#releases)
- [Retention](#retention)
- [Launch parameters](#launch-parameters)
- [Capabilities](#capabilities)
- [Other modules](#other-modules)
- [Tests](#tests)

## The plugin contract

Source: [`protocols/`](src/cs_image_system/base/protocols/),
[`registry.py`](src/cs_image_system/base/registry.py),
[`loader.py`](src/cs_image_system/base/loader.py),
[`constants.py`](src/cs_image_system/base/constants.py),
[`basic/abstract_plugin_metadata.py`](src/cs_image_system/base/basic/abstract_plugin_metadata.py).

### Entry points

A plugin is a Python distribution that declares one or more entry points in
the group `cs_image_system.plugins.<type>`. The loader walks these groups in
this order:

| Group suffix   | Plugin type    |
| ---------------- | ---------------- |
| `base`         | base types     |
| `runtime`      | runtime (cloud or container) providers |
| `state`        | terraform state backends |
| `modification` | image modifications (mods) |
| `storage`      | storage builders |
| `group`        | group (identity) builders |
| `user`         | user builders  |
| `image`        | image builders |
| `os`           | OS (base image) builders |
| `instance`     | instance builders |
| `other`        | anything else  |

Each entry point loads to a callable. `load_plugins()` calls it and expects
one `PluginMetadataProtocol` object or a list of them. Entry points within
a group load in name order. Loading is idempotent: a second call in the same
process returns at once unless `Registry().reset()` was called. After every
plugin registered, the loader drops the cached converter so the next
structuring sees the full model set.

A separate group, `cs_image_system.plugins.hooks`, carries run hooks
(see [Other extension seams](#other-extension-seams)).

### Plugin metadata

`PluginMetadataProtocol` has these members. `AbstractPluginMetadata`
implements it from constructor arguments in this order.

| Member                        | Type                                  | Meaning |
| ------------------------------- | --------------------------------------- | --------- |
| `plugin_metadata_version`     | `str`                                 | Version of the metadata shape. |
| `requires_python`             | `SpecifierSet`                        | Python requirement. |
| `services`                    | `dict[str, list[type]]`               | Classes to register, grouped under a service name. Every class implements `PluginArtifactProtocol`. |
| `builders_for_models`         | `dict[type, type]`                    | Model class to builder class. One builder per model. |
| `injected_models`             | `dict[VCT, type]`                     | Item models the plugin injects under a classification. |
| `is_injected_models_default`  | `bool`                                | Whether injected models become the default for their classification. |

`PluginArtifactProtocol` is two class methods:

| Method            | Returns | Meaning |
| ------------------- | --------- | --------- |
| `csis_name()`     | `str`   | The canonical name. For a builder model this is the value a YAML `type:` names. |
| `csis_classifier()` | `VCT` | The classification the class registers under. |

A typical plugin registers a model class and its builder class under the
same service name and maps the model to the builder in
`builders_for_models`.

### Classifications (`VCT`)

`VCT` is a string enum. A `*_BUILDER_MODEL` value classifies a
configuration dataclass (what YAML structures into); the matching
`*_BUILDER` value classifies the class that generates from it. Item models
classify the entries under `images/`, `instances/` and so on.

| Member                                  | Value                                   | Classifies |
| ----------------------------------------- | ----------------------------------------- | ------------ |
| `UNCLASSIFIED`                          | `__NMC__`                               | Objects with no classification. |
| `RUNTIME_BUILDER_MODEL` / `RUNTIME_BUILDER` | `runtime_builder_model` / `runtime_builder` | Runtime provider configuration and builder. Cloud and container models are also registered here. |
| `CLOUD_BUILDER_MODEL` / `CLOUD_BUILDER` | `cloud_builder_model` / `cloud_builder` | A cloud runtime (region and networking). |
| `CONTAINER_BUILDER_MODEL` / `CONTAINER_BUILDER` | `container_builder_model` / `container_builder` | A container runtime. |
| `USER_BUILDER_MODEL` / `USER_BUILDER`   | `user_builder_model` / `user_builder`   | User (identity) builders. |
| `GROUP_BUILDER_MODEL` / `GROUP_BUILDER` | `group_builder_model` / `group_builder` | Group (identity) builders. |
| `OS_BUILDER_MODEL` / `OS_BUILDER`       | `os_builder_model` / `os_builder`       | OS builders, which produce base images. |
| `OS_IMAGE_BUILDER_SUBCONFIG_MODEL` / `OS_IMAGE_BUILDER_SUBCONFIG` | `os_image_builder_subconfig_model` / `os_image_builder_subconfig` | One `runtimes:` entry of an OS builder. |
| `IMAGE_BUILDER_MODEL` / `IMAGE_BUILDER` | `image_builder_model` / `image_builder` | Image builders (bakers). |
| `IMAGE_IMAGE_BUILDER_SUBCONFIG_MODEL`   | `image_image_builder_subconfig_model`   | One `runtimes:` entry of an image. |
| `STORAGE_MAPPING_ITEM_MODEL`            | `storage_mapping_item_model`            | One `storages:` entry of an instance. |
| `MOD_BUILDER_MODEL` / `MOD_BUILDER`     | `mod_builder_model` / `mod_builder`     | Modification builders. |
| `MOD_BUILDER_ITEM_MODEL`                | `mod_builder_item_model`                | One `modifications:` entry of an image. |
| `INSTANCE_BUILDER_MODEL` / `INSTANCE_BUILDER` | `instance_builder_model` / `instance_builder` | Instance builders. |
| `STORAGE_BUILDER_MODEL` / `STORAGE_BUILDER` | `storage_builder_model` / `storage_builder` | Storage builders. |
| `STATE_BACKEND_MODEL` / `STATE_BACKEND` | `state_backend_model` / `state_backend` | Terraform state backends. |
| `EXECUTABLE_MODEL`                      | `executable_model`                      | Executables declared under `executables:`. |
| `VERSION_CHECKER`                       | `version_checker`                       | Version checkers, keyed by executable type. |
| `BASE_IMAGE_MODEL`                      | `base_image_model`                      | Base images (synthesized from OS builders). |
| `IMAGE_MODEL`                           | `image_model`                           | Images under `images/`. |
| `INSTANCE_MODEL`                        | `instance_model`                        | Instances under `instances/`. |
| `GROUP_MODEL`                           | `group_model`                           | Groups under `groups/`. |
| `USER_MODEL`                            | `user_model`                            | Users under `groups/`. |
| `STORAGE_MODEL`                         | `storage_model`                         | Storages under `storages/`. |
| `MOD_MODEL`                             | `mod_model`                             | Reserved for modification items. |
| `SOURCE_MODEL_MODEL`                    | `source_model_model`                    | Reserved. |
| `RESOLVED_IMAGE_MODEL`                  | `resolved_image_model`                  | Reserved. |
| `PROVIDER_SPECIFIC_IMAGE`               | `provider_specific_image`               | An image as one runtime knows it (an AMI id, a GCE image name). |

`sanitize_classifier()` maps `CLOUD_BUILDER_MODEL` and
`CONTAINER_BUILDER_MODEL` to `RUNTIME_BUILDER_MODEL`, so a YAML
`runtime_builders:` entry can name a cloud plugin or a container plugin in
its `type:`.

Two more enums live in `constants.py`: `OSFamilies` (`rhel`, `ubuntu`,
`debian`, `fedora`, `opensuse`, `suse`, `rocky-linux`, `alma-linux`,
`centos`, `centos-stream`) and `ComplianceState` (`ignored`, `acceptable`,
`unacceptable`, the result of an executable version check).

### The registry

`Registry` is a process-wide singleton. It holds:

| Store                     | Keyed by                          | Holds |
| --------------------------- | ----------------------------------- | ------- |
| `models`                  | `VCT`, then canonical name        | Model classes a `type:` value can select. A second registration of the same name is a `ValueError` ("Type Collision"). |
| `builders`                | model class                       | The builder class for a model. |
| `registry` / `vct_type_registry` / `reverse_registry` | service name / `VCT` / class | Services by name and classification; `get_builder_for_model(type_name, classification)` reads `registry`. |
| `instances`               | `VCT`, then name or alias         | Built objects: builder models, builders, items. Cloud and container builders are mirrored under the runtime classifications. |
| `instances_by_global_id`  | `global_id`                       | The same objects by `<classification>::<model_id>::<name>`. |
| `aliases` / `classified_aliases` | `VCT`                      | Builder aliases; a duplicate alias within a classification is an error. |
| `defaults_registry`       | `VCT`                             | The name of the default builder per classification. A default may not be `default`, `self`, empty or `None`. |

`get_instance_by_name_or_alias(vct, "default")` resolves to the registered
default. `reset()` clears everything, which is how tests and repeated loads
start clean.

### Builder base classes and hooks

Source: [`basic/`](src/cs_image_system/base/basic/).

Every builder wraps one builder model (`builder.model`) and extends
`BuilderBase`. The runner calls these hooks with an
`ExecutionLifecyclePhase`:

| Hook                                   | Returns          | When |
| ---------------------------------------- | ------------------ | ------ |
| `generate_items_before(phase)`         | `AssetSet`       | Before every phase, for every builder. |
| `get_commands_to_run_before(phase)`    | `CFExecutables`  | Before every phase, for every builder. |
| `generate_items_during(phase)`         | `AssetSet`       | During a phase, only for builders of that phase's classification. |
| `get_commands_to_run_during(phase)`    | `CFExecutables`  | During a phase, same rule. |
| `generate_items_after(phase)`          | `AssetSet`       | After every phase, for every builder. |
| `get_commands_to_run_after(phase)`     | `CFExecutables`  | After every phase, for every builder. |
| `pre_finalize_phase(phase)` / `post_finalize_phase(phase)` | `None` | Around each phase's deferred commands in a real run. Never in a dry run. |
| `finalize()`                           | `None`           | Once, after the builder is constructed. |
| `copy_external_assets(target, mod)`    | `dict[str, Path]` | Optional asset staging. |

An `AssetSet` is a list of `Asset` objects, each a `(relative path, content)`
pair. The runner writes them under the current generation path; hooks never
write files themselves. `CFExecutables` holds two lists of `ExecutableModel`:
`build_executables` run immediately during generation and
`finalize_executables` are deferred to finalization.

Helpers on `BuilderBase`: `get_path_for_phase(phase, discriminator, suffix)`
returns `<builder>/<phase>/<builder>-<phase>[-<discriminator>][<suffix>]`;
`get_executable_copy()` returns a deep copy of the executable the model
names (an error when it is not declared under `executables:`);
`_get_context()` returns the run context.

Per-kind bases add a contract:

| Base class            | Classification     | Notable members |
| ----------------------- | -------------------- | ----------------- |
| `RuntimeBuilderBase`  | `RUNTIME_BUILDER`  | `query_provider_image`, `query_images`, `verify_instance`, `run_session_command`, `inventory`, `dispose_image`, `retag_image`, `packer_source_type`, `packer_source_blocks`, `build_id_from_artifact`, `session_mechanism`, `session_agent_commands`, `session_verify_commands`, `bake_finalize_commands`, `query_instance_boot_image`, `bake_ssh_username`, `release_commands`, `session_instance_profile`, `provider_specific_image_class`, `create_provider_specific_image_resolved` / `_deferred`. |
| `CloudBuilderBase` / `ContainerBuilderBase` | runtime | Thin subclasses of `RuntimeBuilderBase`. |
| `GroupBuilderBase`    | `GROUP_BUILDER`    | `identity_type()`, `gid_policy()` (`config-time`, `creation-only`, `provider-assigned`), `managed_groups()`, `enrollment_token_reference()`, `base_image_prerequisites()`, `verify_commands()`, `activation_commands()`, `activation_verify_commands()`, `launch_parameters()`, `query_state()`, `validate_attributes()`, `query_attributes()`, `attribute_conflicts()`, `export_gids()`. |
| `UserBuilderBase`     | `USER_BUILDER`     | `add_user_to_builder()` enforces `email_as_username`; `default_managed()`, `is_managed()`, `validate_user()`, `validate_attributes()`, `query_attributes()`. |
| `StorageBuilderBase`  | `STORAGE_BUILDER`  | `capability_type()`, `attachment_cardinality()` (`single` or `many`), `is_posix()`, `base_image_prerequisites()`, `verify_commands()`, `transition_actions()`, `validate_lifecycle()`, `query_state()`, `destroy_whitelist()`. |
| `ImageBuilderBase`    | `IMAGE_BUILDER`    | `add_image()`, `get_images()`, `build_target_label()`, block paths per phase. |
| `InstanceBuilderBase` | `INSTANCE_BUILDER` | `add_instance()`; `finalize()` registers the builder with its runtime. |
| `OsBuilderBase`       | `OS_BUILDER`       | `generate_resolved_image()`, `generate_items_for_os_update()`, `get_configs_for_image_builders()`. |
| `ModBuilderBase`      | `MOD_BUILDER`      | `generate_items_before/during/after_modification(image, mod, image_builder, phase, path)`. |
| `StateBuilderBase`    | `STATE_BACKEND`    | Marker base. |

The run context orders builders as: runtime, state, group, user, OS, mod,
storage, image, instance, each sorted by name. Before/after hooks fire in
that order.

### Version checkers

`AbstractVersionChecker` classifies as `VERSION_CHECKER`. A plugin
registers one per executable type; validation looks it up by the
executable's `type` and runs `get_version()`, which executes the binary
with `get_version_params()` (default `--version`), extracts the first line
and applies `get_regex()`. The result is compared with the executable's
`version` specifier.

### Other extension seams

| Seam | Where | What it adds |
| ------ | ------- | -------------- |
| Run hooks | entry point group `cs_image_system.plugins.hooks`; `HookSet` in [`commands/run_lifecycles.py`](src/cs_image_system/base/commands/run_lifecycles.py) | `validators` (return error strings; any error aborts the run), `after_generate`, `before_apply`, `after_apply` (real runs only), `on_summary`, and `lifecycles` (a list of `LifecycleSpec`). |
| Lifecycles | `register_lifecycle(LifecycleSpec)` in [`lifecycles.py`](src/cs_image_system/base/lifecycles.py) | A lifecycle with its own phases, builder classifications, directory and runner script, positioned after an existing one. |
| Field kinds | `register_field_kind(name, FieldKindHandler)` in [`helpers/field_kinds.py`](src/cs_image_system/base/helpers/field_kinds.py) | A late-binding behaviour for fields carrying `field_kind` metadata: `contribute_context`, `resolve`, `upgrade`. |
| Resolution passes | `register_resolution_pass(name, fn, order)` in [`helpers/resolution_stages.py`](src/cs_image_system/base/helpers/resolution_stages.py) | A string-stage pass over the raw YAML document. Built in: `interpolate` (order 10) and `scope-this` (order 20). |
| Item kinds | `register_item_kind(ItemKind)` in [`global_context.py`](src/cs_image_system/base/global_context.py) | A new domain-item collection: directory, model class, owning builder classification, attach function, optional validation. |

## The configuration tree

A configuration is a directory (the `--root-dir`). The base package reads:

| Path | Read by | Contents |
| ------ | --------- | ---------- |
| `cfg/*.yml`, `cfg/*.yaml` | `read_and_process` (not recursive) | Every file is a mapping. Lists under the same key are concatenated across files; scalar keys are overwritten by later files. Duplicate `name` values within a list are refused. A `name` or `type` containing `{{` is refused. |
| `groups/**` | item kinds `users`, then `groups` | `users:` and `groups:` lists. Users are read first so group members can be checked. |
| `storages/**` | item kind `storages` | `storages:` lists. |
| `images/**` | item kind `images` | `images:` lists. |
| `instances/**` | item kind `instances` | `instances:` lists. |
| `base_images/**` | registered as a base-only kind | Not read in the normal flow. Base images are synthesized from OS builders during the base-image lifecycle. |
| `meta-state/` | `MetaState` | The committed cross-run records ([Meta-state](#meta-state)). |
| `generated/` (or `generation_directory`) | the runner | Generated output. Wiped per lifecycle directory. |

The frozen test fixture under
[`tests/fixtures/config`](../../tests/fixtures/config) is a complete
example, with synthetic personas (`avery.alpha` and friends on example
domains) in its rosters.

Overlays (`--overlay <file>`) are YAML mappings whose keys are `config` and
the item collection keys (`users`, `groups`, `storages`, `images`,
`instances`, `base_images`). A `config` mapping updates the tree's
`config:` key by key. A named entry that exists is updated key by key; a new
one is appended for this invocation only and remembered as transient; an
entry carrying `undeclare: true` removes the tree's entry for this
invocation. `--undeclare <kind>:<name>` does the same without a file. The
tree on disk is never changed.

## How YAML becomes models

Source: [`template_utils.py`](src/cs_image_system/base/template_utils.py),
[`orchestrator.py`](src/cs_image_system/base/orchestrator.py),
[`helpers/field_helpers.py`](src/cs_image_system/base/helpers/field_helpers.py),
[`global_context.py`](src/cs_image_system/base/global_context.py).

### The string stage

Before anything is structured, the merged `cfg/` document is rendered as
text by the ordered resolution passes:

1. `interpolate` renders Jinja tags against `ENV` (the process
   environment), `execution` and the document's own `config:` map.
   `execution.timestamp` is the run start formatted with the tree's
   `dateformat` (fallback `%Y%m%d_%H%M%S`); `execution.date` is the ISO
   date; `execution.dateformat` is the format string.
2. `scope-this` renders, per plugin key (`runtime_builders`,
   `os_builders`, ...), with `this` bound to the nearest enclosing mapping
   and `this.parent` to the mapping that owns it.

Tags that cannot render are kept as written, so a later stage can render
them.

### Structuring

Every model is a pydantic dataclass with one shared configuration
(`CSIS_MODEL_CONFIG`): unknown keys are errors (`extra="forbid"`), numbers
are coerced to strings where a string is declared, and a field can be given
by name or by alias (`type` is the alias of `type_`).

For each plugin key in the document, every entry is structured against the
base class of that key (for example `runtime_builders` against
`RuntimeBuilderModel`). The converter reads the entry's `type`, looks up
`Registry().get_model(<classification>, type)` and structures the entry as
that class. An alias is canonicalized to the class's `csis_name()` first.
A missing `type` is an error; an unknown `type` is a `KeyError`.

Every builder model is then finalized, wrapped in its builder class
(`builders_for_models`), registered, and the classification's default is
set. Exactly one builder per classification must carry `is_default: true`.
A builder whose model has a `runtime` field has that field canonicalized to
the runtime builder's registered name.

Item collections structure the same way. When an item's `type` is `default`
or missing and the kind declares `default_missing_type_to`, the registered
default builder of that classification is used. The item is attached to its
builder (`add_user_to_builder`, `add_group_to_builder`, `add_storage`,
`add_image`, `add_instance`). An image also attaches to every other image
builder named in its `runtimes:` whose runtime differs from the primary.

### Field kinds

Field factories in `helpers/field_helpers.py` stamp metadata that the
`TemplateResolver` acts on:

| Factory | Kind | Behaviour |
| --------- | ------ | ----------- |
| `fk_field(target, also_set_on_update=None, ...)` | `fk` | The value names an object of classification `target`. A `default` value resolves to the registered default. In templates the field name yields the object itself (`{{ runtime.get_default_machine_type() }}`). With `also_set_on_update`, the named attribute (used as `model_id`) is set to the target's `global_id` and `builder` is put in the template context. |
| `templated_field(replace_value, ...)` | `templated` | When the value is `default`, `replace_value` (a Jinja string) is rendered in its place. |
| `deferred_list_field(builder_vct, item_vct)` | `deferred_list` | A list of mappings structured late, after every builder is registered: each entry's `type` selects a builder of `builder_vct`; the entry is structured as the item class registered under `item_vct` (or the owning model's `get_subitem_overrides()`). Used for `modifications:` and `storages:`. |
| `deferred_list_fk_field(target)` | `deferred_list_fk` | A list of foreign keys resolved late. |

A plugin may register a new kind and stamp `field_kind` metadata on its own
fields.

### Template resolution

After structuring, `TemplateResolver.resolve_all()` renders, up to five
passes, every string and mapping field that still contains `{{`. Each
object renders in a `SmartContext` that exposes:

| Name | Value |
| ------ | ------- |
| `this` | The object being resolved. |
| every `fk` field name | The referenced object (or the raw id when unresolved). |
| `builder` | The owning builder model, when an `also_set_on_update` foreign key resolved. |
| `image`, `instance`, `group`, `user`, `storage`, `storagemapping` | The object itself, injected under its own lower-case class name (`SelfInjectedNameProtocol`). |
| `identified_model` | On sub-items, the parent model. |
| `execution`, `ENV` | The run values and the environment. |
| any `global_id` | Every registered object, by id. Hyphen and underscore spellings of a key are tried interchangeably. |

Examples from the fixture: `description: "{{ group.name }} group"`,
`email` derived from a builder's `default_user_email_template`
(`{{ user.name }}@example.invalid`), `OS: "{{ this.parent.family }}"` in an
OS builder's tags, `systemuser: "{{ ENV.USER }}"` in `config:`.

### Naming rules

`safe_name()` strips whitespace, replaces spaces and `:` with `_`, and
lower-cases. Every `name` and alias is normalized this way; `display_name`
keeps the original spelling for output. A name or alias may not be
`default`, `self`, empty or `None`, and may not contain `/` or `\`. An
alias equal to the name is dropped. `super_safe_name()` additionally
replaces `+ . / \ - @` with `_`; it names terraform workspaces and state
files.

## The base models

Source: [`models/`](src/cs_image_system/base/models/). Every table lists
the fields the class adds; inherited fields are named in the first column
of each section. "fk" marks a foreign key and names the classification;
"templated" marks a templated default.

### Common bases

`NameTyped` (every builder model, executable, storage, and subconfig):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `name` | `str` | required | Normalized; see naming rules. |
| `type` | `str` | required | Selects the model class (builder models) or names the owning builder (items). |
| `description` | `str \| None` | `None` | Free text. |
| `aliases` | `set[str]` | empty | Alternative names. |

`BuilderModel` (`NameTyped` plus):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `executable` | `str \| None` | `None` | Name of an entry under `executables:` this builder runs. |
| `is_default` | `bool` | `False` | The default builder of its classification. Exactly one per classification. |
| `config` | `dict[str, Any]` | `{}` | Builder-specific settings. |
| `gitignore` | `list[str]` | `[]` | Extra `.gitignore` entries. |
| `tags` | `dict[str, str]` | `{}` | Tags applied to what the builder produces. |

A `parameters` key on any builder model is refused with a message naming
`variables:` as the replacement for module inputs.

`RuntimeEnabledBuilderModel` (`BuilderModel` plus `runtime`, fk
`RUNTIME_BUILDER_MODEL`, default `default`). Image, instance and storage
builders extend it; `get_runtime_provider()` raises when the value is still
a default sentinel.

`RootItem` (`NameTyped` plus `tags: dict[str, str]` and
`config: dict[str, Any]`, both empty by default) is the base of images,
instances, groups and users. `SubRootItem` adds the parent link
(`_model_id`, `identified_model`, `builder`) used by sub-items.

### `ExecutableModel` (`cfg/executables.yml`, key `executables`)

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `type` | `str` | `executable` | `default` becomes the name. Selects the version checker. |
| `version` | `str \| None` | `None` | A PEP 440 specifier such as `>=1.14, <1.15`; checked at validation. |
| `binary` | `str \| None` | the name | Path or command to run. |
| `prepended_arguments` / `appended_arguments` | `list[str]` | `[]` | Wrapped around every invocation (skipped for version checks). |
| `args` | `list[str]` | `[]` | Arguments set per invocation by builders. |
| `config` | `dict[str, Any]` | `{}` | Free settings. |
| `working_directory` | `Path \| None` | `None` | Set per invocation. |

`execute(*args, skips=False)` runs `[binary] + prepended + args + appended`
with `subprocess.run(check=True, capture_output=True)` in the working
directory. Names must be unique.

### Runtime builders (`cfg/runtime-builders.yml`, key `runtime_builders`)

`RuntimeBuilderModel` (`BuilderModel` plus):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `default_machine_type` | `str` | required | Machine type when nothing more specific is given. |
| `default_image_builder` | `str` (fk `IMAGE_BUILDER_MODEL`) | `default` | Image builder used for bakes on this runtime. |
| `default_owners` | `list[str] \| None` | `None` | Owners added to vendor image queries. |
| `credentials` | `CredentialsBase` | empty | Declared object; each plugin narrows it to its own subclass, so an unknown key is an error. Values name a profile or read the environment; no credential value belongs in the tree. |
| `default_config_username` | `str \| None` | `None` | Fallback SSH user for bakes. |
| `ephemeral` | `bool` | `False` | Nothing baked here survives a successful run; the retention lifecycle disposes every image. Declared storages are never touched. |
| `retention_keep` | `int \| None` | `None` | Builds per series kept for images that declare no `retention`. `None` keeps everything. |
| `on_failure` | `str \| None` | `None` | Runtime default for ephemeral instances: `keep` or `teardown`. |
| `teardown_after` | `str \| None` | `None` | Runtime default duration (`30m`, `2h`, `1d`). |

`CloudBuilderModel` adds `region: str` (required) and `networking:
CloudNetworkingConfig` (required). `ContainerBuilderModel` adds
`networking: ContainerNetworkingModel | None` (with `network_id`, default
`local`).

`RuntimeNetworkingModel`:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `name` | `str` | the network | Label. |
| `network` | `str` | `default` | Network id (a VPC id, a GCE network name). Must not be empty. |
| `subnets` | `list[RuntimeSubnetModel]` | `[]` | At least one; exactly one must be `is_default: true`. |
| `availability_zones` | `list[RuntimeAvailabilityZoneModel]` | `[]` | Named locations, one may be default. |

`RuntimeSubnetModel`: `name` (defaults to `subnet_id`), `subnet_id`
(required), `is_default` (`False`), `public` (`False`), `cidr` (`None`),
`config` (`{}`). `RuntimeAvailabilityZoneModel`: `name`, `is_default`.

`RuntimeBuilderModel.finalize()` is where cloud plugins validate networking
against the cloud, so loading a configuration with cloud runtimes needs
live credentials for each.

### OS builders (`cfg/os-builders.yml`, key `os_builders`)

`OsBuilderModel` (`BuilderModel` plus):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `family` | `str` | required | OS family (see `OSFamilies`). |
| `family_version` | `str` | required | Version; a number is coerced to text. |
| `architecture` | `str` | `default` | CPU architecture. |
| `default_primary_disk_size` | `str \| int` | `200` | Bake disk size in GB when `default`. |
| `tags` | `dict[str, str]` | `{}` | Tags for the base image. |
| `owners` | `list[str]` | `[]` | Vendor image owners. |
| `query` | `dict[str, Any]` | `{}` | Vendor image query (provider-specific filters). |
| `runtimes` | `list[OSBuilderBaseImageBuilderSubconfig]` | required, at least one | One entry per image builder to bake on. `image_builder` must be unique across entries. |
| `config_username` | `str \| None` | `None` | Sudo-capable user for provisioning. |
| `auto_update` | `bool` | `False` | Alias for `update.policy: full`. |
| `update` | `dict \| None` | `None` | Update policy (below); takes precedence over `auto_update`. |
| `identity_types` | `list[str]` | `[]` | Identity types this base image carries (see [Capabilities](#capabilities)). |
| `storage_types` | `list[str]` | `[]` | Storage types this base image carries. |
| `admin_user` | `str` | `csisadmin` | The mandatory local admin user. |
| `admin_public_keys` | `list[str] \| None` | `None` | Public keys for the admin user; `None` means `config.admin_public_keys`. |
| `local_test_image` | `str \| None` | `None` | Container image standing in for this OS in local mod tests. |
| `tests` | `dict[str, Any]` | `{}` | In-bake assertions (see [Other modules](#other-modules)). |

`OSBuilderBaseImageBuilderSubconfig` (one `runtimes:` entry):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `image_builder` | `str` (fk `IMAGE_BUILDER_MODEL`) | `default` | The image builder, and through it the runtime. |
| `name` | `str \| None` | `None` | Unique within the OS builder. |
| `type` | `str` (templated) | the OS builder name | Filled from the parent. |
| `description` | `str` | templated | Free text. |
| `image_id` / `image_name` | `str \| None` | `None` | A pinned vendor image instead of a query. |
| `auto_update` | `bool \| None` | `None` | `None` inherits the OS builder's. |
| `default_machine_type` | `str \| None` | `None` | Bake machine type on this runtime. |
| `default_primary_disk_size` | `int` | `100` | Bake disk size on this runtime. |
| `tags` | mapping | `{}` | Merged over the OS builder's tags. |
| `owners` | `list[str]` | `[]` | Added to the OS builder's and the runtime's default owners. |
| `query` | mapping | `{}` | Merged over the OS builder's query. |
| `ssh_username` | `str` | `default` | Falls back to the OS builder's `config_username`, then the runtime's `default_config_username`; an error when none is set. |
| `tests` | mapping or `None` | `None` | When set, replaces the OS builder's tests for bakes on this runtime. |

Aliases are refused on subconfig entries.

`UpdatePolicy` (`update:`, a mapping or a bare policy name):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `policy` | `str` | `none` | One of `none`, `security`, `packages`, `full`. |
| `packages` | list | `[]` | With `packages`: exactly these; otherwise also these. |
| `exclude` | list | `[]` | Never touched by any policy. |
| `pin` | mapping | `{}` | Package to version, installed and locked. |
| `refresh_days` | `int \| None` | `None` | Re-bake when the series head is at least this old. |

`policy: packages` needs `packages` or `pin`; a package cannot be both
updated and excluded. The base class realizes only `none` and `full`;
package-manager families implement the targeted policies. Every bake also
writes a package manifest to `/var/lib/csis/packages.txt`.

### Image, instance, storage, mod, group, user and state builders

| Model | YAML key | Adds |
| ------- | ---------- | ------ |
| `ImageBuilderModel` | `image_builders` | `runtime` (fk), `default_machine_type` (`default`). Plugins add their own fields (for example a list of required packer plugins). |
| `InstanceBuilderModel` | `instance_builders` | `runtime` (fk). Plugins add fields such as the state backend name. |
| `StorageBuilderModel` | `storage_builders` | `runtime` (fk). Plugins add fields such as `size`, `bucket_name` and `variables`. |
| `ModBuilderModel` | `mod_builders` | Nothing beyond `BuilderModel`. |
| `GroupBuilderModel` | `group_builders` | Nothing beyond `BuilderModel`. `BasicGroupBuilderModel` is an empty subclass. |
| `UserBuilderModel` | `user_builders` | `default_user_email_template` (`{{ user.name }}`), `default_user_description_template` (`User {{ user.name }} / {{ user.email }}`), `email_as_username` (`True`: a user's name must equal its email, case-insensitively; a blank name is set from the email). |
| `StateBuilderModel` | `state_backends` | Nothing beyond `BuilderModel`; the state plugin adds bucket, key, region and so on. |

`ModuleVariables` is the base of a storage builder's `variables:`: `tags`
(builder-wide default tags, merged under the item's) plus the fields a
provider subclass declares. `as_module_args()` returns only the declared
values, so a module's own default applies to the rest.

`ModItemModel` (one `modifications:` entry of an image): `type` (fk
`MOD_BUILDER_MODEL`, default `default`), `name`, `description`, `aliases`,
`tags`, `config`. Plugin item classes add `playbooks`, `script`, `scripts`,
`ensure` and similar.

### `Image` (`images/`, key `images`)

`RootItem` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `type` | `str` (fk `IMAGE_BUILDER_MODEL`) | `default` | The primary image builder. |
| `source_image` | `str \| None` | `None` | Required: the parent image or base image name. |
| `auto_update` | `bool \| None` | `None` | Update during the bake. |
| `parent_policy` | `str` | `pinned` | `pinned`: bake from the pinned parent build until an explicit upgrade. `follow`: a newer parent head re-bakes this image and moves the pin. |
| `retention` | `{keep: N} \| None` | `None` | Keep the newest N builds per runtime. `None` defers to the runtime's `retention_keep`. |
| `release` | `{model: name} \| None` | `None` | A build whose post-bake tests pass is released for the model by the same run. |
| `is_default` | `bool` | `False` | |
| `architecture` | `str` (templated) | the builder's, else `x86_64` | |
| `primary_disk_size` | `str \| int` (templated) | the builder's, else `200` | Bake disk, and every instance's boot disk. |
| `auto_generate_storage` | `bool` | `False` | |
| `variables` | `dict[str, Any]` | `{}` | |
| `modifications` | deferred list of mod items | `[]` | Each entry's `type` names a mod builder. |
| `group` | `str \| None` | `None` | The owning group. Every instance of the image shares it. Required by validation when an instance uses the image. |
| `tests` | `dict[str, Any]` | `{}` | In-bake assertions; `tests.post_bake` runs on a launched instance. |
| `default_groups` | `list[str]` | `[]` | |
| `runtimes` | `list[ImageImageBuilderSubconfig]` | required, at least one | One entry per image builder that bakes this image. |
| `description` | `str \| None` | `Image <name> from source image <source>` | |

`ImageImageBuilderSubconfig`: `image_builder` (fk, default → the default
image builder), `name` (defaults to the image builder), `type`
(templated), `ssh_username` (`default`), `image_identifier`, `machine_type`
(templated: the runtime's default machine type), `tags`, `owners`
(`[self]`). The image's `_runtime_map` is keyed by each entry's runtime.

### `BaseImage` (synthesized; key `base_images`)

A base image object is created by the OS builder during base-image
resolution. `RootItem` plus: `type` (fk `IMAGE_BUILDER_MODEL`), `os` (fk
`OS_BUILDER_MODEL`), `source_image`, `auto_update`, `is_default`,
`primary_disk_size` (templated, else `200`), `variables`, `tags`,
`runtimes` (`list[BaseImageImageBuilderSubconfig]`, at least one),
`description`, `identity_types`, `storage_types`, `admin_user`
(`csisadmin`), `admin_public_keys`, `tests`. Exactly one of `os` and
`source_image` must be set. `BaseImageImageBuilderSubconfig` carries
`runtime` (fk), `image_builder` (fk), `ssh_username`, `tests`,
`auto_update`, `image_identifier`, `machine_type` (templated), `tags`,
`owners`.

### `Instance` (`instances/`, key `instances`)

`RootItem` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `type` | `str` (fk `INSTANCE_BUILDER_MODEL`) | `default` | The instance builder (a terraform root). |
| `image` | `str` (fk `IMAGE_MODEL`) | `None` | Required to finalize. |
| `runtime` | `str` (fk `RUNTIME_BUILDER_MODEL`) | `default` | |
| `description` | `str \| None` | `Instance from {{ image.name }}` | |
| `storages` | deferred list of `StorageMapping` | `[]` | Per-instance attachments. A storage attached twice keeps the later mapping. |
| `userdata` | `str` | `""` | Lines appended to the generated startup script. |
| `image_policy` | `str` | `pinned` | `follow` plans a gated replacement whenever the image's series head moves. |
| `ephemeral` | `bool` | `False` | Launched, verified and torn down in the same run. |
| `on_failure` | `str \| None` | `None` | `keep` (left standing, run fails) or `teardown`; `None` inherits the runtime's. |
| `teardown_after` | `str \| None` | `None` | Duration after a failed verification past which the next run tears it down. |
| `machine_type` | `str` | `""` | Empty means the runtime's default. |

A `groups` key on an instance is refused: ownership lives on the image.

`StorageMapping`: `name` (the storage's name), `type` (fk
`STORAGE_BUILDER_MODEL`, default `default`), `mount_point`
(`/mnt/storage`), `min_size` (`100`, must be positive). Aliases are
ignored.

### `Group` (`groups/`, key `groups`)

`RootItem` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `type` | `str` (fk `GROUP_BUILDER_MODEL`) | `default` | |
| `is_default` | `bool` | `False` | The group every user joins by default. |
| `is_root` | `bool` | `False` | The single root group. Exactly one group must set it. |
| `members` | `set[EncryptedStr]` | empty | User names; each must be a defined user. Entries may be `ENC[age:...]`. |
| `admins` | `set[EncryptedStr]` | empty | |
| `gid` | `int \| str \| None` | `None` | `None`, `0` or `default` defer the gid to the provider; otherwise an integer of at least `1024`. |
| `include_root_group_in_admins` | `bool` | `True` | |
| `unmanaged` | `bool` | `False` | Kept in YAML but left unmanaged (state removed, resource left alive). |
| `attributes` | `dict \| None` | `None` | Provider attributes, validated by the plugin. |
| `in_both` | `bool \| None` | `None` | `True`: admins are also members. `False`: no overlap. |

### `User` (`groups/`, key `users`)

`RootItem` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `type` | `str` (fk `USER_BUILDER_MODEL`) | `default` | |
| `name` | `EncryptedStr` | required | The login. May be encrypted. |
| `first_name` / `last_name` | `EncryptedStr` | required, non-blank | Never derived from the name. |
| `middle_name` | `str \| None` | `None` | |
| `email` | `EncryptedStr` (templated) | the builder's `default_user_email_template` | |
| `description` | `str \| None` (templated) | the builder's description template | |
| `is_service_account` | `bool` | `False` | |
| `is_enabled` | `bool` | `True` | |
| `managed` | `bool \| None` | `None` | `None` means the builder's default (a resource, or a lookup only). |
| `attributes` | `dict \| None` | `None` | Provider attributes. |
| `public_keys` | `list[str]` | `[]` | |
| profile fields | `str \| None` | `None` | `mobile_phone`, `honorific_prefix`, `honorific_suffix`, `title`, `display_name`, `nick_name`, `profile_url`, `second_email`, `primary_phone`, `street_address`, `city`, `state`, `zip_code`, `country_code`, `postal_address`, `preferred_language`, `locale`, `timezone`, `user_type`, `employee_number`, `cost_center`, `organization`, `division`, `department`, `manager_id`, `manager`. |

Aliases are not allowed on users.

### `Storage` (`storages/`, key `storages`)

`NameTyped` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `runtime` | `str` (fk `RUNTIME_BUILDER_MODEL`) | `default` | |
| `type` | `str` (fk `STORAGE_BUILDER_MODEL`) | `default` | |
| `groups` | `list[str]` | `[]` | Groups allowed to use it. The magic value `ALL` is refused. |
| `public_read` | `bool` | `False` | Anyone may mount read-only. |
| `share_mode` | `str` | `2770` | Mode of each group's subtree: `2770` (private) or `2775` (read-shared). |
| `state` | `str` | `active` | Requested state: `active`, `archived` or `destroyed`. |
| `source` | `dict[str, str]` | `{}` | |
| `ephemeral` / `generative` / `singleton` / `is_default` | `bool` | `False` | |
| `mount_point` | `str \| None` | `None` | |
| `bucket_name` | `str \| None` | `None` | |
| `tags` / `config` | dict | `{}` | |
| `lifecycle` | `dict \| None` | `None` | A data lifecycle the builder realizes; a builder without one refuses the key. |

`allows_group(group)` is `public_read or group in groups`.

### `ProviderSpecificImage`

Not a YAML model. A runtime builder creates one per image and runtime,
either `resolved` (a concrete identifier such as an AMI id, from a vendor
query or a pin) or `deferred` (a name pattern a later bake fulfils). It
registers under `PROVIDER_SPECIFIC_IMAGE` with the key
`<source>::<runtime>`; `get_query_assets()` returns provider query inputs.

## `cfg/_config.yml` key by key

`IAConfig` is the top-level document after the plugin keys are removed.

| Key | Type | Default | Meaning |
| ----- | ------ | --------- | --------- |
| `id` | `str` | required | The configuration's identifier. |
| `last_updated` | datetime | now | Informational. |
| `working_directory` | `str` | `./workdir` | Superseded by `--root-dir`. |
| `generation_directory` | `str \| None` | `generated` | Where generated output lands, relative to the root. |
| `dateformat` | `str` | `%Y-%m-%d-%H%M%S` | Used by `last_updated_timestamp_str`. The string stage reads the raw key with fallback `%Y%m%d_%H%M%S` for `execution.timestamp`. |
| `executables` | list of `ExecutableModel` | `[]` | Tools builders run; names unique. |
| `runtime_builders`, `image_builders`, `instance_builders`, `os_builders`, `mod_builders`, `storage_builders`, `group_builders`, `user_builders`, `state_backends` | lists in YAML | `[]` | Builder declarations, each with `name` and `type`. Structured per `type` and stored by name. |
| `gitignore` | `list[str]` | `[]` | Appended to the built-in entries (`target/`, `.terraform/`, `terraform.tfstate`, `terraform.tfstate.backup`, `!.terraform.lock.hcl`); the last occurrence of a duplicate keeps its place. |
| `sleep_before_finalization` | `int` | `1` | Accepted and ignored; finalization never waits on a terminal. |
| `encryption` | `{recipients: [age1...]}` | `[]` | age public keys every encrypted value is encrypted to. |
| `public_safe` | `{allow: [...]}` | `[]` | Substrings and `path:<glob>` entries the scanner accepts. |
| `config` | mapping | `{}` | Free key-value settings, available as `config.<key>` in templates and read by name in code. |

Keys under `config:` that the base package reads:

| Key | Type | Effect |
| ----- | ------ | -------- |
| `use_state_backends` | `bool` | Emit terraform backend and remote-state blocks. |
| `apply_identity`, `apply_storage`, `apply_instances`, `apply_release` | `bool` or list of names | Whether the lifecycle's roots apply. `true` enables every root; a list enables the roots whose builder name or runtime is listed; unset means plan and gate only. |
| `module_source_base` | `str` | Base of terraform module sources; a relative path is relative to the configuration root and rewritten per workspace. Default `../tfmodules`. |
| `admin_public_keys` | list of OpenSSH public key lines | Keys for the admin user on every base image without its own override. Private key material is refused. |
| `require_mod_tests` | `bool` | A release refuses a build whose modification has no local mod test result. |
| `require_image_tests` | `bool` (default `true`) | A release of an image with `tests.post_bake` requires a passing post-bake record. |
| `require_released_builds` | `bool` | An instance may pin only to a released build. |
| `preflight.expected_run_minutes` | `int` (default `30`) | A session expiring within this window blocks a strict preflight. |

## Lifecycles and phases

Source: [`lifecycles.py`](src/cs_image_system/base/lifecycles.py),
[`lifecycle.py`](src/cs_image_system/base/lifecycle.py).

The four built-in lifecycles run in this fixed order. Each owns generation
phases and the builder classifications whose during-phase hooks fire:

| Lifecycle | Phases | Builders | Aliases accepted by `parse_lifecycles` |
| ----------- | -------- | ---------- | ----------- |
| `identity` | `user-generation`, `group-generation` | user, group | `identity`, `id` |
| `storage` | `storage-generation` | storage | `storage`, `storages` |
| `base-image` | `image-generation` | image | `base-image`, `base-images`, `base` |
| `instance-image` | `image-generation`, `instance-generation` | image, instance | `instance-image`, `instance-images`, `instances` |

`all` selects every lifecycle. Names resolve in declared order, never in
argument order.

Two more lifecycles are registered by the base package itself: `release`
(after `instance-image`) and `retention` (after `release`). Both have no
phases; they contribute deferred commands through after-generate hooks. A
plugin registers further lifecycles with `LifecycleSpec(name, phases,
builder_vcts, after, description)`; a name may not be `all`, a built-in
name, or contain `/`.

Each lifecycle owns `generated/<lifecycle>/` and the runner script
`generated/<lifecycle>/run-<lifecycle>.sh`.

`ExecutionLifecyclePhase` is the enum builder hooks key on, in execution
order: `validation`, `post-validation`, `pre-resolution`, `resolve`,
`post-resolution`, then `pre-`/`-`/`post-` triples for `user-generation`,
`group-generation`, `storage-generation`, `image-generation`,
`instance-generation`, then `pre-test`, `test`, `post-test`, `pre-commit`,
`commit`, `post-commit`, `pre-execution`, `execution`, `post-execution`,
`pre-verify`, `finalization`, `verify`, `post-verify`, `pre-cleanup`,
`cleanup`, `post-cleanup`. The built-in lifecycles claim the five
generation phases; the runner drives resolution before each lifecycle and
orders deferred commands by this enum. Deferred commands may not be added
to a phase after `pre-verify`.

## A run: generation, finalization, dry run, commit

Source: [`commands/run_lifecycles.py`](src/cs_image_system/base/commands/run_lifecycles.py),
[`commands/`](src/cs_image_system/base/commands/).

`run_lifecycles(requested, apply=True, commit=False, state_query=True,
only=None, force_bake=None)` performs, in order:

1. Load hook plugins. Reset the "generated this run" set and the bake
   decision cache. Validate `--only` names (an image name, or
   `<image>@<runtime>`; `none` means an empty bake surface).
2. **State query** (unless disabled): ask every plugin for reality, write
   `generated/state-report.json`, log the credential session lines.
3. **Validation**: unique names, executables present and version-compliant
   (`commands/validate.py`), policy checks from `lineage.py`, and every
   registered validator. Any error aborts before anything is generated.
4. **Bake plan** when a bake lifecycle is requested: one decision per
   `<series>@<runtime>` (`bake: <reason>` or `skip: ...`), then the scope
   check (a real run refuses to bake outside its apply scope unless
   allowed).
5. **Generation**, per requested lifecycle in declared order: wipe that
   lifecycle's directory, write its `.gitignore`, resolve (template
   resolution; for `base-image` the vendor image query and base image
   synthesis; for `instance-image` the deferred or pinned
   provider-specific images), run each phase (before hooks, the during
   generator, after hooks), run after-generate hooks, then write the runner
   script if any deferred command was recorded. A lifecycle with no
   deferred work leaves no script.
6. Write `generated/final_execution.sh`, which runs each lifecycle's
   runner script if and only if it exists.
7. **Apply** (unless `--no-apply`): for every lifecycle whose script exists
   and which was generated in this run, run before-apply hooks, then the
   deferred commands phase by phase in-process with every builder's
   `pre_finalize_phase` / `post_finalize_phase` around each phase, then
   after-apply hooks. A script left by an earlier run of a lifecycle not
   requested now is skipped and reported as `stale-script-skipped`.
8. **Commit** (only with `commit=True`): record the run, then
   `commit_meta_state` (see [Meta-state](#meta-state)).
9. Write `generated/run-summary.json` and the run journal; call on-summary
   hooks. A failure sets `ok: false` and `error` in the summary.

`RunSummary` fields: `run_id`, `requested`, `dry_run`, `ok`,
`validation_errors`, `lifecycles` (each with `status`, `runner_script`,
`deferred_commands`, `error`), `apply` (per lifecycle: `executed`,
`dry-run`, `no-script`, `stale-script-skipped`, `failed`,
`not-attempted`), `meta_state_commit`, `error`, `state` (drift counts),
`overlays`, `undeclared`, `bake_plan`.

**Generation versus finalization.** Generation writes files and runs
`build_executables` immediately. Finalization is the deferred
`finalize_executables`: packer builds, terraform init/plan/gate/apply, and
system CLI steps. They are recorded per lifecycle and phase, rendered into
the runner script as reviewable shell lines (working directories relative
to the lifecycle directory; the configuration root as `"$CSIS_ROOT"`), and
executed in-process by the apply step.

**Dry run versus real run.** `dry_run` is a flag on the run context,
`True` unless the caller passes `--no-dry-run`. In a dry run generation is
complete and the runner scripts are written, but the apply step only logs
each deferred command as `[DRY RUN] ... would execute`; no pre/post
finalize hook and no after-apply hook runs. Deferred system CLI steps that
need the configuration are recorded with `--root-dir <root> --no-dry-run`
and the run's overlays, so they execute only inside a real run. The
retention lifecycle's transient-storage teardown step is built the same
way.

**`--commit`.** `commit_meta_state` stages `meta-state/` and the generated
tree, skips any path git ignores, never stages the refused names (plans,
state, tfvars, `.envrc`, key material), scans every file about to be
staged with the public-safe rules and the tree's allowances, refuses the
whole commit on a finding, and commits only those paths with a message
naming the run id and lifecycles. It returns the commit sha, or `None` when
nothing changed or the root is not in a git repository.

## The run context

Source: [`global_context.py`](src/cs_image_system/base/global_context.py).

`GlobalTypeContext` is a singleton constructed once by
`read_config_and_transform` and returned by every later
`GlobalTypeContext()` call. Builders reach it through `self._get_context()`.
What it exposes:

| Member | Meaning |
| -------- | --------- |
| `dry_run`, `verbose`, `force`, `only_providers` | The invocation's flags. |
| `root_dir`, `working_path` | The configuration root. |
| `generation_path` | Where generated files land now: `generated/<lifecycle>/` while a lifecycle is current, else `generated/`. |
| `root_generation_path`, `lifecycle_generation_path(lc)`, `runner_script_path(lc)`, `gating_script_path`, `final_execution_path` | Generated-tree paths. |
| `current_lifecycle`, `generated_lifecycles`, `mark_generated(lc)` | Lifecycle bookkeeping. |
| `run_id`, `start_time`, `iso_start_time` | The run start timestamp; `run_id` is the ISO time with every separator replaced by `_`. |
| `read_config`, `config`, `executables`, `gitignore` | The structured `IAConfig`, its `config:` map, executables by name, the merged gitignore entries. |
| `runtime_builders`, `image_builders`, `instance_builders`, `mod_builders`, `storage_builders`, `os_builders`, `group_builders`, `user_builders`, `state_backends` | Builders by name, read from the registry. |
| `all_sorted_builders` | Every builder in hook order. |
| `default_runtime_builder`, `default_image_builder`, ... | The default builder name per classification (an error when unset). |
| `instances`, `images`, `images_map`, `base_images`, `groups`, `users`, `storages`, `root_group` | The items, read from the registry. |
| `provider_specific_images`, `get_provider_specific_image(source, runtime)` | Provider-specific images by `<source>::<runtime>`. |
| `meta_state`, `meta_state_path` | The `MetaState` at `<root>/meta-state`. |
| `overlays`, `overlay_declared`, `undeclared` | Overlay files, the transient entries they declared, and undeclared entries. |
| `only_images`, `force_bake`, `bake_decisions`, `apply_runtime`, `implied_scope`, `allow_unscoped_bakes`, `explicit_bake_selection`, `only_runtime_scope` | Run scoping. |
| `extend_finalization_phase(phase, executables)`, `get_finalization_executables_for_phase(phase, lifecycle)`, `finalization_phases_for(lifecycle)` | The deferred-command buckets. |
| `write_lifecycle_runner_script(lc, header)`, `write_gating_script()`, `render_executable_line(exe)` | Script rendering. |

## Meta-state

Source: [`meta_state.py`](src/cs_image_system/base/meta_state.py).

Meta-state is the set of committed, human-readable YAML files under
`<root>/meta-state/` that carry memory between runs. It sits outside every
generated directory, so a lifecycle wipe never touches it. Reads are lazy
and cached; writes are atomic per file and refused when a hard public-safe
rule matches the content.

| File | Written by | Records |
| ------ | ----------- | --------- |
| `identity.yaml` | after the identity lifecycle generates | `run`; `groups` (per group: `builder`, `identity_type`, `gid_policy`, `managed`, `is_root`, `members`, `admins`); `users`; `user_builders`. Structural facts only; gids travel by terraform reference. |
| `storage.yaml` | after the storage lifecycle generates, and after a real storage apply | `run`; `storages` (per storage: `builder`, `requested_state`, `current_state`, `generation`, `allowed_groups`, `public_read`, `share_mode`, `lifecycle`, `attachments`, `type`, `plugin`, `attachment_cardinality`, `posix`). |
| `storage-state.yaml` | after a real storage apply | The authoritative state machine: per storage `state`, `generation`, `facts`, and `history` entries (`from`, `to`, `run`, `generation`, `action`). A destroyed-to-active transition increments the generation. |
| `lineage.yaml` | after a bake is recorded | `builds`: per build `build_id`, `series`, `runtime`, `name`, `parent`, `input_fingerprint`, `run`, `capabilities`, `mods` (name, type, operation, idempotent, content hash, run), `local_mods`, `tests` (`in_bake`, `assertions`), `update`, `chain`. Disposal removes a record. |
| `pins.yaml` | on first bind, upgrade, follow, dispose, decommission | `instances` (instance to build), `images` (`<image>@<runtime>` to parent build), `upgrades` (every move: `kind`, `name`, `from`, `to`, `run`, `op`), `pending_replacements`. |
| `launch-params.yaml` | after the instance-image lifecycle generates and after applies | Per instance the recorded launch parameters ([Launch parameters](#launch-parameters)) plus `user_data_sha256`, `run`, `launched`, `launched_run`. |
| `runs.yaml` | every run | The journal: `run`, `requested`, `dry_run`, `ok`, `apply`, `error`; bounded to the last 200. |
| `verifications.yaml` | `verify instance` | Verification verdicts; bounded to the last 500. |
| `image-tests.yaml` | `verify instance` for images with `tests.post_bake` | Per build: `ok`, `run`, `instance`, `runtime`, `time`, `checks`. |
| `releases.yaml` | `release` | `releases` (every release: `image`, `build_id`, `model`, `run`, `note`, `name`, `capabilities`) and `current` (per model, image to build). |
| `mod-tests.yaml` | `test-mods` | Local modification test results keyed by content hash. |

`MetaState` also exposes `series_head(series, runtime)`, `image_pin`,
`instance_pin`, `bind_image`, `bind_instance`, `move_pin`,
`unpin_images_at`, `remove_instance_pin`, `record_storage_transition`,
`record_run`, `record_verification` and `record_image_test`.

Files under `generated/` are not meta-state: `run-summary.json`,
`state-report.json`, `identity/attributes-plan.json`,
`release/releases.yaml` (a read-model of the current releases) and the
runner scripts.

## Encryption

Source: [`encryption.py`](src/cs_image_system/base/encryption.py).

Any value in the configuration may be the marker

```text
ENC[age:<base64 of an age-encryption.org/v1 file>]
```

encrypted to every public key under `encryption.recipients` in
`cfg/_config.yml`. A field declared `EncryptedStr` decrypts such a value at
load; an unmarked value passes through. `EncryptedStr` composes:
`list[EncryptedStr]` and `set[EncryptedStr]` decrypt element by element,
so a roster diff shows which entry changed. The fields that use it are
`User.name`, `User.first_name`, `User.last_name`, `User.email`,
`Group.members` and `Group.admins`.

A decrypted value is a `Decrypted`, a `str` whose `repr` is
`Decrypted('***')` and which remembers the `marker` it came from, so an
emission can refer to the ciphertext instead of the text.

The identity that decrypts comes from the environment variable
`CSIS_CONFIG_IDENTITY`, in one of three forms:

| Value | Meaning |
| ------- | --------- |
| an `AGE-SECRET-KEY-1...` string | The key itself. |
| a file path | An identity file in the `age-keygen` layout (the first `AGE-SECRET-KEY-1` line is used). |
| a directory path | Every `*.age-identity` file in it; each is tried until one opens the value. |

A marked value with no identity set is a load-time `MissingIdentityError`
naming the variable, never a silent plaintext. A value none of the
identities can open is a `ValueError`.

Helpers: `encrypt_value(plaintext, recipients)` produces a marker;
`recipients_from_config(root)` reads `cfg/_config.yml` as text (no identity
needed); `encrypt_fields_in_text(text, field_names, recipients)` encrypts,
in place and byte-preserving, every scalar under a named key and every
element of a block list under such a key, skipping values that are already
markers, contain `{{`, are empty, or start a nested block;
`rotate_text(text, identities, recipients)` re-encrypts every marker in a
text to the current recipients and fails on the first marker it cannot
open.

## The public-safe gate

Source: [`public_safe.py`](src/cs_image_system/base/public_safe.py).

One scanner sits behind the meta-state commit, every meta-state and
state-report write, the `public-safe` command and a pre-commit hook. It
reads bytes; a zip (a saved `tfplan`) or a gzip member is opened and its
members scanned.

**Refused by name at any depth** (`REFUSED_PATHS`): `tfplan`, `*.tfplan`,
`*.tfstate`, `*.tfstate.*`, `*.tfvars`, `*.tfvars.json`, `.envrc`, `*.pem`,
`.private_key.*`, `.public_key.json`.

**Hard rules** (apply everywhere):

| Rule | Shape |
| ------ | ------- |
| `jwt` | `eyJ` followed by 20 or more token characters |
| `pem-private-key` | `-----BEGIN ... PRIVATE KEY-----` |
| `aws-access-key` | `AKIA` or `ASIA` plus 16 upper-case alphanumerics |
| `gcp-service-account` | a `private_key_id` with a value, or `"type": "service_account"` in a document that also carries `private_key` |
| `slack-token` | `xox[baprs]-...` |
| `github-token` | `gh[pousr]_...` |
| `age-identity` | `AGE-SECRET-KEY-1` plus 58 characters |
| `tfvar-assignment` | `TF_VAR_<name>=<literal>` (an assignment from `$VAR` passes) |

**Soft rules** (skipped for `*.md`, `docs/*`, `tests/*.py`, `*/tests/*.py`,
`test_*.py`, `conftest.py`):

| Rule | Shape |
| ------ | ------- |
| `email` | an address whose domain is not `example.com`, `example.org`, `example.net`, `.invalid`, `.test` or `localhost` |
| `high-entropy` | forty or more base64 characters mixing lower case, upper case and digits |

**Blanked before any rule runs** (structural public material):
`ENC[age:...]` ciphertext, scp-style git URLs, age public keys
(`age1...`), `.terraform.lock.hcl` hashes (`h1:`/`zh:`), and SSH public
keys.

**Allowances** come from `public_safe.allow` in `cfg/_config.yml`, read as
text so a tree that cannot load is still gated. A plain entry is a
case-insensitive substring that a matched span may contain (a domain whose
addresses are public by construction, a service account's address). A
`path:<glob>` entry accepts a whole file by path or basename.

Entry points: `scan_tree(root, allow)` over tracked and untracked
non-ignored files (or every file outside a git checkout);
`scan_staged(top, allow)` over the index blobs; `scan_file`; `scan_bytes`;
`assert_public_safe(data, where)` applies the hard rules to a mapping about
to become YAML. A `Finding` carries the path, the rule and a six-character
excerpt, never the value. `PublicSafeError` lists the first twelve findings
and points at `public_safe.allow`.

## Lineage

Source: [`lineage.py`](src/cs_image_system/base/lineage.py).

Every bake writes a new image, so every build gets a unique id and carries
lineage as tags: `csis_series` (the logical image name), `csis_parent`
(the build it was baked from, `series:<name>` when bound after the bake, or
`vendor`), `csis_run`, `csis_fingerprint` (the first 16 characters of the
input fingerprint), `csis_identity_types` and `csis_storage_types`. After
a bake `record_build` appends the lineage record and performs the first
bind of the parent edge. The input fingerprint hashes what determines the
build's content: series, effective parent, capability stamp, every
modification's content hash, the in-bake verification commands, the bake
disk size, and for base images the declared vendor source, admin user and
keys, and update policy. Machine type, usernames, run ids and timestamps
are excluded. `bake_reason(ctx, image, runtime)` decides whether an image
bakes in this run: forced by `--force-bake`, no build yet on that runtime,
the parent moved under `parent_policy: follow`, the parent re-bakes this
run under `follow`, the fingerprint differs from the series head's, or
`update.refresh_days` is due; otherwise it is current and skipped.
Consumers bind once: an instance to the head of its image's series and an
image to the head of its parent's series on its runtime (the pin key is
`<image>@<runtime>`), and stay pinned. Only `upgrade`, a `follow` policy,
disposal or decommission moves a pin, one edge at a time; every move is
journaled in `pins.yaml`.

## Releases

Source: [`release.py`](src/cs_image_system/base/release.py).

A release is a recorded mark on a build for a named model (default
`default`), kept in `meta-state/releases.yaml`. `release(ctx, image,
build_id, model, note)` requires that the build exists in lineage under
that series, that its record carries an in-bake verification, that no
modification it carries has a failed or non-idempotent local mod test (a
missing result is tolerated unless `config.require_mod_tests` is true),
and, when the image declares `tests.post_bake` and
`config.require_image_tests` is not false, that a passing post-bake record
exists. The `release` lifecycle, registered after `instance-image`, writes
`generated/release/releases.yaml` and, for every image declaring
`release: {model: <m>}`, defers a `release --declared` step that at
execution releases each runtime's series head whose post-bake tests
passed. With `config.apply_release` true it also defers each runtime's
`release_commands` (for example tagging the cloud image). The validator
`validate_released_pins` enforces `config.require_released_builds`.

## Retention

Source: [`retention.py`](src/cs_image_system/base/retention.py).

The `retention` lifecycle is registered after `release`, so it runs last.
When any image declares `retention`, any runtime declares
`retention_keep`, or any runtime is `ephemeral`, it defers one step,
`dispose image --retention`, which recomputes at execution (after this
run's bakes and verifications are recorded) and disposes of every build the
declared retention no longer keeps: beyond `retention.keep` per image or
`retention_keep` per runtime, or everything on an ephemeral runtime. A build
an instance is pinned to or was launched from is never disposed; it is
reported as retention debt. Declared storages are never touched. A storage
declared by an overlay on an ephemeral runtime is transient: the lifecycle
adds a second step, a `run storage --only none --no-state-query --no-commit`
without the overlays that declare items (config-only overlays and
`--apply-runtime` carry over), so the transient storage is undeclared there
and destroyed through the gate.

## Launch parameters

Source: [`launch_params.py`](src/cs_image_system/base/launch_params.py).

An image carries all tooling; launch parameters carry only the bindings
specific to one instance, computed from validated configuration and
recorded in `meta-state/launch-params.yaml`. `compute_launch_params`
returns `image`, `build` (the pin, or `unbound`), `group` (the image's
owning group), `identity_type`, `mounts` (per attached storage: `storage`,
`type`, `builder`, `mount_point`, `group`, `share_mode`, `public_read`, and
a `device` for block storage: `/dev/xvdf` onwards in declaration order on
EBS, `/dev/disk/by-id/google-<name>` on GCE), `enrollment` (from the group
builder), `session` (the runtime's mechanism), `hostname` (the instance
name), `ephemeral`, and `userdata` when declared. `user_data_template`
renders these as a bash script for terraform's `templatefile`: hostname,
group gid by reference (`${group_gid}`), block-device wait, format and
fstab lines, EFS (`${efs[...]}`) and Filestore (`${filestore[...]}`) mounts,
the group's private subtree with its share mode, the enrollment trigger
(`${sft_enrollment_token}`, never recorded), the instance's own `userdata`
lines, and finally the marker `/var/lib/csis/launch-applied`. Runtime
values enter only by terraform reference. After a real apply, hooks mark
every declared instance launched, forget decommissioned and ephemeral
instances, and re-record detachments. Launched instances are immutable: a
changed parameter set fails validation unless the instance has a pending
replacement (an explicit upgrade or a `follow` target); the one in-place
change allowed is removing a mount, which is a detach.

## Capabilities

Source: [`capabilities.py`](src/cs_image_system/base/capabilities.py).

A base image declares `identity_types` and `storage_types`; for each
declared type the owning plugin bakes its prerequisites, installed but
dormant, and anything undeclared is unusable downstream. An instance image
names only its owning `group`; the group's builder fixes the identity type
(`GroupBuilderBase.identity_type()`), and each attached storage resolves to
its builder's `capability_type()`. `effective_capabilities(ctx, image,
runtime)` follows `source_image` links to the root base image, walks the
pins from the image toward the root, and returns the first recorded build's
stamped capabilities (`source: pin:<build>`); without a recorded build the
current declaration governs (`source: declaration`). The validators refuse
an image whose group's identity type or whose attached storage types the
root base does not carry. `validate_public_key` accepts one OpenSSH public
key line (`ssh-ed25519`, `ssh-rsa`, `ssh-dss`, `ecdsa-sha2-nistp*`, `sk-*`)
and rejects anything containing `PRIVATE KEY`, a PEM header, or several
lines. `admin_public_keys` returns a base image's own list when set, else
`config.admin_public_keys`; `admin_user` returns the OS builder's
`admin_user`, default `csisadmin`.

## Other modules

| Module | Purpose |
| -------- | --------- |
| [`state_query.py`](src/cs_image_system/base/state_query.py) | Asks every plugin for reality (images by lineage tags, storages by name, groups by gid), diffs it against meta-state, and classifies drift as `missing`, `foreign`, `changed` or `stale`. Hard drift (a pinned build gone, a storage recorded live but absent, a managed group unknown to the provider, an instance pinned to an unrecorded build) makes the next run's validation refuse. `import_foreign` adopts foreign artifacts into meta-state; nothing here writes to a cloud or to terraform state. The report is `generated/state-report.json`. |
| [`storage_state.py`](src/cs_image_system/base/storage_state.py) | The storage state machine: legal transitions (`active` to `archived` and back, either to `destroyed`, and regeneration of a destroyed name), the rule that a storage must be unattached to leave `active`, transitions for undeclared storages, and the recording of applied transitions. |
| [`v2_validation.py`](src/cs_image_system/base/v2_validation.py) | Generation-time rules, all hard: managed groups may not disappear; allowed groups exist; the strict attach rule; single-attach cardinality; data lifecycles only where the builder realizes them; storage transitions are legal; an instance image's group exists and every instance image has one; declared types resolve to configured plugins; admin keys are public keys; every base image has a debug path (keys or a session mechanism); capability resolution on both axes; test specs use the known vocabulary; update policies are valid. |
| [`image_tests.py`](src/cs_image_system/base/image_tests.py) | In-bake assertions emitted as the last packer provisioner: capability verification derived from plugin hooks, plus a declared `tests:` map with keys `files`, `packages`, `commands`, `services_enabled`, `users`. `tests.post_bake` adds `mounts` and runs on a launched instance. |
| [`mod_tests.py`](src/cs_image_system/base/mod_tests.py) | Runs every modification of an instance image against a throwaway local container twice (apply, then idempotence), recording results in `meta-state/mod-tests.yaml` by content hash. |
| [`identity_attributes.py`](src/cs_image_system/base/identity_attributes.py) | Declared provider attributes on users and groups: validation per plugin, a plan written to `generated/identity/attributes-plan.json`, a read-only probe, and an apply that is deliberately disabled. |
| [`read_models.py`](src/cs_image_system/base/read_models.py) | Writes the identity and storage read-models and records applied storage transitions. |
| [`commands/preflight.py`](src/cs_image_system/base/commands/preflight.py) | Reads credential caches (AWS SSO token expiry per profile, GCP application default credentials) without loading the configuration and without reading a credential value. |
| [`commands/gate.py`](src/cs_image_system/base/commands/gate.py) | The apply gate over a `tofu show -json` plan: every planned destroy must match a whitelisted address or prefix; a plan file older than the newest `.tf` in its root is stale. |
| [`commands/upgrade.py`](src/cs_image_system/base/commands/upgrade.py), [`commands/dispose.py`](src/cs_image_system/base/commands/dispose.py), [`commands/restamp.py`](src/cs_image_system/base/commands/restamp.py), [`commands/relabel.py`](src/cs_image_system/base/commands/relabel.py), [`commands/verify_instance.py`](src/cs_image_system/base/commands/verify_instance.py), [`commands/unmount.py`](src/cs_image_system/base/commands/unmount.py), [`commands/runtime_facts.py`](src/cs_image_system/base/commands/runtime_facts.py), [`commands/identity_gids.py`](src/cs_image_system/base/commands/identity_gids.py), [`commands/run_scope.py`](src/cs_image_system/base/commands/run_scope.py) | The operations behind the CLI's `upgrade`, `dispose image`, `lineage restamp`, `lineage relabel`, `verify instance`, `unmount storage`, `runtime describe` / `empty`, `identity export-gids`, and the bake scope check. |
| [`utils.py`](src/cs_image_system/base/utils.py) | `safe_name`, `super_safe_name`, `system_cli_executable` (a deferred call of the system's own CLI), `apply_enabled` / `apply_flag_allows` (the `apply_<lifecycle>` rule), `module_source`, `hcl_expr` and `render_module_call` (terraform module call rendering). |
| [`ansible_launch.py`](src/cs_image_system/base/ansible_launch.py) | Renders the same launch parameters as an ansible inventory and playbook. |

## Tests

The package's tests live in [`tests/`](tests/) and cover the registry and
plugin registration, field helpers and kinds, resolution stages, template
utilities, item kinds, the display name and email-as-username rules, group
gids, provider-specific images and the finalization executor. They run
with the workspace suite; in the workspace, `just test` is the acceptance
bar.
