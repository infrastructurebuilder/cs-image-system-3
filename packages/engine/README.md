# cs-image-system-engine

The engine of cs-image-system: the half of the core that runs a tree.
It discovers and loads the plugins, reads the configuration into a run
context, resolves the templates, runs the lifecycles and their phases,
queues and executes the deferred commands, keeps meta-state on disk,
queries state, and holds every command the CLI host mounts (validate,
the gate, the generators, the release and retention lifecycles, the
state migration, the bootstrap, ...).

The other half is the kit, [cs-image-system-base](../base/README.md):
the base classes, the models and what they import, which is what a
plugin is written against. The direction is one way, contract <- kit <-
engine. The engine imports the [contract](../contract/README.md) and the
kit; the kit imports nothing of the engine, and no plugin imports the
engine (`tests/test_contract.py`, `tests/test_plugins_keep_to_the_surface.py`). The
line between the two is measured: `tests/test_import_closure.py`
computes the closure of what the plugins and the terraform roots import
from the core, over every edge (top-level, function-local and
`TYPE_CHECKING`), and holds the kit package to exactly that closure and
this package to the rest. So a runtime plugin installs with the contract
and the kit alone; the engine is what the CLI host
([system](../system/README.md)) and the umbrella install on top.

This README describes what the engine holds and what a run does with
it: [how YAML becomes models](#how-yaml-becomes-models), [a
run](#a-run-generation-finalization-dry-run-commit) from its first check
to its commit, [meta-state](#meta-state), [the public-safe
gate](#the-public-safe-gate), [releases](#releases),
[retention](#retention) and [the terraform
modules](#the-terraform-modules), and then, in its last four sections,
what a run needs, which checks it runs and how it fails. What a run is
made of -- the models, the registry, [the lifecycles and their
phases](../base/README.md#lifecycles-and-phases), [the run
context](../base/README.md#the-run-context), encryption, lineage, the
launch parameters and the capabilities -- is the kit's, and the kit's
README describes it. A source link names the package its module lives
in: a link into `../base/` is the kit's.

It contains no cloud code: every provider call goes through a plugin
hook. Licensed under Apache-2.0. Requires Python 3.13 or later.

Declared dependencies ([`pyproject.toml`](pyproject.toml)):
`cs-image-system-contract` (its compatible series, as every dependent
pins it), `cs-image-system-base` (the kit, at `==` the kit's own
version), `Jinja2` (the template resolver), `PyYAML`, `packaging` (the
version checks and the pinned release), `pydantic` and `typer` (the
typer context the configuration reader and the commands are handed).

## Contents

- [Modules](#modules)
- [Entry points](#entry-points)
- [How YAML becomes models](#how-yaml-becomes-models)
- [A run: generation, finalization, dry run, commit](#a-run-generation-finalization-dry-run-commit)
- [Meta-state](#meta-state)
- [The public-safe gate](#the-public-safe-gate)
- [Releases](#releases)
- [Retention](#retention)
- [The terraform modules](#the-terraform-modules)
- [The modules in detail](#the-modules-in-detail)
- [Tests](#tests)
- [Prerequisites and integration](#prerequisites-and-integration)
- [Configuration reference](#configuration-reference)
- [What it tests and verifies](#what-it-tests-and-verifies)
- [When it fails](#when-it-fails)

## Modules

Loading a tree:

| Module | Provides |
| -------- | ---------- |
| [`loader.py`](src/cs_image_system/engine/loader.py) | Plugin discovery over the entry-point groups `cs_image_system.plugins.<type>`, the namespace a distribution's name yields, the conformance check at discovery, `load_plugins(reg)` and `installed_registry()`. |
| [`config_loader.py`](src/cs_image_system/engine/config_loader.py) | The configuration reader: the YAML tree, the overlays and undeclares, the decryption, and the run context it makes and hands out with its services bound. |
| [`orchestrator.py`](src/cs_image_system/engine/orchestrator.py) | The converter and the `TemplateResolver`: structuring YAML into the registered models and binding each to its run. |
| [`template_utils.py`](src/cs_image_system/engine/template_utils.py), [`helpers/resolution_stages.py`](src/cs_image_system/engine/helpers/resolution_stages.py) | The string stage: the ordered resolution passes over a configuration's strings. |
| [`reserved_names.py`](src/cs_image_system/engine/reserved_names.py) | Names a configuration may not use. |
| [`init.py`](src/cs_image_system/engine/init.py) | The `base` plugin's entry point function: the default storage mapping model and the generic version checker. |

Running it:

| Module | Provides |
| -------- | ---------- |
| [`commands/`](src/cs_image_system/engine/commands/) | The commands: `run_lifecycles` (the runner), `validate`, `gate`, the five generators (`gen_users`, `gen_groups`, `gen_storages`, `gen_images`, `gen_instances`), `resolve`, `finalization`, `preflight`, `run_scope`, `dispose`, `relabel`, `restamp`, `upgrade`, `unmount`, `state_migration`, `identity_gids`, `login_proof`, `runtime_facts`, `emission`, `load_failures`. The verify command (`verify_instance`) is the kit's, since the lineage and launch rules read it. |
| [`finalizer.py`](src/cs_image_system/engine/finalizer.py), [`in_process.py`](src/cs_image_system/engine/in_process.py) | The deferred-command queue and its executor; the in-process seam through which a run runs the system's own CLI steps. |
| [`validation_rules.py`](src/cs_image_system/engine/validation_rules.py) | The generation-time validation rules the runner registers. |
| [`read_models.py`](src/cs_image_system/engine/read_models.py) | The read-model writers. |
| [`release.py`](src/cs_image_system/engine/release.py), [`retention.py`](src/cs_image_system/engine/retention.py) | The `release` and `retention` lifecycles. |
| [`storage_state.py`](src/cs_image_system/engine/storage_state.py) | The storage state machine. |
| [`accounts_reconcile.py`](src/cs_image_system/engine/accounts_reconcile.py), [`identity_attributes.py`](src/cs_image_system/engine/identity_attributes.py), [`posix_ids.py`](src/cs_image_system/engine/posix_ids.py), [`workload_access.py`](src/cs_image_system/engine/workload_access.py) | Identity after an apply: accounts on the machines, identity attributes, POSIX ids (resolved across every identity at validation, drawn from a pool when undeclared, and recorded in `meta-state/ids.yaml` by an applying run or a `--commit` dry run; [the rule](../../docs/OPERATIONS.md#ids-are-recorded-once)), workload access. |
| [`launch_delivery.py`](src/cs_image_system/engine/launch_delivery.py), [`ansible_launch.py`](src/cs_image_system/engine/ansible_launch.py), [`provider_aliases.py`](src/cs_image_system/engine/provider_aliases.py) | The launch script delivered through the session, the ansible-inventory prototype, and the provider names an instance answers to. |
| [`mod_tests.py`](src/cs_image_system/engine/mod_tests.py) | The local modification tests, over a target a runtime plugin provides. |
| [`tofu_lock.py`](src/cs_image_system/engine/tofu_lock.py) | One tofu process at a time. |

The records and the release:

| Module | Provides |
| -------- | ---------- |
| [`meta_state.py`](src/cs_image_system/engine/meta_state.py) | Meta-state on disk: the records the kit's `meta_ledgers` types, read and committed. |
| [`state_query.py`](src/cs_image_system/engine/state_query.py), [`standing.py`](src/cs_image_system/engine/standing.py), [`state_backup.py`](src/cs_image_system/engine/state_backup.py) | The state query (reality against belief), what the records say stands, and the state backups. |
| [`public_safe.py`](src/cs_image_system/engine/public_safe.py), [`materialize.py`](src/cs_image_system/engine/materialize.py) | The public-safe scanner behind the commit gate; the private mirror an execution runs from. |
| [`modules.py`](src/cs_image_system/engine/modules.py) | The terraform modules every installed plugin ships, listed and materialised into a tree with their stamps. |
| [`pinned_release.py`](src/cs_image_system/engine/pinned_release.py) | A committing run is made by the release the tree pins. |
| [`bootstrap/`](src/cs_image_system/engine/bootstrap/__init__.py) | `cs-image-system bootstrap`: the answers, the facts, the interview, the sections (GitHub here, the clouds' from their plugins) and the generated terraform. |

## Entry points

The engine declares none of its own. The `base` plugin's entry point
(`cs_image_system.plugins.base`, value
`cs_image_system.engine.init:initialize`) and the modules entry point
(`cs_image_system.modules`, value `cs_image_system.base:tfmodules`) are
declared by the kit's distribution, so the registrations the first one
makes carry the namespace `base` and a materialised module's stamp names
`base`. The function the first one names is here because only the
engine's loader calls it; an install without the engine has no loader
and calls nothing.

The engine reads these groups: `cs_image_system.plugins.<type>` (the
plugins, in the order of the contract's `PLUGIN_TYPES`),
`cs_image_system.plugins.hooks` (run hooks), `cs_image_system.modules`
(the terraform modules) and `cs_image_system.bootstrap` (bootstrap
sections). The kit's registry reads `cs_image_system.extras` (the
umbrella's table from a `type:` word to the extra that installs it),
and the system package reads `cs_image_system.commands`.

## How YAML becomes models

Source: [`template_utils.py`](src/cs_image_system/engine/template_utils.py),
[`orchestrator.py`](src/cs_image_system/engine/orchestrator.py),
the contract's [`fields.py`](../contract/src/cs_image_system/contract/fields.py),
[`config_loader.py`](src/cs_image_system/engine/config_loader.py).

### The string stage

Before anything is structured, the merged `cfg/` document -- the one tree
the loader parsed, each `cfg/*.yml` file read exactly once -- is walked by
the ordered resolution passes, each rendering the string leaves it is
responsible for and handing the tree to the next. The document is never
dumped back to YAML text and never parsed again: a pass is a function over
the parsed tree (`fn(tree, *, addl, cycles) -> tree`, the registry in
[`helpers/resolution_stages.py`](src/cs_image_system/engine/helpers/resolution_stages.py)).
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
   [ia_config.py](../base/src/cs_image_system/base/models/ia_config.py), the same
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
   [`template_utils.py`](src/cs_image_system/engine/template_utils.py)).

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
| `parent_field(target, ...)` | `fk` | The `_model_id` of an item that holds its parent by reference: the parent's global id, never a YAML key. It is the one foreign key the resolver never defaults: unset means the item is not parented yet, and the model that holds the item in its list sets it (an OS builder model and an image in their own construction, a deferred list's owner when it enters the item, the loader for a group or a user by its `type`: `parent_by_written_type` for a written one, `parent_by_default_type` for one left at `default`, right after the item is structured and before it is entered in the flat map, so the key it is entered under names its parent). The registry's default for `target` would name another builder for every item but the default's own. The registry keys an item by it too: it is the item's ancestry in `InstanceKey`, except for a group or a user, whose parent is the builder that serves it. |

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
[`reserved_names.py`](src/cs_image_system/engine/reserved_names.py)
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

## A run: generation, finalization, dry run, commit

Source: [`commands/run_lifecycles.py`](src/cs_image_system/engine/commands/run_lifecycles.py),
[`commands/`](src/cs_image_system/engine/commands/).

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
package registers in [`in_process.py`](src/cs_image_system/engine/in_process.py)
(`register_system_cli_runner`; the core never imports the system, so the
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

## Meta-state

Source: [`meta_state.py`](src/cs_image_system/engine/meta_state.py).

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

## The public-safe gate

Source: [`public_safe.py`](src/cs_image_system/engine/public_safe.py).

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

## Releases

Source: [`release.py`](src/cs_image_system/engine/release.py).

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

Source: [`retention.py`](src/cs_image_system/engine/retention.py).

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

## The terraform modules

Every terraform module a builder emits a `module` call against
(`aws_instance`, `gcp_storage_pd`, `docker_volume`, `okta_opa_module`, ...)
is package data inside the plugin that owns it, under that package's
`tfmodules/` directory; the core ships the neutral one,
[`bootstrap_github`](../base/src/cs_image_system/base/tfmodules/bootstrap_github).
A plugin declares its directory with one entry point in the contract's
group `cs_image_system.modules`
([`contract/modules.py`](../contract/src/cs_image_system/contract/modules.py)),
the value `<package>:<dirname>`:

```toml
[project.entry-points."cs_image_system.modules"]
modules = "cs_image_system.aws_runtime:tfmodules"
```

[`modules.py`](src/cs_image_system/engine/modules.py) is the one API over
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
is skipped. `module_verdict(copy, release_hash)` is that judgement of one
copy, writing nothing (`absent`, `refresh`, `adopt`, `current`, `edited`,
`unstamped`, `not-a-directory`): `materialise_modules` acts on it, and
`init-config --changes-since` reports each module by it, so a copy nobody
edited is listed safe to refresh and an edited one is listed as edited.
`cs-image-system modules [--write DIR] [--force]` is the command over it,
and `init-config` uses it for a tree's copies.

The emission reads none of this: `module_source` in `utils.py` resolves a
call's `source` from `config: module_source_base` (every module) and
`config: module_sources` (one module at a time, the entry being the
module itself), so a tree may hold a copy, source a module from
elsewhere, or edit a copy and keep the edit by naming it.

## The modules in detail

The modules of the tables above that a reader meets in more than one
place, each in more detail. The kit's modules are in [its
README](../base/README.md#other-modules).

| Module | Purpose |
| -------- | --------- |
| [`modules.py`](src/cs_image_system/engine/modules.py) | The installed terraform modules (`installed_modules`, from the `cs_image_system.modules` entry points, no plugin import), their materialisation into a tree with a stamp per copy (`materialise_modules`, `module_verdict`, `Stamp`, `content_hash`, `ModulesReport`) and the names `config: module_sources` declares (`declared_overrides`); see [The terraform modules](#the-terraform-modules). |
| [`state_query.py`](src/cs_image_system/engine/state_query.py) | Asks every plugin for reality (images by lineage tags, storages by name, groups by gid), diffs it against meta-state, and classifies drift as `missing`, `foreign`, `changed` or `stale`. Hard drift (a pinned build gone, a storage recorded live but absent, a managed group unknown to the provider, an instance pinned to an unrecorded build) makes the next run's validation refuse. `import_foreign` adopts foreign artifacts into meta-state; nothing here writes to a cloud or to terraform state. The report is `generated/state-report.json`. |
| [`storage_state.py`](src/cs_image_system/engine/storage_state.py) | The storage state machine: legal transitions (`active` to `archived` and back, either to `destroyed`, and regeneration of a destroyed name), the rule that a storage must be unattached to leave `active`, transitions for undeclared storages, and the recording of applied transitions. |
| [`validation_rules.py`](src/cs_image_system/engine/validation_rules.py) | Generation-time rules, all hard: managed groups may not disappear; allowed groups exist; the strict attach rule; single-attach cardinality; data lifecycles only where the builder realizes them; storage transitions are legal; an instance image's group exists and every instance image has one; declared types resolve to configured plugins; admin keys are public keys; every base image has a debug path (keys or a session mechanism); capability resolution on both axes; test specs use the known vocabulary; update policies are valid. |
| [`mod_tests.py`](src/cs_image_system/engine/mod_tests.py) | Runs every modification of an instance image against a throwaway local target twice (apply, then idempotence), recording results in `meta-state/mod-tests.yaml` by content hash. The harness drives an abstract `LocalTarget` (`exec`, `copy_in`, `diff`, `volatile`, `close`, and the ansible connection plugin that reaches it) and names no runtime: the target's factory comes from the one registered runtime builder class whose `local_test_target()` is not None, is handed the tree's executables, and returns nothing when its daemon does not answer (the modifications are then `skipped`, not failed); a target that cannot start raises `ContainerStartError` (`unstarted`). |
| [`identity_attributes.py`](src/cs_image_system/engine/identity_attributes.py) | Declared provider attributes on users and groups: validation per plugin, a plan written to `generated/identity/attributes-plan.json`, a read-only probe, and an apply that is deliberately disabled. |
| [`read_models.py`](src/cs_image_system/engine/read_models.py) | Writes the identity and storage read-models and records applied storage transitions. |
| [`commands/preflight.py`](src/cs_image_system/engine/commands/preflight.py) | The session lines: asks every declared runtime's and state backend's class the contract's `session_status` hook over the loaded models (a state builder of the kit, a `StateBuilderBase`, is also handed the run's runtime builder classes, `ctx.reg.runtime_builder_classes()`, as a third argument, so a backend that borrows a runtime's session reading finds it there) and judges the answers against the expected run length; reads no credential cache itself and names no provider. |
| [`commands/gate.py`](src/cs_image_system/engine/commands/gate.py) | The apply gate over a `tofu show -json` plan: every planned destroy must match a whitelisted address or prefix; a plan file older than the newest `.tf` in its root is stale. |
| [`commands/upgrade.py`](src/cs_image_system/engine/commands/upgrade.py), [`commands/dispose.py`](src/cs_image_system/engine/commands/dispose.py), [`commands/restamp.py`](src/cs_image_system/engine/commands/restamp.py), [`commands/relabel.py`](src/cs_image_system/engine/commands/relabel.py), [`commands/unmount.py`](src/cs_image_system/engine/commands/unmount.py), [`commands/runtime_facts.py`](src/cs_image_system/engine/commands/runtime_facts.py), [`commands/identity_gids.py`](src/cs_image_system/engine/commands/identity_gids.py), [`commands/run_scope.py`](src/cs_image_system/engine/commands/run_scope.py) | The operations behind the CLI's `upgrade`, `dispose image`, `lineage restamp`, `lineage relabel`, `unmount storage`, `runtime describe` / `empty`, `identity export-gids`, and the bake scope check. `verify instance` is the kit's ([its README](../base/README.md#other-modules)). |
| [`in_process.py`](src/cs_image_system/engine/in_process.py) | The seam through which a deferred step that is the system's own CLI runs in the running process: the system package registers its runner (`register_system_cli_runner`), `run_executable` asks for it before it spawns anything, and `names_subcommand` is how a runner tells a nested `run` (which needs a context of its own) from every other step. No runner registered, or a step declined: the step is spawned. |
| [`ansible_launch.py`](src/cs_image_system/engine/ansible_launch.py) | Renders the same launch parameters as an ansible inventory and playbook: the hostname task, each mount's tasks from its storage builder's `launch_tasks()`, the enrollment kind's tasks; `extra_vars(ctx)` is the playbook's variable list, the same names as the launch template's. |
| [`provider_aliases.py`](src/cs_image_system/engine/provider_aliases.py) | After a real instance-image apply, gives each launched, running instance that its group's registry lists the names it lost at boot back (the bare declared name, the pool alias, the provider's `ip-...` label), skipping every collision and every silent registry; a machine with no record of its own (none carries its provider id: it is not registered) is passed over with an INFO line carrying the module's `NOT_LISTED`: the core decides the names, the machine and the moment. Where the names go is the group builder's: for a registry an agent on the machine keeps, a machine this run launched is waited for first, bounded, and the builder's `alias_registration_script` renders the script that tells its agent (the core reads only the contract's `ALIASES_CHANGED` / `ALIASES_UNCHANGED` from its output); for a registry kept in the records (`keeps_recorded_registry`), the names are written into the machine's entry through `record_aliases`, and nothing runs on the machine, so neither its power state nor its enrolment is waited on. And the `reality.instances` entries and notes of the state report. |
| [`workload_access.py`](src/cs_image_system/engine/workload_access.py) | After a real identity apply, reconciles each managed group's CI login policy through the group builder and records the outcome in the identity read-model. |
| [`reserved_names.py`](src/cs_image_system/engine/reserved_names.py) | The read-time refusals: `refuse_reserved_names` (a `name:` at any depth, or an `aliases:` entry, that is a word of `OOPS_DEFAULTS` in any case or spacing, every one listed with the file, the entry's place and the word, `ReservedNameError`) and `refuse_invalid_config_keys` (a key of a document's top-level `config:` that is in `INVALID_CONFIG_KEYS`, `InvalidConfigKeyError`). Called by `read_and_process` for each `cfg/` file, by the item-file reader after decryption, and by `load_overlay`; pure functions of the parsed document, no identity or network. |
| [`materialize.py`](src/cs_image_system/engine/materialize.py) | The private mirror `_private/` beside `generated/`, at the same depth: a root is copied there with every `ENC[age:...]` marker replaced by its plaintext before a deferred command runs, incrementally; only `.terraform.lock.hcl` is ever copied back. `ensure_ignored` appends `_private/` to the configuration root's `.gitignore`. |
| [`commands/login_proof.py`](src/cs_image_system/engine/commands/login_proof.py) | The login proof's driver: which declared instances are targets (launched, not ephemeral, on the runtime asked for), the skips (a group whose builder has no login to prove; a machine that is not running, never started for this), the group builder's own `login_checks` over each target, and every verdict recorded in `meta-state/login-proofs.yaml`. The command that drives it (`verify login`) is mounted by the identity plugin whose client logs in. |
| [`commands/state_migration.py`](src/cs_image_system/engine/commands/state_migration.py) | The runner steps of `--migrate-state` (`begin`, `finish`) and the same-day state `backup` a runner takes into `_private/state-backups/` before any `state rm` it decided on. |
| [`pinned_release.py`](src/cs_image_system/engine/pinned_release.py) | Holds a committing run, and a committing `lineage restamp`, to the release the tree pins in `.csis-version` (`hold_to_pin`, called by `run` before it generates and by the restamp before it computes; each speaks under its own name, `RUN` / `RESTAMP`; a disposal is not held): refused when the version running is not the pin, or when any distribution of the system was installed from somewhere other than an index (`installed_release` reads each dist-info's `direct_url.json`, which an index install never carries), unless `--allow-unpinned` / `CSIS_ALLOW_UNPINNED` says to go on. Pure functions over the tree's root and the install facts; no run context. |

## Tests

The package's own tests live in [`tests/`](tests/): the finalization
executor, the resolution stages, the template resolver and its
utilities, the field and item kinds, models structured through the
run's converter, an item's parent reference and the loader's plugin
conformance check. Their shared fixture, `clean_registry` in
[`tests/conftest.py`](tests/conftest.py), builds the engine's real
`TemplateResolver` over a fresh registry, so a test that needs a whole
resolution or the run's converter lives here; a test that needs only
the kit lives with the [kit's tests](../base/README.md#tests). The rest of
the engine is tested end to end by the workspace suite under
[`../../tests/`](../../tests/), which loads the frozen fixture through
the engine and compares the emission with the golden. In the workspace,
`just test` is the acceptance bar.

## Prerequisites and integration

The core, the engine and the kit under it, contains no cloud code and
makes no network call of its own: every provider call goes through a
plugin hook, and a hook that is not implemented (`can_*` false, or
`NotImplementedError`) makes no claim. The state query says so rather
than staying silent: a builder whose `query_state` (or an image or
storage lookup under it) raises `NotImplementedError` adds
`<kind>/<builder>: cannot be queried (<why>)` to `unavailable`, never
dropped from the report. What a run needs outside the core is therefore
short, and each item says how the core finds it.

- **Python 3.13 or later and the workspace.** `just init` (`uv sync
  --all-extras`) installs this package with the kit, the contract and
  every plugin; a release installs it as a dependency of
  `cs-image-system-system` and of the umbrella, `cs-image-system`.
- **The kit, at an exact version.** Every engine module that reads a
  model, a builder, the registry or the run context imports it from
  `cs_image_system.base`. The kit keeps a version line of its own (it is
  the SDK a plugin names by a range), and the engine pins the one it was
  built and tested with, `==`: the engine reaches past the kit's
  declared surface, which a plugin may not.
- **Plugins, through entry points.** The core registers no runtime, no
  image builder, no OS builder, no storage, group, user, instance or mod
  builder and no state backend. At every CLI start
  [`loader.py`](src/cs_image_system/engine/loader.py) walks the entry-point
  groups `cs_image_system.plugins.<type>` in the order of `PLUGIN_TYPES`
  and registers what each returns; run hooks come from
  `cs_image_system.plugins.hooks`. A configuration whose `type:` names a
  model no installed plugin registered does not load (`KeyError` from the
  converter), and a tree with no `runtime_builders:` at all is refused
  (`No runtime providers configured.`). Every builder class the tree
  declares needs exactly one entry marked `is_default: true` among the
  installed plugins' models. What each plugin needs is in its own
  README, and [the kit's
  README](../base/README.md#prerequisites-and-integration) links every
  one.
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
  [`meta_state.py`](src/cs_image_system/engine/meta_state.py) runs
  `git rev-parse`, `check-ignore`, `add`, `diff --cached`, `commit`,
  `ls-files`); the public-safe tree and staged scans (`git ls-files`,
  `git show :<path>`); `ensure_ignored`, which appends `_private/` to the
  root's `.gitignore` only when `<root>/.git` exists; and the `--commit`
  run-local set-aside (`git ls-files --error-unmatch`). A root outside a
  git repository skips the commit with a warning and is scanned as a plain
  directory; a gitignored tree is skipped with a warning. The commit is
  git's own, so git's requirements (an identity to commit as) apply.
- **The tools the tree declares under `executables:`** (`tofu`,
  `packer`, `ansible-playbook`, the clouds' CLIs, docker: none of them a
  Python package). Every entry's
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
  needs no identity; see [Encryption](../base/README.md#encryption). `preflight` and the
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
  `CSIS_*`, `OKTA_*`, plus every prefix the runtimes and group builders
  the configuration DECLARES name through
  `credential_environment_prefixes()`: `AWS_*`, `GOOGLE_*`,
  `CLOUDSDK_*`, `DOCKER_*`; a provider installed and not declared adds
  none) that is set but EMPTY is reported by name by
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

The engine reads the configuration tree; it adds no key of its own
beyond those the kit's README documents: [the configuration
reference](../base/README.md#configuration-reference) (the top level of
`cfg/_config.yml`, the `config:` keys the core reads, overlays and
undeclares, the collections). The bootstrap's answers file,
`bootstrap.yaml`, is described in [docs/OPERATIONS.md](../../docs/OPERATIONS.md).

## What it tests and verifies

Most of the system's checks live in the core, and the engine is what
runs them, whichever package holds a rule's code: a model's own
refusals and several rules (the lineage policies, the immutability of a
launched instance's parameters, the shape of a public key, the
vocabulary of an image's tests) are the kit's code, and the engine
calls them at the moments below. In short: at load, the
engine refuses a plugin that registers nothing of its group's kind or a
class that does not conform to the protocol of its classification, and
a configuration that does not structure; at `validate` and at the head
of every run, it runs the validators the lifecycles and the plugins
register; at generation, the generation-time rules; at apply, the gate;
at `--commit`, the public-safe scan; and in the state query, reality
against the records. The checks fall at six moments, and each entry
below says what is checked and where the verdict lands. What the kit's
own code refuses, read from the kit's side, is in [its
README](../base/README.md#what-it-tests-and-verifies).

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
- **The in-bake assertions** are generated by the kit's
  [`image_tests`](../base/src/cs_image_system/base/image_tests.py), as the
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
  their code is the core's (this package's
  [`commands/gate.py`](src/cs_image_system/engine/commands/gate.py),
  the kit's `apply_flag_allows`), their behaviour in
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
(generation closed `ephemeral`; its registration retired, as a
decommission's is; a `teardown` policy's failed verdict raises here),
`record_resizes`, `record_detachments`, `register_launched_servers`
(each launched machine of a group whose builder keeps its registry in the
records is registered in `meta-state/servers.yaml`, from the runtime's
report, under the hostname it booted with), `register_provider_aliases`,
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

The package's own tests under [`tests/`](../base/tests/) cover the registry,
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

A failure names its rule. The loader logs one error line for a plugin
whose module fails to import and loads the others; a configuration that
does not load is one line from `load_failures`; a validation failure
lists every error before anything is generated; a refused apply names
the gate's reason. The operator's view of the same failures, in the
order of a working day, is
[docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) chapter 6.

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
- `Instance name collision under <classification>: '<written>' (a
  <Class>) takes '<ns>/<name>' and '<written>' (a <Class>) holds
  '<ns>/<name>'; the emission names every instance by its own name, so
  rename one` (`InstanceCollisionError`, from the registry; `alias
  collision` for an alias; `Instance id collision ... both take the
  global id ...; rename one` for a global id) -- two declarations under
  one name (two spellings that normalise to one), two plugins' instances
  under one name (a cloud and a container runtime, two plugins' groups
  under different builders), or an alias another instance holds as its
  name or alias; the registry is as it was.
- `Plugin <name> is refused: its entry point has no distribution to
  derive a namespace from, and its metadata names none; set
  PluginMetadata.namespace` (`PluginNamespaceError`) -- a plugin
  registered without a distribution behind its entry point and without
  the field; a packaging problem. The plugin is skipped: the line is
  logged once as `Plugin <name> is skipped: refused: ...`, every other
  plugin loads, and only a configuration that needs this one fails.
- `KeyError: <type>` while structuring -- the `type:` names no registered
  model: the plugin is not installed or the name is misspelt (aliases are
  canonicalised first).
- pydantic `Extra inputs are not permitted` naming the key -- a key the
  model does not have; every model forbids extras.
- `... declares 'parameters'; ... use 'variables:'` -- the retired key on
  a builder.
- `Instance '<n>' declares 'groups'; an instance takes no per-instance
  groups ... Set 'group:' on the image instead.`
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
  a login by name cannot choose. Deregister the others`. The same for
  every builder whose group keeps a registry: an outside service's or one
  kept in the records (`meta-state/servers.yaml`, unreadable = did not
  answer).
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
- `Instance <n>: its registration as '<h>' was NOT retired (<e>); a stale
  registration will answer to that name until you <remedy>` (ERROR, the
  forget still happens), the remedy being `deregister it by hand` for a
  registry an outside service keeps and `remove its entry from
  meta-state/servers.yaml (group '<g>') by hand` for one kept in the
  records; on success `Instance <n>: retired <k> registration(s) of '<h>'
  in group '<g>' (<ids>)`, naming each entry retired, or `no registration of '<h>' in group '<g>' to retire`
  (INFO). A decommission, a replacement and an ephemeral teardown each
  retire this way.
- `Instance <n>: group '<g>''s server registry cannot be read; '<h>' is
  NOT registered (the next applying run registers it once the record
  reads)` / `Instance <n>: '<h>' is NOT registered in group '<g>' (<e>)`
  (ERROR, never fatal) / `Instance <n>: registered as '<h>' (<id>) in
  group '<g>''s registry` (INFO) -- the registration of a machine in a
  registry kept in the records; a runtime that reports no machine for it
  registers nothing that run, and says so at INFO.
- `Instance <n>: its aliases [...] were NOT recorded in group '<g>''s
  registry (<e>)` (ERROR, never fatal) / `Instance <n>: now also answers
  to [...] (recorded in group '<g>''s registry)` (INFO) -- the alias pass
  over a registry kept in the records.
- `Group <g>: its CI login policy was
  NOT reconciled (<e>); the CI login proof for this group fails until it
  is` (ERROR, never fatal) / `Instance <n>: alias '<a>' SKIPPED -- already
  claimed by <id> (the registry would resolve it to that record, or refuse
  as ambiguous)` / `group '<g>''s server registry could not be asked; skipping
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
