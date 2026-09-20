# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order: §53 next (it questions whether a bake's own
tests are enforcing, which §19 depends on); §19 waits on it and on a
released build, §30 on the operator's decision. A new hygiene issue
starts bundle IV.

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

## 19. The first real model image, released and in use

**Why**: the system's stated purpose (EXPLORE "Systemic Purpose") is
images that are correct for a given HPC model, formally released, with
scientists logging in. The retrospective's warning still stands — "the
doorway got finished before the building": the fixture's playbooks are
placeholders (DESCRIPTION.md), the dask image installs dask and nothing
else, and no image has been used by anyone. Every mechanism the purpose
needs now exists: shell + ansible modifications with local mod tests,
in-bake and post-bake tests, declared releases, `require_released_builds`,
group ownership → OPA access (proven by `sft ssh` in stage 1), storage
attached by group. This stage spends them on one model, on AWS.

1. **USER — the model.** Decided 2026-09-19: the group is **`coops`**, the
   instance is a **`c5n.4xlarge`**, and it mounts the **existing `mnt_data`
   and `efs-storage`** — no new storage declarations. What that settles, and
   what it implies:
   - Both storages already allow `coops` and are `active`
     ([storage0.yaml](../cs-image-system-testconfig/storages/storage0.yaml)):
     `mnt_data` is EBS at `/mnt/data`, `efs-storage` is EFS shared with
     `stofs` at mode 2775. Nothing there has to change.
   - **The AZ is already right, and nothing needs pinning.** `mnt_data` is the
     100 GiB volume `vol-0fe1e27716f86c2f2` in `us-east-2a`; EBS is AZ-bound,
     so the instance must be there to attach it — and the runtime's DEFAULT
     subnet is `east2-az1-private` (`subnet-09f79018af845358a`), which is 2a.
     The instance model names no subnet; the builder reads the runtime's
     default. `c5n.4xlarge` is offered in 2a, 2b and 2c, so the size does not
     constrain the choice. Both declared private subnets map no public IP, as
     the standing constraint requires. Note for later: if the default subnet
     is ever flipped to 2b, this instance stops being able to attach
     `mnt_data`.
   - Its users are the `coops` roster: `zachary.wills` (member),
     `mykel.alvis` (admin), conformed to OPA on 2026-09-18.
   - **The image derives from `basic-rh-10` directly** (decided 2026-09-19),
     not from either existing `coops` image: a new `coops`-owned instance
     image whose only modifications are the model's. Cleanest lineage, at the
     cost of repeating whatever setup `imgfile-basic-dask` already does.
   - **The instance stands 24/7** (decided 2026-09-19): a normal declaration,
     left running, so the group's members can log in whenever — the half of
     this stage's purpose that an ephemeral instance would not exercise. It
     bills continuously: roughly $620 a month at the figure above, plus the
     100 GiB volume and the EFS filesystem. `mnt_data` is
     `attachment_cardinality: single`, so while this instance stands it owns
     that volume and no other instance can attach it.

   **Still needed from the operator, and blocking the bake:**
   - **What the image must contain**: the model's packages, its source or
     binaries and where they come from, and the data paths it expects under
     `/mnt/data` and the EFS mount.
   - **What "correct" means**: the smoke run that proves the image, and the
     files and services that must be present after a bake.

   Everything else is settled, and nothing can be baked without those two:
   an image derived from `basic-rh-10` with no modifications is just
   `basic-rh-10`. The cost figure above could not be confirmed from the
   account — this role has no `pricing:GetProducts` — so check it before
   relying on it.
2. **The image**: `basic-rh-10` on AWS plus an instance image owned by
   the model's group; real modifications — ansible for the stack, bash
   `ensure` for glue — idempotent and passing `just test-mods`; in-bake
   `tests:` and `tests.post_bake` running the model's smoke test;
   `release: {model: <name>}`.
3. **The instance(s)**: declared for the group with `image_policy: pinned`
   and `require_released_builds: true` (only a released build may pin);
   storage per the decision; launched through the gates on AWS (private
   subnet, no public IP; the existing network configuration untouched —
   standing constraint).
4. **Users in**: the group's members log in through the Okta gateway
   relay (`sft ssh`); evidence captured, the stage-1 shape.
5. **Operations, once**: the upgrade path exercised end to end (`upgrade
image` → re-bake → `upgrade instance` → gated replace) so the model's
   second release is a procedure, not a discovery; the standing cost noted
   for the AWS account.
6. Records: ledger, PLAN, OPERATIONS "a model image, end to end".
   Feature branch `feature/model-<name>`, squash-merged, kept.

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
   `transition_actions`, `supports_archive`…; `RuntimeBuilder`: the 16
   query/session/dispose hooks; `GroupBuilder`, `ImageBuilder`,
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

## 53. Does a bake's own test actually stop the bake?

**Why**: stage 19's first image baked green twice while carrying an
assertion that cannot pass. The image declared `tests.packages: [vim,
mpdecimal]`; on AlmaLinux 10 there is no package named `vim` (`dnf install
vim` resolves a virtual provide to `vim-enhanced`), so `rpm -q vim` is
always false. The emission committed at `5800f3d` carried that assertion,
under `set -e`, in a `provisioner "shell"` scoped `only` to this image --
and the bake produced `ami-0290b3741222d1e47` and recorded
`tests: {assertions: 6, in_bake: true}`. The instance launched from that
AMI then failed the SAME check post-bake. Either the assertion never ran,
or it ran and its failure did not stop the build; either way a green bake
and a recorded assertion count currently prove less than they appear to,
and stage 19 is being asked to trust exactly that.

A second thing surfaced beside it. Run `e72e195`, whose bake decision was
`skip: current`, DELETED the image's whole packer emission from
`generated/` -- 9 files, 174 lines, the build block, the source, the vars,
the plugins and the mod payload -- and the next real bake (`bb14c55`) put
all 9 back. So the committed emission of an image whose bake is skipped
does not describe that image at all, which is awkward for a tree whose
generated IaC is committed on purpose and whose CI asks "is the committed
emission current with the declarations?".

1. **Establish which**, with evidence rather than inference: re-bake a
   throwaway image whose in-bake test is a bare `false`, keeping the packer
   log. If it goes green, the assertions are not enforcing and the cause is
   in how the test provisioner is emitted or invoked (the `inline_shebang`
   and whether `set -e` governs the inline list; whether the provisioner's
   `only` matches the source actually built). If it goes red, the first
   build's history is the thing to explain instead -- start from whether
   the bake regenerated over `5800f3d` before running.
2. **Make the count mean something.** `tests: {assertions: N, in_bake: true}`
   is recorded from the emitted assertion COUNT, not from a result, so a
   build that skipped its tests and a build that passed them record
   identically. Record what the bake actually reported, or stop recording a
   number that reads like a verdict.
3. **Decide what a skipped bake owes the emission.** Either a skipped bake
   keeps the image's committed packer files as they were (so `generated/`
   always describes every declared image), or their removal is deliberate
   and `config-drift` and the `--commit` contract say so out loud. Today it
   is neither: the files disappear and come back with no note.
4. **A test that cannot pass should be refused before it is baked.**
   `rpm -q vim` is a declaration error the system could catch at validate
   on a package that no repository provides -- cheaper than a bake, and it
   is what would have caught stage 19's first image.
5. Records: OPERATIONS on what a green bake proves. Feature branch
   `feature/in-bake-tests-enforce`, squash-merged, kept.
