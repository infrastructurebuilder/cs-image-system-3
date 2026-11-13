# 113. The kit and the engine: `base` splits where the plugins stop

**Status: OPEN 2026-11-03; RE-PLANNED 2026-11-05 on §124's numbers;
RE-MEASURED 2026-11-12 after §132 (below). Waits for "do 113". The
first of the two decomposition stages that remain
([§116](STAGE-116.md) is the other; §114 and §115 landed inside
§125).**

**All numbers re-measured 2026-11-12 on develop at `caa4c26`; the
module and line totals read again 2026-11-13 at `a2c81f1` (one dead
module gone since). The statement counts and the lists are read again
at "do 113".**

**Order.** This stage runs alone: it rewrites imports in ninety-one
test files, so no other stage shares its branch's lifetime.
§134's items 4 and 5 landed first (2026-11-13), as they changed
`encryption`, the resolver and `config_loader`, which this stage
sorts and moves.

**Re-planned on §124's numbers, re-measured after §132.** The first
reading (2026-11-03) was taken over a lazy-import web that hid most
of what the plugins reach (REEXAMINE1 §5.2, REEXAMINE3). §124 made
every cycle-free import a top-level one and wrote the closure script
(`tests/import_closure.py`, held by `tests/test_import_closure.py`),
which counts the top-level, the lazy and the typing edges apart; the
figures in this file are its reading after §132 retired the old
context module, the singleton helper and the orchestrator class.
`base` is 134 modules (26,889 lines); the plugins' top-level closure
(`kit_top`) is **66** of them (13,487 lines), 78 with the lazy and
typing edges (`kit_all`, 15,640 lines); **56** are engine-only
(`engine_all`, 11,249 lines), and no module of the 78 imports any of
the 56, by any edge. The four doors §124 found into the engine from
the plugins' side are closed: no plugin names the kit's context (a
plugin types with the contract's `RunContextProtocol`;
`tests/test_contract.py`, no exception), `HookSet` is the contract's
(`contract/hooks.py`, §125), `os_types` reads the registry it is
handed and imports no loader (§132), and no plugin imports a command
module.

**After §125 and §132:** a plugin imports from the core only
`basic/*`, `models/*` and the two metadata abstractions
(`tests/test_plugin_imports.py`, whose exception list §132 emptied):
36 modules at the top level, 37 with the one typing import
(tofu-roots names `basic.builder_base`). So the kit is the base
classes, the models and what they import, and what they import
still holds six modules §124 counted as the engine's, each reached
by an edge of the kit's own: `orchestrator` (`models.image` and
`models.builder_model` import its `ModelBinding`, the second also
`unstructure`) and through it `template_utils`; `meta_state`
(`run_context`, `network_facts`, `alias_pool`); `loader`
(`public_safe`, which `meta_state` re-exports, imports
`installed_registry`); and `finalizer` by a typing edge alone
(`run_context` names `Finalizer` under `TYPE_CHECKING`), with
`in_process`, which `finalizer` imports; and
`commands.verify_instance` by two of the three lazy edges left in the
core (from `lineage` and `launch_params`). The engine is the rest (the
list below). The split of item 1 is the measured one, and the
four-door work is done.

So the stage's first act is not the script (it exists) but reading
the two sets from the closure test and moving the engine set; the
kit after that is the 78 modules of `kit_all` (and `base`'s own
`__init__`), and the engine the other 56. Inside the kit, the
component the closure test names (`scc_all`: the largest set of
modules that reach each other by some edge) is **27** modules (7,492
lines): `run_context`; nine builder bases (`basic.builder_base` and
its group, image, instance, mod, os, runtime, storage and user
subclasses); five models (`base_image`, `image`, `ia_config`,
`os_builder_model`, `os_builder_runtime_config`); and `lineage`,
`launch_params`, `generations`, `alias_pool`, `capabilities`,
`bake_user`, `image_tests`, `utils`, `ephemeral_policy`, `finalizer`,
`in_process` and `commands.verify_instance`. Forty typing-only edges
and the three lazy ones hold it together; without the typing edges it
is the four-module cycle the lazy edges close (`lineage`,
`launch_params`, `alias_pool`, `commands.verify_instance`). That
component is the layering question this stage answers. No plugin
imports `run_context` any more; it is in the kit because
`basic.builder_base` imports `RunContext` at the top level (for
`_run_context()`), and it names the nine builder bases, eight models,
`finalizer` and `orchestrator`'s `TemplateResolver` under
`TYPE_CHECKING` (19 statements): edges §125's protocol did not cut.
The engine-package decision in item 1 stands; no re-export shim of
item 1 may import the engine from the kit (REEXAMINE3 flaw 2), so an
old path either moves with its module or is dropped. The list of
halves below is the closure test's two sets as read on 2026-11-12.

The goal (the operator, 2026-11-03): decompose the system until a
runtime is defined outside it, so the system installs without any
runtime and a runtime installs without the system's engine. The
contract (§30) is the leaf every plugin is written against and stays
one: `base` depends on it, never the reverse, and
`tests/test_contract.py` holds the direction. What a plugin needs
beyond the contract today is a part of `base`, and that part is
measurable. Over the 134 modules of `base` (26,889 lines), the
transitive closure of what the sixteen plugins and tofu-roots import
(hashicorp-utils and contract-example-plugin import nothing of
`base`) is 78 modules (15,640 lines) over every edge, lazy and typing
ones included, and the closure is closed: none of the 78 imports any
of the other 56 (11,249 lines). So `base` splits into two packages
today with no cycle, along a line nobody drew but the imports already
keep.

The two halves, by name. **The kit** (`kit_all`, 78 modules, and
`base`'s own `__init__`): the base classes (`basic/*`, all fourteen),
the models (`models/*`, all thirty-three), `run_context`, `registry`,
`lineage`, `launch_params`, `launch_enrollment`, `generations`,
`alias_pool`, `capabilities`, `bake_steps`, `bake_user`,
`encryption`, `public_safe`, `power_state`, `image_names`,
`image_sources`, `image_tests`, `os_types`, `network_facts`,
`directory`, `utils`, `ephemeral_policy`, `lifecycles`,
`reserved_names`, `helpers/resolution_stages`,
`commands/verify_instance` (lazily), and the other five §124 counted
as the engine's: `orchestrator`, `template_utils`, `meta_state` and
`loader` (top-level edges) and `finalizer` (a typing edge), with
`in_process`.
**The engine** (`engine_all`, 56 modules; `base`'s `__init__` is one
and stays, so 55 move): every other `commands/*` module (dispose,
emission, finalization, gate, the five generators, identity_gids,
load_failures, login_proof, preflight, relabel, resolve, restamp,
run_lifecycles, run_scope, runtime_facts, state_migration, unmount,
upgrade, validate, and the package), the bootstrap (`bootstrap/*`:
answers, facts, generate, github, hcl, interview, questions,
sections, and the package; `questions` and `facts` re-export the
contract's vocabulary), `config_loader`, `init`, `release`,
`retention`, `state_query`, `state_backup`, `standing`,
`storage_state`, `materialize`, `mod_tests`, `modules`,
`pinned_release`, `provider_aliases`, `read_models`, `v2_validation`,
`workload_access`, `tofu_lock`, `accounts_reconcile`,
`ansible_launch`, `identity_attributes`, `launch_delivery`,
and `posix_ids`. The list is the measurement's,
read again at "do 113"; the script that computes it
(`tests/import_closure.py`) is kept as the test of item 1.

1. The engine moves out of `base` into a package of its own. `base`
   keeps its name and its import paths and becomes the kit, so **no
   plugin changes an import or a dependency**; the engine's modules
   move to `cs_image_system.engine` (package
   `cs-image-system-engine`, depending on the kit), and `system` and
   the tests rewrite their imports to it (today 28 import statements
   in two `system` files, and 292 in 91 test files plus four logger
   names, name an engine module; no plugin, tofu-roots,
   hashicorp-utils or the umbrella's own module does). No old path
   (`cs_image_system.base.commands.validate` and the rest) stays as a
   re-export in the kit, since a re-export would import the engine
   from the kit (REEXAMINE3 flaw 2, the note above); no plugin imports
   one, so none loses a path. Two entry points in `base`'s
   `pyproject.toml` name engine modules and are not imports, so the
   closure does not see them: `cs_image_system.plugins.base`
   (`base.init`) and `cs_image_system.modules` (`base:tfmodules`,
   which holds the bootstrap's `bootstrap_github`). **YOUR
   DECISION:** where the engine goes. A package of its own, `engine`
   (the plan's default): the seam is a distribution boundary, at the
   cost of a twenty-third lock-stepped project (a new PyPI project,
   one more upload in every release), where §126 decided that the
   twenty-two stay and the re-examination asks for fewer. Or into
   `system`: the same seam, measured by the same test, with no new
   project; "no plugin depends on `system`" then has to be held by a
   test rather than by `system` being only the CLI. The test: the
   closure script runs over the workspace and asserts that no kit
   module imports the engine and that every `cs_image_system.base`
   name a plugin imports resolves inside the kit; the seam stays
   measured, not remembered.

   Three more choices surfaced at the re-measurement of 2026-11-12;
   "do 113" asks each:

   - **YOUR DECISION (the kit's size):** move the measured engine set
     alone (the default: no new scope, a kit of 78 modules that still
     carries `orchestrator`, `template_utils`, `loader`, `meta_state`
     and the `finalizer` type), or first cut the four kit-side edges
     named above so those modules move too, a smaller kit as
     REEXAMINE2 and REEXAMINE3 ask, at the cost of new scope.
   - **YOUR DECISION (the undo):** with no re-export left, undoing this
     stage is reverting its squash. Keep the `s113-before`/
     `s113-after` bracket of the acceptance (the default), or drop it
     as REEXAMINE1 §3.4 advises against a second bracket.
   - **YOUR DECISION (the two entry points):** keep both in the kit's
     `pyproject.toml` (the default: a `.csis-module` stamp's `plugin:`
     stays `base`, so the reference's and the starters' copies stay
     byte-identical), or move them to the engine's distribution, which
     changes the module entry's namespace from `base` to `engine` and
     with it every stamp already written.
2. The kit reaches the terraform library nowhere. **Done before this
   stage (§123); nothing is left of this item.** `base` and `system`
   import nothing of hashicorp-utils or tofu-roots at any depth,
   lazily or not (the measurement), hashicorp-utils depends on the
   contract alone (its `pyproject.toml`; `tests/test_contract.py`
   holds it to importing only the contract), and the collector pulls
   the declared state backends from the context it is handed
   (`pull_declared_backends`, in the library).
3. The declaration vocabulary that still lives in `base` moves down
   into the contract. (a) and (b) are done (§125); DESIGN §3P's
   "deferred" list, which this item set out to finish, now names only
   the contract's own repository. (a) `contract.bootstrap` holds
   `Question`, `Section`, `Rendered`, `Secret`, `Raw`, `Refused`,
   `Answers`, the four coverage marks (`MADE`, `READ`, `ADOPTED`,
   `BY_HAND`), `ENTRY_POINT_GROUP` and `FactsProtocol`;
   `base.bootstrap.questions` and `base.bootstrap.facts` re-export
   them for the engine. `Facts` (the gatherer that runs the tools,
   implementing the protocol), `gather`, the interview, the
   generation, the GitHub section and the HCL writer stay in the
   engine. (b) `contract.hooks` holds `HookSet` and
   `HOOK_ENTRY_POINT_GROUP`; `commands/run_lifecycles` (742 lines)
   imports them, and no plugin imports the command. (c) remains: the
   plugin entry-point group names (`cs_image_system.plugins.<kind>`)
   are composed in `loader.py` from the kind words
   `contract.constants.PLUGIN_TYPES` holds; the contract does not hold
   the names themselves yet. The contract README's section "What the
   contract holds, and what the core keeps" names them (the README
   has no "What moved where" table).

**Out of scope**: any change to what a plugin imports
(`tests/test_plugin_imports.py` holds it since §125, which absorbed
§114 and §115); the umbrella's extras (§126's;
[§116](STAGE-116.md) is the external-repository proof), though the
umbrella and `system` do gain the engine as a dependency when it is a
package of its own, which is this stage's; the
contract's own repository; any YAML key, record, emission or cloud
state. The §30 shims are gone already (§125).

**Acceptance**: code only; the emission of the reference and of every
fixture is byte-identical before and after (the bar's golden tests);
`tests/test_contract.py` holds the direction for the three packages
(contract imports nothing from kit or engine; kit imports nothing from
engine); the closure test of item 1 is green and lists its two sets;
no plugin's `pyproject.toml` changes; `uv tool install` of the umbrella
installs the engine; the §30 reversibility bracket is repeated
(`s113-before`/`s113-after` tags whose messages carry the undo). One
squash, branch kept. Records: the squash message; this section goes at
"merge 113".
