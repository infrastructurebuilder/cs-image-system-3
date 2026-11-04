# 113. The kit and the engine: `base` splits where the plugins stop

**Status: OPEN 2026-11-03. Waits for "do 113". First of the four
decomposition stages (§113 to [§116](STAGE-116.md)); the measurement that shaped them
is below.**

The goal (the operator, 2026-11-03): decompose the system until a
runtime is defined outside it, so the system installs without any
runtime and a runtime installs without the system's engine. The
contract (§30) is the leaf every plugin is written against and stays
one: `base` depends on it, never the reverse, and
`tests/test_v2_contract.py` holds the direction. What a plugin needs
beyond the contract today is a part of `base`, and that part is
measurable. Over the 136 modules of `base` (24,649 lines), the
transitive closure of what the sixteen plugins and hashicorp-utils
import is 70 modules (13,932 lines), and the closure is closed: none of
the 70 imports any of the other 66 (10,717 lines). So `base` splits
into two packages today with no cycle, along a line nobody drew but the
imports already keep.

The two halves, by name. **The kit** (what a plugin needs): the base
classes (`basic/*`), the models (`models/*` but the six engine-only
ones below), `global_context`, `registry`, `lineage`, `launch_params`,
`launch_enrollment`, `encryption`, `public_safe`, `capabilities`,
`materialize`, `bake_steps`, `bake_user`, `launch_delivery`,
`power_state`, `posix_ids`, `identity_attributes`, `image_sources`,
`image_tests`, `storage_state`, `singleton`, `utils`,
`helpers/{field_helpers,field_kinds,plugin_config}`, the bootstrap
vocabulary (`bootstrap/facts`, `bootstrap/questions`),
`commands/run_lifecycles` (for `HookSet` alone; item 3 moves it). **The
engine** (what only the system runs): every other `commands/*` module
(validate, emission, preflight, dispose, relabel, resolve, restamp,
gate, the five generators, login_proof, workload_token, runtime_facts,
run_scope, state_migration, unmount, upgrade, load_failures,
finalization, identity_gids), `orchestrator`, `meta_state`,
`state_query`, `template_utils`, `release`, `retention`, `mod_tests`,
`generations`, `provider_aliases`, `alias_pool`, `loader`,
`read_models`, `v2_validation`, `reserved_names`, `workload_access`,
`tofu_lock`, `image_names`, `accounts_reconcile`, `ansible_launch`,
`init`, `lifecycle`, `lifecycles`, `helpers/{async_utils,config,
resolution_stages,yaml_process}`, `models/{container,encryption_config,
ia_config,public_safe_config,root_item,runtime_builder_item}`, and the
bootstrap engine (`bootstrap/{answers,generate,github,hcl,interview,
sections}`). The list is the measurement's, read again at "do 113":
the stage's first act is the script that computes it, kept as the test
of item 1.

1. The engine moves out of `base` into a package of its own. `base`
   keeps its name and its import paths and becomes the kit, so **no
   plugin changes an import or a dependency**; the engine's modules
   move to `cs_image_system.engine` (package
   `cs-image-system-engine`, depending on the kit), and `system` and
   the tests rewrite their imports to it. Every old path
   (`cs_image_system.base.commands.validate` and the rest) stays as a
   re-export of the new one, the §30 shim pattern, so the undo is a
   swap. **YOUR DECISION:** the engine package's name (`engine`, the
   default; or the engine goes into `system`, which blurs "no plugin
   depends on `system`"). The test: the closure script runs over the
   workspace and asserts that no kit module imports the engine and
   that every `cs_image_system.base` name a plugin imports resolves
   inside the kit; the seam stays measured, not remembered.
2. The kit reaches the terraform library nowhere.
   `register_declared_backends` in `global_context` imports
   `cs_image_system.hashicorp_utils.collector` lazily: the kit reaching
   into the library that depends on the kit, a cycle the lazy import
   hides. It is the engine's act at load (the orchestrator hands the
   state backends' registrations to the collector) and moves to the
   engine beside the three other lazy imports of the collector
   (`run_lifecycles`, `validate`), which are the engine's and stay as
   they are. hashicorp-utils then depends on the contract and the kit
   alone, as a plugin does; the engine's dependency on it stays
   optional and lazy (DESIGN §3P: "the library is optional to the
   core").
3. The declaration vocabulary that still lives in `base` moves down
   into the contract, finishing the "deferred" list of DESIGN §3P. (a)
   `contract.bootstrap`: `Facts`, `Question`, `Section`, `Rendered`,
   `Secret`, `Raw`, `Refused`, `Answers`, the four coverage marks
   (`MADE`, `READ`, `ADOPTED`, `BY_HAND`) and `ENTRY_POINT_GROUP`; the
   two modules they come from import nothing from `base` already.
   `gather`, the interview, the generation, the GitHub section and the
   HCL writer stay in the engine. (b) `contract.hooks`: `HookSet` and
   `HOOK_ENTRY_POINT_GROUP`, out of `commands/run_lifecycles` (a
   plugin-facing type in a 734-line command module; dummy-plugin is
   its one user). (c) The plugin entry-point group names
   (`cs_image_system.plugins.<kind>`), where `contract.constants` does
   not hold them yet. The old paths re-export (shims), `assert_conforms`
   covers the new kinds, the contract README's "What moved where"
   table grows.

**Out of scope**: any change to what a plugin imports
([§114](STAGE-114.md), [§115](STAGE-115.md)); the umbrella package's
dependencies ([§116](STAGE-116.md)); removing the §30 shims; the
contract's own repository; any YAML key, record, emission or cloud
state.

**Acceptance**: code only; the emission of the reference and of every
fixture is byte-identical before and after (the bar's golden tests);
`tests/test_v2_contract.py` holds the direction for the three packages
(contract imports nothing from kit or engine; kit imports nothing from
engine); the closure test of item 1 is green and lists its two sets;
no plugin's `pyproject.toml` changes; `uv tool install` of the umbrella
installs the engine; the §30 reversibility bracket is repeated
(`s113-before`/`s113-after` tags whose messages carry the undo). One
squash, branch kept. Records: the squash message; this section goes at
"merge 113".
