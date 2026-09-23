# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order (revised 2026-09-22, when §59 landed):
**none but §30**, which waits on the operator's decision. (§61, hygiene
bundle V, LANDED 2026-09-23: five items and two live proofs -- a dropped
stofs membership pruned from state after a backup and restored through
the gate; the coops model's third release as one `cloud-upgrade` with
`require_released_builds` left true, `coops-model-003`, first alias-pool
draw `cod`.) (§59 LANDED 2026-09-22: `meta-state/aliases.txt` is the
pool, the run that can launch a new durable machine draws its first free
line and comments it out in place, stage 58 gives the name to the machine.
The live pool holds 3400 names; the first live draw happens at the next
new machine.) (§19 LANDED 2026-09-22: the coops model
image had its second release end to end -- a real modification, the bake,
the pin moved, the gated replace to `coops-model-002`, the post-bake proof
on the new machine, the release, the names back, and the login by name --
and the procedure is OPERATIONS "A model image, end to end: the second
release". The image's content is the group's living work from here.) (§56 LANDED 2026-09-22:
the team's workload connection and role stand, the identity lifecycle keeps
one CI login policy per group -- all five created live at 09:07 -- and the
`sft ssh` proof ran by hand at 09:35 as the enrolled client. The WORKLOAD
form of that login runs in the `perform` job the first time `develop`
reaches `main`; that run proves the CI policy itself and shows which Unix
account a workload lands in, after which `WORKLOAD_CONNECTION.md` folds
into OPERATIONS and the operator adds the `ref` pin to the role.) (§57, §55, §58 and
§60 all LANDED 2026-09-21 -- §55 in two passes, steps 1-3 before §58 and
step 4 after §60, which is how the three stages' dependency cycle was
broken. Both live proofs landed 2026-09-21 22:21 in one applies-on
instance-image run the operator made with `coops-model` running: its record
now answers to `ip-10-26-34-156` as an `AltNames` alias, and the ledger
opened it as durable generation 1. `coops-model` is grandfathered under its
bare name until its first sanctioned replacement, which is the first real
`-NNN` launch.) §55 SPLIT because, taken whole,
§55, §58 and §60 formed a dependency cycle. §56 proved what §19 step 4
claims, and §19 step 5 proved §60's meaning live (a sanctioned replacement
is a new generation with a new name). §59 is deliberately LAST: it overlaps the suffix, and only once
that is standing can anyone judge whether a name pool is still wanted. §30 waits on the operator's decision and depends
on none of this. No hygiene bundle is open; the next non-critical
hygiene issue opens bundle VI.

**Nothing in the naming line is left**; §30 waits on the operator's
decision. Nothing in that shorter path has to be redone -- §58
adds the bare name back as an alias, so a proof written against `coops-model`
survives the suffix.

Standing decisions (operator):

- The documentation describes what is; no document carries a commit hash;
  a landed stage is recorded by its squash message, not by a ledger or an
  archive entry.
- A hygiene issue that should be fixed but does not threaten function goes
  into the open **hygiene bundle** stage as a numbered item, not into a
  stage of its own and not only into a commit message. If no bundle is
  open, start one. Work that is large, or that blocks something, still
  earns its own stage.
- Publication is done: both repositories are public, each a single commit
  built from a redacted tree, with the pre-publication history private and
  archived. The identifiers (account id, project number, VPC, subnet and
  security-group ids, image ids, the state bucket, the Okta org and OPA
  team) are public by decision; the live rosters are real and encrypted to
  the four recipients; the fixture's people are synthetic.
- All terraform state stays in the AWS S3 backend by design; a GCS backend
  for the GCE roots and per-runtime networking validation are the very
  last priorities and are not stages; a session identity for the runtime
  session hook other than the operator's login key is deferred.
- No new GCP work unless a change is likely to make the existing GCP code
  fail; then the GCE cycle runs as the proof, on the operator's account,
  and is torn down. GCP is the operator's money.
- `main` performs (stage 45): a push to `main` records the full
  configuration, then bakes, releases and applies retention on the AWS
  runtime under the write role, then records again. The GCE runtime stays
  out of CI: a declaration change there fails the job before anything
  performs. A push to `main` is the operator's act.
- State backends (stages 46 and 47, landed 2026-09-17): three types, `s3`,
  `local` and `gcs`; every live root stays on the default S3 backend and
  the `gcs` backend is declared (commented out in the live tree) and bound
  to nothing until moving the GCE roots is decided.
- Releases publish to an index (stage 41, landed 2026-09-17): PyPI,
  TestPyPI first, every version through `just release <part|version>
  [test|pypi]`; the first upload, `0.1.1.dev1`, is on TestPyPI and
  installs from it into a fresh virtualenv (an install in the seconds after
  an upload can fail to resolve until the index has propagated). Versions
  on TestPyPI will be deleted during development, and a deleted version is
  never re-cut. The first final version (`just release stage pypi`, after
  a green `full-test` with docker on a clean live configuration, with
  `PYPI_TOKEN` in place) is the operator's call; trusted publishing
  replaces the tokens once the package names are stable.
- §19 (the first real model image) stays planned by the operator's
  instruction; §30 (the contract package) is planned.

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
