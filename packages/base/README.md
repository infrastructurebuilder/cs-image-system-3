# cs-image-system-base

The core library of cs-image-system. It implements the plugin contract
([contract](../contract/README.md)) with its base models and
builder bases, and defines the registry, the plugin loader, the lifecycle
runner, the cross-run meta-state, value encryption, the public-safe gate,
and the lineage, release, retention, launch-parameter and capability
rules that every built-in plugin and the command-line host build on.

It contains no cloud code. Clouds, identity providers, packer and terraform
live in plugins that register through the contract; the loader and the
registry that read them are described here. The package is licensed under
Apache-2.0 and requires Python 3.13 or later.

Declared dependencies ([`pyproject.toml`](pyproject.toml)):
`cs-image-system-contract` (the one sibling it depends on; the contract
depends on no sibling), `Jinja2`, `PyYAML`, `age`, `packaging`, `pydantic`
and `typer`. The models are pydantic dataclasses; `packaging` parses
version specifiers; `age` is the library behind every `ENC[age:...]` value.

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

The contract itself is the [contract](../contract/README.md) package:
the protocols a model and a builder satisfy, the constants and field
helpers, the lifecycle phases, the data carriers a hook returns. This
package implements it -- the base models and builder bases below carry a
default for every hook -- and reads it: the loader and the registry are
here. Source: [`loader.py`](src/cs_image_system/base/loader.py),
[`registry.py`](src/cs_image_system/base/registry.py),
[`basic/abstract_plugin_metadata.py`](src/cs_image_system/base/basic/abstract_plugin_metadata.py),
[`models/mixins.py`](src/cs_image_system/base/models/mixins.py) (the bodies
of the contract's three marker protocols), and the base models and builder
bases. The constants, the model configuration, the field helpers and
kinds, the lifecycle phases and data, the assets, the command lists, the
name and HCL helpers and the provider-specific image's enums are the
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
chose, what it registers and the group that fits. A plugin may register
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
own; a plugin with no distribution and no field is refused at discovery.
The instance-level tables (what the tree declared: built builders and
items, their aliases, the defaults) are keyed by the tree's own names,
which carry no namespace. The reasoning is in
[the stage index](../../docs/CHANGES.md#s131).

| Store                     | Keyed by                          | Holds |
| --------------------------- | ----------------------------------- | ------- |
| `models`                  | `RegistrationKey`                 | Model classes a `type:` value can select (`get_model(vct, word)`; `models_under(vct)` lists them by the shortest word that resolves, `registration_keys(vct)` the keys). A *different* class under a key already taken is a `ValueError` ("Type Collision"); the same class under the same key, or under another namespace, is the same registration. |
| `builders`                | model class                       | The builder class for a model. |
| `registry` / `vct_type_registry` / `reverse_registry` | `RegistrationKey` / `VCT` / class | Services by key, the classes per classification (one entry per class, however many plugins carry it), and every key a class is registered under; `get_builder_for_model(type_name, classification)` reads `registry` by the resolution rule below, and `register_service` refuses a different class under a taken key. |
| `instances`               | `VCT`, then name or alias         | Built objects: builder models, builders, items. Cloud and container builders are mirrored under the runtime classifications. |
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
| Run hooks | entry point group `cs_image_system.plugins.hooks`; `HookSet` in [`commands/run_lifecycles.py`](src/cs_image_system/base/commands/run_lifecycles.py) | `validators` (return error strings; any error aborts the run), `after_generate`, `before_apply`, `after_apply` (real runs only), `on_summary`, `state_bindings` (answer `{lifecycle: {workspace: state file}}`, merged into the runner-script headers and the summary's `state_bindings`; the tofu-roots plugin answers for the terraform roots), and `lifecycles` (a list of `LifecycleSpec`). |
| Lifecycles | `register_lifecycle(LifecycleSpec)` in [`lifecycles.py`](src/cs_image_system/base/lifecycles.py) | A lifecycle with its own phases, builder classifications, directory and runner script, positioned after an existing one. |
| Field kinds | `register_field_kind(name, FieldKindHandler)` in the contract's [`field_kinds.py`](../contract/src/cs_image_system/contract/field_kinds.py) | A late-binding behaviour for fields carrying `field_kind` metadata: `contribute_context`, `resolve`, `upgrade`. |
| Resolution passes | `register_resolution_pass(name, fn, order)` in [`helpers/resolution_stages.py`](src/cs_image_system/base/helpers/resolution_stages.py) | A string-stage pass over the raw YAML document. Built in: `interpolate` (order 10) and `scope-this` (order 20). |
| Item kinds | `register_item_kind(ItemKind)` in [`config_loader.py`](src/cs_image_system/base/config_loader.py) | A new domain-item collection: directory, model class, owning builder classification, attach function, optional validation. |

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

### Image sources (`cfg/image-sources*.yml`, key `image_sources`)

Source: [`image_sources.py`](src/cs_image_system/base/image_sources.py).
The catalog of vendor image sources per family and runtime
type, in the system's query vocabulary (`contract.image.ImageQuery`).
The release's layer is not a file of this package: each installed
runtime plugin ships its own part as package data
(`data/image-sources.yml` beside its code, the blocks keyed by its
runtime type) and answers it from its builder class's
`image_source_entries()`; `packaged_default_entries(classes)` here asks
every runtime builder class it is given (a registry's
`runtime_builder_classes()`) and merges the parts by family
(`sources` is the union by runtime type; `description`, `is` and
`versions` take the first non-empty value, a disagreement logged at
WARNING). The catalog therefore depends on which runtime plugins are
installed, never on which a tree declares, and this module names no
runtime. The tree's `image_sources:` entries land on the merged result
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

## How YAML becomes models

Source: [`template_utils.py`](src/cs_image_system/base/template_utils.py),
[`orchestrator.py`](src/cs_image_system/base/orchestrator.py),
the contract's [`fields.py`](../contract/src/cs_image_system/contract/fields.py),
[`config_loader.py`](src/cs_image_system/base/config_loader.py).

### The string stage

Before anything is structured, the merged `cfg/` document -- the one tree
the loader parsed, each `cfg/*.yml` file read exactly once -- is walked by
the ordered resolution passes, each rendering the string leaves it is
responsible for and handing the tree to the next. The document is never
dumped back to YAML text and never parsed again: a pass is a function over
the parsed tree (`fn(tree, *, addl, cycles) -> tree`, the registry in
[`helpers/resolution_stages.py`](src/cs_image_system/base/helpers/resolution_stages.py)).
A template renders to text, and that text stays a string: `port: "{{
config.port }}"` over `port: 22` is the string `'22'` until the field it
lands in is structured (a declared integer field coerces it; a free-form
mapping keeps the text). A leaf without a tag keeps the type the file gave
it, and a document with no tag at all passes through untouched. A mapping
keeps the key order its file gave it, so a free-form mapping an emission
writes as it is (an image's `tags`) comes out in the file's order (an older
loader began by dumping the document to YAML text, whose dumper sorted
every mapping's keys). The passes:

1. `interpolate` renders Jinja tags against `ENV` (the process
   environment), `execution` and the document's own `config:` map.
   `execution.timestamp` is the run start formatted with the tree's
   `dateformat` (default `%Y%m%d_%H%M%S`, `DEFAULT_DATEFORMAT` in
   [ia_config.py](src/cs_image_system/base/models/ia_config.py), the same
   default the model carries); `execution.date` is the ISO
   date; `execution.dateformat` is the format string.
2. `scope-this` renders, per plugin key (`runtime_builders`,
   `os_builders`, ...), with `this` bound to the nearest enclosing mapping
   and `this.parent` to the mapping that owns it. `config` is scoped the
   same way: a top-level item's own `config:` is merged over the
   document's `config:` for that item, and a NESTED mapping's
   own `config:` (an OS builder's `runtimes[]` entry, for example) is
   merged over the enclosing one for its subtree, key by key, so
   `{{ config.x }}` in the entry's `description` resolves from the entry's
   own `config` first (`_render_scoped` in
   [`template_utils.py`](src/cs_image_system/base/template_utils.py)).

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

Field factories in the contract's `fields.py` stamp metadata that the
run's `TemplateResolver` acts on. The resolver is one per run: the loader
makes it over the run's registry (`TemplateResolver(reg, addl=...,
converter=...)`), it holds the flat map of the run's structured models
and the run's converter (`PydanticConverter(reg, image_sources)`), and
the context carries it as `ctx.template_resolver`. The converter hands
every model it structures the run's registry and image-source catalog
(pydantic's validation context, a `ModelBinding`), which the model keeps
(`NameTyped.bind_run(reg, image_sources)`; `on_bound()` is where a model
checks what needs them). `TemplateResolver()` with no argument, the
process-wide resolver, and the `Orchestrator` class that handed out a
converter are gone: use `ctx.template_resolver` and its `.converter`.
The kinds:

| Factory | Kind | Behaviour |
| --------- | ------ | ----------- |
| `fk_field(target, also_set_on_update=None, ...)` | `fk` | The value names an object of classification `target`. A `default` value resolves to the registered default. In templates the field name yields the object itself (`{{ runtime.get_default_machine_type() }}`). With `also_set_on_update`, the named attribute (used as `model_id`) is set to the target's `global_id` and `builder` is put in the template context. |
| `templated_field(replace_value, ...)` | `templated` | When the value is `default`, `replace_value` (a Jinja string) is rendered in its place. |
| `deferred_list_field(builder_vct, item_vct)` | `deferred_list` | A list of mappings structured late, after every builder is registered: each entry's `type` selects a builder of `builder_vct`; the entry is structured as the item class registered under `item_vct` for that builder's type, else the owning model's `get_subitem_overrides()` entry for `item_vct`, else `item_vct`'s default model (the item model a plugin's metadata injected as that classification's default, such as the base's `storage_mapping`). Used for `modifications:` and `storages:`. |
| `deferred_list_fk_field(target)` | `deferred_list_fk` | A list of foreign keys resolved late. |
| `parent_field(target, ...)` | `fk` | The `_model_id` of an item that holds its parent by reference: the parent's global id, never a YAML key. It is the one foreign key the resolver never defaults: unset means the item is not parented yet, and the model that holds the item in its list sets it (an OS builder model and an image in their own construction, a deferred list's owner when it enters the item, the loader for a group or a user by its `type`: `parent_by_written_type` for a written one, `parent_by_default_type` for one left at `default`, right after the item is structured and before it is entered in the flat map, so the key it is entered under names its parent). The registry's default for `target` would name another builder for every item but the default's own. |

A plugin may register a new kind and stamp `field_kind` metadata on its own
fields.

### Template resolution

After structuring, the run's resolver (`ctx.template_resolver.resolve_all()`) renders, up to five
passes, every string and mapping field that still contains `{{`, and
every templated string value of a plain mapping in its map (the run
scopes `execution` and `ENV`). Every one of those renders inherits its
inputs' encryption: a value derived from a decrypted one comes out of
the resolution carrying a ciphertext built from its pieces
(`mark_plaintexts`), so the emission writes `ENC[age:...]` where the
plaintext was.

A pass that changes nothing ends the resolution. A template whose
rendering feeds another needs one pass per link, so a chain longer than
five, or a template that renders to a new template every time, is still
unrendered when the fifth pass ends: then a WARNING names each field
the passes worked on that still holds `{{` (the object's flat-map key, a
model's global id or a run scope's name, and the field), once per field
for the run's resolver, never its value. The field keeps what the last
pass left and the run goes on. A replace template that names something
not yet defined is logged as an error and tried again in the next pass;
one that does not compile is logged the same way and fails the load.

A change is measured against what the field held when the pass began.
A templated field that holds `default` gets its replace template back
in every pass and is rendered again, so a value its inputs gained since
can still reach it; a rendering back to `default` is not a change, so
such a field (an image builder subconfig's `machine_type` when no
machine type is named anywhere) holds no pass open. The resolver keeps
the number of passes each call made (`passes_made`).

Each object renders in a `SmartContext` that exposes:

| Name | Value |
| ------ | ------- |
| `this` | The object being resolved. |
| every `fk` field name | The referenced object (or the raw id when unresolved). |
| `builder` | The model a resolved `also_set_on_update` foreign key names: for a group or a user, the builder model its `type` names (its parent); for an entry of an image's or a base image's `runtimes` list, the owning image or base image, because the entry's own parent field (`_model_id`) declares `also_set_on_update`, so an entry's templates can write `{{ builder.<field> }}`. That declaration on the parent field is not a no-op: without it an entry's context has no `builder`. A storage's `type` declares none (a storage holds no parent), so a storage's context has no `builder`. |
| `image`, `instance`, `group`, `user`, `storage`, `storagemapping` | The object itself, injected under its own lower-case class name (`SelfInjectedNameProtocol`). |
| `this.identified_model` | On sub-items, the parent model. It is a property, not a field, so it is reached through `this`; a bare `identified_model` names nothing in the context and a template that writes it is kept as written. |
| `execution`, `ENV` | The run values and the environment. |
| any `global_id` | Every registered object, by id. Hyphen and underscore spellings of a key are tried interchangeably. |

Examples from the fixture: `description: "{{ group.name }} group"`,
`email` derived from a builder's `default_user_email_template`
(`{{ user.name }}@example.invalid`), `OS: "{{ this.parent.family }}"` in an
OS builder's tags, `systemuser: "{{ ENV.USER }}"` in `config:`.

### Naming rules

`safe_name()` strips whitespace, replaces spaces and `:` with `_`, and
lower-cases. Every `name` and alias is normalized this way; `display_name`
keeps the original spelling for output. A name or alias may not contain
`/` or `\`, and may not be one of the reserved words of
`OOPS_DEFAULTS` -- `default`, `self`, `none`, empty or `None` -- in any
case or spacing, because those words mean "not set" wherever a value is
read: an item named after one would be unreachable, and a reference to
it would mean something else. The rule is held twice:
[`reserved_names.py`](src/cs_image_system/base/reserved_names.py)
refuses such a `name:` at any depth, and such an `aliases:` entry, where
each configuration file is read -- every `cfg/` file, every item file
after decryption, every overlay -- naming the file, the entry's place
and the word; and `NameTyped` / `RootItem` refuse it again when a model
is built, the backstop for objects made in code. A REFERENCE written
`none` is a different matter: a foreign key takes its default only when
the value equals the field's own default (`field_set_to_default`), so
`default` resolves and `none` names nothing -- `validate` refuses it
(`check_foreign_keys`; the tofu-roots state-location validator for a
state backend) with what to write instead. A field that gives `none` a meaning of its own (`update:
{policy: none}`, `--only none`) tests for the word by name, never
through the list. An alias equal to the name is dropped. `super_safe_name()` additionally
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
image builder and none is the default, and then names the image), `ssh_username` (`default`), `image_identifier`, `machine_type`
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
registers under `PROVIDER_SPECIFIC_IMAGE` with the key
`<source>::<runtime>`; `get_query_assets()` returns provider query inputs.
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

1. Check the `--only` names first (an image name or an OS builder, or
   `<image>@<runtime>` with a configured runtime; `none` alone means an
   empty bake surface and is no name to check). An unknown name returns
   a failed summary with nothing requested, and that is all: no hook
   plugin is loaded, nothing on the context is reset, and nothing is
   written, recorded or handed to the on-summary hooks. Otherwise: load
   hook plugins; reset the "generated this run" set, the bake decision
   cache and the bake surface (`only_images`, `force_bake`); write the
   root `generated/.gitignore` (the merged policy plus the run-local
   file names). A `--migrate-state` under a dry run is refused here,
   before the state query.
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
   generator, after hooks), run after-generate hooks (the tofu-roots
   plugin's records every generated terraform root's resolved state
   location in `meta-state/state-locations.yaml`; a root migrating this
   run keeps its old record until the migration's `finish` step), then
   write the runner script if any deferred command was recorded. A
   lifecycle with no deferred work leaves no script.
6. Collect the state-isolation evidence from the state-bindings hooks
   into the summary's `state_bindings`, then write
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
way, with the overlays that declare items left out.

**System CLI steps run in the running process.** The executor hands a
step whose binary is the system's own CLI to the runner the system
package registers in [`in_process.py`](src/cs_image_system/base/in_process.py)
(`register_system_cli_runner`; the base never imports the system, so the
registration goes that way round), and the runner drives the command in
this process over the loaded context: the configuration is loaded once
per run, not once more per step. The teardown step is the one that
cannot read the loaded context, because other overlays are another
configuration; the runner runs it in this process too, as a nested run
over a second context it loads from the step's own arguments. Nothing of
a load is kept by the process, so the two runs share nothing
([the test](../../tests/test_nested_run_in_this_process.py) holds the
nested run to what a child process did). With no runner registered (an
embedding without the CLI), and for a step a runner declines (the
system's declines none), `run_executable` spawns the step as the
executable itself does. The committed scripts keep every such step as a
command line.

**`--commit`.** `commit_meta_state` stages `meta-state/` and the generated
tree, skips any path git ignores, never stages the refused names (plans,
state, tfvars, `.envrc`, key material), scans every file about to be
staged with the public-safe rules and the tree's allowances, refuses the
whole commit on a finding, and commits only those paths with a message
naming the run id and lifecycles. It returns the commit sha, or `None` when
nothing changed or the root is not in a git repository.

## The run context

Source: [`run_context.py`](src/cs_image_system/base/run_context.py) (the
context), [`config_loader.py`](src/cs_image_system/base/config_loader.py)
(the loader that makes one), [`finalizer.py`](src/cs_image_system/base/finalizer.py)
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
| `plugin_state(key, factory)` | The one object a library or plugin keeps for this run under `key`: made by `factory` on the first ask, the same object after, gone with the context. |

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

## Meta-state

Source: [`meta_state.py`](src/cs_image_system/base/meta_state.py).

Meta-state is the set of committed, human-readable YAML files under
`<root>/meta-state/` that carry memory between runs. It sits outside every
generated directory, so a lifecycle wipe never touches it. Reads are lazy
and cached; writes are atomic per file and refused when a hard public-safe
rule matches the content.

The module owns the read-models (`identity.yaml`, `storage.yaml`:
structural facts only, gids travel by terraform reference), the
authoritative storage state machine (`storage-state.yaml`, where a
destroyed-to-active transition increments the generation), the lineage
and pin records (`lineage.yaml`, from which a disposal removes the
record, and `pins.yaml`, where every pin move is journaled under
`upgrades` with its `op`), the launch parameters (`launch-params.yaml`),
the run journal (`runs.yaml`, bounded to the last 200 runs), the
verdicts (`verifications.yaml` and `login-proofs.yaml`, bounded to the
last 500; `image-tests.yaml`; `mod-tests.yaml`, keyed by content hash),
the releases (`releases.yaml`), the state locations and every performed
move (`state-locations.yaml`: the record, not the emission, is what the
move guard compares against), the instance generations
(`instance-state.yaml`, from which nothing is ever deleted) and the alias
pool (`aliases.txt`: not a record but a pool of free names, one per
line; the run that launches a new durable machine comments the first
free line out as `# <name>  -- instance <i> as <hostname> <time> run
<run>`; an absent file means no aliases and no error). What each file
holds and which step writes it is the one table under
[Meta-state in OPERATIONS](../../docs/OPERATIONS.md#meta-state-config-rootmeta-state).

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

The emission under `generated/` carries the ciphertext a `Decrypted`
remembers (emission by reference), and
[`materialize.py`](src/cs_image_system/base/materialize.py) replaces it
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

## The public-safe gate

Source: [`public_safe.py`](src/cs_image_system/base/public_safe.py).

One scanner sits behind the meta-state commit, every meta-state and
state-report write, the `public-safe` command and a pre-commit hook. It
reads bytes; a zip (a saved `tfplan`) or a gzip member is opened and its
members scanned.

**Refused by name at any depth** (`REFUSED_PATHS`): `tfplan`, `*.tfplan`,
`*.tfstate`, `*.tfstate.*`, `*.tfvars`, `*.tfvars.json`, `.envrc`, `*.pem`,
`.private_key.*`, `.public_key.json`.

**Hard rules** (apply everywhere). The scan carries the shapes that are
the same whoever issued them; each installed runtime plugin adds the
shapes of its own cloud's keys through the contract's `secret_patterns()`
hook (`hard_rules()` gathers them, loading the plugins if nothing has),
so the core names no cloud and a new runtime brings its own shapes:

| Rule | Shape | Declared by |
| ------ | ------- | ------ |
| `jwt` | `eyJ` followed by 20 or more token characters | the scan |
| `pem-private-key` | `-----BEGIN ... PRIVATE KEY-----` | the scan |
| `slack-token` | `xox[baprs]-...` | the scan |
| `github-token` | `gh[pousr]_...` | the scan |
| `age-identity` | `AGE-SECRET-KEY-1` plus 58 characters | the scan |
| `tfvar-assignment` | `TF_VAR_<name>=<literal>` (an assignment from `$VAR` passes) | the scan |
| `pkrvar-assignment` | `PKR_VAR_<name>=<literal>` (the same rule for packer) | the scan |
| `aws-access-key` | `AKIA` or `ASIA` plus 16 upper-case alphanumerics | the aws-runtime plugin |
| `gcp-service-account` | a `private_key_id` with a long hex value (the key body itself is a PEM block the scan's own rule refuses) | the gcloud-runtime plugin |

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
one grace: an unreleased pin is admitted while it is the
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
and destroyed through the gate. That step is a run nested in the one that
deferred it: it executes in the same process, over a context of its own
(its own registry, run id, journal entry and summary), and its exit code
is the step's, so a teardown that fails fails the `retention` lifecycle.

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

## The terraform modules

Every terraform module a builder emits a `module` call against
(`aws_instance`, `gcp_storage_pd`, `docker_volume`, `okta_opa_module`, ...)
is package data inside the plugin that owns it, under that package's
`tfmodules/` directory; the core ships the neutral one,
[`bootstrap_github`](src/cs_image_system/base/tfmodules/bootstrap_github).
A plugin declares its directory with one entry point in the contract's
group `cs_image_system.modules`
([`contract/modules.py`](../contract/src/cs_image_system/contract/modules.py)),
the value `<package>:<dirname>`:

```toml
[project.entry-points."cs_image_system.modules"]
modules = "cs_image_system.aws_runtime:tfmodules"
```

[`modules.py`](src/cs_image_system/base/modules.py) is the one API over
that declaration. `installed_modules()` reads the entry points and returns
every module by directory name (`ModuleSource`: the name, the namespace the
distribution's name yields exactly as a plugin's registrations do,
the distribution, its version, the directory), importing no plugin code
and refusing a name two distributions ship. `materialise_modules(dest,
force=..., overrides=..., only=...)` writes them into a tree's modules
directory and stamps every copy with `.csis-module` (`plugin`, `release`,
`hash`: `content_hash` over the copy's files, the stamp excluded); the
report (`ModulesReport`: `written`, `refreshed`, `adopted`, `kept`,
`skipped`, `refused`, with `lines()`) says what happened to each. The
rules: an absent copy is written; a stamped copy whose content is still
what its stamp says is kept when it is the release's and refreshed when it
is an older release's; a stamped copy edited in the tree is refused by
name, `force` or not; an unstamped copy is adopted when identical to the
release's and refused otherwise (`force` replaces it); a module named in
`overrides` (the keys of `config: module_sources`, which
`declared_overrides(config_root)` reads from the raw `cfg/_config.yml`)
is skipped. `cs-image-system modules [--write DIR] [--force]` is the
command over it, and `init-config` uses it for a tree's copies.

The emission reads none of this: `module_source` in `utils.py` resolves a
call's `source` from `config: module_source_base` (every module) and
`config: module_sources` (one module at a time, the entry being the
module itself), so a tree may hold a copy, source a module from
elsewhere, or edit a copy and keep the edit by naming it.

## Other modules

| Module | Purpose |
| -------- | --------- |
| [`modules.py`](src/cs_image_system/base/modules.py) | The installed terraform modules (`installed_modules`, from the `cs_image_system.modules` entry points, no plugin import), their materialisation into a tree with a stamp per copy (`materialise_modules`, `Stamp`, `content_hash`, `ModulesReport`) and the names `config: module_sources` declares (`declared_overrides`); see [The terraform modules](#the-terraform-modules). |
| [`state_query.py`](src/cs_image_system/base/state_query.py) | Asks every plugin for reality (images by lineage tags, storages by name, groups by gid), diffs it against meta-state, and classifies drift as `missing`, `foreign`, `changed` or `stale`. Hard drift (a pinned build gone, a storage recorded live but absent, a managed group unknown to the provider, an instance pinned to an unrecorded build) makes the next run's validation refuse. `import_foreign` adopts foreign artifacts into meta-state; nothing here writes to a cloud or to terraform state. The report is `generated/state-report.json`. |
| [`storage_state.py`](src/cs_image_system/base/storage_state.py) | The storage state machine: legal transitions (`active` to `archived` and back, either to `destroyed`, and regeneration of a destroyed name), the rule that a storage must be unattached to leave `active`, transitions for undeclared storages, and the recording of applied transitions. |
| [`v2_validation.py`](src/cs_image_system/base/v2_validation.py) | Generation-time rules, all hard: managed groups may not disappear; allowed groups exist; the strict attach rule; single-attach cardinality; data lifecycles only where the builder realizes them; storage transitions are legal; an instance image's group exists and every instance image has one; declared types resolve to configured plugins; admin keys are public keys; every base image has a debug path (keys or a session mechanism); capability resolution on both axes; test specs use the known vocabulary; update policies are valid. |
| [`image_tests.py`](src/cs_image_system/base/image_tests.py) | In-bake assertions emitted as the last packer provisioner: capability verification derived from plugin hooks, plus a declared `tests:` map with keys `files`, `packages`, `commands`, `services_enabled`, `users`. `tests.post_bake` adds `mounts` and runs on a launched instance. |
| [`mod_tests.py`](src/cs_image_system/base/mod_tests.py) | Runs every modification of an instance image against a throwaway local target twice (apply, then idempotence), recording results in `meta-state/mod-tests.yaml` by content hash. The harness drives an abstract `LocalTarget` (`exec`, `copy_in`, `diff`, `volatile`, `close`, and the ansible connection plugin that reaches it) and names no runtime: the target's factory comes from the one registered runtime builder class whose `local_test_target()` is not None, is handed the tree's executables, and returns nothing when its daemon does not answer (the modifications are then `skipped`, not failed); a target that cannot start raises `ContainerStartError` (`unstarted`). |
| [`identity_attributes.py`](src/cs_image_system/base/identity_attributes.py) | Declared provider attributes on users and groups: validation per plugin, a plan written to `generated/identity/attributes-plan.json`, a read-only probe, and an apply that is deliberately disabled. |
| [`read_models.py`](src/cs_image_system/base/read_models.py) | Writes the identity and storage read-models and records applied storage transitions. |
| [`commands/preflight.py`](src/cs_image_system/base/commands/preflight.py) | The session lines: asks every declared runtime's and state backend's class the contract's `session_status` hook over the loaded models (a state builder of the kit, a `StateBuilderBase`, is also handed the run's runtime builder classes, `ctx.reg.runtime_builder_classes()`, as a third argument, so a backend that borrows a runtime's session reading finds it there) and judges the answers against the expected run length; reads no credential cache itself and names no provider. |
| [`commands/gate.py`](src/cs_image_system/base/commands/gate.py) | The apply gate over a `tofu show -json` plan: every planned destroy must match a whitelisted address or prefix; a plan file older than the newest `.tf` in its root is stale. |
| [`commands/upgrade.py`](src/cs_image_system/base/commands/upgrade.py), [`commands/dispose.py`](src/cs_image_system/base/commands/dispose.py), [`commands/restamp.py`](src/cs_image_system/base/commands/restamp.py), [`commands/relabel.py`](src/cs_image_system/base/commands/relabel.py), [`commands/verify_instance.py`](src/cs_image_system/base/commands/verify_instance.py), [`commands/unmount.py`](src/cs_image_system/base/commands/unmount.py), [`commands/runtime_facts.py`](src/cs_image_system/base/commands/runtime_facts.py), [`commands/identity_gids.py`](src/cs_image_system/base/commands/identity_gids.py), [`commands/run_scope.py`](src/cs_image_system/base/commands/run_scope.py) | The operations behind the CLI's `upgrade`, `dispose image`, `lineage restamp`, `lineage relabel`, `verify instance`, `unmount storage`, `runtime describe` / `empty`, `identity export-gids`, and the bake scope check. |
| [`in_process.py`](src/cs_image_system/base/in_process.py) | The seam through which a deferred step that is the system's own CLI runs in the running process: the system package registers its runner (`register_system_cli_runner`), `run_executable` asks for it before it spawns anything, and `names_subcommand` is how a runner tells a nested `run` (which needs a context of its own) from every other step. No runner registered, or a step declined: the step is spawned. |
| [`utils.py`](src/cs_image_system/base/utils.py) | `safe_name`, `super_safe_name`, `system_cli_executable` (a deferred call of the system's own CLI), `apply_enabled` / `apply_flag_allows` (the `apply_<lifecycle>` rule), `module_source` and `module_source_overrides` (a call's source from `module_source_base` and `module_sources`), `hcl_expr` and `render_module_call` (terraform module call rendering). |
| [`ansible_launch.py`](src/cs_image_system/base/ansible_launch.py) | Renders the same launch parameters as an ansible inventory and playbook: the hostname task, each mount's tasks from its storage builder's `launch_tasks()`, the enrollment kind's tasks; `extra_vars(ctx)` is the playbook's variable list, the same names as the launch template's. |
| [`power_state.py`](src/cs_image_system/base/power_state.py) | The system's power-state vocabulary (`running`, `stopped`, `suspended`, `starting`, `stopping`, `absent`, `unknown`; `None` is "cannot answer"), `wait_until_reachable`, and `running_for_task`, the one bounded exception under which a stopped machine is started for work that needs it and stopped again afterwards. |
| [`generations.py`](src/cs_image_system/base/generations.py) | Instance generations: one per machine, opened `inferred` by a launch and confirmed `observed` (or closed as `replaced-out-of-band`) by the provider's instance id after a real apply; a machine launched before the record existed is `adopted` as generation 1 of it. |
| [`alias_pool.py`](src/cs_image_system/base/alias_pool.py) | The pool of pre-approved names in `meta-state/aliases.txt`: a new durable machine's alias is the first free line, burnt in place under an exclusive lock by the run that can launch it. |
| [`provider_aliases.py`](src/cs_image_system/base/provider_aliases.py) | After a real instance-image apply, gives each launched, running instance that its group's registry lists the names it lost at boot back (the bare declared name, the pool alias, the provider's `ip-...` label), skipping every collision and every silent registry; a machine with no record of its own (none carries its provider id: it has not enrolled) is passed over with an INFO line carrying the module's `NOT_LISTED`, and one this run launched is waited for first, bounded: the core decides the names, the machine and the moment, and the group builder's `alias_registration_script` renders the script that tells its agent (the core reads only the contract's `ALIASES_CHANGED` / `ALIASES_UNCHANGED` from its output); and the `reality.instances` entries and notes of the state report. |
| [`workload_access.py`](src/cs_image_system/base/workload_access.py) | After a real identity apply, reconciles each managed group's CI login policy through the group builder and records the outcome in the identity read-model. |
| [`reserved_names.py`](src/cs_image_system/base/reserved_names.py) | The read-time refusals: `refuse_reserved_names` (a `name:` at any depth, or an `aliases:` entry, that is a word of `OOPS_DEFAULTS` in any case or spacing, every one listed with the file, the entry's place and the word, `ReservedNameError`) and `refuse_invalid_config_keys` (a key of a document's top-level `config:` that is in `INVALID_CONFIG_KEYS`, `InvalidConfigKeyError`). Called by `read_and_process` for each `cfg/` file, by the item-file reader after decryption, and by `load_overlay`; pure functions of the parsed document, no identity or network. |
| [`materialize.py`](src/cs_image_system/base/materialize.py) | The private mirror `_private/` beside `generated/`, at the same depth: a root is copied there with every `ENC[age:...]` marker replaced by its plaintext before a deferred command runs, incrementally; only `.terraform.lock.hcl` is ever copied back. `ensure_ignored` appends `_private/` to the configuration root's `.gitignore`. |
| [`commands/login_proof.py`](src/cs_image_system/base/commands/login_proof.py) | The login proof's driver: which declared instances are targets (launched, not ephemeral, on the runtime asked for), the skips (a group whose builder has no login to prove; a machine that is not running, never started for this), the group builder's own `login_checks` over each target, and every verdict recorded in `meta-state/login-proofs.yaml`. The command that drives it (`verify login`) is mounted by the identity plugin whose client logs in. |
| [`commands/state_migration.py`](src/cs_image_system/base/commands/state_migration.py) | The runner steps of `--migrate-state` (`begin`, `finish`) and the same-day state `backup` a runner takes into `_private/state-backups/` before any `state rm` it decided on. |
| [`pinned_release.py`](src/cs_image_system/base/pinned_release.py) | Holds a committing run, and a committing `lineage restamp`, to the release the tree pins in `.csis-version` (`hold_to_pin`, called by `run` before it generates and by the restamp before it computes; each speaks under its own name, `RUN` / `RESTAMP`; a disposal is not held): refused when the version running is not the pin, or when any distribution of the system was installed from somewhere other than an index (`installed_release` reads each dist-info's `direct_url.json`, which an index install never carries), unless `--allow-unpinned` / `CSIS_ALLOW_UNPINNED` says to go on. Pure functions over the tree's root and the install facts; no run context. |

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
to `unavailable`, never dropped from the report. What
the core needs outside itself is therefore short, and each item says how
the core finds it.

- **Python 3.13 or later and the workspace.** `requires-python = ">=3.13"`
  in [`pyproject.toml`](pyproject.toml); `just init` (`uv sync`) installs
  this package and every plugin beside it. The dependencies are the six
  named at the top of this file; nothing else is imported at runtime except
  the standard library. The core imports no terraform library: what the
  roots need of [hashicorp-utils](../hashicorp-utils/README.md) and
  [tofu-roots](../tofu-roots/README.md) reaches the run through hook
  plugins and the context's plugin state (below).
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
  [contract-example-plugin](../contract-example-plugin/README.md),
  [default-os-plugin](../default-os-plugin/README.md),
  [docker-runtime-plugin](../docker-runtime-plugin/README.md),
  [dummy-plugin](../dummy-plugin/README.md),
  [gcloud-runtime-plugin](../gcloud-runtime-plugin/README.md),
  [gcs-state-plugin](../gcs-state-plugin/README.md),
  [local-state-plugin](../local-state-plugin/README.md),
  [okta-opa-plugin](../okta-opa-plugin/README.md),
  [packer-plugin](../packer-plugin/README.md),
  [posix-identity-plugin](../posix-identity-plugin/README.md),
  [tf-docker-plugin](../tf-docker-plugin/README.md),
  [tf-ebs-instance-plugin](../tf-ebs-instance-plugin/README.md),
  [tf-gcp-plugin](../tf-gcp-plugin/README.md),
  [tf-s3-state-plugin](../tf-s3-state-plugin/README.md).
- **Nothing of hashicorp-utils.** The core imports no terraform
  library. The state-location check, the state-location records and the
  runner headers' state bindings are the
  [tofu-roots](../tofu-roots/README.md) hook plugin's, reached through
  the run hooks above; a workspace without it validates and runs with
  no state-location check and an empty `state_bindings`.
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
  session lines of every run read credential CACHES, never values, and
  the core reads none of them itself: each runtime's and state backend's
  class answers the contract's `session_status` hook with what it read
  (the AWS plugin a profile's SSO token cache under `~/.aws`, or
  `CSIS_AWS_DIR`; the GCP plugin the Application Default Credentials file,
  for presence and `type`; the docker plugin its daemon's answer), and
  `preflight` prints and judges the answer. `OPA_TOKEN` decides whether a
  login proof is recorded `as: workload` or `as: client`; the core never
  reads its value. `USER` (else `USERNAME`) names the operator in an
  `unmount --confirm` receipt. A credential-shaped variable (`TF_VAR_*`,
  `CSIS_*`, `OKTA_*`, plus every prefix the installed runtimes declare
  through `credential_environment_prefixes()`: `AWS_*`, `GOOGLE_*`,
  `CLOUDSDK_*`, `DOCKER_*`) that is set but EMPTY is reported by name by
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
seventeen plugin READMEs linked above. Every model is a pydantic dataclass
with `extra="forbid"`: an unknown key is refused at load.

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
[`reserved_names.py`](src/cs_image_system/base/reserved_names.py)).
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
[`commands/preflight.py`](src/cs_image_system/base/commands/preflight.py):
a session expiring within the window is `blocking` -- `preflight
--strict` and `state query --strict` exit 1, a run warns; read raw before
the load, so never encrypted; a non-integer falls back to 30). Any other
key is carried for plugins (`okta_gateway_selector` is the identity
plugin's) and usable as `{{ config.<key> }}` in `cfg/` strings. Each
key's type, default, reader and effect is the table in
[CONFIGURATION section 2.3](../../docs/CONFIGURATION.md#23-config-keys-the-code-reads).

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
  needed (`refuse_markers_at`); a `name:` at any depth or an `aliases:`
  entry that is a reserved word is refused, every one listed with the
  file, its place and the word (`refuse_reserved_names`, which also runs
  on each item file after decryption and on each overlay); a key of the
  document's `config:` that is one of the seventeen words of
  `INVALID_CONFIG_KEYS` is refused naming the file and the key
  (`refuse_invalid_config_keys`, also on each overlay).
- **Decryption** (`decrypt_tree`): every whole-value marker opens with an
  identity from `CSIS_CONFIG_IDENTITY`; no identity, or no identity that
  opens the value, or a marker embedded in a longer string, is refused
  naming the value's path.
- **Every model** (`CSIS_MODEL_CONFIG`): unknown keys are refused; a
  `parameters` key on a builder is refused naming `variables:`; names and
  aliases may not be a reserved word (`default`, `self`, `none`, empty or
  `None`), nor contain `/` or `\`; each plugin key's entries need `name` and `type`; an unknown
  `type` is a `KeyError`; exactly one `is_default` per classification
  (`No default builder found` / `Multiple default builders found`); a
  duplicate builder name; a builder's `runtime` must resolve; a
  `RuntimeBuilderModel` needs `default_machine_type`; networking needs a
  `network`, at least one subnet and exactly one default subnet; an OS
  builder needs at least one `runtimes[]` entry with unique image
  builders (an OS builder entry may not declare `image_name`, nor an
  `update` that is not a mapping); a `rhel` OS builder's
  `family_version` major must be 8, 9 or 10 (whatever the update
  policy); an image needs `source_image` and at least one `runtimes[]`
  entry; an instance may not declare `groups`; a storage mapping needs a
  non-empty `mount_point` and a positive `min_size`; a storage refuses
  `ALL`, an unknown `state` and an unknown `share_mode`; a group's `gid`
  must be an int of at least 1024 or a deferral; a user needs non-blank
  `first_name` and `last_name` and may not have aliases; an executable's
  name may not be a default placeholder and must be unique; `last_updated`
  in `cfg/_config.yml` is an unknown key. An instance with
  no `image` logs the warning `Instance '<name>' does not have an image
  specified; the load refuses it when the configuration finalizes.` while
  it is structured, and its `finalize()` then refuses it.
- **After the items are read**: exactly one group is `is_root: true`;
  every group member is a declared user (`_validate_groups`); every item's
  `type` resolves to a configured builder, or to the registered default
  when the field allows it; every foreign key that resolved to nothing is
  returned by the object stage's resolution pass and carried on the run
  context (`ctx.unresolved_foreign_keys`, the object, field, value and
  target of each) for `validate` to refuse.
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
| state locations | `state_location_problems` in the [tofu-roots](../tofu-roots/README.md) hook plugin, a registered validator | a root (or its runtime) naming state backend `none`, which would otherwise read as unset and put the state on the DEFAULT backend -- there is no "no backend": declare one of type `local`, or leave the field out; a root naming an undeclared backend; two roots sharing one state object; a root whose location moved while resources stand in it (the fix is `--migrate-state`) |
| foreign keys | `check_foreign_keys` | a field that names no object of its classification, naming the object, field, value and what is declared; a field written `none`, which names nothing (it is not the field's default, which resolves only by equality), with the remedy: leave the field out, or write `default` |
| availability zones | `check_availability_zones` | a zonal storage in a zone other than its runtime's; an instance, its zonal storages and its runtime's subnet asking for more than one zone |
| bake users | `check_bake_users` | an OS builder entry or image entry whose bake user nothing names; on a runtime with one user per chain (GCE), an image naming a user other than its chain root's |
| label keys | `check_label_keys` | a tag key on an image, instance or storage that its runtime cannot take as a label (GCE: a lowercase letter first), named with who declared it |
| state backend executables | `check_state_backend_executables` | a state backend whose declared `executable` is not in the executables list |
| the alias pool | `check_alias_pool` | a free line that is not an RFC 1123 label, repeats another, or is a name an instance already has; remaining names logged, an empty pool warned |
| canonical hostnames | `check_canonical_hostnames` | a hostname over 63 characters, with characters outside letters, digits and hyphens, or starting or ending with a hyphen |
| policies | `validate_policies` | `parent_policy` / `image_policy` not `pinned` or `follow`; `retention` not `{keep: <non-negative int>}`; `release` not `{model: <name>}`; `retention_keep` not a non-negative int; `on_failure` not `keep` or `teardown`; a `teardown_after` not `<n>m|h|d` |
| test specs | `validate_test_specs` | unknown `tests` keys, a `files` entry without `path`, a `commands` entry without `run`, a `post_bake` that is not a map or has unknown keys, a `mounts` entry that is not absolute |
| update policies | `validate_update_policies` | an `update` that is not a mapping (from YAML the load refuses it first); `packages` without packages or pins; a package both updated and excluded; a non-positive `refresh_days` |
| identity | `validate_identity` | a group the read-model records as managed that is missing from the YAML |
| storages | `validate_storages` | an unknown allowed group; an instance attaching a group-gated storage its image's group is not allowed (or with no owning group); a data lifecycle the builder cannot realize; a single-attach storage attached by several instances (naming the multi-host builders on that runtime); every illegal transition (a new storage not starting `active`, an illegal pair, a transition while attached, `archived` on a builder without archive support, an undeclared storage whose record names no root, an attachment of an unknown or non-active storage) |
| image groups | `validate_image_groups` | an image naming an unknown group; an instance whose image has no group |
| base images | `validate_base_images` | an identity or storage type no configured plugin provides; an admin key that is not one OpenSSH public-key line (private material is named as such); an empty `admin_user`; a base image with neither an admin key nor a session mechanism on a runtime (the N9 dead end) |
| capabilities | `validate_capabilities` | an image that does not chain to a base; a group with no identity builder; an identity type or attached storage type the root base does not carry (resolved through the pins to the stamped build, else the declaration) |
| identity items | `validate_identity_items` | whatever the owning user or group plugin's `validate_user` / `validate_attributes` returns |
| immutability | `validate_immutability` | a launched instance whose launch parameters changed, unless a replacement is pending, a follow target exists, or the only change is a removed mount |
| claimed hostnames | `validate_claimed_hostnames` (only when the instance-image lifecycle is requested AND `apply_instances` allows the root AND the run is not a dry run) | an unlaunched instance whose canonical hostname is already registered; a launched one with more than one registration; a registry that could not be asked |
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
  runtime for the vendor image (by query, or by id when the entry pins an
  `image_id`); no image builder, no runtime builder, no resolved
  identifier for an OS builder, or a pinned id the provider does not know
  raises and the lifecycle is recorded `failed`. Template resolution runs up to five passes; what
  still carries `{{` stays as written, and when the fifth pass still
  changed something each such field is named in a warning (see
  [Template resolution](#template-resolution)).
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
  [system's README](../system/README.md), and the sequence they sit in
  (`rm -f tfplan`, `init`, `prune-attachments`, `plan`, `gate-plan`,
  `apply-check`, `apply`) under
  [the apply gate in OPERATIONS](../../docs/OPERATIONS.md#the-apply-gate).
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
suite pins the rest of what this section describes; among them
[`tests/test_stale_attachments.py`](../../tests/test_stale_attachments.py),
[`tests/test_power_state.py`](../../tests/test_power_state.py),
[`tests/test_canonical_names.py`](../../tests/test_canonical_names.py),
[`tests/test_hostname_claims.py`](../../tests/test_hostname_claims.py),
[`tests/test_provider_aliases.py`](../../tests/test_provider_aliases.py),
[`tests/test_generations.py`](../../tests/test_generations.py),
[`tests/test_alias_pool.py`](../../tests/test_alias_pool.py),
[`tests/test_state_backends.py`](../../tests/test_state_backends.py)
(the single `dateformat` default, the command built once, a
zero-minute session is expired),
[`tests/test_login_proof.py`](../../tests/test_login_proof.py),
[`tests/test_workload_access.py`](../../tests/test_workload_access.py)
and [`tests/test_identity_plan_in_mirror.py`](../../tests/test_identity_plan_in_mirror.py).
`just test` is the acceptance bar.

## When it fails

Incidents -- what a live run showed, what it meant and what the system
does about it now -- are recorded once, newest first, on
[INCIDENTS.md](../../docs/INCIDENTS.md). This section keeps the symptom,
its meaning and the action to take, and links the story where there is
one; the table is the short form, and the messages the code writes, in
the order the operator meets them, follow it.

| Symptom | Meaning | Action |
| --- | --- | --- |
| `Error reading config file : <e>` and a traceback, exit 1, nothing generated | The load refused a declaration: an unknown key, a reserved name, a marker where none may stand, a marker no identity opens, a `type` no installed plugin registers | Read the line before the traceback; it names the file, the entry or the value. A refusal that still ends in a bare stack is a defect to report ([the ones made into one line so far](../../docs/INCIDENTS.md#refusals-that-surfaced-as-tracebacks)). |
| `validation: <exe>: binary '<b>' not found` / `<exe> <v> does not meet its requirement` | A declared tool is absent, or its version floor moved | Install or repoint it; in CI a failure naming a version means the floor moved. Every declared version is checked at `validate` and every run ([the checks that once never ran](../../docs/INCIDENTS.md#checks-that-had-never-run-versions-foreign-keys-playbooks-the-manifest)). |
| `validation: state: <class> <kind> <name> ... [HARD]` | Reality disagrees with the record: a pinned build gone, a recorded storage absent, a managed group the provider answered does not exist | Repair through `state import`, `upgrade`, `forget instance` or the provider, never by editing the record. A provider that could not be ASKED is an `unavailable:` line, never hard drift ([a lapsed key once read as five missing groups](../../docs/INCIDENTS.md#a-lapsed-opa-key-read-as-five-missing-groups)). |
| `run scope: bake(s) outside the apply scope [...]` | The bake surface is wider than the apply scope of a real run | Select images with `--only` / `--only-runtime`, or pass `--allow-unscoped-bakes` ([the scoped apply that baked on the other cloud](../../docs/INCIDENTS.md#an-apply-scoped-to-gce-baked-two-amis-on-aws)). |
| `apply: stale-script-skipped` in the summary | A runner script of a lifecycle not generated this run lies under `generated/` | Not an error; request the lifecycle to regenerate it ([the stale script that baked two unrecorded AMIs](../../docs/INCIDENTS.md#the-apply-step-executed-another-lifecycles-stale-runner-script)). |
| `storage-state.yaml` or `launch-params.yaml` claims a transition or a launch no apply produced | A reality-claiming recorder ran with its lifecycle's apply flag off | Every reality-claiming after-apply hook is gated on its flag; the state query's hard drift is what catches a wrong claim ([the recorder that claimed a reality no apply produced](../../docs/INCIDENTS.md#a-recorder-claimed-a-reality-no-apply-produced)). |
| `instance '<i>' is pinned to build <b> ... not a released build (no grace: <why>)` | `require_released_builds` is on and the pin is neither released nor the series head under its own proof | Release the build, `upgrade instance` back, or `forget instance` for a pin that outlived its machine; the flag is never switched off for a release ([the release grace](../../docs/INCIDENTS.md#the-release-flag-had-to-be-switched-off-by-hand-mid-release), [a pin that outlived its instance](../../docs/INCIDENTS.md#a-pin-outlived-its-instance)). |
| `canonical hostname '<h>' is already registered to <n> server(s)` / `could not check whether canonical hostname ... is already claimed` | Another registration answers to the name, or the registry was silent | Retire the stale registration; silence is never a free name ([three registrations of one name](../../docs/INCIDENTS.md#three-registrations-of-one-hostname-in-opa-one-live), [the hostname that failed silently at boot](../../docs/INCIDENTS.md#an-invalid-hostname-failed-silently-at-boot)). A dry run never asks ([it once did](../../docs/INCIDENTS.md#a-dry-run-asked-the-hostname-registry)). |
| `instance '<i>' cannot be in more than one availability zone: ...` | A zone is replace-forcing: the instance, its zonal storages and its runtime's subnet disagree | Fix the declaration, never the plan ([the zone change that planned to destroy a data volume](../../docs/INCIDENTS.md#a-zone-change-planned-to-destroy-a-data-volume)). |
| `instance '<i>' was launched (run <r>) and its launch parameters changed` | A launched instance is immutable | Replace it (`upgrade instance`, or decommission and redeclare); a removed mount and a `machine_type` change are the two sanctioned in-place changes. |
| `the machine bearing this name is <id2>, not <id1> -- generation ... closed as replaced out of band` | Something outside the system replaced the machine | The records match reality again; find out who did it. |
| `not reachable within 300s of its launch; no alias this run` / `not enrolled within 300s` | The new machine had not answered or enrolled when the alias pass ran | The next applies-on run gives the names back ([the first live replacement](../../docs/INCIDENTS.md#the-first-live-replacement-four-traps-in-one-afternoon)). |
| `note: instances/<name>: STOPPED (switched off; not drift)` | The operator switched the machine off | Nothing: only `verify instance` starts it, and stops it again ([a stopped machine once read as an unreachable cloud](../../docs/INCIDENTS.md#a-stopped-machine-was-reported-as-the-provider-could-not-answer)). |
| `retention debt: <b> (<series>@<rt>) would be disposed but an instance is pinned to it` | Declared retention would dispose a build still in use | Nothing, or release the build: a released build is kept by decision ([the ephemeral runtime that had no moment to release](../../docs/INCIDENTS.md#the-ephemeral-runtime-had-no-moment-to-release)). |
| `bake plan: <series>@<rt>: skip` for a `follow` child whose parent bakes this run | The parent's new head is not recorded at plan time | Nothing: `bake_reason` reads a parent that bakes this run as a move, kept out of the fingerprint on purpose ([the follow image that saw no move](../../docs/INCIDENTS.md#a-follow-image-baked-in-the-same-run-as-its-parent-saw-no-move)). |
| A `follow` child on an ephemeral runtime is due every run with reason `inputs changed` | The parent's build id changes every cycle by design, so a fingerprint over it could never agree with the record | The fingerprint hashes the parent's own fingerprint, never a build id ([the image that re-baked every cycle](../../docs/INCIDENTS.md#a-follow-image-re-baked-every-cycle-on-the-ephemeral-runtime)). |
| `instance <n> failed verification: <check>` on a build that baked green | An in-bake assertion that could not fail the bake | Package, storage and runtime assertions test and `exit 1` for themselves; re-bake ([the assertion that could not stop the bake](../../docs/INCIDENTS.md#a-false-in-bake-assertion-could-not-stop-the-bake)). |
| `verify assert` fails the run with the records describing a torn-down instance | Under the `teardown` policy the verdict must fail the run after the records match reality | The verdict fails the run from `forget_ephemerals`, after the forget ([the assert that failed the run after the teardown](../../docs/INCIDENTS.md#a-verify-assert-as-the-runners-last-step-failed-the-run-after-the-teardown)). |
| `user "<x>" is not present within group "<g>"` from the identity provider on refresh | A membership attachment in state that the provider no longer holds | The identity runner's `prune-attachments` step removes it after a state backup; a silent provider removes nothing ([the stale attachment that blocked every plan](../../docs/INCIDENTS.md#a-stale-attachment-in-state-blocked-every-identity-plan)). |
| `no users found` from every user lookup in an identity plan | The plan ran on ciphertext | Plans run in the private mirror; a dry run plans nothing at generation ([the plan that ran on ciphertext](../../docs/INCIDENTS.md#the-identity-plan-ran-on-ciphertext)). |
| `CI login policy '...' is absent` / `workload role '...' is not known to OPA` in the state report | Workload drift is reported, never hard: the policy's absence is the state the identity apply repairs | The identity apply that creates the policy runs; the strict query and the login proof still see the drift ([the reconcile once refused by hard drift](../../docs/INCIDENTS.md#the-first-ci-policy-reconcile-was-refused-by-hard-drift)). |
| `state backup for workspace '<ws>' REFUSED` | The runner step ran where no initialised root, or no state, is | Initialise the root against its location and rerun; the runner's `materialize` wrapper puts the step in the right directory ([the backup that kept nothing](../../docs/INCIDENTS.md#a-runner-step-acted-in-the-configuration-root-and-the-backup-kept-nothing)). |
| `Refusing meta-state/<file>: material that must not be public` / `Refusing the run's meta-state commit` | A hard public-safe rule matched a value about to be written or staged | Encrypt the value or allow it by decision in `public_safe.allow`; nothing was written. The plaintext scan runs at the commit, never before generation ([the guard that read the emission it was about to replace](../../docs/INCIDENTS.md#the-plaintext-guard-read-the-emission-the-run-was-about-to-replace)). |
| `run --commit` fails with git saying the mirror's path is ignored | The commit must exclude `_private/` without an exclude pathspec | The root's `.gitignore`, `refused_path` and the scanner's skip keep the mirror out; commit by hand or re-run ([the commit that failed under a running launch](../../docs/INCIDENTS.md#the-runs-commit-failed-while-the-instance-it-launched-was-running)). |
| A `.gitignore` negation such as `!.terraform.lock.hcl` does nothing | A restated rule was deduplicated into the wrong place | The last occurrence of a duplicate keeps its place ([the dropped rule](../../docs/INCIDENTS.md#the-generated-gitignore-dropped-a-restated-rule)). |
| A stray `instances.auto.tfvars` under `generated/release/` or `generated/retention/`, refused by name at commit | A lifecycle that does not own the instance roots wrote one | The instance builder's finalize hook acts for instance-image alone ([the stray tfvars file](../../docs/INCIDENTS.md#the-release-and-retention-runs-left-a-stray-tfvars-file)). |
| `tofu init` in the mirror cannot read `../tfmodules` or its local state | The mirror does not stand at the emission's depth | Compare the depth of `_private/<...>` with `generated/<...>`; `mirror_path` replaces the generation directory's name ([the mirror that stood one level too deep](../../docs/INCIDENTS.md#the-private-mirror-stood-one-level-too-deep)). |
| A decommissioned instance's root plans nothing, or a dry run erased its record | The root is emitted for a recorded instance and the forget waits for the real apply | Re-run as a real run; nothing is forgotten by a dry run ([the last GCE instance](../../docs/INCIDENTS.md#decommissioning-the-last-gce-instance-planned-no-destroy-and-a-dry-run-erased-its-record)). |
| `preflight: a session ... EXPIRED` / `a session expires before the expected run length` | The credential cache lapsed, or lapses within `preflight.expected_run_minutes` | `aws sso login --profile <p>` and rerun; a session that lapses mid-run is environmental ([the session that lapsed mid-cycle](../../docs/INCIDENTS.md#the-aws-session-lapsed-mid-cycle-and-then-before-the-preflight-could-say-so), [the zero-minute session](../../docs/INCIDENTS.md#a-session-with-exactly-zero-minutes-left-was-not-expired), [the refreshing profile read as absent](../../docs/INCIDENTS.md#an-sso-session-profile-was-read-as-absent-for-an-hour)). |
| `sft resolve <h>: exit 126 -- the client has no session` in a login proof | The client wanted a browser and `--quiet` forbade it | As the enrolled client, `sft login`; as the workload, `OPA_TOKEN` is missing or was refused ([the silent exit 126](../../docs/INCIDENTS.md#sft-resolve-exited-126-with-nothing-on-stderr)). |
| The SSM agent or the package manager dies on a bake host | The bake host is too small for the update | Declare a per-instance `machine_type` ([the starved bake host](../../docs/INCIDENTS.md#a-1-gb-bake-host-starved-the-package-manager-and-the-ssm-agent)). |
| `/dev/xvdf` never appears on a launched instance | Nitro instances expose the device under another name | The launch script falls back to the by-id path ([the device that never appeared](../../docs/INCIDENTS.md#the-ebs-device-never-appeared-as-xvdf-on-a-nitro-instance)). |
| The identity provider ERRORs on refresh naming an enrollment token | The token was deleted out of band | Hard drift names `state rm` as the repair ([the token deleted out of band](../../docs/INCIDENTS.md#an-enrollment-token-deleted-out-of-band)). |
| `STALE PLANFILE: ...` from the gate | A failed plan left an older `tfplan` behind | The plan step did not run or did not succeed; read the runner's output above the gate line ([the stale plan that once passed](../../docs/INCIDENTS.md#a-stale-plan-file-passed-the-gate)). |
| A GCE data disk attached but not mounted | GCE forbids underscores in device names | `_gce_device_name` renders the name GCE uses ([the refused underscores](../../docs/INCIDENTS.md#gce-refused-underscores-in-resource-names)). |

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
- `No runtime providers configured.` -- no `runtime_builders:` entry, or
  no runtime plugin installed.
- `No default builder found in <classification> list.` / `Multiple default
  builders found: <a> and <b>` -- mark exactly one `is_default: true` per
  builder class.
- `Duplicate builder name found: <n>` / `Builder with default name found`
  -- rename; `default`, `self`, `none` and empty are reserved.
- `<file>: <list>[<i>].name: a name may not be '<word>'` (or `...aliases[<j>]:
  an alias may not be ...`, or `... may not be empty (null)`), every one
  in the file at once, `ReservedNameError` at load -- rename the entry or
  drop the alias; the reserved words are `default`, `self`, `none`, the
  empty string and null, in any case.
- ``<file>: config.<key>: '<key>' may not be a `config:` key``,
  `InvalidConfigKeyError` at load -- rename the key; the message lists
  all seventeen guarded words.
- ``<Class> '<name>': field '<f>' names 'none', which is no <target> ...
  -- `none` names nothing and is not this field's default`` at
  `validate` -- leave the field out, or write `default`, for the default.
- `workspace '<ws>' names state backend 'none', which names nothing` at
  `validate` -- declare a backend of type `local` for state on disk, or
  leave `state_configuration` out for the default backend.
- `Type Collision: <namespace>/<name> under <classification> is
  <module.Class>, and <module.Other> registers it too` (`ValueError`
  from the registry) -- two *different* classes under one classification,
  namespace and canonical name: one plugin registering two classes under
  one word, or two plugins whose distributions derive the same namespace;
  a packaging problem, not a configuration one. Two plugins using one word
  under different namespaces is not this: both load, and the tree picks
  one by its qualified form.
- `type '<word>' is ambiguous under <classification>: N plugins register
  it; write one of <ns>/<word>, ...` (`AmbiguousTypeError`; `validate`
  prints it as ` - <the line>` under `Validation failed with 1
  error(s).`) -- the tree wrote a bare `type:` word that different
  installed plugins' classes answer to; write one of the qualified forms
  named.
- `Plugin <name> is refused: its entry point has no distribution to
  derive a namespace from, and its metadata names none; set
  PluginMetadata.namespace` (`PluginNamespaceError`) -- a plugin
  registered without a distribution behind its entry point and without
  the field; a packaging problem.
- `KeyError: <type>` while structuring -- the `type:` names no registered
  model: the plugin is not installed or the name is misspelt (aliases are
  canonicalised first).
- pydantic `Extra inputs are not permitted` naming the key -- a key the
  model does not have; every model forbids extras.
- `... declares 'parameters'; ... use 'variables:'` -- the retired key on
  a builder.
- `Instance '<n>' declares 'groups'; V2 removed per-instance groups ...
  Set 'group:' on the image instead.`
- Warning `Instance '<name>' does not have an image specified; the load
  refuses it when the configuration finalizes.`, then `Instance '<name>'
  cannot be finalized without an image specified.` (`ValueError`) -- an
  instance declares no `image`. Name the image to launch.
- `Image <n> must have at least one runtime specified in the 'runtimes'
  field` / `Image <n> must have either 'os' or 'source_image' specified`.
- `OS builder <n> must have at least one runtime configuration.` /
  ``OS builder <n>: two `runtimes` entries name image builder <ib>; one entry per image builder``.
- `Unsupported RHEL version '<v>' in OS builder <n> (supported: 8, 9, 10)`
  / `Could not determine RHEL version from family_version '<v>' in OS
  builder <n>` -- a `type: rhel` OS builder whose major is not 8, 9 or 10,
  or whose `family_version` does not parse; refused at load, whatever
  the update policy.
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
- ``base image '<n>': update: must be a mapping (`update: {policy: <name>}`), got <type>``
  (a bare name is never accepted) / the
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
  before anything else of the run: the refused summary is returned to
  the caller and never written, journalled or handed to the on-summary
  hooks) and `run scope: bake(s) outside the apply scope [...]` (after
  the bake plan, a real run only).
- `--migrate-state moves state and needs --no-dry-run: a dry run never
  moves state`.

**During generation and apply** (`run-summary.json` records the
lifecycle `failed` or the apply `failed`; exit 1):

- `Resolution failed for lifecycle <lc>` / `Image Builder for OS <n> not
  found in predefined_resolve` / `Runtime Builder for OS <n> not found` /
  `No resolved Image identifiers for OS <n> in predefined_resolve` -- the
  vendor query answered nothing (the runtime plugin's filters, owners or
  credentials).
- `OS builder <n>: image_id '<id>' on runtime <rt> is not known to the
  provider` -- an OS builder entry pins an `image_id` the runtime's
  `query_provider_image_by_id` cannot find (an AMI id from another region,
  a deregistered AMI, a GCE image name not in the entry's owner
  projects). A runtime plugin that does not implement the hook raises
  `<class> cannot look a vendor image up by id` instead.
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
  [...]: <e>` / `alias write failed (<rc>): <tail>` (also when the
  command answered with no output at all, whatever its exit status: the
  tail then reads `no output`).
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
