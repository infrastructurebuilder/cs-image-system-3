# cs-image-system-base

The core library of cs-image-system. It defines the configuration models,
the plugin contract, the registry, the lifecycle runner, the cross-run
meta-state, value encryption, the public-safe gate, and the lineage,
release, retention, launch-parameter and capability rules that every plugin
and the command-line host build on.

It contains no cloud code. Clouds, identity providers, packer and terraform
live in plugins that register through the contract described here. The
package is licensed under Apache-2.0 and requires Python 3.13 or later.

Declared dependencies ([`pyproject.toml`](pyproject.toml)): `Jinja2`,
`PyYAML`, `age`, `packaging`, `pydantic` and `typer`. The models are
pydantic dataclasses; `packaging` parses version specifiers; `age` is the
library behind every `ENC[age:...]` value.

The package registers itself as a plugin too: the entry point
`cs_image_system.plugins.base` (`cs_image_system.base.init:initialize`)
injects the `StorageMapping` item model as the default
`STORAGE_MAPPING_ITEM_MODEL` and registers `GenericVersionChecker`, the
version checker every executable of the default type `executable` falls
back to.

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
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)

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
| `RuntimeBuilderBase`  | `RUNTIME_BUILDER`  | `query_provider_image`, `query_images`, `verify_instance`, `run_session_command`, `inventory`, `dispose_image`, `retag_image`, `packer_source_type`, `packer_source_blocks`, `build_id_from_artifact`, `session_mechanism`, `session_agent_commands`, `session_verify_commands`, `bake_finalize_commands`, `bake_ssh_username`, `release_commands`, `session_instance_profile`, `provider_specific_image_class`, `create_provider_specific_image_resolved` / `_deferred`; and the gated reality hooks, each behind a `can_*` predicate so an unsupported cloud makes no claim: `can_query_instance_boot_image` / `query_instance_boot_image`, `can_query_instance_power_state` / `query_instance_power_state` (the vocabulary of [`power_state.py`](src/cs_image_system/base/power_state.py); `None` means "cannot answer", never "stopped"), `can_set_instance_power_state` / `start_instance` / `stop_instance`, `can_query_instance_identity` / `query_instance_identity` (`instance_id`, `provider_hostname`). |
| `CloudBuilderBase` / `ContainerBuilderBase` | runtime | Thin subclasses of `RuntimeBuilderBase`. |
| `GroupBuilderBase`    | `GROUP_BUILDER`    | `identity_type()`, `gid_policy()` (`config-time`, `creation-only`, `provider-assigned`), `manages_groups()` (stage 63: `False` for a lookup-only builder, whose groups the read-model records `managed: false` and which comes after a managing builder of its type), `managed_groups()`, `enrollment_token_reference()`, `base_image_prerequisites()`, `verify_commands()`, `activation_commands()`, `activation_verify_commands()`, `launch_parameters()`, `query_state()`, `validate_attributes()`, `query_attributes()`, `attribute_conflicts()`, `export_gids()`; the server registry (stage 55): `can_query_servers()`, `registered_servers(group)` (`None` when the provider could not be asked, never an empty list), `retire_servers_named(group, hostname)`; `prune_stale_attachments(tofu, run_id, cwd)` (stage 61, a runner step, default no-op); and the CI login policy (stage 56): `can_manage_workload_access()`, `workload_access_expected(group)`, `workload_access_state(group)`, `ensure_workload_access(group)`. |
| `UserBuilderBase`     | `USER_BUILDER`     | `add_user_to_builder()` enforces `email_as_username`; `default_managed()`, `is_managed()`, `validate_user()`, `validate_attributes()`, `query_attributes()`. |
| `StorageBuilderBase`  | `STORAGE_BUILDER`  | `capability_type()`, `attachment_cardinality()` (`single` or `many`), `is_zonal()` (default `False`: a regional storage constrains no availability zone), `is_posix()`, `base_image_prerequisites()`, `verify_commands()`, `transition_actions()`, `validate_lifecycle()`, `query_state()`, `destroy_whitelist()`. |
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
`availability_zone` (`None`; declared, never inferred, and what the
zone-compatibility check reads for the runtime when no availability zone
is marked default), `config` (`{}`). `RuntimeAvailabilityZoneModel`:
`name`, `is_default`; `RuntimeNetworkingModel.default_availability_zone`
is the name of the entry marked default, else `None`.

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
| `UserBuilderModel` | `user_builders` | `default_user_email_template` (`{{ user.name }}`), `default_user_description_template` (`User {{ user.name }} / {{ user.email }}`), `email_domain` (`None`; the domain half of a derived address, substituted for the placeholder `{{ builder.email_domain }}` in the email template by `get_user_email_template()` before rendering, so it can be declared encrypted on its own), `email_as_username` (`True`: a user's name must equal its email, case-insensitively; a blank name is set from the email). |
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
| `availability_zone` | `str \| None` | `None` | The zone the instance is bound to. Declared, never inferred; validation refuses a set of zones that is not compatible across the instance, the zonal storages it mounts and its runtime's subnet. |

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
| `email` | `EncryptedStr` (templated) | the builder's `get_user_email_template()` (`default_user_email_template` with `email_domain` folded in) | A value derived from an encrypted input inherits its ciphertext in the emission. |
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
| `availability_zone` | `str \| None` | `None` | The zone a ZONAL storage lives in (meaningful only when its builder's `is_zonal()` is true). Declared, never inferred. |
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
   `<image>@<runtime>`; `none` means an empty bake surface). Write the
   root `generated/.gitignore` (the merged policy plus the run-local
   file names). A `--migrate-state` under a dry run is refused here,
   before anything else.
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
6. Record every generated terraform root's resolved state location in
   `meta-state/state-locations.yaml` (a root migrating this run keeps its
   old record until the migration's `finish` step), then write
   `generated/final_execution.sh`, which runs each lifecycle's runner
   script if and only if it exists.
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
| `state-locations.yaml` | every run that generates a terraform root; `state-migration finish` | `workspaces` (per root: the backend's `backend`, `type`, `location` and the settings its `.tfbackend.hcl` carried, plus `run`) and `migrations` (every performed move: `workspace`, `from`, `to`, `run`, `at`, `serial`, `backup`). The record, not the emission, is what the move guard compares against. |
| `instance-state.yaml` | `mark_launched`, the after-apply observation, the forgets | Per instance name: `generation` counters (`durable`, `ephemeral`), `current` (the open generation: `number`, `kind`, `how` (`observed`, `inferred`, `adopted`), `opened_run`, `opened_at`, `instance_id`, `provider_hostname`, a `launch_params` snapshot) and `history` (every closed generation with `closed_run`, `closed_at`, `why`). Nothing is ever deleted from it. |
| `login-proofs.yaml` | `verify login` | Every CI login verdict (`instance`, `runtime`, `hostname`, `group`, `run`, `as`, `time`, `ok`, `skipped`, `checks`, `evidence`); bounded to the last 500. |
| `aliases.txt` | the operator (appends), the run that launches a new durable machine (comments a line out) | Not a record file but a pool: one free name per line; a spent line is `# <name>  -- instance <i> as <hostname> <time> run <run>`. Absent means no aliases and no error. |

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
`validate_released_pins` enforces `config.require_released_builds`, with
one grace since stage 61: an unreleased pin is admitted while it is the
head of the image's series on its runtime, its record carries an in-bake
verification, no post-bake record for it FAILED, and the instance is
either a pending replacement onto it or stands on it (its open generation
booted with that build); the refusal otherwise names what is missing
(`release_grace`).

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
builder), `session` (the runtime's mechanism), `hostname` (the canonical
hostname: for a launched machine this run does not replace, the hostname
it was recorded with; for a new machine, `<declared name>-NNN` where NNN
is its kind's next generation, zero-padded to three digits), `alias` (only
when a name was drawn from `meta-state/aliases.txt` for a new durable
machine by a run that can launch it, or was recorded earlier), `ephemeral`,
and `userdata` when declared. `user_data_template`
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
| [`power_state.py`](src/cs_image_system/base/power_state.py) | The system's power-state vocabulary (`running`, `stopped`, `suspended`, `starting`, `stopping`, `absent`, `unknown`; `None` is "cannot answer"), `wait_until_reachable`, and `running_for_task`, the one bounded exception under which a stopped machine is started for work that needs it and stopped again afterwards. |
| [`generations.py`](src/cs_image_system/base/generations.py) | Instance generations (stage 60): one per machine, opened `inferred` by a launch and confirmed `observed` (or closed as `replaced-out-of-band`) by the provider's instance id after a real apply; a pre-ledger machine is `adopted` as generation 1 of the record. |
| [`alias_pool.py`](src/cs_image_system/base/alias_pool.py) | The pool of pre-approved names in `meta-state/aliases.txt` (stage 59): a new durable machine's alias is the first free line, burnt in place under an exclusive lock by the run that can launch it. |
| [`provider_aliases.py`](src/cs_image_system/base/provider_aliases.py) | After a real instance-image apply, gives each launched, running instance back the names it lost at boot (the bare declared name, the pool alias, the provider's `ip-...` label) as an `AltNames` block in `/etc/sft/sftd.yaml`, skipping every collision and every silent registry; and the `reality.instances` entries and notes of the state report. |
| [`workload_access.py`](src/cs_image_system/base/workload_access.py) | After a real identity apply, reconciles each managed group's CI login policy through the group builder (stage 56) and records the outcome in the identity read-model. |
| [`materialize.py`](src/cs_image_system/base/materialize.py) | The private mirror `_private/` beside `generated/`, at the same depth: a root is copied there with every `ENC[age:...]` marker replaced by its plaintext before a deferred command runs, incrementally; only `.terraform.lock.hcl` is ever copied back. `ensure_ignored` appends `_private/` to the configuration root's `.gitignore`. |
| [`commands/login_proof.py`](src/cs_image_system/base/commands/login_proof.py) | `verify login`: for each standing instance of a group that names a workload connection and role, checks the machine is running, exactly one registration answers to its hostname, `sft resolve` resolves it and `sft ssh ... id` logs in; every verdict goes to `meta-state/login-proofs.yaml`. |
| [`commands/state_migration.py`](src/cs_image_system/base/commands/state_migration.py) | The runner steps of `--migrate-state` (`begin`, `finish`) and the same-day state `backup` a runner takes into `_private/state-backups/` before any `state rm` it decided on. |

## Tests

The package's tests live in [`tests/`](tests/) and cover the registry and
plugin registration, field helpers and kinds, resolution stages, template
utilities, item kinds, the display name and email-as-username rules, group
gids, provider-specific images and the finalization executor. They run
with the workspace suite; in the workspace, `just test` is the acceptance
bar.

## Prerequisites and integration

The core contains no cloud code and makes no network call of its own:
every provider call goes through a plugin hook, and a hook that is not
implemented (`can_*` false, or `NotImplementedError`) makes no claim. The
state query says so rather than staying silent: a builder whose
`query_state` (or an image or storage lookup under it) raises
`NotImplementedError` adds `<kind>/<builder>: cannot be queried (<why>)`
to `unavailable` (stage 63 item 17; it used to vanish from the report). What
the core needs outside itself is therefore short, and each item says how
the core finds it.

- **Python 3.13 or later and the workspace.** `requires-python = ">=3.13"`
  in [`pyproject.toml`](pyproject.toml); `just init` (`uv sync`) installs
  this package and every plugin beside it. The dependencies are the six
  named at the top of this file; nothing else is imported at runtime except
  the standard library and, optionally,
  [hashicorp-utils](../hashicorp-utils/README.md) (below).
- **Plugins, through entry points.** The core registers no runtime, no
  image builder, no OS builder, no storage, group, user, instance or mod
  builder and no state backend. At every CLI start
  [`loader.py`](src/cs_image_system/base/loader.py) walks the entry-point
  groups `cs_image_system.plugins.<type>` in the order of `PLUGIN_TYPES`
  and registers what each returns; run hooks come from
  `cs_image_system.plugins.hooks`. A configuration whose `type:` names a
  model no installed plugin registered does not load (`KeyError` from the
  converter), and a tree with no `runtime_builders:` at all is refused
  (`No runtime providers configured.`). Every builder class the tree
  declares needs exactly one entry marked `is_default: true` among the
  installed plugins' models. The plugin READMEs say what each needs:
  [ansible-plugin](../ansible-plugin/README.md),
  [aws-runtime-plugin](../aws-runtime-plugin/README.md),
  [bash-mod-plugin](../bash-mod-plugin/README.md),
  [default-os-plugin](../default-os-plugin/README.md),
  [dummy-plugin](../dummy-plugin/README.md),
  [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md),
  [gcs-state-plugin](../gcs-state-plugin/README.md),
  [local-state-plugin](../local-state-plugin/README.md),
  [okta-opa-plugin](../okta-opa-plugin/README.md),
  [packer-plugin](../packer-plugin/README.md),
  [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md),
  [tf-gcp-plugin](../tf-gcp-plugin/README.md),
  [tf-s3-state-plugin](../tf-s3-state-plugin/README.md).
- **hashicorp-utils, for the state-location checks.**
  `check_state_locations` in
  [`commands/validate.py`](src/cs_image_system/base/commands/validate.py)
  and the state-location recording and runner headers in
  [`commands/run_lifecycles.py`](src/cs_image_system/base/commands/run_lifecycles.py)
  import `cs_image_system.hashicorp_utils.collector` inside a `try`; an
  `ImportError` skips them silently. The workspace always installs it, so
  the skip is a packaging accident, never a configuration.
- **A configuration root with `cfg/`.** `--root-dir` (the CLI's, default
  the current directory) must hold a `cfg/` directory with at least one
  YAML file, or the load stops with `Failed to read configuration from
  <root>/cfg`. The Justfile's `config-guard` refuses earlier, naming the
  clone command, when `cfg/_config.yml` is missing. `meta-state/` is
  created at the first write; `generated/` (or `generation_directory`) at
  the first run; `_private/` beside `generated/` at the first real
  deferred command.
- **git, on `PATH`, for four things and nothing else.** `--commit`
  (`commit_meta_state` in
  [`meta_state.py`](src/cs_image_system/base/meta_state.py) runs
  `git rev-parse`, `check-ignore`, `add`, `diff --cached`, `commit`,
  `ls-files`); the public-safe tree and staged scans (`git ls-files`,
  `git show :<path>`); `ensure_ignored`, which appends `_private/` to the
  root's `.gitignore` only when `<root>/.git` exists; and the `--commit`
  run-local set-aside (`git ls-files --error-unmatch`). A root outside a
  git repository skips the commit with a warning and is scanned as a plain
  directory; a gitignored tree is skipped with a warning. The commit is
  git's own, so git's requirements (an identity to commit as) apply.
- **The tools the tree declares under `executables:`.** Every entry's
  `binary` (default: its name) must be an absolute path or a name on
  `PATH` (`shutil.which`), and when it declares a `version`, the checker
  registered under the entry's name, else its type, must read a version
  inside the PEP 440 specifier. This is checked at `validate` and at the
  head of every run, never at load. The core itself invokes only what a
  builder hands it (`ExecutableModel.execute`, `subprocess.run` with
  `check=True`); which binaries those are is each plugin's business.
- **Three binaries the core's own commands call by name.** `tofu` (or the
  root's declared binary, passed as `--tofu`) for `gate-plan`'s
  `tofu show -json <planfile>` and for `state-migration begin|finish` and
  the runner's state `backup` (`state pull`, `init`); `sft` on `PATH` for
  `verify login` (`sft resolve --quiet`, `sft ssh <name> --command`); and
  `docker` on `PATH` with a reachable daemon for `test-mods`
  (`docker info` decides; absent, every mod test is recorded `skipped`).
- **Credentials: none read by the core, several looked at by name.** The
  age identity comes from `CSIS_CONFIG_IDENTITY` (the `AGE-SECRET-KEY-1`
  string, an identity file, or a directory of `*.age-identity` files),
  resolved lazily on the first marker seen, so a tree without markers
  needs no identity; see [Encryption](#encryption). `preflight` and the
  session lines of every run read credential CACHES, never values: the
  profile named by a runtime's `profile` or `credentials.profile_name`
  (else `AWS_PROFILE`) in `~/.aws/config` and `~/.aws/sso/cache/<sha1>.json`
  (the directory is `CSIS_AWS_DIR` when set); `AWS_ACCESS_KEY_ID` only for
  its presence (static keys have no readable expiry); the GCP Application
  Default Credentials at `GOOGLE_APPLICATION_CREDENTIALS` or
  `~/.config/gcloud/application_default_credentials.json`, only for their
  presence and `type`. `OPA_TOKEN` decides whether a login proof is
  recorded `as: workload` or `as: client`; the core never reads its value.
  `USER` (else `USERNAME`) names the operator in an `unmount --confirm`
  receipt. A credential-shaped variable (`AWS_*`, `GOOGLE_*`, `OKTA_*`,
  `TF_VAR_*`, `CSIS_*`) that is set but EMPTY is reported by name by
  `preflight` (`empty_environment_credentials`). `CSIS_CONFIG_ROOT` is the
  Justfile's, not the core's: the CLI takes `--root-dir`.
- **The whole process environment, as `ENV`.** The string stage renders
  `{{ ENV.<name> }}` in any `cfg/` string against `os.environ.copy()`
  taken at load; a variable absent from the environment leaves the tag
  unrendered rather than failing.
- **Network assumptions.** Loading a configuration constructs every
  runtime builder and calls its model's `finalize()`, which is where the
  cloud plugins validate networking against the cloud, so a load needs
  live credentials for every declared cloud runtime (the plugin READMEs
  say which). The core's own after-apply hooks ask the group builder's
  server registry and the runtime's identity, power-state and session
  hooks; an unreachable provider is a warning or a skip, never a guess,
  and a silent registry is never read as a free name.

## Configuration reference

The core owns [`cfg/_config.yml`](../../tests/fixtures/config/cfg/_config.yml)
(the `IAConfig` document that remains after the builder collections are
popped out) and the shape of the five collections under `groups/`,
`storages/`, `images/` and `instances/` (`base_images/` is registered
but not read). The fields each plugin adds to its own builder models and
sub-items, and the plugin's own reading of collection fields (a runtime
plugin's `machine_type`, the identity plugin's `attributes`), are in the
thirteen plugin READMEs linked above. Every model is a pydantic dataclass
with `extra="forbid"`: an unknown key is refused at load.

### `cfg/_config.yml`, top level

| Field | Type | Default | Meaning |
|---|---|---|---|
| `id` | str | required | The configuration's identifier. Read into `IAConfig.id`; nothing in the core acts on the value. |
| `generation_directory` | str or null | `generated` | Where a run writes, relative to the root. The CLI resolves it once at load; every `generated/<lifecycle>/`, `run-summary.json`, `state-report.json` and `final_execution.sh` path hangs under it, and `_private/` replaces its NAME beside it (`mirror_path`). |
| `dateformat` | str | `%Y-%m-%d-%H%M%S` on the model | The `strftime` format of `execution.timestamp` in the string stage. Two readers, two defaults: the string stage reads the RAW key with fallback `%Y%m%d_%H%M%S` when the key is absent; the model's default feeds only the `last_updated_timestamp_str` property, which nothing calls. Declare it explicitly. |
| `executables` | list of `ExecutableModel` | `[]` | The tools builders run; usually in `cfg/executables.yml`. Names unique and never `default`, `self` or empty; checked for presence and version at `validate` and every run. See [`ExecutableModel`](#executablemodel-cfgexecutablesyml-key-executables). |
| `runtime_builders`, `state_backends`, `os_builders`, `mod_builders`, `storage_builders`, `group_builders`, `user_builders`, `image_builders`, `instance_builders` | lists | `[]` | The builder declarations, each with `name` and `type`; structured per `type` against the plugin model and stored by name. Accepted at the top level of ANY `cfg/*.yml`; lists are concatenated across files. |
| `gitignore` | list[str] | `[]` | Appended to the built-in entries (`target/`, `.terraform/`, `terraform.tfstate`, `terraform.tfstate.backup`, `!.terraform.lock.hcl`); a duplicate keeps its LAST position. Written as `.gitignore` into `generated/` (plus the run-local names there) and into every lifecycle directory. |
| `encryption.recipients` | list[str] | `[]` | age public keys (`age1...`) every `ENC[age:...]` value is encrypted to. Read as TEXT by `encrypt` and `reencrypt` (no identity needed); a marker here is refused. |
| `public_safe.allow` | list[str] | `[]` | What the scanner lets through by decision: a plain entry is a case-insensitive substring a matched span may contain; `path:<glob>` accepts a file whole (path or basename). Read as text by the commit gate, `public-safe` and the hook; must be a list of strings. A marker here is refused. |
| `config` | mapping | `{}` | Free settings: available as `config.<key>` in the string stage and on the context as `ctx.config`; the keys the core reads are tabled next. An overlay's `config:` overrides these key by key for one invocation. |
| `sleep_before_finalization` | int | `1` | Accepted and IGNORED: finalization never waits on a terminal; a real run logs `sleep_before_finalization=<n> is ignored`. |
| `working_directory` | str | `./workdir` | Accepted, not read: `--root-dir` is the working directory. |
| `last_updated` | datetime | now | Accepted, not read. |

### `config:` keys the core reads

| Key | Type | Default | Read by | Effect |
|---|---|---|---|---|
| `apply_identity` | bool, str or list[str] | `false` | `apply_enabled("identity")` in [`utils.py`](src/cs_image_system/base/utils.py); the identity plugins at generation; `apply-check` at execution; `workload_access`, `reconcile_generations` and the launch-params hooks read the sibling flags | `true`: every root of the lifecycle applies; `false`, unset or an empty list: plan and gate only; a list: only the roots whose builder NAME or RUNTIME is listed apply (a string is a one-element list; entries are stripped). May not be encrypted (read raw by `apply-check`). |
| `apply_storage` | same | `false` | as above; `record_storage_transitions` | Same rule, the storage roots. Also feeds the run's apply SCOPE (below). |
| `apply_instances` | same | `false` | as above; `mark_launched`, `forget_decommissioned`, `forget_ephemerals`, `record_detachments`, `register_provider_aliases`, `reconcile_generations`, `validate_claimed_hostnames`, `alias_for` | Same rule, the instance roots. When ON, the after-apply recorders claim reality, the hostname claims are checked against the registry, and a run that can launch draws from the alias pool. |
| `apply_release` | same | `false` | `release.after_generate` | On: the runtime's `release_commands` for every CURRENT release are deferred into the release runner (the cloud-side marking). Off: only the read-model and the `release --declared` step. |
| `use_state_backends` | bool | `false` | hashicorp-utils' collector (`backends_enabled`); the core's `check_state_locations` and `_record_state_locations` skip when off | Off: no backend block, no `.tfbackend.hcl`, no remote-state data source, no location record, no collision or move check. |
| `module_source_base` | str | `../tfmodules` | `module_source` in `utils.py` | The base of terraform module sources; a relative value is relative to the configuration root and rewritten per workspace depth; absolute paths and URLs pass through. |
| `admin_public_keys` | list[str] (a lone string is accepted) | `[]` | `admin_public_keys` in [`capabilities.py`](src/cs_image_system/base/capabilities.py); `validate_base_images`; the fingerprint; the in-bake tests | The mandatory local admin user's OpenSSH public keys for every base image without its own `admin_public_keys`; each must be one public-key line and never private-key material. May be `ENC[age:...]` (the fixture's is). |
| `require_mod_tests` | bool | `false` | `release()` | A release refuses a build whose modification has no local mod-test record; off, a missing record is tolerated (a FAILED or non-idempotent one always refuses). |
| `require_image_tests` | bool | `true` | `release()` | A release of an image declaring `tests.post_bake` needs a PASSING post-bake record for that build. |
| `require_released_builds` | bool | `false` | `validate_released_pins` | An instance may be pinned only to a released build of its image, or to the series head under the release grace. |
| `preflight.expected_run_minutes` | int | `30` | `expected_run_minutes` and `raw_expected_run_minutes` in [`commands/preflight.py`](src/cs_image_system/base/commands/preflight.py) | A session expiring within this many minutes is `blocking`: `preflight --strict` and `state query --strict` exit 1 on it, a run warns. Read raw (before the load) from `cfg/_config.yml` and the overlays, so it may not be encrypted; a non-integer falls back to 30. |
| any other key | any | | `ctx.config`, the string stage | Carried for plugins (`okta_gateway_selector` is the identity plugin's) and usable as `{{ config.<key> }}` in `cfg/` strings. |

Which apply flags shape the run's SCOPE: `apply_scope_runtimes` in
[`commands/run_scope.py`](src/cs_image_system/base/commands/run_scope.py)
reads `apply_storage` and `apply_instances` (never `apply_identity`) plus
`--apply-runtime`; a `true` anywhere means no scope, a list names runtimes
directly or through a root's runtime.

### Overlays and `--undeclare`

An overlay file is a mapping whose keys are `config` (a mapping, merged
key by key over `config:`) and the collection keys `users`, `groups`,
`storages`, `images`, `instances`, `base_images` (each a list of
mappings with a `name`). A named entry that exists in the tree is
updated key by key; a new one is appended and remembered as transient
(`ctx.overlay_declared`); `undeclare: true` removes the tree's entry for
this invocation. Any other top-level key, a non-mapping `config`, a
non-list collection, or a missing file is refused. `--undeclare
<kind>:<name>` is the flag form; the kind is a collection key or its
singular. An overlay-declared storage on an ephemeral runtime is torn
down by the retention lifecycle's closing storage run.

### The collections: what the core reads

The model tables under [The base models](#the-base-models) give every
field's type and default. This table says which fields the CORE acts on
and where, and names the ones it accepts without reading. A field marked
"plugin" is consumed by the plugin that owns the builder; see that
plugin's README.

**`images:`** (`Image`)

| Field | Read by the core | Effect |
|---|---|---|
| `name` | everything | The series name: lineage, pins (`<image>@<runtime>`), the bake plan, releases, retention. |
| `type` | the load; `primary_runtime_of` | The primary image builder, hence the primary runtime. |
| `source_image` | `image_chain`, `effective_capabilities`, `parent_reference`, `upgrade image` | The parent; the chain must end at an OS builder or capability resolution fails validation. Required at load. |
| `group` | `validate_image_groups`, `validate_capabilities`, `validate_storages`, `compute_launch_params`, `provider_aliases`, `login_proof` | The owning group; required by validation for any image an instance uses; its identity type must be one the root base carries. |
| `runtimes[]` | the load (`_runtime_map` keyed by each entry's runtime), the bake plan (one bake per image builder), `resolve` (deferred provider-specific images) | Which image builders bake it. The entries' `machine_type`, `ssh_username`, `image_identifier`, `owners`, `tags` are read by the packer and runtime plugins. |
| `modifications[]` | `mod_records` (content hashes into lineage and the fingerprint), `mod_tests`, the fingerprint | Each entry's `type` names a mod builder; the item class is the plugin's. |
| `tests` | `validate_test_specs`, `image_tests` (in-bake and `post_bake`), `release`, `verify instance` | The known keys are `files`, `packages`, `commands`, `services_enabled`, `users`, and `post_bake` (the same plus `mounts`). |
| `parent_policy` | `validate_policies`, `effective_parent_build`, `bake_reason` | `pinned` or `follow`. |
| `retention` | `validate_policies`, `retention_keep_for`, the retention lifecycle | `{keep: N}`, N a non-negative int. |
| `release` | `validate_policies`, `declared_release_targets`, the release lifecycle | `{model: <name>}`. |
| `primary_disk_size` | `_bake_disk_size` (the fingerprint) | Part of the input fingerprint; the bake disk and every boot disk (plugin). |
| `tags` | `get_tags` (merged for the sub-config) | Plugin (packer tags). |
| `architecture` | templated at load | Plugin. |
| `description`, `config`, `aliases` | the load | `description` defaults to `Image <name> from source image <source>`; aliases register; `config` is template context. |
| `auto_update` | -- | Accepted, not read for instance images (updates are a base-image policy). |
| `is_default`, `auto_generate_storage`, `default_groups` | -- | Accepted, not read. |
| `variables` | -- | Accepted, not read by the core; the packer plugin reads it. |

**`instances:`** (`Instance`)

| Field | Read by the core | Effect |
|---|---|---|
| `name` | everything | The declared name; the canonical hostname is derived from it. |
| `type` | the load; per-root apply scoping (`apply_enabled("instances", type, [runtime])`) | The instance builder (the terraform root). |
| `image` | `finalize` (required), pins, launch parameters, verification, capabilities | The instance image. |
| `runtime` | apply scoping, `verify instance`, `unmount`, `login_proof`, power state, identity, the zone check | The runtime whose hooks answer for this machine. |
| `storages[]` (`name`, `mount_point`, `min_size`, `type`) | `storage_mappings()`: attachments, the strict attach rule, cardinality, `compute_launch_params` (`mounts`), `detachments`, the zone check | `name` must be a declared, `active` storage; `mount_point` non-empty; `min_size` positive (not consumed further); `type` is set to the storage's builder. A name attached twice keeps the later mapping; aliases are ignored with a warning. |
| `availability_zone` | `check_availability_zones` | One of the zone claimants. |
| `userdata` | `compute_launch_params`, `user_data_template` | Appended to the launch script under `set -e`; a launch parameter (immutable). |
| `image_policy` | `validate_policies`, `instance_follow_target`, `will_replace`, `canonical_hostname` | `pinned` or `follow`. |
| `ephemeral` | `compute_launch_params`, `forget_ephemerals`, `generations.kind_of`, `alias_for`, `standing_instances`, the state query | Launched, verified and torn down in one run; counts on its own generation counter; draws no alias; never a login-proof target. |
| `on_failure`, `teardown_after` | `validate_policies`, `failure_policy`, `teardown_due` | `keep` or `teardown`; `<n>m|h|d`. Null inherits the runtime's. |
| `machine_type` | -- | Accepted by the core, read by the instance builder plugins. |
| `description`, `tags`, `config`, `aliases` | the load | Plugin (`tags`); template context. |
| `groups` | the load | REFUSED with a message naming `group:` on the image. |

**`storages:`** (`Storage`)

| Field | Read by the core | Effect |
|---|---|---|
| `name` | everything | System-wide unique; the storage state machine, the read-model, attachments and facts key on it. |
| `type` | the load (`also_set_on_update`), `validate_storages`, `storage_type_of`, `storage_facts`, `_root_applied` | The storage builder: fixes the capability type, the cardinality, whether it is zonal, and the runtime the root applies on. |
| `runtime` | `check_availability_zones`, as a fallback only (`_storage_runtime`) | The BUILDER's runtime governs everywhere, the zone check included since stage 63 item 20; the item's own value is read only when the builder names no runtime. Until 2026-09-25 the zone check read this field, whose `default` resolved to the default runtime, not the builder's. |
| `groups` | the load (`ALL` refused), `validate_storages`, `allows_group`, the read-model | The groups allowed to attach; each must be declared. |
| `public_read` | `allows_group`, `compute_launch_params`, the read-model | Anyone may mount read-only. |
| `share_mode` | the load (`2770` or `2775`), `compute_launch_params`, the read-model | The mode of each group's subtree. |
| `state` | the load (`active`, `archived`, `destroyed`), `pending_transitions`, `validate_transitions`, `is_attachable`, the read-model | The REQUESTED state; `storage-state.yaml` holds the current one. |
| `lifecycle` | `validate_storages` (through the builder's `validate_lifecycle`), the read-model, the state query (`stale` until applied) | A data lifecycle only its builder realizes. |
| `availability_zone` | `check_availability_zones` | Meaningful only when the builder is zonal. |
| `bucket_name` | `storage_facts` (recorded so an undeclared bucket can still be wiped) | Plugin otherwise. |
| `tags`, `config`, `description`, `aliases` | the load | Plugin (`tags`, `config`). |
| `is_default`, `singleton`, `ephemeral`, `generative`, `source`, `mount_point` | -- | Accepted, not read (the attachment's `mount_point` on the instance is what a launch uses). |

**`groups:`** (`Group`)

| Field | Read by the core | Effect |
|---|---|---|
| `name` | everything | Unique; the read-model, the launch parameters (`group`), the server registry lookups. |
| `type` | the load | The group builder; fixes the identity type. |
| `is_root` | `_validate_groups` (exactly one), `ctx.root_group`, the read-model, `group_drift` (root admins merged into every group's expected admins) | The single root group. |
| `members`, `admins` | `_validate_groups` (every member is a declared user), `__post_init__` (`in_both`), the read-model, `group_drift` | Rosters; entries may be `ENC[age:...]` and are public by decision in the read-model. |
| `in_both` | `__post_init__` | `true` adds admins to members; `false` removes the overlap. |
| `gid` | `__post_init__` (normalised to `int >= 1024` or `None`) | Plugin otherwise. |
| `unmanaged` | the read-model (`managed`), `validate_identity`, `workload_access` | A managed group may leave management, never the YAML. |
| `attributes` | `identity_attributes` (validate per plugin, plan, probe; apply disabled) | Provider attributes. |
| `include_root_group_in_admins` | -- | Accepted by the core, read by the identity plugin. |
| `is_default` | -- | Accepted, not read. |
| `description`, `tags`, `config`, `aliases` | the load | Template context; aliases register. |

**`users:`** (`User`)

| Field | Read by the core | Effect |
|---|---|---|
| `name` | `_validate_groups`, the read-model, `email_as_username` (through the builder base) | The login; may be encrypted and stays public by decision in emissions. |
| `type` | the load | The user builder. |
| `first_name`, `last_name` | the load (required, non-blank, never derived) | Plugin otherwise. |
| `email` | templated at load from the builder's template | Plugin otherwise; a derived address inherits its inputs' encryption. |
| `description` | templated at load | |
| `attributes` | `identity_attributes` | Provider attributes. |
| `managed` | `validate_identity_items` (through the builder's `validate_user`) | Plugin otherwise. |
| `middle_name`, `is_enabled`, the profile fields | -- | Accepted by the core, read by the identity plugin. |
| `is_service_account`, `public_keys` | -- | Accepted, not read anywhere. |
| `tags`, `config` | -- | Accepted, not read. |
| `aliases` | the load | REFUSED. |

**`base_images:`**: the kind is registered `base_only` and never read;
base images are synthesized from `os_builders` during the base-image
lifecycle.

**Builder-level fields the core itself acts on** (everything else on a
builder model is its plugin's):

| Where | Field | Read by |
|---|---|---|
| runtime builder | `ephemeral` | `retention_keep_for` (0 builds kept), `ephemeral_runtimes`, `transient_storages_on_ephemeral_runtimes` |
| runtime builder | `retention_keep` | `validate_policies` (non-negative int), `retention_keep_for` |
| runtime builder | `on_failure`, `teardown_after` | `validate_policies`, `failure_policy` (the instance's null inherits) |
| runtime builder | `default_machine_type`, `default_image_builder`, `default_owners`, `default_config_username` | the models' templated defaults and the resolve step; the plugins |
| runtime builder | `networking.subnets[].availability_zone`, `networking.availability_zones[].is_default` | `_runtime_zone` (the zone the runtime asserts) |
| runtime builder | `credentials.profile_name`, `profile` | `preflight` (raw, before the load); may not be encrypted |
| runtime builder | `name`, `type` | `preflight` (raw); may not be encrypted |
| OS builder | `identity_types`, `storage_types` | `declared_capabilities`, `validate_base_images`, the capability stamp and lineage tags |
| OS builder | `admin_user`, `admin_public_keys` | `validate_base_images`, `admin_public_keys`, the fingerprint, the in-bake tests |
| OS builder | `update`, `auto_update` | `validate_update_policies`, `update_policy_of` (the fingerprint, `refresh_days`) |
| OS builder | `tests`, `runtimes[].tests` | `validate_test_specs`, the in-bake tests, the fingerprint |
| OS builder | `runtimes[].image_builder`, `image_id`, `image_name`, `query`, `default_primary_disk_size` | `base_image_runtimes`, `_vendor_source`, `_bake_disk_size` (the fingerprint) |
| OS builder | `family`, `family_version`, `architecture`, `query` | `_vendor_source` (the fingerprint); the plugins |
| every builder | `executable` | `check_existence_of_executable`: must name an entry under `executables:` |
| every builder | `is_default` | the load: exactly one per classification |
| every builder | `state_configuration` (storage, instance, group, user, runtime) | `terraform_workspaces` (the state-location chain) |

### Variations

- **Dry run vs real run** (`--dry-run`, the default, vs `--no-dry-run`).
  A dry run generates everything, writes the runner scripts and the
  read-models, records launch parameters, and then only logs each
  deferred command as `[DRY RUN] <lifecycle>/<phase>: would execute ...`;
  no `pre_finalize_phase`/`post_finalize_phase`, no after-apply hook, no
  materialisation into `_private/`, no pin moves under `follow`, no
  forgets, no alias draw (the log says what it WOULD take), no
  `--migrate-state` (refused). The hostname claim check is NOT gated on
  the dry run: it runs whenever the instance-image lifecycle is requested
  and `apply_instances` allows the root, and asks the registry. Deferred system-CLI steps
  are recorded with `--no-dry-run`, so they only ever run inside a real
  run. A real run executes each generated lifecycle's deferred commands in
  process, each terraform or packer command from its private mirror, and
  fires the after-apply hooks.
- **Apply flag on vs off, bool vs list.** Off (or unset): the roots plan
  and gate, nothing applies, and no reality-claiming record is written
  (transitions, `launched`, generations, releases' cloud marking, the
  prune step's effect). `true`: every root of the lifecycle applies and
  the run has no apply scope. A list: only the named roots or runtimes
  apply; the run's apply scope is those runtimes, and a `--no-dry-run`
  run whose bake plan would bake outside it is refused before any bake
  (a dry run warns; `--allow-unscoped-bakes` or an explicit `--only` /
  `--only-runtime` allows it). `--apply-runtime <rt>` sets
  `apply_storage` and `apply_instances` to `[<rt>]` for the run and, unless
  images were selected explicitly, implies `--only-runtime <rt>`.
- **`--only` / `--only-runtime` vs an unscoped run.** Unscoped: every
  lifecycle directory is wiped whole and regenerated. Under a runtime
  scope the image, storage and instance builders bound to OTHER runtimes
  keep their directories exactly as committed, the bake plan reads
  `skip: not selected (--only)` or `skip: outside the apply scope`, and
  the retention step carries `--runtime <rt>`. `--only none` is an
  explicitly empty bake surface (the terraform roots alone).
- **Ephemeral vs durable instance.** A durable instance is launched once,
  its launch parameters are immutable afterwards, its pin moves only
  through `upgrade instance`, `image_policy: follow`, decommission or
  disposal, and a new machine of it draws an alias from the pool. An
  ephemeral instance's root sequence is launch, `verify instance`, a
  second plan with the instance absent, gate, apply; after a real apply
  its launch record and pin are forgotten (`op: ephemeral`), its
  generation closes as `ephemeral`, it counts on the `ephemeral` counter
  (so `gce-test-007` never moves `coops-model`'s number), it draws no
  alias, the state query reports one still standing as `changed`, and
  `verify login` never targets it. `on_failure: keep` leaves a failed one
  standing and fails the run; `teardown` records the verdict with
  `--record-only`, tears it down, forgets the record and fails the run
  from `forget_ephemerals`; `teardown_after` lets a later run tear it down
  once the duration has elapsed.
- **Pinned vs follow.** `parent_policy: pinned` bakes an image from its
  pinned parent build until `upgrade image`; `follow` bakes from a newer
  parent head (or from a parent that bakes this run) and moves the pin
  when the bake is recorded (`op: follow`). `image_policy: pinned` keeps
  an instance on its build until `upgrade instance`; `follow` plans the
  gated replacement whenever the image's head on its runtime is newer,
  which is also a sanctioned exit from immutability and a new canonical
  hostname.
- **`require_released_builds` on vs off.** Off: any recorded build may be
  pinned. On: only a released build, except under the release grace (the
  series head, verified in bake, no failed post-bake record, and the
  instance a pending replacement onto it or standing on it), which is
  logged as a warning naming why it is allowed; `forget instance` exists
  for the pin that outlived its instance and would otherwise refuse every
  run.
- **`require_image_tests` / `require_mod_tests`.** With post-bake tests
  declared and `require_image_tests` on (the default), `release` refuses a
  build with no passing record; `release --declared` simply skips such a
  head. `require_mod_tests` turns a missing mod-test record from tolerated
  into a refusal.
- **Encrypted vs clear values.** Any value may be an `ENC[age:...]`
  marker except a mapping key, a marker embedded in a longer string, a
  declaration's `name` or `type`, and the raw-read paths (`EXEMPT_PATHS`).
  A clear value is emitted and recorded as written. An encrypted value is
  decrypted at load (identity required), emitted as its SOURCE ciphertext
  (`emit`), materialised into `_private/` for execution, recorded in
  meta-state as the ciphertext (except a username, public by decision),
  hashed in its materialised form for the fingerprint (so a `reencrypt`
  moves no fingerprint), and searched for in clear under `generated/` and
  `meta-state/` by `validate` and every commit. A derived value (an
  address built from an encrypted domain) inherits the ciphertext of its
  pieces (`mark_plaintexts`).
- **Ephemeral vs durable runtime.** `runtime_builders[].ephemeral: true`
  keeps zero builds: the retention step disposes every recorded build
  there except released builds and builds an instance is pinned to or was
  launched from (reported as debt); declared storages are never touched,
  but a storage declared by an OVERLAY on such a runtime is torn down by
  the same run's closing storage step. A durable runtime keeps everything
  unless `retention_keep` or an image's `retention` says otherwise.
- **A storage that is declared, undeclared, or requested `archived` /
  `destroyed`.** Declared and `active`: created and kept. Its entry
  removed: the next storage run plans its whitelisted destroy (its root
  is still emitted from the recorded facts) and records the tombstone
  with action `undeclared`; re-declared later, it is a new `generation`
  (`regenerate`). `archived`: only a builder whose `supports_archive()` is
  true may request it, and only unattached; `destroyed` from `active` or
  `archived`, only unattached. Attaching a non-active storage is refused.
- **Managed vs `unmanaged: true` group.** A managed group is recorded
  `managed: true` in the read-model and its disappearance from the YAML
  refuses validation; `unmanaged: true` keeps the entry, records
  `managed: false`, exempts it from the drift and prune rules and from the
  CI login policy reconcile, and lets the identity plugin remove it from
  state without destroying it.
- **A machine that is running vs one that is stopped.** A stopped machine
  is a `note` in the state report, never drift and never "unavailable";
  its booted image, identity and aliases are simply not read. Only
  `verify instance` (and the post-bake tests inside it) may start it
  through `running_for_task`, saying so, and stops it again whether the
  work passed, failed or raised; a runtime that cannot start it makes
  the verification a SKIP recording nothing. The alias pass and the login
  proof leave a stopped machine alone. A runtime that cannot answer the
  power-state query changes nothing: silence is never read as stopped.
- **The registry answers vs the registry is silent.** With
  `apply_instances` on and the instance-image lifecycle requested, a
  registry that answers lets the hostname claims be checked and the
  aliases written; a registry that cannot be asked (`registered_servers`
  returns `None`) REFUSES the launch ("could not check whether canonical
  hostname ... is already claimed"), skips every alias that run, and fails
  the login proof's "one registration" check. Silence is never a free
  name.
- **`use_state_backends` on vs off.** On: every terraform root's state
  location is resolved from the declarations (own `state_configuration`,
  else the runtime's, else the default backend), collisions and unsafe
  moves are refused at `validate`, the locations are recorded and the
  runner headers list them. Off: none of it, and every root initialises
  with `-backend=false`.
- **A git repository vs a plain directory as the root.** In a repository
  `--commit` stages and commits `meta-state/` and `generated/` by
  pathspec (never the refused names or the run-local files) after the
  scan; `_private/` is appended to the root's `.gitignore`; the public-safe
  tree scan covers tracked and untracked non-ignored files. Outside one
  the commit is skipped with a warning, no `.gitignore` is touched and the
  scan covers every file.
- **An alias pool present vs absent.** With `meta-state/aliases.txt`,
  `validate` checks every free line and reports how many remain, and the
  run that can launch a new durable machine burns the first free line
  before its apply (a run that dies in between costs one name). Without
  the file: no aliases, no error. An empty pool is a warning and the
  launch proceeds without an alias.
- **`OPA_TOKEN` set vs not.** `verify login` records `as: workload` when
  the variable is set (CI, the token minted from the job's OIDC token)
  and `as: client` otherwise (the operator's enrolled `sft` client). The
  checks are the same.
- **One runtime vs another.** The core never branches on a cloud's name;
  what differs is which hooks a plugin implements. Block-device names in
  the launch parameters are the one place the core knows two storage
  types by name: `/dev/xvdf` onwards for `ebs`, `/dev/disk/by-id/google-<name>`
  for `pd`; `efs` and `filestore` mount by reference; `s3` and `gcs` get
  no mount.

## What it tests and verifies

The core is where most of the system's checks live. They fall at six
moments; each entry says what is checked and where the verdict lands.

### At load (structuring, `__post_init__`, the item-kind validators)

The verdict is an exception from the load: the command that loaded the
tree (`validate`, `run`, anything) stops before any rule below runs; the
CLI's callback prints `Error reading config file : <message>` on stderr
and re-raises, so the traceback follows and the process exits 1. Nothing
is written.

- **The raw `cfg/` documents** (`read_and_process`): every file is a
  mapping; lists under one key are concatenated; a duplicate `name` in a
  list is refused; a `name` or `type` containing `{{` is refused; a marker
  standing where one may not (a mapping key, an `EXEMPT_PATHS` value, a
  declaration's `name` or `type`) is refused by path, with no identity
  needed (`refuse_markers_at`).
- **Decryption** (`decrypt_tree`): every whole-value marker opens with an
  identity from `CSIS_CONFIG_IDENTITY`; no identity, or no identity that
  opens the value, or a marker embedded in a longer string, is refused
  naming the value's path.
- **Every model** (`CSIS_MODEL_CONFIG`): unknown keys are refused; a
  `parameters` key on a builder is refused naming `variables:`; names and
  aliases may not be `default`, `self`, empty or `None`, nor contain `/`
  or `\`; each plugin key's entries need `name` and `type`; an unknown
  `type` is a `KeyError`; exactly one `is_default` per classification
  (`No default builder found` / `Multiple default builders found`); a
  duplicate builder name; a builder's `runtime` must resolve; a
  `RuntimeBuilderModel` needs `default_machine_type`; networking needs a
  `network`, at least one subnet and exactly one default subnet; an OS
  builder needs at least one `runtimes[]` entry with unique image
  builders; an image needs `source_image` and at least one `runtimes[]`
  entry; an instance may not declare `groups`; a storage mapping needs a
  non-empty `mount_point` and a positive `min_size`; a storage refuses
  `ALL`, an unknown `state` and an unknown `share_mode`; a group's `gid`
  must be an int of at least 1024 or a deferral; a user needs non-blank
  `first_name` and `last_name` and may not have aliases; an executable's
  name may not be a default placeholder and must be unique.
- **After the items are read**: exactly one group is `is_root: true`;
  every group member is a declared user (`_validate_groups`); every item's
  `type` resolves to a configured builder, or to the registered default
  when the field allows it; every foreign key that resolved to nothing is
  remembered for `validate` (`UNRESOLVED_FKS`).
- **Every builder model's `finalize()`** and the builder's own
  `finalize()` run at load, which is where the plugins validate against
  their providers.

### At `validate`, and at the head of every `run`

`collect_validation_errors`, `validate_policies` and every registered
validator run with no side effect on generated output. Each error is a
string; `validate` prints them all and exits 1; `run` logs each as
`validation: <error>`, records them under `validation_errors` in
`generated/run-summary.json` and in `meta-state/runs.yaml`, generates
nothing, and exits 1. The run's own additional pre-checks are noted
where they differ.

| Check | Function | What it refuses |
|---|---|---|
| unique global ids | `check_name_uniquness` | two OS builders, runtime configurations or images with one id |
| executables | `check_executables_exist_and_versions` | a declared binary not found; a version that cannot be read or parsed; a version outside its requirement; a builder's `executable` naming no entry. What passed is one INFO line, `Executables: <name> <version> ok (...)` |
| state locations | `check_state_locations` | a root naming an undeclared backend; two roots sharing one state object; a root whose location moved while resources stand in it (the fix is `--migrate-state`) |
| foreign keys | `check_foreign_keys` | a field that names no object of its classification, naming the object, field, value and what is declared |
| availability zones | `check_availability_zones` | a zonal storage in a zone other than its runtime's; an instance, its zonal storages and its runtime's subnet asking for more than one zone |
| the alias pool | `check_alias_pool` | a free line that is not an RFC 1123 label, repeats another, or is a name an instance already has; remaining names logged, an empty pool warned |
| canonical hostnames | `check_canonical_hostnames` | a hostname over 63 characters, with characters outside letters, digits and hyphens, or starting or ending with a hyphen |
| policies | `validate_policies` | `parent_policy` / `image_policy` not `pinned` or `follow`; `retention` not `{keep: <non-negative int>}`; `release` not `{model: <name>}`; `retention_keep` not a non-negative int; `on_failure` not `keep` or `teardown`; a `teardown_after` not `<n>m|h|d` |
| test specs | `validate_test_specs` | unknown `tests` keys, a `files` entry without `path`, a `commands` entry without `run`, a `post_bake` that is not a map or has unknown keys, a `mounts` entry that is not absolute |
| update policies | `validate_update_policies` | an `update` that is neither a mapping nor a policy name; `packages` without packages or pins; a package both updated and excluded; a non-positive `refresh_days` |
| identity | `validate_identity` | a group the read-model records as managed that is missing from the YAML |
| storages | `validate_storages` | an unknown allowed group; an instance attaching a group-gated storage its image's group is not allowed (or with no owning group); a data lifecycle the builder cannot realize; a single-attach storage attached by several instances (naming the multi-host builders on that runtime); every illegal transition (a new storage not starting `active`, an illegal pair, a transition while attached, `archived` on a builder without archive support, an undeclared storage whose record names no root, an attachment of an unknown or non-active storage) |
| image groups | `validate_image_groups` | an image naming an unknown group; an instance whose image has no group |
| base images | `validate_base_images` | an identity or storage type no configured plugin provides; an admin key that is not one OpenSSH public-key line (private material is named as such); an empty `admin_user`; a base image with neither an admin key nor a session mechanism on a runtime (the N9 dead end) |
| capabilities | `validate_capabilities` | an image that does not chain to a base; a group with no identity builder; an identity type or attached storage type the root base does not carry (resolved through the pins to the stamped build, else the declaration) |
| identity items | `validate_identity_items` | whatever the owning user or group plugin's `validate_user` / `validate_attributes` returns |
| immutability | `validate_immutability` | a launched instance whose launch parameters changed, unless a replacement is pending, a follow target exists, or the only change is a removed mount |
| claimed hostnames | `validate_claimed_hostnames` (only when the instance-image lifecycle is requested AND `apply_instances` allows the root AND the run is not a dry run, since stage 63 item 10) | an unlaunched instance whose canonical hostname is already registered; a launched one with more than one registration; a registry that could not be asked |
| released pins | `validate_released_pins` (only with `require_released_builds`) | a pin that is neither released nor under the grace, naming what is missing |
| the state report | `validate_state_report` | any `hard: true` drift in the last `generated/state-report.json` (re-run `state query` after fixing) |

Before validation a `run` also: queries reality unless `--no-state-query`
(the report and its counts go to `state-report.json` and the summary's
`state`; every `unavailable` line is a warning), prints one `session:`
line per credential source (a blocking one as a warning), and after
validation computes the bake plan (logged per `<series>@<runtime>` and
journaled under `bake_plan`) and applies the scope check.

### At generation

- **Resolution** (`predefined_resolve`): a base-image lifecycle asks each
  runtime for the vendor image; no image builder, no runtime builder, or
  no resolved identifier for an OS builder raises and the lifecycle is
  recorded `failed`. Template resolution runs up to five passes; what
  still carries `{{` stays as written.
- **The phases**: a before-hook, generator or after-hook returning false,
  or a build executable exiting non-zero, raises `LifecycleRunError`
  (`[<lifecycle>] before-phase hooks failed for <phase>` and so on); the
  summary records the lifecycle `failed` with the error and the run exits 1.
- **The read-models** are written after the identity and storage
  lifecycles generate; **the launch parameters** after instance-image
  (an instance with a pending detach keeps its old record until the
  detach applies); **the attributes plan** after identity when anything
  declares attributes (and is removed when nothing does); **the state
  locations** after every lifecycle; **the runner script** when any
  deferred command was recorded. Every meta-state write passes
  `assert_public_safe` (the hard rules) and is refused with a
  `PublicSafeError` otherwise.
- **The in-bake assertions** are generated here (`image_tests`), as the
  last packer provisioner: the admin user and keys, every declared
  identity and storage type's `verify_commands`, the runtime's session
  agent, the group's activation, and the declared `tests:`. Their verdict
  is the bake's: a build exists in lineage only because they passed, and
  the record says `tests: {in_bake: true, assertions: N}`.
- **The bake plan and the fingerprint**: every path that reads a bake
  decision reads the one cached per run, so the sources, provisioners,
  runner scripts and lineage records agree.

### At apply (a real run's deferred commands)

- Each deferred command is materialised into `_private/` and executed;
  a non-zero exit or an exception logs
  `[<lifecycle>/<phase>] command failed` or `command returned <rc>`,
  marks the lifecycle's apply `failed` in the summary and journal, and
  the run exits 1. Later lifecycles are not attempted.
- The terraform sequence's own checks are the system CLI's: `gate-plan`
  (every planned destroy whitelisted, the planfile fresh, every detach
  unmounted; exit 3) and `apply-check` (the flag still on now; exit 3);
  their code is in this package
  ([`commands/gate.py`](src/cs_image_system/base/commands/gate.py),
  `apply_flag_allows`), their behaviour in
  [system's README](../system/README.md).
- The deferred system-CLI steps verify as they go: `verify instance`
  (the runtime's checks, the booted image against the pin or the series,
  the declared post-bake tests; verdict in `verifications.yaml` and
  `image-tests.yaml`, a failed one raises and stops the runner unless
  `--record-only`); `verify assert` (the last verdict must be ok);
  `unmount storage` (a receipt, success or not, and a raise on failure);
  `release --declared` (each target re-evaluated at execution);
  `dispose image --retention` (recomputed at execution; debt logged);
  `prune-attachments` and the state `backup` (an uninitialised root, a
  failed pull or a location with no state stops the runner before any
  `state rm`); `state-migration begin` (the new location must be empty
  or hold this lineage) and `finish`.

### After apply (the after-apply hooks, never in a dry run, each gated on its lifecycle's apply flag)

In order: `write_read_model` is generation-time; then
`record_storage_transitions` (requested states become authoritative for
the roots that applied), `record_launch_params` is generation-time,
`mark_launched` (the `launched` marker; a generation opens `inferred`; a
replaced machine's old registration is retired), `forget_decommissioned`
(pin, launch parameters and registration of an undeclared instance whose
root applied; generation closed `decommission`), `forget_ephemerals`
(generation closed `ephemeral`; a `teardown` policy's failed verdict
raises here), `record_detachments`, `register_provider_aliases`,
`reconcile_generations` (the provider's instance id confirms, adopts or
replaces the open generation), `reconcile_workload_access` (the CI login
policy per managed group, recorded under `workload` in the read-model;
a failure is an ERROR, never fatal). Every outcome is a log line and a
meta-state write.

### At `--commit`

The would-be additions are listed with `git add --dry-run`; a refused
name (`tfplan`, `*.tfstate`, `*.tfvars`, `.envrc`, `*.pem`, ...) is
warned about and excluded by pathspec; every other file is scanned with
the tree's allowances; every plaintext this run decrypted is searched for
under `generated/` and `meta-state/`; one finding raises `PublicSafeError`
naming the path, the rule and a six-character excerpt, and nothing is
staged. The verdict of a successful commit is its sha, in the log and
under `meta_state_commit` in the summary.

### In the state query

`state query` (and every run's first step) classifies drift as `missing`,
`foreign`, `changed` or `stale`, marks `hard` a pinned build gone, a
storage recorded live but absent, a managed group the provider answered
does not exist, a missing enrollment token, and a pin to an unrecorded
build; lists `unavailable:` providers (a group whose provider could not be
asked is one of these, never `missing`); and adds `note:` lines (a stopped
machine, a pending replacement, a workload connection in draft, a
registered name that is not the booted one, an alias not yet given back).
The report is `generated/state-report.json` (run-local, never
committed), printed by `render()`; `--strict` exits 1 on hard drift, on
any class but `stale`, and on a blocking session. The hard entries feed
`validate_state_report` at the next run.

### In the suite

The package's own tests under [`tests/`](tests/) cover the registry,
plugin registration, field helpers and kinds, resolution stages, template
utilities, item kinds, display names, `email_as_username`, group gids,
provider-specific images and the finalization executor. The workspace
suite pins the rest of what this section describes; the recent ones are
[`tests/test_v2_hygiene_five.py`](../../tests/test_v2_hygiene_five.py)
(stage 61), [`tests/test_v2_power_state.py`](../../tests/test_v2_power_state.py),
[`tests/test_v2_canonical_names.py`](../../tests/test_v2_canonical_names.py),
[`tests/test_v2_hostname_claims.py`](../../tests/test_v2_hostname_claims.py),
[`tests/test_v2_provider_aliases.py`](../../tests/test_v2_provider_aliases.py),
[`tests/test_v2_generations.py`](../../tests/test_v2_generations.py),
[`tests/test_v2_alias_pool.py`](../../tests/test_v2_alias_pool.py),
[`tests/test_v2_login_proof.py`](../../tests/test_v2_login_proof.py),
[`tests/test_v2_workload_access.py`](../../tests/test_v2_workload_access.py)
and [`tests/test_v2_identity_plan_in_mirror.py`](../../tests/test_v2_identity_plan_in_mirror.py).
`just test` is the acceptance bar.

## When it fails

### Failures that have happened

Newest first. Each names the date, what the operator saw, what it meant,
and what changed; the tests named pin the fix. Older findings are in
[docs/history/LEDGER.md](../../docs/history/LEDGER.md), frozen.

- **2026-09-23, the runner's state backup pulled nothing and let the
  removal run** (stage 61 item 3). The first version of `backup` in
  [`commands/state_migration.py`](src/cs_image_system/base/commands/state_migration.py)
  was invoked with the configuration root as its directory, pulled an
  empty state, said "nothing to keep" and let `state rm` proceed unbacked.
  Now a directory that is not an initialised root, a pull that fails, or a
  location holding no state each exit 1 with `state backup for workspace
  '<ws>' REFUSED ...` and stop the runner before anything leaves state.
  The backup lands in `_private/state-backups/<ws>.backup-<run>.tfstate`;
  the log line names the serial and the resource count (`serial 36` on
  2026-09-23 10:46). Pinned by `test_the_backup_keeps_the_pulled_state_under_the_private_root_and_refuses_everything_else`.
- **2026-09-23 10:15, a runner step acted in the wrong directory.** The
  CLI's callback loads the configuration, which changes directory to the
  root AND replaces the context object, so `state-migration begin` and
  `finish` and the prune step ran from the configuration root instead of
  the initialised root the runner entered. The steps now use the recorded
  invocation directory. Symptom: a `begin` or `backup` reporting no state
  where `tofu state pull` in the mirror shows one. Pinned by
  `test_the_migration_commands_run_from_the_directory_the_runner_entered`.
- **2026-09-23, the identity read-model is no witness of state** (same
  item). The read-model is written at generation and outlives a failed
  runner, so it cannot say what is in state; the prune step lists the
  state the root is bound to instead. Also learnt: a pipe to `tail` masks
  the bar's exit code.
- **2026-09-22 (and 2026-09-20), `require_released_builds` switched off
  by hand for the middle of a release** (stage 61 item 4). A durable
  instance whose volume allows one attachment can only prove a new build
  on itself, after `upgrade instance` pinned it to that build, which the
  validator refused: `instance '<name>' is pinned to build <id> of
  '<image>', which is not a released build`. The release grace now admits
  the series head while its own proof is under way and refuses naming
  what is missing (`no grace: <reason>`). Proved 2026-09-23 12:58 to 13:11
  as the coops model's third release with the flag never touched. Pinned
  by `test_the_series_head_under_its_own_proof_is_allowed_and_refused_when_the_proof_fails`.
- **2026-09-22, a stale attachment in state blocked the identity plan**
  (stage 61 item 3, filed by stage 56). A membership dropped from the
  declaration that OPA no longer held made the provider ERROR on refresh
  (`user "x" is not present within group "g"`) instead of planning the
  destroy. Every identity runner now carries a `prune-attachments` step
  between its `init` and its plan (a silent OPA removes nothing), and the
  group root's generation-time plan is a preview with `-refresh=false`.
  Three live attempts; proved 2026-09-23 10:46, restored through the gate
  at 11:00.
- **2026-09-22, the release and retention lifecycles wrote an instance
  root's `instances.auto.tfvars` under their own directories** (stage 61
  item 5): the instance builder's finalize hook acted for every lifecycle.
  It now acts for instance-image alone. Symptom: a stray tfvars file
  under `generated/release/` or `generated/retention/`, which the scanner
  refuses by name at commit. Pinned by
  `test_release_and_retention_never_write_an_instance_roots_tfvars`.
- **2026-09-22, the first live replacement wrote no alias.** The alias
  pass ran before the new machine had answered and enrolled, and wrote
  nothing (`provider_aliases.register_provider_aliases`). It now waits
  for a machine launched in the same run to be reachable
  (`REACHABLE_WAIT_SECONDS`, 300) and then for its registration
  (`REGISTRATION_WAIT_SECONDS`, 300), and gives up loudly: `not reachable
  within 300s of its launch; no alias this run` or `not enrolled within
  300s`. The next applies-on run gives the names back.
- **2026-09-22, the strict state query refused the run that finished an
  upgrade.** After `upgrade instance` moved the pin, the booted image
  behind the pin was `changed` drift and `cloud-launch`'s preflight
  refused the very launch that would finish the replacement. A pending
  replacement is now a `note:` (`booted image <x> is behind its pin <y>;
  the replacement is PENDING`).
- **2026-09-22, the gate refused the volume attachment alone.** A
  replaced instance's volume attachments bind to the instance id, so the
  replace plan destroyed them too and the gate refused the attachment as
  an unwhitelisted destroy. The attachments are whitelisted with the
  replace (the instance plugin's whitelist; the gate's rule is in
  [`commands/gate.py`](src/cs_image_system/base/commands/gate.py)).
- **2026-09-22, a replaced machine's registration claimed the new
  machine's alias.** Found in review before the first live replacement:
  the old machine's OPA registration under `<name>-001` would have
  outlived it and claimed the bare alias. `mark_launched` now retires the
  registration of the hostname the previous generation booted with when
  the new one differs.
- **2026-09-22, `sft resolve --quiet` exit 126 with no output.** The
  client wanted a browser and `--quiet` forbade it: by hand, an expired
  client session; as the workload, no token. The login proof now says
  so in the `resolves` check (`the client has no session ...`).
- **2026-09-22, the identity plan ran on ciphertext.** The first real
  identity run after stage 51: the generation-time plan ran in
  `generated/`, where a derived address's domain is `ENC[age:...]`, so
  every Okta user lookup failed with "no users found". The generation-time
  plan now runs in the private mirror too; a dry run plans nothing at
  generation time. Pinned by
  [`tests/test_v2_identity_plan_in_mirror.py`](../../tests/test_v2_identity_plan_in_mirror.py).
- **2026-09-22, the first live CI-policy reconcile was refused by hard
  drift.** An absent CI login policy read as `missing [HARD]`, and the
  validator refuses a run on hard drift, so the identity apply that
  would CREATE the policy could not run. Workload drift is never hard now
  (`workload_drift`); it stays drift for the strict query and the login
  proof.
- **2026-09-21, a lapsed OPA key read as five missing groups** (stage 61
  item 1, found while landing stage 57). Under an unsourced `.envrc` the
  provider answered `HTTP 401` and every managed group became `missing
  ... [HARD]`, which refused every run. A group the provider could not
  be ASKED about is now an `unavailable:` line naming the group and the
  error (`group_drift`); only an answered absence (a 404) is hard. Pinned
  by `test_a_group_the_provider_could_not_be_asked_about_is_unavailable_not_missing`.
- **2026-09-21, three `coops-model` registrations in OPA, one live**
  (stages 55 and 60). Every relaunch of one declaration enrolled another
  server under the same name and nothing retired the old one; `sft ssh`
  could not choose. Now a decommission retires the registration with the
  pin and the launch parameters (a failure is `its OPA registration as
  '<host>' was NOT retired ... a stale server will answer to that name
  until it is deregistered by hand`), `validate_claimed_hostnames` refuses
  a claimed name before a run that can launch, a new machine is named
  `<declared>-NNN`, and generations are observed through the provider's
  instance id. To deregister by hand, servers live under the resource
  group path (`DELETE` answers 204); the team-level path answers `401
  Missing capability`.
- **2026-09-21, an invalid hostname failed silently at boot.** The launch
  script's `hostnamectl set-hostname '<name>' || true` swallowed an
  invalid name; the machine kept the hyperscaler's `ip-10-26-34-156`,
  enrolled under it, and `sft ssh <declared>` found nothing while every
  step reported success. `check_canonical_hostnames` refuses at validate
  what the boot swallowed, and the state report notes a machine
  `registered in OPA as '<x>' but its generation booted as '<y>'`.
- **2026-09-21, the sso-session profile's `expiresAt` was the access
  token, not the window.** Read against a 30-minute run it refused a
  full-test on its last leg while the CLI would have refreshed the token;
  for an hour the readiness check read the refreshable token as ABSENT
  and skipped the live legs while `full-test` "passed". `aws_sso_expiry`
  now reports a profile with a `refreshToken` as `present; refreshes
  itself ... (no fixed expiry readable)`, and readiness counts it present.
  A session that lapses mid-run is environmental; the repair is `aws sso
  login --profile <p>` then `just full-test-legs`.
- **2026-09-21, a stopped machine was reported as "the provider could not
  answer"** (stage 57). The boot-image probe filters on `running`, so the
  operator's own stopped `coops-model` was indistinguishable from an
  unreachable cloud, and a stopped ephemeral was invisible while its
  disks billed. `power_state` separates `None` from `STOPPED`; the report
  says `note: instances/<name>: STOPPED (switched off; not drift) ...`,
  and a stopped ephemeral shows as standing. Confirmed live: a plan over
  the stopped machine reported no changes and left it stopped.
- **2026-09-20, the run's commit failed while the instance it launched
  was running** (stage 54.1). Stage 49 excluded the private mirror by an
  `:(exclude)` pathspec and stage 54 named it in the root's `.gitignore`;
  together `git add -A` exited 1 saying the path is ignored, so stage 19's
  launch succeeded and its commit did not. The pathspec is gone; the
  `.gitignore`, `refused_path` and the scanner's skip keep the mirror out.
  The regression test runs a real `git add`.
- **2026-09-20, a pin outlived its instance** (stage 54). `coops-model`
  was destroyed through the gate and `pins.yaml` kept binding it, with its
  launch parameters; with `require_released_builds` on, `validate`
  refused every run, including the one that would release the build, so
  the declaration had to be commented out. The forgetting mechanism was
  found to work and a test now proves it; the live cause stays
  unexplained; `forget instance <name>` (the system CLI) drops a record
  that outlived its instance and refuses while the instance is declared.
- **2026-09-20, an in-bake assertion could not fail a build** (stage 53).
  A package assertion was written `a || { b && c; }`, POSIX suppresses
  errexit inside an AND-OR list, and stage 19's first image baked green
  twice asserting `rpm -q vim` on AlmaLinux 10, which has no such
  package; the instance launched from it then failed the same check.
  Package checks now test and `exit 1` for themselves naming the package
  on stderr; the storage and runtime PREREQUISITE checks shared the shape
  (an image missing its mount tooling could pass its own verification).
  Pinned by [`tests/test_v2_in_bake_tests_enforce.py`](../../tests/test_v2_in_bake_tests_enforce.py),
  which runs each generated assertion under `sh -e` with a sentinel.
- **2026-09-19, the private mirror stood one level too deep.** Stage 49
  put it at `_private/generated/...`; every relative path in an emission
  counts directories up to the configuration root, so `tofu init` in the
  mirror could not read its module. `mirror_path` replaces the generation
  directory's name with `_private` instead of nesting under it.
- **2026-09-19, a zone change planned to DESTROY a data volume** (stage
  52). Proven against a copy of the live tree: pointing the runtime at a
  subnet in another zone planned `us-east-2a -> us-east-2b # forces
  replacement` on a 100 GiB volume holding data; the gate refused it as an
  unwhitelisted destroy, but at apply time and naming the volume rather
  than the cause. `check_availability_zones` refuses at validate, naming
  every claimant. Live subnets and `mnt_data` declare their zones since.
- **2026-09-18, the stage-49 guard read the emission the run was about to
  replace** (stage 51): run before generation, the first run after a
  value was newly encrypted could never regenerate the tree that made it
  fail. The plaintext scan moved to the commit (and to `validate` by hand
  as `check_no_plaintext_emitted`).
- **2026-09-17, the version checkers had never run** (stage 48): they
  were registered by name while the lookup keyed on the type in the wrong
  table, so no declared version was ever checked; and a foreign key that
  resolved to nothing fell back to the raw id with a warning, which let
  both trees name a non-existent image builder for months. Both are
  refusals now (`check_single_version`, `check_foreign_keys`).
- **2026-09-11, the generated `.gitignore` dropped a restated rule.** The
  first-wins dedupe kept the built-in `!.terraform.lock.hcl` ahead of a
  configuration's own `.*`, so the negation did nothing; the last
  occurrence keeps its place now.
- **2026-09-09, `--apply-runtime gcloud-east1` without `--only-runtime`
  baked two AMIs on AWS** (ledger 68). `--apply-runtime` scoped the
  applies while the bake surface was unfiltered. The CLI now implies
  `--only-runtime`, and a real run whose bake plan would bake outside a
  proper-subset apply scope refuses: `run scope: bake(s) outside the apply
  scope [...]: <series>@<rt> -- pass --allow-unscoped-bakes, or select
  images with --only / --only-runtime`.
- **2026-09-09, the first preflight could not report an expired
  session.** Loading the configuration validates every runtime against
  its cloud and died on the expired session before any preflight could
  say so; `raw_session_infos` reads `cfg/runtime-builders.yml` before the
  load. And **2026-09-08** (ledger 65) a fifteen-minute cycle failed at
  its GCE instance plan because the AWS SSO session lapsed AFTER the
  preflight had passed; hence `expected_run_minutes` and the blocking
  window.
- **2026-09-09, a `verify assert` as the runner's last step failed the
  run after the teardown** (ledger 68, `teardown` policy). The records
  then described an instance that no longer existed; the verdict now
  fails the run from `forget_ephemerals`, after the records are
  consistent with reality.
- **2026-09-08, a follow image baked in the same run as its parent saw
  no move** (ledger 70). The parent's new head is not recorded at plan
  time, so the pin/head comparison saw nothing; `_bake_reason` now reads a
  parent that bakes this run as a move (`parent <build> re-bakes this run
  (parent_policy: follow)`), kept out of the fingerprint on purpose.
- **2026-09-07 to 09, the ephemeral runtime had no moment to release**
  (ledger 71): retention disposed the verified build before the operator
  could release it; hence `release: {model}` on an image and the
  `release --declared` step of the same run.
- **2026-09-05, decommissioning the last GCE instance** (findings 52 and
  53). The runtime's root vanished with its last declaration, so nothing
  planned the destroy and the VM stayed orphaned; and the forget ran at
  generation, so a DRY run erased the record and the gate then had
  nothing to whitelist. The root is still emitted for a recorded instance
  and the forget waits for the real apply.
- **2026-09-03, the apply step executed an unrequested lifecycle's stale
  runner script** (finding 34): `run storage --no-dry-run` ran the
  previous day's base-image script hook-lessly and baked two unrecorded
  AMIs. A script of a lifecycle not generated this run is
  `stale-script-skipped` with a warning.
- **2026-09-02, a recorder claimed reality no apply produced** (finding
  21): the transition recorder wrote `None -> active` on a run whose
  apply flag was off; the state query's hard drift caught it. Every
  reality-claiming after-apply hook is gated on its lifecycle's flag.
- **2026-09-02 onwards, the ledger's shape** (findings 25, 28, 32, 33,
  47 to 50): a `t2.micro` OOM-killed the SSM agent (per-instance
  `machine_type`); `/dev/xvdf` never appears on Nitro instances (the
  by-id fallback in `user_data_template`); an enrollment token deleted
  out of band makes the oktapam provider ERROR on refresh (hard drift
  naming `state rm` as the repair); a failed plan left a stale planfile
  the gate accepted (`planfile_is_stale`); GCE forbids underscores in
  device names and attached `gce_data` while the script mounted
  `google-gce-data` (`_gce_device_name`); the booted image was never
  compared with the pin (`instance_boot_drift`); the first successful
  bake's meta-state commit hit a gitignored tree (skipped with a
  warning); an unmount ran on the instance with no receipt written
  (`write_receipt` on success and failure).

### Failures the code raises

Grouped by where the operator meets them. The message is quoted as the
code writes it (values in angle brackets).

**At load** (stderr, exit 1, nothing generated):

- `Failed to read configuration from <root>/cfg` -- no `cfg/` directory or
  no YAML in it. Check `--root-dir`.
- `Duplicate name '<n>' found in list for key '<k>'` / `Name '<n>' in list
  for key '<k>' contains template markers.` -- two entries with one name
  across the `cfg/` files, or a templated name. Rename; a name is never a
  template.
- `<file>: <path>: this value may not be encrypted -- it is read before the
  configuration loads, with no identity available` /
  `a declaration's 'name' may not be encrypted` / `a mapping KEY may not be
  encrypted` / `an encrypted value is embedded in a longer string; make the
  marker the ENTIRE value` -- a marker where one may not stand. Move the
  secret into a whole value the loader reads.
- `an encrypted value is present but CSIS_CONFIG_IDENTITY is not set` /
  `CSIS_CONFIG_IDENTITY=<v>: not an AGE-SECRET-KEY-1 string, an identity
  file or a directory` / `no *.age-identity files in that directory` /
  `no identity in CSIS_CONFIG_IDENTITY can decrypt this value (<n> tried;
  it was encrypted to other recipients)` -- export the identity (this
  repository's `.envrc` does; a subshell of the tool needs it sourced), or
  `reencrypt` the tree to the current recipients from a holder that can
  open it.
- `No runtime providers configured.` / `No runtime builders found in
  config file.` -- no `runtime_builders:` entry, or no runtime plugin
  installed.
- `No default builder found in <classification> list.` / `Multiple default
  builders found: <a> and <b>` -- mark exactly one `is_default: true` per
  builder class.
- `Duplicate builder name found: <n>` / `Builder with default name found`
  -- rename; `default`, `self` and empty are reserved.
- `Type Collision` (`ValueError` from the registry) -- two installed
  plugins register one canonical name; a packaging problem, not a
  configuration one.
- `KeyError: <type>` while structuring -- the `type:` names no registered
  model: the plugin is not installed or the name is misspelt (aliases are
  canonicalised first).
- pydantic `Extra inputs are not permitted` naming the key -- a key the
  model does not have; every model forbids extras.
- `... declares 'parameters'; ... use 'variables:'` -- the retired key on
  a builder.
- `Instance '<n>' declares 'groups'; V2 removed per-instance groups ...
  Set 'group:' on the image instead.`
- `Image <n> must have at least one runtime specified in the 'runtimes'
  field` / `Image <n> must have either 'os' or 'source_image' specified`.
- `OS builder <n> must have at least one runtime configuration.` /
  `Duplicate runtime configuration name <ib> in OS builder <n>`.
- `Runtime builder <n> must have a default machine type specified.` /
  `RuntimeNetworkingModel must have a network specified.` /
  `... has no subnets defined.` / `No default subnet defined for network
  <net>.`
- `Storage '<n>' uses the retired 'ALL' group value; declare the specific
  allowed groups, or 'public_read: true'` / `has unknown state <s>` /
  `has share_mode <m>; expected one of ('2770', '2775')` / `must have a
  runtime specified` / `must have a type specified`.
- `StorageMapping '<n>' must have a mount_point specified.` / `must have a
  positive min_size specified. Got: <n>`; and the warning `has aliases
  defined ... Ignoring aliases`.
- `Group <n> has gid <g>; gid must be an integer of at least 1024, a string
  representing one, or 'default'/0/None to defer it.`
- `User <n> requires a non-blank first_name (got <v>); names are never
  derived from the user name.` / `Aliases are not allowed for User items.`
- `Expected exactly one root group (is_root: true), found <n>` / `Group <g>
  has member <u> which is not in the list of defined users`.
- `<kind> builder '<type>' specified for '<name>' not configured` / `<kind>
  item '<name>' has no builder type and no default is registered for
  <classification>` -- an item's `type` names no builder.
- `Executable name cannot be a default placeholder: <n>` / `Duplicate
  executable name found: <n>`.
- `Overlay <path> does not exist` / `must be a mapping at the top level` /
  `unknown top-level key(s) <keys>; allowed: [...]` / `'config' must be a
  mapping` / `'<key>' must be a list of named entries`; `--undeclare
  <spec>: expected <kind>:<name>` / `unknown kind <k>; allowed: [...]`; and
  the warning `Overlay <file>: <kind> '<name>' is not declared; nothing to
  undeclare`.
- `Meta-state file <path> must hold a mapping at the top level` -- a
  hand-edited meta-state file.

**At `validate` and at the head of a run** (each line `validation: ...`
in a run; `validate` exits 1, `run` exits 1 with the errors in the
summary):

- `<exe>: binary '<b>' not found (declared in cfg/executables.yml; an
  absolute path, or a name on PATH)` / `<exe>: could not read its version
  (...)` / `<exe>: <Checker> could not parse a version from ...` / `<exe>
  <v> does not meet its requirement <spec> (cfg/executables.yml)` /
  `Executable <e> specified for provider <p> not found in executables
  list.` -- install or repoint the tool; a CI failure naming a version
  means the floor moved.
- `<Class> '<obj>': field '<f>' names '<v>', which is no <target>
  (declared: ...)` -- an unresolved foreign key. Name a declared object.
- `state location collision: ...` / `workspace '<ws>' names state backend
  '<b>', which is not declared` / `workspace '<ws>' would move its state
  from <old> to <new> while <what> stand(s) in it ... --migrate-state
  <ws> ...` -- see [Where state lives](../../docs/OPERATIONS.md) in
  OPERATIONS; never rebind past the refusal.
- `storage '<s>' declares availability zone '<z>' but runtime '<rt>' ... is
  in '<z2>'` / `instance '<i>' cannot be in more than one availability
  zone: <zone> (<claimants>); ...` -- a zone is replace-forcing; fix the
  declaration, never the plan.
- `alias pool aliases.txt: line <n>: '<name>' is <n> characters, over the
  63 a hostname label allows` / `contains [...], which a hostname may not`
  / `repeats an earlier free line` / `is a name the configuration already
  gives an instance` -- edit the free line; and the warning `alias pool
  aliases.txt: EMPTY -- a new machine launches without an alias; append
  names to refill`.
- `instance '<i>': canonical hostname '<h>' <problem> (RFC 1123 label, at
  most 63 characters ...)` -- shorten or respell the declared name (the
  suffix `-NNN` counts).
- `image '<i>': parent_policy '<p>' is not one of ('pinned', 'follow')` /
  `retention must be {keep: <non-negative int>}` / `release must be
  {model: <name>}` / `runtime '<rt>': retention_keep must be a non-negative
  int` / `instance '<i>': on_failure '<p>' is not one of ('keep',
  'teardown')` / `teardown_after: duration '<d>' must be <number><m|h|d>` /
  `image_policy '<p>' is not one of ...`.
- `<where>: unknown tests keys [...] (known: [...])` / `every tests.files
  entry needs a path` / `every tests.commands entry needs run` /
  `tests.post_bake must be a map` / `every mounts entry is an absolute mount
  point`.
- `base image '<n>': update: must be a mapping or a policy name` / the
  update-policy messages (`packages` needs packages or pins; a package
  both updated and excluded; `update.refresh_days must be a positive
  number of days`).
- `identity: group '<g>' was managed by the system but is missing from the
  YAML; groups never leave the configuration (keep the entry with
  'unmanaged: true' ...)`.
- `storage '<s>' allows unknown group '<g>'` / `instance '<i>' attaches
  group-gated storage '<s>' but its image '<img>' has no owning group` /
  `instance '<i>' (image '<img>', group '<g>') may not attach storage '<s>':
  allowed groups are [...] (N2)` / `storage '<s>' (<type>) is single-attach
  but instances [...] all attach it (N16); multi-host storage builders on
  <rt>: [...]` / `storage: storage '<s>' has never been applied; a new
  storage must start 'active', not '<req>'` / `transition <a> -> <b> is not
  legal` / `cannot move <a> -> <b> while attached by [...] (detach in one
  run, transition in the next; N21)` / `requests archived, which its
  builder does not realize` / `is recorded <state> but no longer declared,
  and its record names no storage builder: re-declare it (or record it
  with 'state import')` / `instances [...] attach unknown storage '<s>'` /
  `attach storage '<s>' which is <state>` / `is <state> but instances
  attach it`.
- `image '<i>' names unknown owning group '<g>'` / `instance '<i>' uses
  image '<img>' which has no owning group; every instance image belongs to
  exactly one group (Q4)`.
- `base image '<b>' declares identity type '<t>' but no identity plugin of
  that type is configured (known: [...])` / `declares storage type ...` /
  `admin public key rejected: <reason>` (`PRIVATE key material (never
  allowed; the config repo is public)`, `not an OpenSSH public key line`,
  `multi-line value`, `empty key`) / `admin_user may not be empty` / `has
  NO debug path: no admin public key (config.admin_public_keys /
  admin_public_keys) and no session mechanism on the runtime (N9 dead
  end)`.
- `image '<i>' does not chain to a base image (source_image=...)` /
  `group '<g>' has no identity builder` / `uses an identity type its base
  '<b>' does not declare (declared: [...], via pin:<build> | declaration);
  the cycle is broken` / `attaches storage '<s>' of type '<t>' which base
  '<b>' does not declare ...` -- declare the type on the OS builder and
  re-bake the chain; a pinned root build's stamp governs until then.
- `instance '<i>' was launched (run <r>) and its launch parameters changed
  (<keys>); launch parameters are immutable after launch -- replace the
  instance (upgrade instance, or decommission and redeclare) (N26)`.
- `instance '<i>': could not check whether canonical hostname '<h>' is
  already claimed (group '<g>''s server registry did not answer); refusing
  to launch on silence` / `canonical hostname '<h>' is already registered
  to <n> server(s) in group '<g>' (...); launching would enroll a second
  machine under the same name. Retire the stale registration first` /
  `is registered to <n> servers ... and only one of them is this machine;
  sft ssh cannot choose. Deregister the others`.
- `instance '<i>' is pinned to build <b> of '<img>', which is not a released
  build (config.require_released_builds; no grace: <why>)` -- release it,
  `upgrade instance` back, or `forget instance` for a record that outlived
  its instance.
- `state: <class> <kind> <name>: <detail> (from state-report.json; re-run
  'state query' after fixing)` -- hard drift from the last report.
- `--only names unknown image(s): ...; known: ...` (the summary's `error`,
  before validation) and `run scope: bake(s) outside the apply scope
  [...]` (after the bake plan, a real run only).
- `--migrate-state moves state and needs --no-dry-run: a dry run never
  moves state`.

**During generation and apply** (`run-summary.json` records the
lifecycle `failed` or the apply `failed`; exit 1):

- `Resolution failed for lifecycle <lc>` / `Image Builder for OS <n> not
  found in predefined_resolve` / `Runtime Builder for OS <n> not found` /
  `No resolved Image identifiers for OS <n> in predefined_resolve` -- the
  vendor query answered nothing (the runtime plugin's filters, owners or
  credentials).
- `[<lc>] before-phase hooks failed for <phase>` / `generation failed for
  <phase>` / `after-phase hooks failed for <phase>` / `Command failed
  before|after phase <phase>: <name> (Return code: <rc>)` -- a builder's
  run-now command (`fmt`, `init`, `validate`) failed; the command's stdout
  and stderr are logged as warnings beside it.
- `Extending finalization phase after PRE_VERIFY not allowed` -- a plugin
  deferring a command to a phase past `pre-verify`.
- `[<lc>/<phase>] command failed: <e>` / `command returned <rc>` -- a
  deferred command (packer, tofu, a system-CLI step) failed in the mirror.
  Read the command line logged just before it (`executing ...`), rerun it
  in `_private/<lc>/<root>/<phase>/` to see the tool's own message.
- `Apply failed for lifecycle <lc>` follows, and later lifecycles are not
  attempted (`not-attempted`).
- `Refusing meta-state/<file>: material that must not be public -- <path>:
  <rule>: <excerpt> ... (public-safe by construction; allow a value by
  decision in cfg/_config.yml public_safe.allow)` -- a meta-state or
  state-report write that a hard rule matched. Nothing was written. Find
  the value (the rule names its shape), declare it encrypted or allow it
  by decision.
- `dispose: build '<b>' is not recorded in lineage; an unrecorded image is
  adopted with 'state import' or left to the orphan sweep, never deleted
  blind` / `instance(s) [...] are pinned to / launched from the build(s)
  [...]; decommission them first` / `unknown runtime` / `--all needs
  --runtime <name>`; and the warnings `retention debt: <b> (<series>@<rt>)
  would be disposed but an instance is pinned to it or was launched from
  it` / `... it is a RELEASED build (kept by decision; dispose it
  explicitly)`.
- `build '<b>' is not recorded in lineage; only baked builds can be
  released` / `belongs to series '<s>', not '<img>'` / `carries no in-bake
  verification record; rebuild it with the verify provisioner` /
  `modification '<m>' of build '<b>' has no local mod-test result
  (config.require_mod_tests)` / `failed its local mod test (status=...,
  idempotent=...)` / `has no post-bake test record while '<img>' declares
  tests.post_bake -- launch it (ephemeral) and verify first` / `failed its
  post-bake tests in run <r>: ...` -- `release` refused; exit 1.
- `upgrade: instance '<n>' is not defined in the configuration` / `image
  '<n>' is baked on runtimes [...]; pass --runtime` / `no build of series
  '<s>' is recorded in lineage; build it first or pass --to <build id>` /
  `build '<b>' is not recorded in lineage` / `belongs to series ...` /
  `<kind> '<n>' is already pinned to <b>` / `was baked on runtime '<a>',
  not '<b>'`.
- `verify: instance '<n>' is not declared` / `names runtime '<rt>', which is
  not configured` / `instance <n> failed verification: <check>: <detail>;
  ...` (the runner stops; an ephemeral is left standing under `keep`) /
  `verify <n>: SKIPPED -- the machine is STOPPED (switched off; not drift)
  and verification needs it running. Nothing is recorded` (not a failure;
  start the machine or accept the skip).
- `<n> is STOPPED ...; STARTING it because verifying instance <n>. It will
  be stopped again when that is done.` then `<n>: work finished (...);
  stopping it again` -- informational; and the one case that leaves work:
  `<n>: FAILED to stop it again after <why>: <e>. It was switched off
  before this run and is now RUNNING -- stop it by hand.`
- `unmount: instance '<n>' is not declared` / `unmount of <mp> on <n>
  failed (exit <rc>): <tail>` -- a receipt with `ok: false` was written;
  the gate's `--require-unmounted` then refuses the detach.
- `login proof FAILED for <names>: <check>: <detail>` -- exit 1 unless
  `--record-only`; the record in `login-proofs.yaml` says which check:
  `one registration` (`has <n> registrations` or `the machine never
  enrolled`, or `the group's server registry could not be asked (silence
  is not one server)`), `resolves` (`sft resolve <h>: exit <rc> -- ...`),
  `login` (`sft ssh <h> --command id: exit <rc> -- ...`). A skip
  (`SKIPPED -- the machine is STOPPED ...` or `group <g> names no workload
  connection and role`) proves nothing and fails nothing.
- `state-migration begin: --backend-config ... is required` / `meta-state
  records no location for workspace '<ws>'; there is nothing to migrate
  from` / `the new location <loc> already holds state (lineage <l>) that is
  not this workspace's: a collision, refused. The old state is untouched.`
  / `init against <file> failed: ...` / `state-migration finish: no
  <ws>.state-migration.json -- 'begin' did not run`.
- `state backup for workspace '<ws>' REFUSED: <dir> is not an initialised
  terraform root; nothing is removed from state` / `FAILED; nothing is
  removed from state: <e>` / `REFUSED: the location holds no state, yet a
  state rm is due` -- the runner stops before its `state rm`; initialise
  the root against its location and rerun.
- `identity attributes: the provider reports conflicts; refusing: [...]` /
  `writing identity attributes is disabled (DESIGN Q7 not confirmed);
  <n> change(s) were NOT applied` (exit 4).
- `Instance <n>: its OPA registration as '<h>' was NOT retired (<e>); a
  stale server will answer to that name until it is deregistered by hand`
  (ERROR, the forget still happens) / `Group <g>: its CI login policy was
  NOT reconciled (<e>); the CI login proof for this group fails until it
  is` (ERROR, never fatal) / `Instance <n>: alias '<a>' SKIPPED -- already
  claimed by <id> (OPA would resolve it to that record, or refuse as
  ambiguous)` / `group '<g>''s server registry could not be asked; skipping
  alias [...] -- silence is not a free name` / `could not write its aliases
  [...]: <e>` / `alias write failed (<rc>): <tail>`.
- `Instance <n>: the machine bearing this name is <id2>, not <id1> --
  generation <kind> <k> closed as replaced out of band, <kind> <k+1>
  opened. Nothing in this system did that.` -- a WARNING: a taint, a
  console terminate and re-apply, or a replacement outside the system.
  The records now match reality; find out who did it.
- `instance '<n>' already has an open generation (...); close it first` --
  `open_generation` over an open one; not reachable from configuration,
  only from a hand-edited `instance-state.yaml`.
- `Config root <root> is not inside a git repository; meta-state commit
  skipped` / `Meta-state commit: <path> is gitignored here; not committing
  it` (warnings) / `Meta-state commit: never staging <files> (plans, state
  and key material carry decrypted values)` / `Refusing the run's
  meta-state commit: material that must not be public -- ...` -- the
  commit is refused whole; the run's generated tree is intact. Encrypt
  the value, or allow it by decision, and commit again.
- `Could not write run summary: <e>` -- the summary or journal could not
  be written; the original failure is still the one reported.
- `on-summary hook <name> failed: <e>` -- a notifier failed; the run's
  outcome is unchanged.

**Where to look, in general.** The run's log names the lifecycle and
phase of every failure; `generated/run-summary.json` carries `ok`,
`error`, `validation_errors`, each lifecycle's `status` and `error`, and
each lifecycle's `apply` status (`executed`, `dry-run`, `no-script`,
`stale-script-skipped`, `failed`, `not-attempted`); `meta-state/runs.yaml`
keeps the same per run for the last 200 runs; `generated/state-report.json`
holds the last reality check; a tool's own output is under
`_private/<lifecycle>/<root>/<phase>/` where it ran. A failure caused by
an expired session, an unreachable provider or a missing binary is
environmental and says so by name; a failure naming a declaration is a
configuration to fix; a failure naming a record (`pins.yaml`,
`launch-params.yaml`, `instance-state.yaml`) is repaired through the
operations named in the message (`upgrade`, `forget instance`, `state
import`, `--migrate-state`), never by editing the record.
