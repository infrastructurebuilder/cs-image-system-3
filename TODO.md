# TODO

One section per stage in flight. A landed stage's section is removed;
its squash commit is the record, and the history is in git and
[docs/history/](docs/history/README.md). **USER** marks a step only the
operator can take.

**Open**

- §30, the plugin contract package: planned, re-measured 2026-10-28 and
  reshaped 2026-10-29 by the operator's decisions; two branches, Tier C
  deferred; waits for "do 30".
- §94, the F44 review: standing; next on or after 2026-11-09.
- No hygiene bundle is open; the next non-critical issue opens bundle
  XIX.
- No documentation stage is open.

**Release**

- 0.1.3, the latest final release: PyPI and TestPyPI, tag `v0.1.3`
  (3c05229), 2026-10-28, cut straight from 0.1.2 (no development
  release between). Carries §98 and §100. Its tag published the four
  template repositories again (tag `v0.1.3`).
- The reference configuration runs 0.1.3 (take 683eb45); `perform`
  green on 2026-10-28, nothing baked. Its tags `v0.1.3-before`
  (bf3cc6e, on 0.1.2.dev2) and `v0.1.3-after` (b80b27e) bracket the
  move.
- Last development release: 0.1.2.dev2.
- The §66 proof passed whole on 0.1.3 (2026-10-28): "Use this
  template" on `standard-aws`, the copy's first push green with
  `perform` SKIPPED (red on 0.1.2, §98 item 3), `uv tool install
  cs-image-system==0.1.3` all 18 from PyPI, `just init` in the copy,
  a dispatched dry run green with `live` and `perform` SKIPPED. The
  copy was deleted afterwards. Nothing is owed at the next final
  release but the usual republication.
- `STARTER_PUSH_TOKEN` (`cs-image-system-starter-repos-token`) expires
  2027-10-25: renew it before then.

**Landed since 2026-10-05** (newest first)

- §101, hygiene bundle XVIII: 2026-10-28, its squash commit. The CLI
  takes `--version` and prints the installed release before anything
  loads, so a starter's `just init` line names the release it found.
- §100, hygiene bundle XVII: 2026-10-28, its squash commit. CI's
  guard (`runtime-unchanged`) passes the vendor's newest image moving
  under a base with no build yet, as `config-drift` does, and names
  the move; a diff cut short is never read as one.
- §98, hygiene bundle XVI: 2026-10-27, its squash commit.
  `config-drift` says what it is doing as it goes and leaves the
  provider cache out of its copy, as every `full-test` copy now does
  too; an unconfigured copy of a starter skips `perform` on its first
  push to `main`.
- §99, a development pin installs from TestPyPI again: 2026-10-26, its
  squash commit (every install line names `--index-strategy
  unsafe-first-match`).
- §97, hygiene bundle XV: 2026-10-24, its squash commit. A tree
  `init-config` writes links out of the starter at the release's tag.
- §66, starter repositories on GitHub: 2026-10-24, its squash commit.
  Four public template repositories generated from `docs/examples/`
  per final release; every CI job reads its image from
  `vars.CSIS_RUNNER_IMAGE`; the runner image is public.
- §96, hygiene bundle XIV: 2026-10-23, its squash commit. A release
  resumes after a partial upload (`release-finish`), uploads one project
  at a time, reads PyPI's new-project limit as "not now" and proves its
  token; the strict query reads each group's OPA objects back.
- §83, a release asks its publish target first: bbb7ee4, 2026-10-17.
- §95, hygiene bundle XIII: 8cdc07c, 2026-10-17.
- §92, CI runs in the system's own AlmaLinux 10 image: 661270f and four
  follow-ups, 2026-10-16.
- §93, everything carries its configuration's id: 23bb441, 2026-10-16.
- §81, hygiene bundle XII: 64c3bc7 to ca7127d, item 33 b28d50b,
  2026-10-14.
- §65, the walk of the daily driver: 8afd4ef, 2026-10-14.
- §84 to §91, the walk's findings: 4fb338b, b0494fa, c6af4b2, 9655327,
  20206e8, 7eb5962, cdb80bf, e72cc1b, 2026-10-07 to 2026-10-14.
- §82, an image says which configuration owns it: 0d1850c, 2026-10-05.

**Standing decisions** (the operator's)

- Documents describe what is and carry no commit hash; a landed stage's
  record is its squash message.
- A non-critical issue goes into the open hygiene bundle (start one if
  none is open); large or blocking work gets its own stage.
- A stage is a plan until the operator says to execute it.
- A documentation stage changes no code; a code change it needs is a new
  stage.
- Documentation stays current: work that changes behaviour,
  configuration, tests or procedure and lands undocumented opens the
  rolling documentation stage, which lists what changed since the last
  update.
- Both repositories are public, each from one redacted commit. Account,
  project, network, image and bucket ids and the Okta org and team are
  public by decision; live rosters are encrypted to the four recipients;
  fixture people are synthetic.
- All terraform state stays on the S3 backend. Backends `s3`, `local`
  and `gcs` exist; `gcs` is declared and bound to nothing. Moving the
  GCE roots to GCS and per-runtime network checks are last, and not
  stages.
- GCP is the operator's money: no new GCP work unless a change could
  break the GCP code; then the GCE cycle runs on the operator's account
  and is torn down.
- `main` performs (stage 45): it records, bakes, releases and applies
  retention on AWS under the write role, then records again. GCE stays
  out of CI. A push to `main` is the operator's.
- Releases: `just release <part|version> [test|pypi]`, TestPyPI first; a
  deleted version is never re-cut; trusted publishing replaces the
  tokens once package names are stable.
- The bootstrap is ongoing work: a new release-owned part, runtime or
  secret owes it a section, module or question in the same stage.
  Keeping its state in GitHub is not built. The operator's words (§70):

  > Initially, the user must install the base application (generally using `uv`).
  > Then the user would fork and clone the starter repository.  This would give them
  > a place to land the bootstrapping code.  They would then start the bootstrapping
  > interview, and should end up with a runnable copy of the application, as well
  > as a configured set of dependencies, bootstrap code, and target locations for
  > state management (including, possibly, storing state in github [not recommended]).
  >
  > Once landed, the §70 work should be considered part of the ongoing updates of the application
  > and the starter repository, such that any new items are part of the process.

---

## 30. The plugin contract is a package of protocols

**Status: planned; re-measured 2026-10-28 against the tree after §101
and reshaped 2026-10-29 by the operator's decisions below. Waits for
"do 30".**

**Why**: a plugin author should be able to write a plugin against ONE
package, `cs-image-system-contract`, and never import, let alone
subclass, the core's base classes. The base classes are the convenient
implementation of that contract, not the contract itself; a plugin that
satisfies the protocols structurally is a first-class plugin (the
operator's goal, 2026-09-13; it reversed the direction §29 had taken).
The contract is upstream of the core: the core conforms to it, and a
new hook is a contract change first, the base's change second, in that
order within one branch.

**Decisions** (the operator's, 2026-10-29)

- One package, `packages/contract` -> `cs_image_system.contract`, with
  one module per kind (`contract.runtime`, `contract.storage`,
  `contract.state`, ...) over `contract.core`, and a test that holds
  the import direction between the modules: a kind module imports
  `core` and only the kinds it declares it reads. Not one api package
  per kind: the shared core dominates (three names are used by all
  fourteen plugins, most kind surfaces are thin), the kinds read each
  other (a storage plugin reads the runtime builders; images read
  groups and storages), and the `==` lockstep would erase independent
  versioning anyway.
- The contract lives in this repository as a workspace member. A change
  spanning contract and core would otherwise need a release between two
  repositories at every step, and a PyPI release of `base` cannot carry
  a git-sourced dependency. The separation is enforced here by the
  metadata test (declared dependencies equal the imports) and the
  import-direction test. A separate repository is the end state once
  the contract stops changing weekly, and an external proof plugin in
  its own repository, installing the contract from the index and
  nothing else, comes at that point.
- Tiers A and B now, as two branches. Tier C, the run-context
  protocol, is its own later stage.
- The proof plugin is a state backend under `packages/`, pinned by the
  root package and published like every member (the dummy plugin's
  precedent; every build, publish and test machine is glob-driven).
- No out-of-tree plugin exists: `base/protocols/` is removed, no shim.
- Versions: `==` lockstep during §30. The contract's own compatibility
  version, with `base` declaring the range it implements, is a later
  stage; the docs tell an external plugin to pin a floor.
- Abortable means each branch lands alone and leaves the tree strictly
  better (bar green, golden byte-identical, docs current); the next
  branch starts on the operator's word.
- `docs/example-plugin/plugin-b` is deleted in branch 1 (nothing tests
  it, its model and builder names differ, it imports the bases). The
  dummy plugin stays as the hook template and test double.
- The `cs_image_system.plugins.hooks` and `cs_image_system.bootstrap`
  entry points are out of scope: a plugin contributing a hook or a
  bootstrap section still depends on `base`, and the contract README
  says so.
- One release after the last branch; no development release and no
  reference move mid-stage.

**Where things stand** (measured 2026-10-28; the 2026-09-13 numbers had
drifted): plugins import 148 names from 63 `base` modules, 65 of them
used by one plugin and three by all fourteen (`AbstractPluginMetadata`,
`CSIS_MODEL_CONFIG`, `PluginMetadataProtocol`); 29 of the names are
functions whose first argument is the run context, at 48 call sites;
the context is reached by 53 `_get_context()` calls and 20
`GlobalTypeContext()` constructions, and four `base.utils` helpers
construct it inside. `GlobalTypeContext` has 76 public names,
`MetaState` 54. The kind bases carry about 127 domain hooks (runtime
41, group 41, storage 12, os 12, user 11, image 6, mod 3, instance 1,
state 0) beside the six universal ones; `module_args` and
`supports_archive` are plugin-only. No plugin imports `system` and no
cross-plugin dependency is undeclared any more (the dummy imports left
in e74cb59); the three private cross-plugin names (`_groups`,
`_public_read`, `_make_credentials`) remain, and `packer-plugin`
declares an `aws-runtime-plugin` pin it never imports. No plugin
declares `base`; all reach it through `system`. `tf-s3-state-plugin`
needs 6 core names and three from `hashicorp-utils`, none of them
context-first: a state backend registers itself by pushing a
`BackendRegistration` into the `hashicorp-utils` collector singleton
from its `finalize`, and the core itself reads only the backend's
executable. Found on the way: `issubclass(bc, NameTypedProtocol)` in
`global_context` would raise `TypeError` (the protocol has a property
member) and is masked only by the short-circuit before it; the
orchestrator's `csis_name` hatch moved behind an `Any` rather than
being fixed; `AbstractPluginMetadata.version` returns the metadata
version; `StateManagementRootProtocol` has zero implementers. DESIGN
has no plugin-contract section and OPERATIONS has no "writing a
plugin": both are written new, not rewritten.

**Branch 1, `feature/contract-package`** (Tiers A and B, about four
days)

1. The package: a workspace member depending on pydantic and
   `packaging` only; `base` depends on it, never the reverse, and a
   test asserts the direction. It carries what a plugin constructs or
   reads without behaviour: the constants (`VCT`, `FK_TARGET`,
   `DEFAULT`/`SELF`/`NONE`/`OOPS_DEFAULTS`, the model-id sentinels,
   `PLUGIN_TYPES`), `CSIS_MODEL_CONFIG`, `fk_field`/`templated_field`
   and the field kinds, `ExecutionLifecyclePhase`, `Lifecycle` and
   `LifecycleSpec` as data (the lifecycle registry stays in `base`),
   `Asset`/`AssetSet` (with `sort_and_write`'s context reach moved out
   to `base`), a `PluginMetadata` record (the seven fields as data;
   `AbstractPluginMetadata` becomes its convenience, its `version`
   fixed by an explicit argument), and the pure helpers plugins use
   (`super_safe_name`, `safe_name`, `hcl_expr`, `HclRaw`,
   `render_module_call`), which `base` re-exports. `ExecutableModel`
   stays in `base` (it runs subprocesses); the contract carries an
   `Executable` protocol and `CFExecutables` as the command-list
   carrier typed on it. `HookSet` stays in `base`.
2. Tier A, the model protocols, one module per kind: `NameTyped`
   (`name`, `type_`, `description`, `aliases`, `global_id`,
   `get_classification`), `BuilderModel`, and one per kind with exactly
   the attributes the core reads. `ParentPropertyHolding` declares
   `_model_id`/`model_id` only; the registry reach in
   `identified_model` moves to a `base` mixin, and the nine hand copies
   of `_model_id` (seven in `base`, two in the cloud networking models)
   go through it.
3. Tier B, the behaviour protocols: `PluginArtifact`, `Builder` (the
   six universal hooks and the three finalize-phase hooks), and one
   protocol per kind for the domain hooks, recounted from the bases
   when written, not from this section. `contract.state` also carries
   the backend seam: `StateLocation` and `BackendRegistration` as data
   carriers and the kind protocol (`location`, `backend_settings`,
   `remote_state_settings`); the collector PULLS registrations from
   the registry's state models (`to_backend_registration()`) instead
   of a model pushing into the singleton, so the three state plugins
   and the proof plugin import nothing from `hashicorp-utils`. The
   protocols carry NO bodies: the `global_id`, `get_classification`,
   `get_self_injected_name` and `get_subitem_overrides` defaults move
   to the base classes. `StateManagementRootProtocol` is deleted and
   `state_backends` is typed on the contract's state model protocol.
4. The base classes implement the protocols nominally, so pyright
   checks every base against its protocol at definition time;
   `contract.testing` ships `assert_conforms(cls, protocol)`
   (signature-level, stricter than `runtime_checkable`'s name-only
   check) and the core's tests run it over every base class and every
   built-in plugin's models and builders. `ProviderSpecificImage` and
   `BuilderBase` conform deliberately.
5. Runtime checks stay structural and move to the contract's
   protocols: the loader (`PluginMetadata`), the registry (`NameTyped`,
   `PluginArtifact`), the orchestrator's marker dispatch
   (`SelfInjectedName`, `ParentPropertyHolding`, `SubItemOverride`).
   The masked `issubclass` TypeError is fixed there. The mapper drops
   its base-class identity table (`_base_vcts`) and `PLUGIN_TYPEMAP`'s
   gate dispatches on the contract's `BuilderModel`.
6. Plugins depend on the contract: every plugin's `pyproject.toml`
   declares `cs-image-system-contract` and, where it subclasses the
   bases (all fourteen today), `cs-image-system-base`; none declares
   `system`. `hashicorp-utils` is declared for what it is, a library,
   and `packer-plugin`'s unused pin goes. The three private
   cross-plugin names get public names.
7. Residue from §29: `RuntimeBuilderBase`'s inline `TypeVar`; the four
   escape hatches (`builder_base.py`'s `csis_classifier`, the
   orchestrator's `csis_name` behind `Any`, the registry's `cast`,
   `os_builder_runtime_config.py`'s `identified_model`) fixed, not
   repointed. `docs/example-plugin/plugin-b` deleted.
8. Records and docs: the contract's README, held to the four sections
   with "Writing a plugin" before them (the entry point, the metadata
   record, a model and a builder per kind, what may be imported, how
   an external plugin pins the contract); `base`'s README "The plugin
   contract" rewritten to point at it; PLUGINS.md's tables and
   DAILY_DRIVER's chapter 7 gain the package; a new OPERATIONS "Writing
   a plugin" and a new DESIGN plugin-contract subsection; the dummy
   README's pointer to plugin-b goes. The touch points a new member
   owes: the root pins, `tool.uv.sources`, testpaths, pythonpath,
   extraPaths, bumpversion's `glob_exclude` (the contract joins it,
   `base` leaves it), `NOT_PLUGINS` in the examples test, the member
   count in the metadata test, SPDX headers, and the prose counts of
   packages and projects in OPERATIONS, PLUGINS.md and DAILY_DRIVER.

**Branch 2, `feature/contract-example`** (the proof, about two days)

9. `packages/contract-example-plugin`: a trivial state backend
   implemented against `cs_image_system.contract` ONLY. A test greps
   its source for `cs_image_system.base`, `cs_image_system.system` and
   `cs_image_system.hashicorp_utils` and fails on any hit; it is loaded
   by entry point, its model structures from a fixture YAML, and it
   takes part in a dry `run --all` over a copy of the frozen fixture
   with its backend emitted for a root that names it. It is in
   `NOT_PLUGINS` like the dummy, so the published starters do not
   declare its key. Without it the contract is a claim.

**Deferred, each a stage of its own**: Tier C (`RunContext` with the
76 members and `MetaState` as its own protocol; the 29 context-first
functions as methods of it; `bind(ctx)` injection replacing the 20
constructions and 53 `_get_context()` calls; the four `base.utils`
helpers that build the context inside); the hooks and bootstrap entry
points in the contract; the contract's own compatibility version; the
separate repository and the external proof plugin.

**Acceptance at every branch**: golden byte-identical; bar green;
pyright at 0 errors; the conformance test green over every base and
every built-in plugin; the docs tests green; `just full-test` legs
green. Records: each branch's squash message; this section goes when
the last branch lands.

## 94. A verification starts a machine its operator switched off: KEPT, and reviewed monthly

**Status: OPEN 2026-10-15 as a stage of its own, moved here from hygiene
XII (item 25) when the bundle closed; the bundle's thirty-three items
landed in §82, §86, §88, §91, §93 (a plan) and the seven groups and item
33 of 2026-10-14/15. Nothing here runs: it is a standing review. USER,
on or after each date: keep the behaviour, or make it a stage (a
verification SKIPS a machine that is off unless it is asked to start
it). Each review is written below with its date and its outcome.**

**The finding.** The walk's F44 (2026-10-09, stage 14f; seen in the
machine's own boot log and in CloudTrail). `verify instance` on a
stopped machine starts it, checks it and stops it again (stage 57's
bounded exception); the daily driver's failure table said the opposite.
The operator's decision that day: "let's keep the behavior for F44 but
make a very prominent note about it somewhere. We should revisit that
question at least once a month for the next 4 months." The note is made:
`DAILY_DRIVER.md` 3.5 in capitals, and the section 6 row corrected.

**The reviews.**

- 2026-11-09: (open)
- 2026-12-09: (open)
- 2027-01-09: (open)
- 2027-02-09: (open)
