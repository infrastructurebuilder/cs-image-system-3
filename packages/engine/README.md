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
engine (`tests/test_contract.py`, `tests/test_plugin_imports.py`). The
line between the two is measured: `tests/test_import_closure.py`
computes the closure of what the plugins and the terraform roots import
from the core, over every edge (top-level, function-local and
`TYPE_CHECKING`), and holds the kit package to exactly that closure and
this package to the rest. So a runtime plugin installs with the contract
and the kit alone; the engine is what the CLI host
([system](../system/README.md)) and the umbrella install on top.

The behaviour of a run is described once, for the kit and the engine
together, in the kit's README: [how YAML becomes
models](../base/README.md#how-yaml-becomes-models), [lifecycles and
phases](../base/README.md#lifecycles-and-phases), [a
run](../base/README.md#a-run-generation-finalization-dry-run-commit),
[meta-state](../base/README.md#meta-state), [the public-safe
gate](../base/README.md#the-public-safe-gate),
[releases](../base/README.md#releases),
[retention](../base/README.md#retention) and [the terraform
modules](../base/README.md#the-terraform-modules). Its source links name
the package each module lives in. This README says what the engine
package holds and how it fits.

It contains no cloud code: every provider call goes through a plugin
hook. Licensed under Apache-2.0. Requires Python 3.13 or later.

Declared dependencies ([`pyproject.toml`](pyproject.toml)):
`cs-image-system-contract` (its compatible series, as every dependent
pins it), `cs-image-system-base` (the kit, at `==` the workspace
version), `Jinja2` (the template resolver), `PyYAML`, `packaging` (the
version checks and the pinned release), `pydantic` and `typer` (the
typer context the configuration reader and the commands are handed).

## Contents

- [Modules](#modules)
- [Entry points](#entry-points)
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
| [`v2_validation.py`](src/cs_image_system/engine/v2_validation.py) | The generation-time validation rules the runner registers. |
| [`read_models.py`](src/cs_image_system/engine/read_models.py) | The read-model writers. |
| [`release.py`](src/cs_image_system/engine/release.py), [`retention.py`](src/cs_image_system/engine/retention.py) | The `release` and `retention` lifecycles. |
| [`storage_state.py`](src/cs_image_system/engine/storage_state.py) | The storage state machine. |
| [`accounts_reconcile.py`](src/cs_image_system/engine/accounts_reconcile.py), [`identity_attributes.py`](src/cs_image_system/engine/identity_attributes.py), [`posix_ids.py`](src/cs_image_system/engine/posix_ids.py), [`workload_access.py`](src/cs_image_system/engine/workload_access.py) | Identity after an apply: accounts on the machines, identity attributes, POSIX ids, workload access. |
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

## Tests

The package's own tests live in [`tests/`](tests/): the finalization
executor, the resolution stages and the template utilities. The rest of
the engine is tested end to end by the workspace suite under
[`../../tests/`](../../tests/), which loads the frozen fixture through
the engine and compares the emission with the golden. In the workspace,
`just test` is the acceptance bar.

## Prerequisites and integration

- **Python 3.13 or later and the workspace.** `just init` (`uv sync
  --all-extras`) installs this package with the kit, the contract and
  every plugin; a release installs it as a dependency of
  `cs-image-system-system` and of the umbrella, `cs-image-system`.
- **The kit, at the same version.** Every engine module that reads a
  model, a builder, the registry or the run context imports it from
  `cs_image_system.base`; the pin is `==` because the two release
  together.
- **Plugins, through entry points.** The engine registers no runtime and
  no builder of its own; what a tree's `type:` words need comes from the
  installed plugins ([the kit's README](../base/README.md#prerequisites-and-integration)
  lists what each needs).
- **The tools a run drives** (`tofu`, `packer`, `ansible-playbook`, the
  clouds' CLIs, docker) are not Python packages; a tree's
  `cfg/executables.yml` says where they are, and the version checks the
  plugins register verify them.

## Configuration reference

The engine reads the configuration tree; it adds no key of its own
beyond those the kit's README documents: [the configuration
reference](../base/README.md#configuration-reference) (the top level of
`cfg/_config.yml`, the `config:` keys the core reads, overlays and
undeclares, the collections). The bootstrap's answers file,
`bootstrap.yaml`, is described in [docs/OPERATIONS.md](../../docs/OPERATIONS.md).

## What it tests and verifies

At load, the engine refuses a plugin that registers nothing of its
group's kind or a class that does not conform to the protocol of its
classification, and a configuration that does not structure. At
`validate` and at the head of every run, it runs the validators the
lifecycles and the plugins register; at generation, the generation-time
rules; at apply, the gate; at `--commit`, the public-safe scan; and in
the state query, reality against the records. Each check, where it
runs and what it refuses is listed once in [the kit's
README](../base/README.md#what-it-tests-and-verifies).

## When it fails

A failure names its rule. The loader logs one error line for a plugin
whose module fails to import and loads the others; a configuration that
does not load is one line from `load_failures`; a validation failure
lists every error before anything is generated; a refused apply names
the gate's reason. The failures the code raises, and what to do about
each, are in [the kit's README](../base/README.md#when-it-fails) and in
[docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md) chapter 6.
