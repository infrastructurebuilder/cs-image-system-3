# TODO

One section per stage in flight. A landed stage's section is removed;
its squash commit is the record, and the history is in git and
[docs/history/](docs/history/README.md). **USER** marks a step only the
operator can take.

**Open**

- §30, the plugin contract package: planned; waits on the operator's
  decision.
- §94, the F44 review: standing; next on or after 2026-11-09.
- §98, hygiene bundle XVI: open, one item; a plan, waits for "do 98".
- No documentation stage is open.

**Release**

- 0.1.1, the first final release: PyPI and TestPyPI, tag `v0.1.1`
  (766a210), 2026-10-22.
- The reference configuration runs it from PyPI; `perform` green on
  2026-10-23.
- Last development release: 0.1.1.dev26.
- Owed at the next final release: the first publication of the four
  template repositories (§66, landed). Proof: the tag's `publish` job
  publishes all four; "Use this template" on `standard-aws`, `just init`
  in the copy, and its CI green with no setup.
- `STARTER_PUSH_TOKEN` (`cs-image-system-starter-repos-token`) expires
  2027-10-25: renew it before then.

**Landed since 2026-10-05** (newest first)

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

**Why**: a plugin author should be able to write a plugin against ONE
package — `cs-image-system-contract` — and never import, let alone
subclass, the core's base classes. The base classes are the convenient
implementation of that contract, not the contract itself; a plugin that
satisfies the protocols structurally is a first-class plugin. That is the
operator's stated goal (2026-09-13) and it reverses the direction §29 had
taken (fold the protocols into the bases): the protocols are kept and made
real. Today the promise is not delivered: `base/protocols/` imports
`constants`, `registry` and the field helpers from the rest of `base`; a
plugin's own `pyproject.toml` depends on `cs-image-system-system` (the CLI
host); plugins import from ~60 core modules and ~106 names, of which ~24
are functions whose first argument is the live run context, reached
through the `GlobalTypeContext` singleton at ~50 sites; the mapper
dispatches on base-class identity; and two things already satisfy a
protocol structurally only by accident (`ProviderSpecificImage`, and every
`BuilderBase` at the registry's gate). Measured 2026-09-13 with the
per-plugin distance: `tf-s3-state-plugin` needs 7 core names,
`tf-ebs-instance-plugin` 42 plus 24 context reaches.

**Honest cost**, in three tiers: the two static tiers (models, behaviour)
are ~3–4 days of mostly mechanical work; the context interface is 1–2
weeks and is the part that makes an external plugin real; the proving
plugin 1–2 days. Call it three weeks, done as three branches.

1. **The package**: `packages/contract` → `cs_image_system.contract`, a
   workspace member with NO dependency on `base` or `system` (pydantic and
   `packaging` only); `base` depends on it, never the reverse, and a test
   asserts the import direction. It carries the constants protocols need
   (`VCT`, `FK_TARGET`, `DEFAULT`/`SELF`/`OOPS_DEFAULTS`),
   `CSIS_MODEL_CONFIG`, `fk_field`/`templated_field`, the lifecycle enums
   (`ExecutionLifecyclePhase`, `Lifecycle`, `LifecycleSpec`, `HookSet`) and
   the value types a plugin constructs (`Asset`/`AssetSet`,
   `ExecutableModel`, `CFExecutables`) — concrete data carriers are part
   of a contract; behaviour is not.
2. **Tier A — model protocols** (structural, with attribute declarations):
   `NameTyped` (`name`, `type_`, `description`, `aliases`, `global_id`,
   `get_classification`), `BuilderModel`, and one per builder kind
   (runtime, os, storage, image, instance, mod, group, user, state) with
   exactly the attributes the core reads. A plugin model is any pydantic
   dataclass under `CSIS_MODEL_CONFIG` that satisfies them; the `type`
   alias and `fk_field` metadata are the contract's, exported. The
   `ParentPropertyHolding` attribute (`_model_id`) is declared in the
   protocol and by each implementer — a protocol cannot carry a dataclass
   field, which is why it is copied at nine sites today; `base` offers a
   pydantic-dataclass mixin as the convenience, and the copies in the
   core's own models go through it.
3. **Tier B — behaviour protocols**: `PluginMetadata` (the seven
   properties; `AbstractPluginMetadata`'s `version` bug — it returns the
   metadata version — fixed on the way), `PluginArtifact`
   (`csis_name`/`csis_classifier`), and the builder surface: the six
   universal lifecycle hooks (`generate_items_{before,during,after}`,
   `get_commands_to_run_{before,during,after}`) as `Builder`, plus one
   protocol per kind for the ~60 domain hooks (`StorageBuilder`:
   `module_args`, `capability_type`, `attachment_cardinality`,
   `transition_actions`, `supports_archive`…; `RuntimeBuilder`: the 21
   query/session/dispose/power hooks (16 until stage 57 added the power
   state -- `can_query`/`query_instance_power_state` and
   `can_set_instance_power_state`/`start_instance`/`stop_instance` -- so
   recount before trusting any number written here); `GroupBuilder`, `ImageBuilder`,
   `InstanceBuilder`, `ModBuilder`, `UserBuilder`, `StateBuilder`). The
   protocols carry NO implementation (today `NameTypedProtocol` supplies
   `global_id` and a `get_classification` default; those bodies move to
   the base classes). `StateManagementRootProtocol` is dead — zero
   implementers — and is deleted.
4. **Tier C — the context protocol**, the expensive part: `RunContext`
   with the ~55 members plugins read (top: `meta_state`,
   `runtime_builders`, `os_builders`, `run_id`, `instances`, `images_map`,
   `generation_path`, `storage_builders`, `storages`, `dry_run`, …), with
   `MetaState` its own protocol (the mutable run records that the storage
   and instance builders write on both clouds); the ~24 context-first
   functions plugins import (`capabilities.*`, `lineage.*`,
   `launch_params.*`, `image_tests.*`, `storage_state.*`,
   `identity_attributes.*`, three from `commands.verify_instance`) either
   become methods of the protocol or are re-exported by the contract as
   functions typed against it. `GlobalTypeContext` implements it; the
   builder protocol receives the context by injection (`bind(ctx)`) so a
   plugin never constructs the singleton — the ~18 direct
   `GlobalTypeContext()` constructions in plugin code and the 33
   `_get_context()` calls go through it.
5. **The base classes implement the protocols** — `class NameTyped(…)`
   declares the protocol nominally as well, so pyright checks every base
   against it at definition time; a `contract.testing` module ships
   `assert_conforms(cls, protocol)` (signature-level, via `typing`
   introspection, stricter than `runtime_checkable`'s name-only check)
   and the core's tests run it over every base class and every built-in
   plugin. The two accidental structural implementers become deliberate:
   `ProviderSpecificImage` and `BuilderBase` conform by the same test.
6. **Runtime checks stay structural** and move to the contract's
   protocols: `loader.py` (`PluginMetadata`), `registry.py`
   (`NameTyped`, `PluginArtifact`), the orchestrator's marker dispatch
   (`SelfInjectedName`, `ParentPropertyHolding`, `SubItemOverride`) — all
   `runtime_checkable`, all name-only at runtime, all backed by step 5's
   conformance test so the looseness is not the only check. The mapper:
   `PydanticConverter` drops its base-class identity table (`_base_vcts`)
   and dispatches by `csis_classifier()` for any registered dataclass that
   satisfies `NameTyped` — the registry already resolves plugin models by
   type key.
7. **Plugins depend on the contract**: every plugin's `pyproject.toml`
   depends on `cs-image-system-contract` and, only where it truly uses a
   core utility, on `base` (the ~12 pure helpers — `render_module_call`,
   `hcl_expr`, `super_safe_name`, … — move to the contract or to
   `hashicorp-utils`, which is declared for what it is: a library five
   plugins use, not a plugin). The three undeclared dependencies
   (`tf-ebs`→`aws_runtime`, `aws-runtime`/`gcloud-runtime`→`dummy_plugin`)
   are declared or removed; the three private cross-plugin imports
   (`_groups`, `_public_read`, `_make_credentials`) get public names. No
   plugin depends on `system`.
8. **The proof — an external plugin**: a new workspace member
   `packages/contract-example-plugin` implementing one trivial storage (or
   runtime) plugin against `cs_image_system.contract` ONLY — a test greps
   its source for `cs_image_system.base` and fails on any hit; it is
   loaded by entry point, its model structures from a fixture YAML, and it
   participates in a dry `run --all` over a copy of the frozen fixture
   with its module call emitted. That is the acceptance; without it the
   contract is a claim.
9. Residue carried from §29: fix `RuntimeBuilderBase`'s anonymous inline
   TypeVar (it was never generic); the nine `_model_id` copies in the core
   go through the mixin; the four type-escape hatches caused by the
   protocol/base split (`builder_base.py:61`, `orchestrator.py:681`,
   `registry.py:86`, `os_builder_runtime_config.py:173`) are fixed, not
   repointed. Golden byte-identical at every branch; bar green; pyright at
   0 errors. Records: ledger; DESIGN's plugin-contract section rewritten
   around the package; OPERATIONS "writing a plugin". Branches
   `feature/contract-package` (steps 1–3, 5–7),
   `feature/contract-context` (step 4), `feature/contract-example`
   (step 8), each squash-merged, kept.

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

## 98. Hygiene bundle XVI

- **Status:** OPEN 2026-10-26, one item; a plan until the operator says
  "do 98". The next non-critical issue joins it.

1. **`config-drift` is silent for minutes.**
   - *Seen:* on 2026-10-26, taking 0.1.2.dev1 into the reference
     configuration, `just config-drift` printed nothing for many minutes
     after `just record` finished, and looked stuck. It makes a dry run
     of every lifecycle into a temporary copy (a `tofu init` per root)
     and says nothing until the comparison.
   - *Fix:* it says what it is doing as it goes -- the copy, each
     lifecycle, each root's `init` -- and how long it took; the daily
     driver says a refresh takes minutes.
