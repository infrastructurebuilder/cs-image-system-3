# cs-image-system-base

The kit of cs-image-system: the first library of the SDK a plugin is
written against, beside the plugin contract
([contract](../contract/README.md)). It declares what a plugin may use
of it (its `surface` module) and keeps a version of its own, whose
middle number rises only when something on that surface is removed or
altered ([WRITING_A_PROVIDER.md](../../docs/WRITING_A_PROVIDER.md)). It implements the
contract with its base models (`models/`) and builder bases (`basic/`),
and holds what those import: the registry, the run context, the
lifecycles and phases, value encryption, lineage, generations, launch
parameters, capabilities, the power states and the meta-state record
types. A plugin imports what this package's `surface` module declares
and nothing else of it; the check is this package's own
(`python -m cs_image_system.base.surface check <source directory>`), and
`tests/test_plugins_keep_to_the_surface.py` runs it over every plugin of
the workspace.

The engine is the other half of the core, a package of its own
([engine](../engine/README.md)): the plugin loader, the configuration
reader, the resolver, the lifecycle runner and its commands, meta-state
on disk, the state query, releases, retention and the bootstrap. The
direction is one way, contract <- kit <- engine: no module here imports
the engine, by any edge (`tests/test_contract.py`,
`tests/test_import_closure.py`).

This README describes the kit: the plugin contract as the kit
implements it, the configuration tree and the models it structures
into, the lifecycles and phases, the run context, encryption, lineage,
launch parameters and capabilities. What a run does with them -- [how
YAML becomes models](../engine/README.md#how-yaml-becomes-models), [a
run](../engine/README.md#a-run-generation-finalization-dry-run-commit)
from its first check to its commit,
[meta-state](../engine/README.md#meta-state), [the public-safe
gate](../engine/README.md#the-public-safe-gate),
[releases](../engine/README.md#releases),
[retention](../engine/README.md#retention), [the terraform
modules](../engine/README.md#the-terraform-modules), and every check a
run makes and every failure it reports -- is described in [the
engine's README](../engine/README.md). A source link names the package
its module lives in: a link into `../engine/` is the engine's.

It contains no cloud code. Clouds, identity providers, packer and terraform
live in plugins that register through the contract. The package is
licensed under Apache-2.0 and requires Python 3.13 or later.

Declared dependencies ([`pyproject.toml`](pyproject.toml)):
`cs-image-system-contract` (the one sibling it depends on; the contract
depends on no sibling), `PyYAML`, `age`, `packaging`, `pydantic` and
`typer`. The models are pydantic dataclasses; `packaging` parses
version specifiers; `age` is the library behind every `ENC[age:...]`
value.

The package declares two entry points. The plugin entry point
`cs_image_system.plugins.base` (`cs_image_system.engine.init:initialize`)
injects the `StorageMapping` item model as the default
`STORAGE_MAPPING_ITEM_MODEL` and registers `GenericVersionChecker`, the
version checker every executable of the default type `executable` falls
back to; its function is the engine's, since only the engine's loader
calls it, and the declaration stays here so that the registrations carry
the namespace `base`. The modules entry point `cs_image_system.modules`
(`cs_image_system.base:tfmodules`) names the terraform modules this
package ships as package data ([The terraform
modules](../engine/README.md#the-terraform-modules)).

## Contents

- [The plugin contract](#the-plugin-contract)
- [The configuration tree](#the-configuration-tree)
- [The base models](#the-base-models)
- [`cfg/_config.yml` key by key](#cfg_configyml-key-by-key)
- [Lifecycles and phases](#lifecycles-and-phases)
- [The run context](#the-run-context)
- [Encryption](#encryption)
- [Lineage](#lineage)
- [Launch parameters](#launch-parameters)
- [Capabilities](#capabilities)
- [Other modules](#other-modules)
- [Tests](#tests)
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)

## The plugin contract

The contract itself is the [contract](../contract/README.md) package:
the protocols a model and a builder satisfy, the constants and field
helpers, the lifecycle phases, the data carriers a hook returns. This
package implements it -- the base models and builder bases below carry a
default for every hook -- and reads it: the registry is here, and the
engine's loader fills it. Source:
[`registry.py`](src/cs_image_system/base/registry.py),
[`basic/abstract_plugin_metadata.py`](src/cs_image_system/base/basic/abstract_plugin_metadata.py),
[`models/mixins.py`](src/cs_image_system/base/models/mixins.py) (the
bodies of the contract's three marker protocols), the base models and
builder bases, and the engine's
[`loader.py`](../engine/src/cs_image_system/engine/loader.py). The
constants, the model configuration, the field helpers and kinds, the
lifecycle phases and data, the assets, the command lists, the name and
HCL helpers and the provider-specific image's enums are the
contract's ([contract](../contract/README.md)), and every module here
imports them from it; the core has no path of its own for them. The
vocabulary the engine reads (the tag words in `lineage.py`, the enrollment
variable in `launch_params.py`, the power states in `power_state.py`,
`EncryptedStr` in `encryption.py`, the bootstrap's question model in
`bootstrap/questions.py`, the id claim in `posix_ids.py`) is the
contract's too, imported into those modules so a reader of the engine
keeps its path.

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

The group names the kind the plugin is, and `_discovered_plugins` holds it
to that (`check_group`, `GROUP_CLASSIFICATIONS`): a plugin found under a
group other than `base` or `other` must register at least one class of
that group's classification (`runtime`: a cloud or container builder
model or a runtime builder; `state`: a state backend; `storage`, `group`,
`user`, `image`, `os`, `instance`, `modification`: the builder or its
model), else it is refused with a `PluginGroupError` naming the group it
chose, what it registers and the group that fits; a refused plugin is
skipped, with one error line, and the others load. A plugin may register
more than its group's kind (the terraform root plugins declare `instance`
and register their storage roots; the identity plugins declare `group` and
register their user builders); `other` is for a plugin that registers none
of the named kinds (a checker, an injected model).

Each entry point loads to a callable. `load_plugins(reg)` calls it and expects
one object satisfying the contract's `PluginMetadataProtocol`, or a list of
them (the check is `isinstance`, name-only; anything else is logged as an
error and skipped). An entry point whose module fails to import, or whose
callable raises, is skipped the same way: one error line names the plugin
and the error, the other plugins load, and every command keeps working
without it (a tree whose `type:` names that plugin's model fails at load
as any missing plugin does). The entry point's distribution gives the plugin its
namespace (`namespace_of_distribution`: `cs-image-system-aws-runtime-plugin`
is `aws-runtime`), unless the metadata names one. The load log gives one
info line with how many classes registered under how many namespaces, and
at debug level what registered under each. Entry points within a group
load in name order. Loading
is idempotent per registry: a second `load_plugins(reg)` on a registry
that already holds the plugins returns at once (until `reg.reset()`).
`load_plugins` takes the registry to load into; there is no default one.
The loader of a run passes the run's; code that needs the installed
classes before, or without, a load calls `installed_registry()`, which
returns a new registry with the plugins loaded and nothing else.

A plugin that has commands of its own registers one entry point in the
group `cs_image_system.commands`: a callable returning a list of the
contract's `CommandMount` records (`contract/commands.py`), each a
sub-app under the root or a command under an existing sub-app by path,
which the system package's console script mounts when it starts
([docs/PLUGINS.md](../../docs/PLUGINS.md#what-a-plugin-adds-to-the-command-line)).

A separate group, `cs_image_system.plugins.hooks`, carries run hooks
(see [Other extension seams](#other-extension-seams)); it and the
`cs_image_system.bootstrap` group are not part of the contract yet, so a
plugin that contributes to them depends on this package. A bootstrap
section (`bootstrap.Section`) declares, besides its questions and its
render, the repository secrets its part of CI reads (`secrets`) and the
Actions variables it reads, each valued by one of the section's answers
(`variables`); the GitHub section's script and module set the unions, so
the core names only its own.

### Plugin metadata

`PluginMetadataProtocol` (the contract's `core`) has these members. The
contract's `metadata.PluginMetadata` is the data record that satisfies
it; `AbstractPluginMetadata` here is the class-based convenience that
does the same from constructor arguments in this order (the plugin's
`version` last, as a keyword).

| Member                        | Type                                  | Meaning |
| ------------------------------- | --------------------------------------- | --------- |
| `plugin_metadata_version`     | `str`                                 | Version of the metadata shape. |
| `requires_python`             | `SpecifierSet`                        | Python requirement; a bare version (`"3.13"`) reads as its floor. Declared, not enforced. |
| `services`                    | `dict[str, list[type]]`               | Classes to register, grouped under a service name. Every class implements `PluginArtifactProtocol`. |
| `builders_for_models`         | `dict[type, type]`                    | Model class to builder class. One builder per model. |
| `injected_models`             | `dict[VCT, type]`                     | Item models the plugin injects under a classification. |
| `is_injected_models_default`  | `bool`                                | Whether injected models become the default for their classification. |
| `version`                     | `str`                                 | The plugin's own version: the one given, else the version of the distribution that ships the metadata class, else `0`. |
| `namespace`                   | `str | None`                          | The namespace the registry qualifies the plugin's registrations with (`<namespace>/<name>`). `None` leaves it to the loader, which derives it from the distribution's name (`cs-image-system-` and `-plugin` dropped: `aws-runtime`, `tf-ebs-instance`, `base`); a plugin with no distribution must name one. |

`PluginArtifactProtocol` is two class methods:

| Method            | Returns | Meaning |
| ------------------- | --------- | --------- |
| `csis_name()`     | `str`   | The canonical name. For a builder model this is the value a YAML `type:` names. |
| `csis_classifier()` | `VCT` | The classification the class registers under. |

A typical plugin registers a model class and its builder class under the
same service name and maps the model to the builder in
`builders_for_models`. Every class is keyed by its classification, the
plugin's namespace and its `csis_name` ("The registry" below), so two
plugins may use one word; the registry refuses only a *different* class
under one classification, namespace and name (`Type Collision`).

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

`Registry` is one instance per run, and the process holds none: the
loader makes it, replays the plugins' registrations into it
(`load_plugins(reg)`; discovery itself happens once per process) and the
context carries it as `ctx.reg`. Nothing fetches "the" registry:

- code that holds a context reads `ctx.reg`;
- a builder reads `self._run_context().reg` (before the loader binds it,
  during `finalize()`, `self._model_registry()`: its model's);
- a model holds the registry of the run that structured it: the run's
  converter hands it over as it builds the model (`NameTyped.bind_run`,
  see "Field kinds" below), and a model made in code is bound by its
  maker with `model.bind_run(reg)`. A model bound to no run refuses a
  question that needs the registry, by name;
- the template resolver and the converter are made over the run's
  registry (`ctx.template_resolver`);
- a command that runs before, or without, a load makes a registry of its
  own with `loader.installed_registry()`.

`registry.current_registry()` and `bind_current_registry()`, the fetch
that stood in for the old singleton for one release, are gone; each
caller above says what replaces it. A deep copy of a model keeps its
registry handle rather than cloning the registry. It holds:

The class-level tables (what the plugins registered) are keyed by one
typed key, `RegistrationKey(classification, namespace, name)`, a named
tuple and never a joined string: the classification the class registers
under, the namespace of the plugin that registered it and the class's
canonical name (`csis_name`). The namespace comes from the loader, which
derives it from the plugin's distribution name with the `cs-image-system-`
prefix and the `-plugin` suffix dropped (`aws-runtime`, `tf-ebs-instance`,
`okta-opa`, `contract-example`; the core's own registrations through its
`base` entry point, the generic version checker and the storage mapping,
carry `base`), unless the plugin's metadata names a `namespace` of its
own; a plugin with no distribution and no field is refused at discovery
and skipped.
The reasoning is in [the stage index](../../docs/CHANGES.md#s131).

The instance-level table (what the tree declared: built builders and
items, and their aliases) is keyed the same way, by a typed
`InstanceKey(classification, namespace, ancestry, name)`, one dict per
classification. The namespace is the plugin's that serves the instance:
the namespace its class is registered under (`namespace_of_class`), and
`base` for a class no plugin registers (the core's own item models: an
image, an instance, a group, an image's entries). The ancestry is the
instance's ancestry in the configuration: the global id of the item it
is declared in (its parent reference, `ancestry_of`), and empty for an
item a tree declares at its top level. It is never the builder an item's
`type` names: a group and a user hold a parent reference to that builder,
but they are declared at the top of a tree, so their ancestry is empty
like every top-level item's. So the entries of two
images, both named `pckr-ebs-ans`, are two keys, where a key by bare name
held one entry for both. An instance is entered under its own name and
under each alias (the same key with another name), and a cloud or a
container again in the runtime classification of its kind. The model is
untouched: its `name` is the name the tree wrote, and its `global_id`
stays `<classification>::<model id>::<name>`; the key is the registry's
and is never written out. The joined form, `<namespace>/<name>` for a
top-level instance and `<namespace>/<ancestry>/<name>` for one declared
in another item, appears only in a message and in a word a tree writes.

| Store                     | Keyed by                          | Holds |
| --------------------------- | ----------------------------------- | ------- |
| `models`                  | `RegistrationKey`                 | Model classes a `type:` value can select (`get_model(vct, word)`; `models_under(vct)` lists them by the shortest word that resolves, `registration_keys(vct)` the keys). A *different* class under a key already taken is a `ValueError` ("Type Collision"); the same class under the same key, or under another namespace, is the same registration. |
| `builders`                | model class                       | The builder class for a model. |
| `registry` / `vct_type_registry` / `reverse_registry` | `RegistrationKey` / `VCT` / class | Services by key, the classes per classification (one entry per class, however many plugins carry it), and every key a class is registered under; `get_builder_for_model(type_name, classification)` reads `registry` by the resolution rule below, and `register_service` refuses a different class under a taken key. |
| `instances`               | `VCT`, then `InstanceKey`         | Built objects: builder models, builders, items, each under its own name and each alias. Cloud and container builders are mirrored under the runtime classifications. `get_all_instances_by_classification(vct)` answers each instance once, by the shortest word that names it: a top-level instance's bare name (unique per table), an item declared in another one's qualified form, so no two items collapse into one entry. |
| `instances_by_global_id`  | `global_id`                       | The same objects by `<classification>::<model_id>::<name>`. |
| `aliases` / `classified_aliases` | `VCT`                      | Builder aliases; a duplicate alias within a classification is an error. |
| `defaults_registry`       | `VCT`                             | The name of the default builder per classification. A default may not be a reserved word (`default`, `self`, `none`, empty or `None`). |

**Resolution.** A `type:` word is read against `models` (or `registry`)
under one classification by one rule, wherever the word comes from (a
builder's `type:`, an item's, a version checker looked up by an
executable's name and type). A **qualified** word, `<namespace>/<name>`,
reads its key directly. A **bare** word resolves when exactly one class
answers to it, whatever the namespaces carrying it: the one version
checker the three terraform-root plugins register is three keys and one
class, so `tofu` is not ambiguous. When *different* classes answer to a
bare word the lookup raises `AmbiguousTypeError`, which names every
qualified form (`type 'x' is ambiguous under instance_builder_model: 2
plugins register it; write one of one/x, two/x`), and `validate` prints
it as one configuration error. A word nobody registered is `None`, as
before. What a tree wrote is what is recorded: the converter
canonicalises an alias to the class's `csis_name` but never rewrites a
bare word to its qualified form (the mod fingerprint hashes the type word,
so the golden and every emission are unchanged) nor a qualified one to
the bare word, and the registry answers either.

**Instances.** A word a tree writes for an instance (a foreign key, a
`type:` that names a builder) is read against `instances` under one
classification by the same kind of rule. A **bare** name or alias finds
the top-level instance (ancestry empty) that answers to it, whatever
namespace serves it; an item declared in another one is never found by a
bare word, since its siblings in other parents share its name. No bare
word has two answers: the emission names every instance by its own name
(the generated directories, the provider-specific image's
`<source>::<runtime>`, terraform labels, state keys, tags, the
meta-state records), so registration keeps a top-level name or alias to
one instance per table across every plugin (see **Registration** below),
and the instance-level lookups raise no ambiguity. A **qualified**
word reads its key directly: `<namespace>/<name>`
(`aws-runtime/aws-east2-runtime`) or `<namespace>/<ancestry>/<name>`.
No name, alias or global id carries `/` (the load refuses it in a name
and an alias), so the split is never ambiguous.

A qualified reference works wherever a bare one does because the load
reads it as the bare word once, at the edge: `Registry.word_for(vct,
word)` turns a qualified word that names an instance into the word the
registry lists that instance by (a top-level instance's bare name; an
item declared in another one's qualified form), and leaves every other
word, a bare name and an alias included, as written.
A model is built from the words read bare where the instance is
registered already (`NameTyped`'s before-validator,
`models.references.written_references_bare`: an image entry named after its
image builder takes the builder's name); an item kind's items are read
bare again once the kind is read (an image's `source_image` naming
another image), and a builder model before its builder is made (a
runtime's `state_configuration`). The fields read are the foreign keys
(`FK_TARGET`) and the plain fields that name instances, marked
`metadata={REFERENCE_TARGET: <vct>}` (`models/references.py`; a
tuple for a field that may name
either of two kinds): a storage's `groups`, an image's `group`,
`default_groups` and `source_image`, a group's `members` and `admins`,
the okta group builder's `posix`. Every reader after the load (a
comparison with a name, a key of a listing such as `ctx.runtime_builders`,
a name in the emission) reads what a bare tree would have written, so
a qualified fixture emits exactly what the bare one does. A storage
mapping's `name` is the mapping's own name (the storage an instance
mounts), which may not carry `/`, so it is always bare.

**Registration.** `register_built_instance` checks every key it will
write, and the global id, before it writes any, and refuses
(`InstanceCollisionError`, naming both declarations by the names the
tree wrote and their classes, never a model's repr) a key or a global id
a different instance holds: two declarations under one name (a state
backend declared twice), an alias another item holds. A top-level name
or alias is one instance's per table whatever plugin serves it: another
plugin's instance under a held name (a cloud runtime and a container
runtime of one name, both entered in the runtime classification; two
plugins' groups or users of one name under different builders) or under
a held alias, or an alias equal to another plugin's instance's name, is
refused the same way, because the emission could write out only one of
them; rename one. The qualified form is still accepted as a spelling and
reads as the bare word, but an instance never needs it. The registry is
as it was after a refusal. The same instance again is no collision: it is
entered again as its parent reference is set or refined, and moves to
its key now, leaving every key and id it held before. The one instance
replaced on purpose is the provider-specific image: a runtime builder
makes it again for the same source and runtime, through
`replace_built_instance`, which removes the old image's keys and id and
puts the new one in its place; a key a third instance holds is still
refused there.

`get_instance_by_name_or_alias(vct, "default")` resolves to the registered
default. `reset()` clears an instance; a repeated load makes a new registry
instead, and the test harness unbinds the current one between loads.

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
`_get_context()` returns the run context the loader bound to the builder (`bind(ctx)`).

Per-kind bases add a contract:

| Base class            | Classification     | Notable members |
| ----------------------- | -------------------- | ----------------- |
| `RuntimeBuilderBase`  | `RUNTIME_BUILDER`  | `query_provider_image`, `query_provider_image_by_id(entry, image_id)` (the vendor image an OS builder entry pins by `image_id`, same return shape as `query_provider_image`, `None` when the provider does not know it; the base raises `NotImplementedError`, AWS and GCE implement it), `query_images`, `verify_instance`, `run_session_command`, `inventory`, `dispose_image`, `retag_image`, `packer_source_type`, `packer_source_blocks`, `build_id_from_artifact`, `session_mechanism`, `session_agent_commands`, `session_verify_commands`, `bake_finalize_commands`, `bake_ssh_username(image)`, `default_bake_user(family)` and `one_bake_user_per_chain()` (the last step of the bake-user order and the GCE one-user rule), `label_key_problem(key)` (why a declared tag key cannot become a label on this runtime; the base says nothing, GCE wants a lowercase letter first), `release_commands`, `session_instance_profile`, `provider_specific_image_class`, `create_provider_specific_image_resolved` / `_deferred`; and the gated reality hooks, each behind a `can_*` predicate so an unsupported cloud makes no claim: `can_query_instance_boot_image` / `query_instance_boot_image`, `can_query_instance_power_state` / `query_instance_power_state` (the vocabulary of [`power_state.py`](src/cs_image_system/base/power_state.py); `None` means "cannot answer", never "stopped"), `can_set_instance_power_state` / `start_instance` / `stop_instance`, `can_query_instance_identity` / `query_instance_identity` (`instance_id`, `provider_hostname`). |
| `CloudBuilderBase` / `ContainerBuilderBase` | runtime | Thin subclasses of `RuntimeBuilderBase`. |
| `GroupBuilderBase`    | `GROUP_BUILDER`    | `identity_type()`, `gid_policy()` (`config-time`, `creation-only`, `provider-assigned`), `manages_groups()` (`False` for a lookup-only builder, whose groups the read-model records `managed: false` and which comes after a managing builder of its type), `managed_groups()`, `enrollment_token_reference()`, `base_image_prerequisites()`, `verify_commands()`, `activation_commands()`, `activation_verify_commands()`, `launch_parameters()`, `query_state()`, `validate_attributes()`, `query_attributes()`, `attribute_conflicts()`, `export_gids()`; the server registry: `can_query_servers()`, `registered_servers(group)` (`None` when the provider could not be asked, never an empty list), `retire_servers_named(group, hostname)`; `prune_stale_attachments(tofu, run_id, cwd)` (a runner step, default no-op); and the CI login policy: `can_manage_workload_access()`, `workload_access_expected(group)`, `workload_access_state(group)`, `ensure_workload_access(group)`. |
| `UserBuilderBase`     | `USER_BUILDER`     | `add_user_to_builder()` enforces `email_as_username`; `default_managed()`, `is_managed()`, `validate_user()`, `validate_attributes()`, `query_attributes()`. |
| `StorageBuilderBase`  | `STORAGE_BUILDER`  | `capability_type()`, `attachment_cardinality()` (`single` or `many`), `is_zonal()` (default `False`: a regional storage constrains no availability zone), `is_posix()`, `platform_mounts()`, `base_image_prerequisites()`, `verify_commands()`, `transition_actions()`, `validate_lifecycle()`, `query_state()`, `destroy_whitelist()`, `retag_storage()`; and the launch hooks, because the device and mount lines are the storage's: `launch_mount(storage, mapping, index)` (the storage-specific keys of an instance's mount record, such as a block store's device name; `index` counts the earlier mounts of the same capability type), `launch_script_lines(mount, group)` (the mount's whole block of the launch script, header to subtree), `launch_tasks(mount, group)` (its whole ansible task list) and `launch_variables()` (the template variables its lines read by reference). The shared pieces are static helpers a plugin composes: `mount_header_lines`, `mount_mark_line`, `group_subtree_lines`, `block_device_lines`, `fstab_mount_lines`, `mount_directory_task`, `group_subtree_task`, `block_device_tasks`. The defaults: no extra keys (`platform_mounted` when the platform mounts the storage), the header alone (plus the mark and the subtree when platform-mounted), the directory task alone, no variables. |
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
| Run hooks | entry point group `cs_image_system.plugins.hooks`; `HookSet` in [`commands/run_lifecycles.py`](../engine/src/cs_image_system/engine/commands/run_lifecycles.py) | `validators` (return error strings; any error aborts the run), `after_generate`, `before_apply`, `after_apply` (real runs only), `on_summary`, `state_bindings` (answer `{lifecycle: {workspace: state file}}`, merged into the runner-script headers and the summary's `state_bindings`; the tofu-roots plugin answers for the terraform roots), and `lifecycles` (a list of `LifecycleSpec`). |
| Lifecycles | `register_lifecycle(LifecycleSpec)` in [`lifecycles.py`](src/cs_image_system/base/lifecycles.py) | A lifecycle with its own phases, builder classifications, directory and runner script, positioned after an existing one. |
| Field kinds | `register_field_kind(name, FieldKindHandler)` in the contract's [`field_kinds.py`](../contract/src/cs_image_system/contract/field_kinds.py) | A late-binding behaviour for fields carrying `field_kind` metadata: `contribute_context`, `resolve`, `upgrade`. |
| Resolution passes | `register_resolution_pass(name, fn, order)` in [`helpers/resolution_stages.py`](../engine/src/cs_image_system/engine/helpers/resolution_stages.py) | A string-stage pass over the raw YAML document. Built in: `interpolate` (order 10) and `scope-this` (order 20). |
| Item kinds | `register_item_kind(ItemKind)` in [`config_loader.py`](../engine/src/cs_image_system/engine/config_loader.py) | A new domain-item collection: directory, model class, owning builder classification, attach function, optional validation. |

## The configuration tree

A configuration is a directory (the `--root-dir`). The engine's loader
([`config_loader.py`](../engine/src/cs_image_system/engine/config_loader.py))
reads it into the kit's models, described below, and the run writes back
under two of its paths:

| Path | Read by | Contents |
| ------ | --------- | ---------- |
| `cfg/*.yml`, `cfg/*.yaml` | `read_and_process` (not recursive) | Every file is a mapping. Lists under the same key are concatenated across files; scalar keys are overwritten by later files. Duplicate `name` values within a list are refused. A `name` or `type` containing `{{` is refused. |
| `groups/**` | item kinds `users`, then `groups` | `users:` and `groups:` lists. Users are read first so group members can be checked. |
| `storages/**` | item kind `storages` | `storages:` lists. |
| `images/**` | item kind `images` | `images:` lists. |
| `instances/**` | item kind `instances` | `instances:` lists. |
| `base_images/**` | registered as a base-only kind | Not read in the normal flow. Base images are synthesized from OS builders during the base-image lifecycle. |
| `meta-state/` | `MetaState` | The committed cross-run records ([Meta-state](../engine/README.md#meta-state)). |
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

### Image sources (`cfg/image-sources*.yml`, key `image_sources`)

Source: [`image_sources.py`](src/cs_image_system/base/image_sources.py).
The catalog of vendor image sources per family and runtime
type, in the system's query vocabulary (`contract.image.ImageQuery`).
The release's layer is not a file of this package: each installed
runtime plugin ships its own part as package data
(`data/image-sources.yml` beside its code, the blocks keyed by its
runtime type) and answers it from its builder class's
`image_source_entries()`; `packaged_default_entries(classes)` here asks
every runtime builder class it is given and merges the parts by family
(`sources` is the union by runtime type; `description`, `is` and
`versions` take the first non-empty value, a disagreement logged at
WARNING). A runtime type's block that two parts give differently is a
collision: neither is used, and one error line names both parts; and
when one plugin ships a block for a runtime type another plugin
registers, discovery skips both plugins. The classes asked are those of
the runtimes a configuration DECLARES, once the loader has said which
(`ImageSourceCatalog.set_declared`): a provider installed beside them
has no say in what a family is or in its blocks. Before a configuration
is loaded they are every installed runtime's. The one reader that looks
past the declared runtimes is the stand-in for the local modification
tests, an installed runtime by its nature, whose own block is read
beside them. This module names no runtime. The tree's `image_sources:` entries land on the merged result
by family and version (`ImageSourceCatalog(reg)`, one per run like the
registry: the loader makes it over the run's registry and carries it as
`ctx.image_sources`; an OS model holds the one of the run that
structured it, handed over with the registry, so `get_family()` and
`image_query()` take no argument. `current_catalog()` and
`bind_current_catalog()` are gone: read `ctx.image_sources`). An OS
builder's runtime entry resolves its effective
query through it (`image_query()`), `get_family()` reads what a family
IS through it (`is:`), a missing OS builder `type` is defaulted from it
(`default_os_type`), the modification tests take their stand-in
container from its stand-in block (`stand_in_block`: the block keyed by
the type of the one registered runtime whose `local_test_target()` is
not None, `stand_in_runtime_type(classes)`; `container_reference` turns it into
an image reference), and `validate.check_image_sources` refuses an
unknown key, an entry with no source and a key the runtime cannot
translate. CONFIGURATION 5a is the reference.

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
(`_model_id`, `identified_model`, `builder`) used by sub-items; a group
and a user hold the same link (`ParentPropertyHolding`), to the model of
the builder their `type` names.
`identified_model` raises `ValueError` while the reference is unset or
names nothing in the run's registry. A parent set twice is one parent
when the second id refines the first (a bare name replaced by a global
id ending in it, or a model's global id replaced by its builder's, the
same model id and name under the builder's classification); a different
parent is a warning.

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
directory (`skips=True` leaves out the prepended and appended arguments).
It builds that command list once. Names must be unique.

### Runtime builders (`cfg/runtime-builders.yml`, key `runtime_builders`)

`RuntimeBuilderModel` (`BuilderModel` plus):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `default_machine_type` | `str` | required | Machine type when nothing more specific is given. |
| `default_image_builder` | `str` (fk `IMAGE_BUILDER_MODEL`) | `default` | Image builder used for bakes on this runtime. |
| `default_owners` | `list[str] \| None` | `None` | Owners added to vendor image queries, between the OS builder's and the entry's. |
| `credentials` | `CredentialsBase` | empty | Declared object; each plugin narrows it to its own subclass, so an unknown key is an error. Values name a profile or read the environment; no credential value belongs in the tree. |
| `default_config_username` | `str \| None` | `None` | Step 5 of the bake-user order ([bake_user.py](src/cs_image_system/base/bake_user.py); CONFIGURATION 5.1.1). |
| `ephemeral` | `bool` | `False` | Nothing baked here survives a successful run; the retention lifecycle disposes every image. Declared storages are never touched. |
| `retention_keep` | `int \| None` | `None` | Builds per series kept for images that declare no `retention`. `None` keeps everything. |
| `on_failure` | `str \| None` | `None` | Runtime default for ephemeral instances: `keep` or `teardown`. |
| `teardown_after` | `str \| None` | `None` | Runtime default duration (`30m`, `2h`, `1d`). |

`CloudBuilderModel` adds `region: str` (required) and `networking:
CloudNetworkingConfig` (required). `ContainerBuilderModel` adds `host` and
`context` (one or neither), `networking: ContainerNetworkingModel | None`
(a network by NAME, default `bridge`; no subnets, no zones) and
`machine_types: dict[str, {cpus, memory}]`, of which `default_machine_type`
must name one when any are declared; it classifies as
`CONTAINER_BUILDER_MODEL` and the loader folds it into the runtime
namespace as it does the cloud one.

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
| `default_primary_disk_size` | `str \| int` | `200` | Bake disk size in GB for the base image, the last step of `lineage.bake_disk_size`: used when the runtime declares no `default_disk_size` and the entry for that runtime no `default_primary_disk_size`. |
| `tags` | `dict[str, str]` | `{}` | Tags for the base image. |
| `owners` | `list[str]` | `[]` | Vendor image owners. |
| `query` | `dict[str, Any]` | `{}` | Vendor image query (provider-specific filters). |
| `runtimes` | `list[OSBuilderBaseImageBuilderSubconfig]` | required, at least one | One entry per image builder to bake on. `image_builder` must be unique across entries (``two `runtimes` entries name image builder <ib>; one entry per image builder`` at load). |
| `config_username` | `str \| None` | `None` | Step 3 of the bake-user order: the sudo-capable user on this OS's vendor image, for every runtime whose entry names none. |
| `auto_update` | `bool` | `False` | Alias for `update.policy: full`. |
| `update` | `dict \| None` | `None` | Update policy (below), a mapping; takes precedence over `auto_update`. A bare policy name (`update: none`) is refused at load. |
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
| `type` | `str` (templated) | the OS builder name | `{{ this.identified_model.name }}`: the name of the OS builder whose `runtimes` list holds the entry. The OS builder model parents each entry in its own construction, so the resolver's first pass renders it; the OS builder that wraps the model then refines the reference to its own global id. |
| `description` | `str` | templated | Free text. |
| `image_id` | `str \| None` | `None` | A pinned vendor image instead of a query. On the base-image lifecycle `predefined_resolve` skips `query_provider_image` and calls the runtime's `query_provider_image_by_id(entry, image_id)`: on AWS an AMI id, on GCE an image name searched in the entry's owner projects. An id the provider does not know stops resolution. Pinning makes base bakes reproducible. |
| `auto_update` | `bool \| None` | `None` | `None` inherits the OS builder's. |
| `default_machine_type` | `str \| None` | `None` | Bake machine type on this runtime. |
| `default_primary_disk_size` | `int \| None` | `None` | The base image's bake disk on this runtime when declared, step 2 of `lineage.bake_disk_size`; the runtime's own `default_disk_size` still wins. |
| `tags` | mapping | `{}` | Merged over the OS builder's tags. |
| `owners` | `list[str]` | `[]` | Added to the OS builder's and the runtime's default owners. |
| `query` | mapping | `{}` | Merged over the OS builder's query. |
| `ssh_username` | `str` | `default` | Step 2 of the bake-user order; unset, the order continues with the OS builder's `config_username`, the runtime's `ssh_username` and `default_config_username`, then the runtime's family default, and refuses when none answers. The entry's `finalize()` no longer fills it (it had no caller, and would have put `config_username` ahead of the runtime's `ssh_username`). |
| `tests` | mapping or `None` | `None` | When set, replaces the OS builder's tests for bakes on this runtime. |
| `config` | mapping | `{}` | Free-form templating values: `get_config()` returns it, and the string stage lets it shadow the enclosing `config` for the entry's own templated fields. |

Aliases are refused on subconfig entries. `image_name` is not a field:
declaring it is an unknown-key refusal at load. The fingerprint's
vendor-source record carries an `image_name: null` member, so no
fingerprint depends on the field's absence ([when it
went](../../docs/CHANGES.md#s63)).

`UpdatePolicy` (`update:`, always a mapping; `update: none` is refused):

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `policy` | `str` | `none` | One of `none`, `security`, `packages`, `full`. |
| `packages` | list | `[]` | With `packages`: exactly these; otherwise also these. |
| `exclude` | list | `[]` | Never touched by any policy. |
| `pin` | mapping | `{}` | Package to version, installed and locked. |
| `refresh_days` | `int \| None` | `None` | Re-bake when the series head is at least this old. |

`policy: packages` needs `packages` or `pin`; a package cannot be both
updated and excluded. `UpdatePolicy.from_config` refuses anything that is
not a mapping with ``update: must be a mapping (`update: {policy: <name>}`), got <type>``
(the field's own type refuses a bare name at load first). The base class
realizes only `none` and `full`;
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
(the image builder's name, set at construction; its template,
`{{ this.identified_model.name }}`, applies only when the entry names no
image builder and none is the default, and then names the image),
`ssh_username` (`default`), `image_identifier`, `machine_type`
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
| `type` | `str` (fk `GROUP_BUILDER_MODEL`) | `default` | The group builder, and the group's parent: the group holds that builder's model (its global id) as `_model_id`, so `identified_model` and `builder` are it. The loader sets it right after the group is structured, before the resolver's first pass: a written `type` names it, a `type` left at `default` the registry's default builder for groups. |
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
| `type` | `str` (fk `USER_BUILDER_MODEL`) | `default` | The user builder, and the user's parent, as a group's `type` is the group's. |
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
| `uid` | `int \| None` | `None` | A POSIX uid the configuration declares (the posix user builder); the twin of `Group.gid`. |

Aliases are not allowed on users. The core's `User` carries only what
every identity reads; an identity plugin that keeps more on a user
injects a subclass under `USER_MODEL` as the default item model
(`injected_models`, `is_injected_models_default`), and the loader
(`item_model_class` in `config_loader.py`) structures every `users:`
item into that subclass while the plugin is installed -- the okta-opa
plugin's `OktaUser` adds the Okta profile fields this way. The YAML key
and the `isinstance` check stay the kind's; a subclass only adds fields.

### `Storage` (`storages/`, key `storages`)

`NameTyped` plus:

| Field | Type | Default | Meaning |
| ------- | ------ | --------- | --------- |
| `runtime` | `str` (fk `RUNTIME_BUILDER_MODEL`) | `default` | |
| `type` | `str` (fk `STORAGE_BUILDER_MODEL`) | `default` | The storage builder that realizes the storage; `default` is the registry's default storage builder. A plain foreign key: a storage holds no parent, so it sets no `model_id` and puts no `builder` in the storage's template context. |
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
registers under `PROVIDER_SPECIFIC_IMAGE` by the name
`<source>::<runtime>`, through `replace_built_instance`: an image made
again for the same source and runtime (the resolved one a query found
for the deferred one a build promised) takes the old one's place, the
one registration that replaces on purpose. `get_query_assets()` returns
provider query inputs.
An image holds no context: what it needs of its runtime, the runtime
builder gives it as it makes it, in `prepare_provider_specific_image(psi)`
(a hook on `RuntimeBuilderBase`, nothing by default; the docker runtime
sets the repository its floating tag is read from).

## `cfg/_config.yml` key by key

`IAConfig` is the top-level document after the plugin keys are removed:
the tree's `id`, its generation directory and `dateformat`, the
`executables` and the nine builder lists, the extra `gitignore` entries,
the `encryption` recipients, the `public_safe` allowances and the free
`config:` mapping, of which the core reads the four apply flags,
`use_state_backends`, `module_source_base`, `module_sources`,
`admin_public_keys`, the `require_*` release gates and `preflight.expected_run_minutes`. Every
key with its type, default and meaning is the table in
[CONFIGURATION section 2](../../docs/CONFIGURATION.md#2-cfg_configyml),
and the `config:` keys the code reads are its
[section 2.3](../../docs/CONFIGURATION.md#23-config-keys-the-code-reads);
which of those the core itself acts on, and where, is under
[Configuration reference](#configuration-reference) below.

## Lifecycles and phases

Source: [`lifecycles.py`](src/cs_image_system/base/lifecycles.py) (the
registry) over the contract's
[`lifecycles.py`](../contract/src/cs_image_system/contract/lifecycles.py) and
[`lifecycle.py`](../contract/src/cs_image_system/contract/lifecycle.py) (the data
and the phases).

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

Two more lifecycles are registered by the core itself, from the
engine's [`release.py`](../engine/src/cs_image_system/engine/release.py)
and [`retention.py`](../engine/src/cs_image_system/engine/retention.py):
`release` (after `instance-image`) and `retention` (after `release`).
Both have no phases; they contribute deferred commands through
after-generate hooks ([releases](../engine/README.md#releases),
[retention](../engine/README.md#retention)). A
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

## The run context

Source: [`run_context.py`](src/cs_image_system/base/run_context.py) (the
context), [`config_loader.py`](../engine/src/cs_image_system/engine/config_loader.py)
(the loader that makes one), [`finalizer.py`](../engine/src/cs_image_system/engine/finalizer.py)
(the deferred-command queue and executor of one run).

`RunContext` is what one run knows: the configuration, the collections,
the paths and the flags. It is read-only in the sense that nothing on it
loads or executes: the loader (`read_config_and_transform`) constructs
it with the full configuration and returns it, and the finalizer, bound to
it, owns the deferred commands and the runner scripts. There is one
context per load, and the process keeps no current one: the loader binds
every builder it registers to the context it made
(`BuilderBase.bind(ctx)`), a builder reaches it through
`self._get_context()` (a builder made in code and never bound refuses,
by name; bind it with `bind(ctx)`), a command takes it as its `ctx`
argument, and the console script keeps it on the typer context
(`typer_cntx.obj["ctx"]`). A copy of a model shares its run, never
clones it: the context, the registry and the image-source catalog answer
`copy.deepcopy` with themselves.

Two contexts loaded in one process share nothing: each has its own
registry (`ctx.reg`), image-source catalog (`ctx.image_sources`),
template resolver (`ctx.template_resolver`) and finalizer
(`ctx.finalizer`), and every model and builder of a run answers with
that run's ([the test](../../tests/test_two_runs_in_one_process_share_nothing.py)).
A run's nested run (the transient-storage teardown) is such a second
context.

The names that stood for the old singleton for one release are gone.
What replaces each:

| Gone | Use |
| ---- | --- |
| `GlobalTypeContext` (the annotation), `global_context.py` | `RunContext` from `run_context.py`; the loader's names (`read_config_and_transform`, `load_overlay`, `parse_undeclare`, `ItemKind`, ...) from `config_loader.py`; the finalizer's (`Finalizer`, `ROOT_VARIABLE`, `render_executable_line`, `script_lines`, `write_script`) from `finalizer.py`. A plugin annotates with the contract's `RunContextProtocol`. |
| `GlobalTypeContext()` with no arguments, `run_context.current_context()`, `bind_current()` | The context you were given: a command's `ctx`, a builder's `self._get_context()`. A model method that needs something of the run takes it as an argument, or reads the registry and catalog the model is bound to. |
| The fallback in `BuilderBase._get_context()` to the process's current context | `builder.bind(ctx)`: an unbound builder raises instead of answering with another run's context. |
| `ctx.get_finalization_executables_for_phase`, `ctx.finalization_phases_for`, `ctx.final_execution_path`, `ctx.render_executable_line`, `ctx.write_final_execution_script`, `ctx.write_lifecycle_runner_script`, `ctx.write_gating_script`, `ctx.after_failed_phase`, `ctx.final_execute` | The same name on `ctx.finalizer` (`render_executable_line` is the function in `finalizer.py`). `ctx.extend_finalization_phase` stays: the contract's `RunContextProtocol` declares it. |
| `registry.current_registry()`, `bind_current_registry()`, `load_plugins()` with no registry | `ctx.reg`; `loader.installed_registry()` where no run is loaded; `load_plugins(reg)`. |
| `image_sources.current_catalog()`, `bind_current_catalog()` | `ctx.image_sources`. |
| `TemplateResolver()` (process-wide), `Orchestrator().get_converter()` | `ctx.template_resolver`, `ctx.template_resolver.converter`. |
| `os_type_for_family(family)`, `version_checker_for(exe)`, `check_single_version(exe)`, `packaged_default_entries()`, `stand_in_runtime_type()`, `stand_in_target_factory()` | Each takes what it reads: `os_type_for_family(family, reg)` (a plugin: `ctx.services.images.os_type_for_family(family)`), `version_checker_for(exe, reg)`, `check_single_version(exe, reg)`, and the runtime classes (`reg.runtime_builder_classes()`) for the other three. |

What the context exposes:

| Member | Meaning |
| -------- | --------- |
| `dry_run`, `verbose` | The invocation's flags. |
| `root_dir`, `working_path` | The configuration root. |
| `generation_path` | Where generated files land now: `generated/<lifecycle>/` while a lifecycle is current, else `generated/`. |
| `root_generation_path`, `lifecycle_generation_path(lc)`, `runner_script_path(lc)`, `gating_script_path` | Generated-tree paths. |
| `current_lifecycle`, `generated_lifecycles`, `mark_generated(lc)` | Lifecycle bookkeeping. |
| `last_lifecycle_step` | What the run was last doing (`generation of <lifecycle>`, `the apply of <lifecycle>`), kept past the reset of `current_lifecycle` so an interrupted run is journalled where it was; each run's own, a nested run's included. |
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
| `reg`, `image_sources`, `template_resolver` | The run's registry, image-source catalog and template resolver (with its converter): one of each per load. |
| `finalizer` | The run's deferred-command queue and executor: `get_finalization_executables_for_phase(phase, lifecycle)`, `finalization_phases_for(lifecycle)`, `final_execution_path`, `write_lifecycle_runner_script(lc, header)`, `write_gating_script()`, `final_execute()`. |
| `extend_finalization_phase(phase, executables)` | Queue executables for a phase on the run's finalizer (the one finalizer verb the contract's context protocol declares). |
| `plugin_state(key, factory)` | The one object a library or plugin keeps for this run under `key`: made by `factory` on the first ask, the same object after, gone with the context. A key is `<namespace>/<name>`, the namespace being the plugin's or library's own (what its registrations carry), so two plugins that choose one name never hold one object; a key that names no namespace is refused. |

### What a process shares between runs, and what it must not

A process may hold more than one run. A run's transient-storage teardown is
a nested run of its own (the same root under fewer overlays), loaded and run
in the same process, and a test loads many trees in one process. So
anything a run's configuration, credentials, overlays, root, clock or
meta-state decides belongs to that run: on its context, or on an object the
run owns. What the process keeps for every run is either a fact of what is
installed or the process's own by design, and every run shares it safely:

| Where | What it holds | Why sharing it is safe |
| ----- | ------------- | ---------------------- |
| `loader._discovered_plugins` | The installed plugins, discovered and held to the contract once. | What is installed does not change under a process; each run replays it into a registry of its own. |
| `basic.abstract_plugin_metadata._distribution_roots` | Where each installed distribution's files are, and its version. | Installed. |
| `public_safe._runtime_rules` | The secret shapes the installed runtime classes declare. | Installed; nothing of a run is read. |
| The hook lists in `commands/run_lifecycles.py` (`_VALIDATORS` to `_STATE_BINDINGS`), `_HOOK_PLUGINS_LOADED` | The run hooks of the core and of the installed hook plugins. | Filled once from code and entry points; every hook is handed the run it serves; registering one again adds nothing. |
| `lifecycles._REGISTERED` | The lifecycles code and hook plugins register. | Each is registered once and never changed. |
| `config_loader._ITEM_KINDS` | The domain-item kinds the loader reads. | Registered at import; a run reads its items into its own context. |
| `helpers.resolution_stages._PASSES` | The string-stage passes. | Registered at import; each pass walks the document it is handed. |
| The contract's `field_kinds._HANDLERS`, `enrollment._KINDS`, `secrets._decoder` | The field-kind handlers, the launch-enrollment renderers, the core's marker decoder. | Each is handed what it works on (the run's resolver and registry, a launch's parameters, a marker). |
| `in_process._RUNNER` | The system CLI's in-process runner. | One per process, handed the run's context on every call; a nested run loads a context of its own. |
| The system CLI's `_DEFERRED_LOAD_COMMANDS` | The plugin sub-apps whose commands load the tree themselves. | Filled at import from the installed command mounts. |
| `encryption._identities_for` | The age identities `CSIS_CONFIG_IDENTITY` names. | Keyed by the environment's value, which every run in the process reads alike. |
| `encryption._OPENED`, `_OPENED_KEYS` | Every marker opened in the process and its plaintext, and the keys each plaintext was read under. | A marker opens to one plaintext under the process's one identity, and every reader takes a plaintext more as one more value to hide (a stricter scan of what is written, a derived value marked, a record written as ciphertext), never as one fewer. The nested run reads the same root under some of its outer run's overlays. |
| The working directory, the logging, standard output, the typer context | The process's own. | A nested run leaves each as it found it (`run_nested` in the system CLI). |

What is a run's own: its registry, image-source catalog, template resolver,
finalizer and meta-state handle, its run id and start time, its bake
decisions (`ctx.bake_decisions`), and whatever a library or plugin keeps
through `ctx.plugin_state(key, factory)`: the terraform and packer
collectors ([hashicorp-utils](../hashicorp-utils/README.md)) and the alias
pool's draws (`alias_pool.drawn_this_run(ctx)`). The draws are kept by run,
not by run id: a run id is the load's start time to the second and names no
root, so two runs loaded in one second carry one id
([the test](../../tests/test_two_runs_in_one_process_share_nothing.py)).

For a plugin author: never keep run state at module level. No
`functools.cache` over anything a run's configuration, credentials or
overlays decide; no module-level SDK client, session or token built from a
runtime's settings; no dict of cloud answers keyed by region, project or
profile, which would serve one run's answer to another run under other
overlays. Build a client per call from the builder's own model, as every
built-in runtime does, or keep it for the run through `ctx.plugin_state`,
which gives one object per run and drops it with the context. Only a fact
of what is installed may be cached for the process.

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

The emission under `generated/` carries the ciphertext a `Decrypted`
remembers (emission by reference), and
[`materialize.py`](../engine/src/cs_image_system/engine/materialize.py) replaces it
with the plaintext in the private mirror `_private/` before a deferred
command runs. The rules a tree follows -- which values may be encrypted,
where a marker may not stand, what a marker protects and what stays
public by decision -- are
[CONFIGURATION section 13](../../docs/CONFIGURATION.md#13-encrypted-values).

Helpers: `encrypt_value(plaintext, recipients)` produces a marker;
`recipients_from_config(root)` reads `cfg/_config.yml` as text (no identity
needed); `encrypt_fields_in_text(text, field_names, recipients)` encrypts,
in place and byte-preserving, every scalar under a named key and every
element of a block list under such a key, skipping values that are already
markers, contain `{{`, are empty, or start a nested block;
`rotate_text(text, identities, recipients)` re-encrypts every marker in a
text to the current recipients and fails on the first marker it cannot
open.

## Lineage

Source: [`lineage.py`](src/cs_image_system/base/lineage.py).

Every bake writes a new image, so every build gets a unique id and carries
lineage as tags: `csis_series` (the logical image name), `csis_parent`
(the build it was baked from, `series:<name>` when bound after the bake, or
`vendor`), `csis_run`, `csis_fingerprint` (the first 16 characters of the
input fingerprint), `csis_identity_types` and `csis_storage_types`. After
a bake `record_build` appends the lineage record and performs the first
bind of the parent edge. The input fingerprint hashes what determines the
build's content: series, the parent image's own fingerprint on that
runtime (`parent_fingerprint`, never a build id: hashing the parent's
build id would make a child on an ephemeral runtime re-bake every
cycle, because retention disposes the build it was recorded against),
capability stamp, every modification's content hash, the in-bake
verification commands, the bake disk size, and for base images the
declared vendor source, admin user and keys, and update policy. Machine
type, usernames, run ids and timestamps are excluded. The bake disk
size is `bake_disk_size(ctx, image, runtime)`, the one rule the packer
sources (AWS `volume_size`, GCE `disk_size`) also use: the runtime's
own `default_disk_size` when declared; else, for a base image, its OS
builder entry's `default_primary_disk_size` for that runtime when
declared, else the OS builder's `default_primary_disk_size`; for an
instance image, its own `primary_disk_size`. The fingerprint hashes
what is baked, so a recorded fingerprint that predates the current
recipe reads DUE until `lineage restamp --runtime <rt> --commit`
re-records it ([when the recipe last
moved](../../docs/CHANGES.md#s63)). `bake_reason(ctx, image, runtime)` decides whether an image
bakes in this run: forced by `--force-bake`, no build yet on that runtime,
the parent moved under `parent_policy: follow`, the parent re-bakes this
run under `follow`, the fingerprint differs from the series head's, or
`update.refresh_days` is due; otherwise it is current and skipped.
Consumers bind once: an instance to the head of its image's series and an
image to the head of its parent's series on its runtime (the pin key is
`<image>@<runtime>`), and stay pinned. Only `upgrade`, a `follow` policy,
disposal or decommission moves a pin, one edge at a time; every move is
journaled in `pins.yaml`.

## Launch parameters

Source: [`launch_params.py`](src/cs_image_system/base/launch_params.py).

An image carries all tooling; launch parameters carry only the bindings
specific to one instance, computed from validated configuration and
recorded in `meta-state/launch-params.yaml`. `compute_launch_params`
returns `image`, `build` (the pin, or `unbound`), `group` (the image's
owning group), `identity_type`, `mounts` (per attached storage: `storage`,
`type`, `builder`, `mount_point`, `group`, `share_mode`, `public_read`,
plus whatever the storage builder's `launch_mount()` adds -- a `device`
for a block store, named by its plugin's own rule, in declaration order
among the mounts of its type; `platform_mounted` for a storage the
platform mounts itself), `enrollment` (from the group
builder), `session` (the runtime's mechanism), `hostname` (the canonical
hostname: for a launched machine this run does not replace, the hostname
it was recorded with; for a new machine, `<declared name>-NNN` where NNN
is its kind's next generation, zero-padded to three digits), `alias` (only
when a name was drawn from `meta-state/aliases.txt` for a new durable
machine by a run that can launch it, or was recorded earlier), `ephemeral`,
and `userdata` when declared. `user_data_template`
renders these as a bash script for terraform's `templatefile`: hostname,
group gid by reference (`${group_gid}`), then one block per mount, then
the enrollment trigger (`${enrollment_token}`, never recorded), the
instance's own `userdata` lines, and finally the marker
`/var/lib/csis/launch-applied`. The core knows no storage kind: each
mount's block, from its `# mount storage <name> (<type>) at <mount point>`
header to the group's private subtree (or the comment that an object
store is not mounted), is the storage builder's `launch_script_lines()`,
and the builder names the template variables its block reads
(`launch_variables()`: a map per storage kind, such as a shared
filesystem's ids, keyed by storage name); `launch_variables(ctx)` lists
them for a tree as `group_gid`, the builders' own in declaration order,
the enrollment token. A block that mounts something ends in the mount
mark line (`csis-mount: <mount point> mounted` or `NOT mounted`), which
is how `mounted_points()` -- and so `verify instance` -- knows which
declared mount points to look for. Runtime
values enter only by terraform reference. After a real apply, hooks mark
every declared instance launched, forget decommissioned and ephemeral
instances, and re-record detachments. Launched instances are immutable: a
changed parameter set fails validation unless the instance has a pending
replacement (an explicit upgrade or a `follow` target). Two in-place
changes are sanctioned and recorded instead
([DESIGN N26](../../docs/DESIGN.md)): removing a mount, which is a detach
(unmounted first; the gate refuses the plan without the receipt), and
changing `machine_type`, which is a resize of the same machine (the
provider stops, changes and starts it; the generation's snapshot is
updated and a `resized` event is kept in `instance-state.yaml`).

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

The kit's modules the sections above do not describe. The engine's are
in [its README](../engine/README.md#the-modules-in-detail).

| Module | Purpose |
| -------- | --------- |
| [`image_tests.py`](src/cs_image_system/base/image_tests.py) | In-bake assertions emitted as the last packer provisioner: capability verification derived from plugin hooks, plus a declared `tests:` map with keys `files`, `packages`, `commands`, `services_enabled`, `users`. `tests.post_bake` adds `mounts` and runs on a launched instance. |
| [`commands/verify_instance.py`](src/cs_image_system/base/commands/verify_instance.py) | The operation behind the CLI's `verify instance`: the kit's, since the lineage and launch rules read it. |
| [`utils.py`](src/cs_image_system/base/utils.py) | `safe_name`, `super_safe_name`, `system_cli_executable` (a deferred call of the system's own CLI), `apply_enabled` / `apply_flag_allows` (the `apply_<lifecycle>` rule), `module_source` and `module_source_overrides` (a call's source from `module_source_base` and `module_sources`), `hcl_expr` and `render_module_call` (terraform module call rendering). |
| [`power_state.py`](src/cs_image_system/base/power_state.py) | The system's power-state vocabulary (`running`, `stopped`, `suspended`, `starting`, `stopping`, `absent`, `unknown`; `None` is "cannot answer"), `wait_until_reachable`, and `running_for_task`, the one bounded exception under which a stopped machine is started for work that needs it and stopped again afterwards. |
| [`generations.py`](src/cs_image_system/base/generations.py) | Instance generations: one per machine, opened `inferred` by a launch and confirmed `observed` (or closed as `replaced-out-of-band`) by the provider's instance id after a real apply; a machine launched before the record existed is `adopted` as generation 1 of it. |
| [`alias_pool.py`](src/cs_image_system/base/alias_pool.py) | The pool of pre-approved names in `meta-state/aliases.txt`: a new durable machine's alias is the first free line, burnt in place under an exclusive lock by the run that can launch it. |

## Tests

The package's tests live in [`tests/`](tests/) and cover the registry
(plugin registration, the checks a registration makes before it writes,
the instance keys and the global-id index), the global ids of builders
and items, a parent reference's refinement, the field helpers and the
field-kind classifier, the display name, email-as-username and
required-name rules, group gids, provider-specific images and
`in_directory`. They import nothing of the engine, and
`tests/test_contract.py` holds that: their shared fixture,
`clean_registry` in [`tests/conftest.py`](tests/conftest.py), is a
fresh registry behind a stand-in that satisfies the kit's
`TemplateResolverLike` protocol (from `run_context`) and resolves and
structures nothing. A test that needs a whole resolution, or a model
structured by the run's converter, is the engine's
([engine](../engine/README.md#tests)), as are the tests of the
resolution stages, the template utilities and the finalization
executor. They run with the workspace suite; in the workspace, `just
test` is the acceptance bar.

## Prerequisites and integration

The kit contains no cloud code and makes no network call of its own: it
is the classes and the records a run is made of, and the engine is what
loads a tree into them and runs it. What a run needs outside the core
-- a configuration root, git, the declared tools, the credentials the
plugins look at, the network -- is listed in [the engine's
README](../engine/README.md#prerequisites-and-integration). What the kit
itself needs is short.

- **Python 3.13 or later and the workspace.** `requires-python =
  ">=3.13"` in [`pyproject.toml`](pyproject.toml); `just init` (`uv
  sync`) installs this package, the [engine](../engine/README.md) and
  every plugin beside it. The kit's dependencies are the contract and
  the five libraries named at the top of this file; nothing else is
  imported at runtime except the standard library.
- **The contract, in its compatible series.** Every model and builder
  base here implements a protocol of the
  [contract](../contract/README.md), and every constant, field helper and
  phase is imported from it; the pin is `>=0.4,<0.5`, the range every
  package of the workspace declares.
- **Nothing of the engine, and nothing of hashicorp-utils.** No module
  here imports the engine, by any edge, and the kit imports no terraform
  library: what the terraform roots need of
  [hashicorp-utils](../hashicorp-utils/README.md) and
  [tofu-roots](../tofu-roots/README.md) reaches a run through hook
  plugins and the context's plugin state ([what a process shares between
  runs](#what-a-process-shares-between-runs-and-what-it-must-not)). A
  runtime plugin therefore installs with the contract and the kit alone.
- **Commands only as a builder hands them over.** The kit runs a
  command in two places: `ExecutableModel.execute` (a step a builder
  queued, `subprocess.run` with `check=True`) and the version checkers,
  which read a declared tool's version. Which binaries those are is each
  plugin's business and the tree's `executables:`.
- **An age identity, only for a tree with markers.** `EncryptedStr`
  decrypts with the identity `CSIS_CONFIG_IDENTITY` names, resolved on
  the first marker seen, so a tree without markers needs none
  ([Encryption](#encryption)).
- **Plugins, which subclass the kit.** The kit registers no runtime, no
  image builder, no OS builder, no storage, group, user, instance or mod
  builder and no state backend; every one comes from a plugin that
  subclasses a base here and registers through the contract's entry
  points. The plugin READMEs say what each needs:
  [ansible-plugin](../ansible-plugin/README.md),
  [aws-runtime-plugin](../aws-runtime-plugin/README.md),
  [bash-mod-plugin](../bash-mod-plugin/README.md),
  [contract-example-plugin](../contract-example-plugin/README.md),
  [default-os-plugin](../default-os-plugin/README.md),
  [docker-plugin](../docker-plugin/README.md),
  [dummy-plugin](../dummy-plugin/README.md),
  [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md),
  [gcs-state-plugin](../gcs-state-plugin/README.md),
  [local-state-plugin](../local-state-plugin/README.md),
  [okta-opa-plugin](../okta-opa-plugin/README.md),
  [packer-plugin](../packer-plugin/README.md),
  [posix-identity-plugin](../posix-identity-plugin/README.md),
  [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md),
  [tf-gcp-plugin](../tf-gcp-plugin/README.md),
  [tf-s3-state-plugin](../tf-s3-state-plugin/README.md).

## Configuration reference

The core owns [`cfg/_config.yml`](../../tests/fixtures/config/cfg/_config.yml)
(the `IAConfig` document that remains after the builder collections are
popped out) and the shape of the five collections under `groups/`,
`storages/`, `images/` and `instances/` (`base_images/` is registered
but not read). The fields each plugin adds to its own builder models and
sub-items, and the plugin's own reading of collection fields (a runtime
plugin's `machine_type`, the identity plugin's `attributes`), are in the
seventeen plugin READMEs linked
[above](#prerequisites-and-integration). Every model is a pydantic
dataclass with `extra="forbid"`: an unknown key is refused at load.

### `cfg/_config.yml`, top level

The document is `IAConfig`: `id` (read, acted on by nothing in the
core), `generation_directory` (under which every `generated/<lifecycle>/`,
`run-summary.json`, `state-report.json` and `final_execution.sh` path
hangs, and whose NAME `_private/` replaces beside it, `mirror_path`),
`dateformat` (read raw by the string stage, falling back to
`DEFAULT_DATEFORMAT`, the model's own default), `executables` (names
unique and never a reserved word; presence and version checked at
`validate` and every run), the nine builder lists (accepted at the top
level of ANY `cfg/*.yml`, concatenated across files), `gitignore`
(appended to the built-in entries, a duplicate keeping its LAST position,
written into `generated/` and every lifecycle directory),
`encryption.recipients` and `public_safe.allow` (both read as TEXT by the
value tools, the commit gate and the hook, so a marker in either is
refused), the free `config` mapping (on the context as `ctx.config`,
overridden key by key by an overlay's `config:`), and the accepted but
unread `working_directory` and `sleep_before_finalization`;
`last_updated` is an unknown key, refused at load. Every field with its
type, default and meaning is the table in
[CONFIGURATION section 2](../../docs/CONFIGURATION.md#2-cfg_configyml).

### `config:` keys the core reads

Any other key is carried on the context for plugins, except seventeen
that are refused where the file is read (`INVALID_CONFIG_KEYS`:
`self`, `this`, `same`, `runtime`, `os`, `default`, `defaults`, `any`,
`anything`, `none`, `null`, the empty string, `timestamp`, `date`,
`datetime`, `config`, `configuration`, in any case;
`refuse_invalid_config_keys` in
[`reserved_names.py`](../engine/src/cs_image_system/engine/reserved_names.py)).
None of the seventeen collides with the template context. The collision
that does exist is not guarded: a key named after a mapping method
(`items`, `keys`, `values`, `get`, `update`, `copy`, `pop`) renders the
method in `{{ config.<key> }}`, not the value -- so avoid those names.

The keys the core reads, and who reads them: the four apply flags
`apply_identity`, `apply_storage`, `apply_instances` and `apply_release`
(`apply_enabled` in [`utils.py`](src/cs_image_system/base/utils.py), the
plugins at generation, `apply-check` at execution and every after-apply
recorder: `true` applies every root of the lifecycle, `false`, unset or
an empty list plans and gates only, and a list applies only the roots
whose builder NAME or RUNTIME is listed; a string is a one-element list;
read raw by `apply-check`, so never encrypted; with `apply_instances` on,
the recorders claim reality, the hostname claims are checked against the
registry and a run that can launch draws from the alias pool; with
`apply_release` on, the runtime's `release_commands` for every CURRENT
release are deferred into the release runner); `use_state_backends`
(hashicorp-utils' collector and the tofu-roots hook plugin's
state-location validator and recorder: off, no backend block, no
`.tfbackend.hcl`, no remote-state data source, no location record, no
collision or move check); `module_source_base` and `module_sources`
(`module_source` in `utils.py`: a relative value is relative to the
configuration root and rewritten per workspace depth, absolute paths and
URLs pass through; an entry of `module_sources` is the source of that one
module, and `validate_module_sources` refuses a value that is not a
mapping of strings); `admin_public_keys`
([`capabilities.py`](src/cs_image_system/base/capabilities.py),
`validate_base_images`, the fingerprint and the in-bake tests: one
OpenSSH public-key line each, never private material, a lone string
accepted, encryption allowed); `require_mod_tests`, `require_image_tests`
(default `true`) and `require_released_builds` (`release()` and
`validate_released_pins`: a missing mod-test record is tolerated unless
required, a FAILED one never; a declared `tests.post_bake` needs a
PASSING record; a pin must be released or under the release grace); and
`preflight.expected_run_minutes` (`expected_run_minutes` and
`raw_expected_run_minutes` in
[`commands/preflight.py`](../engine/src/cs_image_system/engine/commands/preflight.py):
a session expiring within the window is `blocking` -- `preflight
--strict` and `state query --strict` exit 1, a run warns; read raw before
the load, so never encrypted; a non-integer falls back to 30). Any other
key is carried for plugins (`okta_gateway_selector` is the identity
plugin's) and usable as `{{ config.<key> }}` in `cfg/` strings. Each
key's type, default, reader and effect is the table in
[CONFIGURATION section 2.3](../../docs/CONFIGURATION.md#23-config-keys-the-code-reads).

Which apply flags shape the run's SCOPE: `apply_scope_runtimes` in
[`commands/run_scope.py`](../engine/src/cs_image_system/engine/commands/run_scope.py)
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
| `primary_disk_size` | `bake_disk_size` (the fingerprint and both packer sources) | Part of the input fingerprint; the bake disk and every boot disk (plugin), unless the runtime declares `default_disk_size`. |
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
| `type` | the load, `validate_storages`, `storage_type_of`, `storage_facts`, `_root_applied` | The storage builder: fixes the capability type, the cardinality, whether it is zonal, and the runtime the root applies on. |
| `runtime` | `check_availability_zones`, as a fallback only (`_storage_runtime`) | The BUILDER's runtime governs everywhere, the zone check included; the item's own value is read only when the builder names no runtime (read first, its `default` would resolve to the default runtime, not the builder's). |
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
| OS builder | `runtimes[].image_builder`, `image_id`, `query`, `default_primary_disk_size` | `base_image_runtimes`, `_vendor_source`, `bake_disk_size` (the fingerprint and the packer sources); `image_id` also `predefined_resolve` (the lookup by id) |
| OS builder | `runtimes[].config` | the string stage (`_render_scoped`), `get_config()` |
| OS builder | `default_primary_disk_size` | `bake_disk_size`, when neither the runtime nor the entry declares a size |
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
  `--migrate-state` (refused), and no hostname claim check: it asks the
  registry only when a launch is possible (the instance-image lifecycle
  requested, `apply_instances` allowing the root, a real run). Deferred system-CLI steps
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
  aliases written for every machine it lists (by the provider id the
  agent enrolled with); a machine it answers without (not enrolled, so
  no record of its own to judge its names beside) is passed over with an
  INFO line, as a stopped one is, and gets its aliases at the next
  applies-on run that finds it listed. A registry that cannot be asked
  (`registered_servers` returns `None`) REFUSES the launch ("could not
  check whether canonical hostname ... is already claimed"), skips every
  alias that run, and fails the login proof's "one registration" check.
  Silence is never a free name.
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
- **A queried vs a pinned vendor image.** Without `image_id` on an OS
  builder's runtime entry, the base-image lifecycle asks the runtime's
  `query_provider_image` for the newest image matching the merged
  `owners` and `query`, so a base bake can start from a newer vendor image
  each time. With `image_id` it asks
  `query_provider_image_by_id` for exactly that image instead; an unknown
  id stops resolution. The id enters the fingerprint's vendor source, so
  setting or changing it re-bakes that base on that runtime.
- **Where the bake disk comes from.** The runtime's `default_disk_size`
  when it declares one; else the entry's `default_primary_disk_size`;
  else the OS builder's (200). One rule, `bake_disk_size`, for the packer
  sources and the fingerprint.
- **One runtime vs another.** The core never branches on a cloud's name;
  what differs is which hooks a plugin implements. Block-device names in
  the launch parameters are the one place the core knows two storage
  types by name: `/dev/xvdf` onwards for `ebs`, `/dev/disk/by-id/google-<name>`
  for `pd`; `efs` and `filestore` mount by reference; `s3` and `gcs` get
  no mount.

## What it tests and verifies

The kit's code holds rules, and the engine decides when they run: at
load, at `validate` and at the head of every run, at generation, after
an apply. The whole list, moment by moment, with where each verdict
lands, is [the engine's](../engine/README.md#what-it-tests-and-verifies).
Read from the kit's side, the rules are these.

- **At construction, in every model.** One model configuration
  (`CSIS_MODEL_CONFIG`) refuses an unknown key (`extra="forbid"`).
  `NameTyped` and `RootItem` refuse a name or an alias that is a
  reserved word of `OOPS_DEFAULTS` (`default`, `self`, `none`, empty or
  `None`, in any case or spacing) or holds `/` or `\`: the backstop for
  an object made in code, since the engine refuses such a name earlier,
  where the file is read ([naming
  rules](../engine/README.md#naming-rules)). Each model's
  `__post_init__` refuses what its own fields cannot hold: a storage's
  `ALL`, unknown `state` or unknown `share_mode`, a group's `gid` below
  1024 that is not a deferral, a user's blank `first_name` or
  `last_name`, an instance's `groups`, and the rest the engine's list
  names under [at
  load](../engine/README.md#at-load-structuring-__post_init__-the-item-kind-validators).
- **In the registry.** A different class registered under a key already
  taken (classification, namespace and canonical name) is refused as a
  `Type Collision`; a bare `type:` word that several installed plugins
  answer to is refused as ambiguous (`AmbiguousTypeError`); two
  instances under one name, or an alias another instance holds, are
  refused as a collision (`InstanceCollisionError`), and the registry is
  left as it was ([the registry](#the-registry)).
- **In a builder.** A builder bound to no run context refuses to answer
  for one (`BuilderBase._get_context()`), rather than answering with
  another run's.
- **Rules the engine calls.** `validate_policies` in
  [`lineage.py`](src/cs_image_system/base/lineage.py) (an unknown
  `parent_policy` or `image_policy`); `validate_immutability` and
  `validate_claimed_hostnames` in
  [`launch_params.py`](src/cs_image_system/base/launch_params.py),
  registered as validators by its `register(runner)` (a launched
  instance's parameters may not change but by a sanctioned detach or
  resize; a canonical hostname another registration answers to is
  refused); `validate_public_key` in
  [`capabilities.py`](src/cs_image_system/base/capabilities.py) (one
  OpenSSH public-key line, never private material); and
  `validate_tests_spec` in
  [`image_tests.py`](src/cs_image_system/base/image_tests.py) (an image's
  `tests:` use the known vocabulary). The engine's
  [`validation_rules.py`](../engine/src/cs_image_system/engine/validation_rules.py)
  calls the last two at `validate` and at the head of every run.
- **The kit's own tests** ([Tests](#tests)) hold the registry, the field
  helpers and kinds, the item kinds and the models' rules; the
  workspace suite holds the rest end to end.

## When it fails

A failure names its rule. The failures below are the ones the kit's own
code raises, with what each means to a plugin author or an operator;
every failure a run reports, in the order the operator meets them, and
the incidents behind them, are [the engine's
list](../engine/README.md#when-it-fails), and the operator's view, in
the order of a working day, is
[docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) chapter 6.

- `Type Collision: <namespace>/<name> under <classification> is
  <module.Class>, and <module.Other> registers it too` (`ValueError`
  from the registry) -- two different classes under one classification,
  namespace and canonical name: a packaging problem, not a
  configuration one. Rename one class's word, or give one plugin its
  own namespace.
- `type '<word>' is ambiguous under <classification>: N plugins register
  it; write one of <ns>/<word>, ...` (`AmbiguousTypeError`) -- the tree
  wrote a bare `type:` word that several installed plugins answer to;
  write one of the qualified forms named.
- `Instance name collision under <classification>: ...`
  (`InstanceCollisionError`) -- two declarations under one name, or an
  alias another instance holds; rename one.
- `builder '<name>' is bound to no run context: the loader binds every
  builder it registers; a builder made in code is bound with bind(ctx)`
  (`RuntimeError`) -- a builder made in code (a test's, a plugin's own)
  was asked for its context before anything bound one; call
  `builder.bind(ctx)` with the context you were given.
- `an encrypted value is present but CSIS_CONFIG_IDENTITY is not set`
  (`MissingIdentityError`), or `no identity in CSIS_CONFIG_IDENTITY can
  decrypt this value (...)` -- a marker met with no identity, or with
  none that opens it; export the identity, or re-encrypt the tree to the
  current recipients ([Encryption](#encryption)).
