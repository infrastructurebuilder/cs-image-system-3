# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: none in progress. **§65, walking the daily driver,
LANDED 2026-10-14 (8afd4ef)**: between 2026-10-05 and 2026-10-14 the
operator took two configuration repositories (`standard-aws`, then
`standard-aws-posix`) from nothing to running and back to nothing
against 0.1.1.dev14 to 0.1.1.dev23, typing from a page the system
wrote as it went, now frozen as
[docs/history/WALK-2026-10.md](docs/history/WALK-2026-10.md). It found
64 things: six became stages 86 to 91 (landed, released, proved);
thirty are hygiene bundle XII (§81, a plan); one (F44) was kept by
decision with a monthly review; nineteen owed words alone, written
with the landing. Open and waiting for the operator's word: §92 (an
AlmaLinux 10 CI image, planned), §81, §83, §66 and §30. The `setup-just`
correction (b23f33f) and the walk's words await the next release.
§91, CI names the machine it runs on and the actions it
uses (hygiene XII items 7 and 28, made one stage by the operator's
word of 2026-10-14, "do 7 and 28 together as a single stage"; GitHub
moves `ubuntu-latest` to Ubuntu 26 from 2026-10-19), LANDED
2026-10-14 (e72cc1b) by the operator's word, released in dev24
(b263aea) and PROVED on the reference configuration: `verify` and
`live` green on `Image: ubuntu-24.04`, and its `perform` green on
`main` the same day (nothing to bake, the login proof as a workload
ok, no drift). One notice survived, since `setup-just@v3` is
composite and wraps an inner action on Node 20; its v4 does not,
and the correction LANDED (b23f33f) by the operator's word, to go
out with the next release.
§90, a group's release is decided by the state and
cannot be spent by a dry run (the removal of an unmanaged group
from state was decided from the identity read-model, which every
dry run and every `record` rewrites, so the run after a dry run
planned the group's destruction and only the gate refused it; now
the runner's pre-plan step asks the state; walk finding F63),
LANDED 2026-10-13 (cdb80bf) by the operator's word, who made it a
stage of its own and had it done before the walk went on, is
released in dev23 (ec7e4ef), which the reference configuration has
taken on its `develop`, and is PROVED live: the first walk's own
group, released by the sequence that had failed (the dry form,
then the run), left state with its eight resources in the runner's
pre-plan step, and the run applied nothing.
§89, CI makes the login proof while it still holds the
write identity (every starter's workflow took the read-only identity
back before the proof, and a posix proof's ssh opens a session the
read-only role may not; walk finding F58), LANDED 2026-10-13
(7eb5962) by the operator's word, the read-only role left as it
was. It is released in dev22 (9584a03, 2026-10-13), which the
reference configuration has taken on its `develop` (CI green), and
is PROVED live: the posix walk took the release and its `perform`
on `main` went green the same day, CI logging in as the group's
proof user over ssh while it held the write identity, where three
hours earlier the same step had been refused the session.
§88, a membership the YAML dropped is removed by the
run (the runner's prune step names the attachment of each one, and
the gate allows exactly those; walk finding F38), LANDED 2026-10-08
(20206e8), is released in dev21, which the reference
configuration has taken, and is PROVED live: the walk put its
second person into `walk_team` by a run and took them out by a
run, the gate sanctioning exactly that attachment and OPA holding
nobody afterwards. §87, the
group on a machine lists its members by their
account names (each read from OPA's `unix_user_name`, never derived;
walk finding F37), LANDED 2026-10-08 (9655327), is released in
dev20 and PROVED live: the walk's second person, whose two names
differ, logged in and their session carried the group. §86, a bake
waits for the package database (the
first provisioner settles the build machine, a package step waits
out a held database, and the starters' base tests name what a base
carries; walk findings F29 and F28), LANDED 2026-10-07 (c6af4b2):
released in dev19 (dev18 was cut from the walk branch by mistake and
is on the index, unused) and PROVED live: the walk's third `perform`
baked both its images under the bootstrap-made write role, Systems
Manager finishing its work on each build machine undisturbed. §81,
hygiene bundle XII, is open (thirty items the walk
found; 3 and 4 landed with §82, the rest a plan). §82, an image
says which configuration owns it, LANDED 2026-10-05 (0d1850c) and
is released in dev15, taken by the reference configuration, its
images relabelled. §84, a new group can be created (the gid lookup
waits for its group; walk finding F22), LANDED 2026-10-07 (4fb338b)
and is released in dev16. §85, the first identity apply of a new
tree has nothing to prune (a root with no state yet is not a failed
`state list`; walk finding F24), LANDED 2026-10-07 (b0494fa) and is
released in dev17. Both are PROVED live: the walk's identity run on
dev17 created its first group (8 added, 0 destroyed; its CI green
with no drift). No documentation stage is open.
Planned, by the operator's word: §66, §30 and §83 (a release asks
its publish target before it starts).

Releases: dev15 (2026-10-06) carries §82 and hygiene XII items 3
and 4. dev16 carries §84, dev17 §85 (the reference configuration's
`main`: perform green on it, run 37635442502). dev18 is on the index
and unused. dev19 (2026-10-07) carries §86 and is the walk's
`develop` and `main` and the reference's `develop` (CI green); the
reference's `main` moves to it on the operator's word.

Recently landed: §80, hygiene bundle XI (2026-10-05, cf186de): the
reference tree's AWS runtimes default to a t3.medium, and the daily
driver's SSH-timeout row names the bake host's size; §75, a POSIX
identity plugin, alone and beside Okta (2026-10-05; merged c02511d,
released in dev13): OPA's groups exist on their machines with their gid
and members join at login, and a posix-only group is proved over real
ssh; §78, the documentation stage for §75 and §79 (2026-10-04, 4e40043);
§79, hygiene bundle X (2026-10-04, fffef2a; the branch
`feature/hygiene-x` kept): `--only` beside `--only-runtime` narrows a
bake, a failed packer block keeps the records of the builds that
completed, and an adopted build counts as current; §76 (2026-10-03,
980963e), reserved names -- `none` joined `OOPS_DEFAULTS`, a reserved
name is refused where its file is read, a reference written `none` is
refused at `validate`, the `config:` key guard is on -- and §77, its
documentation stage (63fc128); §73 (2026-10-01), the coops model
replaced onto a second EFS filesystem -- `coops-model-005`, generation
5, alias `gar`, the planted file absent, the old `efs-storage` standing
with its data and mounted nowhere; §72 (2026-09-30), the coops model
resized in place twice (`c5n.4xlarge` to `t3.xlarge` to `t3.medium`, the
same machine, two `resized` events) and then replaced as
`coops-model-004` with its planted file, EFS filesystem and EBS volume
intact; §71, hygiene bundle VIII (2026-10-01, five items); §69
(2026-09-28, its step 5 done 2026-09-29); §68, hygiene bundle VII
(2026-09-29); §63, §67 and §64 (2026-09-26).

Open stages and their order (revised 2026-09-22, when §59 landed):
**§64**, the release that carries everything a configuration repository
needs and the reference configuration standing alone, LANDED 2026-09-26
(one squash; the release that carries it, the sibling's secrets and the
federation trusts are the operator's, listed in `_uncommitted/`; §63, the
code defects the documentation found, LANDED the same day in five
squashes); then **§65**, walking the daily driver from a fresh repository
against a release, and **§66**, the three starter repositories published
from `docs/examples/` per release, both planned;
§30 waits on the operator's decision. (§62, the daily driver, LANDED
2026-09-24 as the operator's "one attempt, accepted": the README contract
and its test, sixteen READMEs to it, seven passes of manual corrections,
DAILY_DRIVER.md for a team that installs a release and owns its
configuration repository, three starter trees that are whole repositories,
loaded and validated by a test; it will be worked on over time, and every
material change to the system that invalidates it owes it an update.)
(§61, hygiene
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
account a workload lands in, after which the operator adds the `ref` pin to
the role; the checklist folded into the starters' CI_SETUP.md in §69.) (§57, §55, §58 and
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
on none of this. **Hygiene bundle VIII (§71) is open since 2026-09-30**; the
next non-critical hygiene issue joins it. (§68, bundle VII, LANDED
2026-09-29 in four squashes: bookworm, the CSIS override and the
callbacks, the identity step, the client's environment; §67, bundle VI,
LANDED 2026-09-26.)

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
- A documentation stage modifies no code (operator, 2026-09-23): its diff
  is markdown, example configuration trees and the tests that hold the
  documentation contract; a code change it would need is a new stage,
  written as a plan, never a side edit.
- §30 (the contract package), §65 and §66 are planned, not started; §70
  (the bootstrap: the one-time initialisation as terraform from an
  interview) landed 2026-10-02 in four squashes;
  §69 (the CI-from-scratch guide) landed 2026-09-28 and its step 5 was done
  2026-09-29: the operator set the reference configuration's secrets and
  trust by the guide alone, and its first performing run on `main` was
  green end to end, the login proof as a workload included;
  §63, §67 and §64 landed 2026-09-26;
  a stage is a plan in this file until the operator says to execute it
  (2026-09-23). §62 landed 2026-09-24.
- **Documentation stays current by stage** (operator, 2026-09-23). Once
  §62 has landed, every stage that changes behaviour, configuration,
  tests or procedure owes a documentation update, done as a stage of its
  own: a rolling **documentation stage** that is open whenever such work
  has landed undocumented. If none is open, the stage that lands the
  change opens one. Several stages of work may land before the
  documentation stage runs, but the documentation stage must LIST what
  was worked on since the last update (the stages, by number and name,
  and what each changed), so whoever writes the docs has the context.
  The same convention as the hygiene bundle: one open stage, appended to,
  landed as one.

- **The bootstrap is ongoing work** (the operator's own words in §70,
  kept verbatim when it landed):

  > Initially, the user must install the base application (generally using `uv`).
  > Then the user would fork and clone the starter repository.  This would give them
  > a place to land the bootstrapping code.  They would then start the bootstrapping
  > interview, and should end up with a runnable copy of the application, as well
  > as a configured set of dependencies, bootstrap code, and target locations for 
  > state management (including, possibly, storing state in github [not recommended]).
  >
  > Once landed, the §70 work should be considered part of the ongoing updates of the application
  > and the starter repository, such that any new items are part of the process.

  So a new release-owned part, a new runtime or a new secret owes the
  bootstrap its section, module or question in the same stage. One part
  of that paragraph is not built: keeping the bootstrap root's state in
  GitHub ("not recommended" there too). The root's state is the tree's
  declared S3 backend when its bucket exists, else local for the first
  apply (decision D8); a GitHub-hosted state would be a stage of its own
  if it is ever wanted.

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

## 66. Starter repositories a team can use from GitHub

**Status: PLANNED, not started** (the operator, 2026-09-24: "I want to make
a template repo that holds the docs examples").

**The question, and the answer.** Three example trees stand under
`docs/examples/` and a team should be able to start from one with a click.
The choices were three repositories, one repository with three branches,
or a script that copies a tree out. The answer is shaped by one fact: the
examples are held to the code by the tests (each loads and validates;
each tree's Justfile, workflow, hook, scripts and modules are the
release's, byte for byte), so **`docs/examples/` is the only place they
are edited**, and everything published from them is generated, per
release, and never edited at the destination. Then:

- **Three template repositories, not branches.** GitHub's "Use this
  template" copies a repository's default branch, and a template is a
  repository: three branches would hand every team the wrong two thirds
  and one repository of three directories would hand them all three. One
  repository per example: `cs-image-system-starter-aws`,
  `cs-image-system-starter-gce`, `cs-image-system-starter-complete`,
  each marked a template in its settings.
- **Published by CI from `docs/examples/`, one commit per release**, as
  `publish-tree` already publishes the public repositories: the mirror's
  `main` is replaced from the example, `.csis-version` is written with
  the released version, the commit is `cs-image-system <version>`, the
  tag is `v<version>`, and the README opens with a line saying the
  repository is generated from cs-image-system's `docs/examples/<name>`
  at that version and takes no pull requests (changes go to the system
  repository, where the tests hold them). Tracking changes to an example
  is then ordinary work here; the mirrors are write-only and their
  history is one line per release.
- **The release itself is the primary template.** §64's `cs-image-system
  init-config <dir> --from <name>` needs no GitHub and cannot drift,
  since the starter inside the release matches the command that reads
  it; the template repositories are the browser-friendly mirror of the
  same source. A copy script alone (the third option) is `init-config`
  without the version lock, and is not enough.

1. **The mirrors exist** (USER): three empty repositories under the
   organisation, each marked "Template repository", each with a
   fine-grained token (contents: write, that repository alone) stored
   here as `STARTER_PUSH_TOKEN_<AWS|GCE|COMPLETE>`; `main` protected
   against everything but the publishing job.
2. **A `publish-starters` recipe** in this repository's Justfile: for
   each example, build the tree into a scratch checkout of its mirror
   (the example's tracked files, `.csis-version` written, the README's
   generated line prepended), `public-safe` over the result with the
   example's own allow list, one commit, the tag, the push. Dry form
   (`yes`) builds and shows the diff, pushes nothing. Refuses a dirty
   tree and a version the mirror already carries.
3. **The `publish` job runs it** after the index upload succeeds for a
   final version (never for a `.dev` release: a team's template names a
   version teams can install from PyPI). The job is gated on the three
   tokens the way every other job is gated: none is SKIPPED and said so,
   some is a failure that names them.
4. **The examples know they are templates**: each README under
   `docs/examples/` says where its mirror is and that the mirror is
   generated; `DAILY_DRIVER.md` section 1.9 names the three template
   repositories first and `init-config` second (once §64 lands), and the
   copy from `docs/examples/` last.
5. **A test** holds the three mirrors' names and the recipe's file list
   to the examples: what the recipe would publish equals the tree under
   `docs/examples/<name>` plus the two generated lines, so a file added
   to an example is published and a file removed is removed.
6. **Records**: OPERATIONS section 2 gains the recipe beside
   `publish-tree`; §64 step 1 (the release ships the starters) and this
   stage share the source and the version stamp. Proved by one real
   publication of a final version, then "Use this template" on the AWS
   mirror and `just init` in the result.

**Sizing**: the recipe and its test half a day; the job an hour; the
mirrors and tokens are the operator's (an hour); the live proof waits on
the first final version on PyPI (§41's open call).

## 83. A release asks its publish target before it starts

**Status: PLANNED 2026-10-06, not started -- a plan; nothing here runs
until the operator says "do 83".** (The operator, 2026-10-06, after an
index outage cost a release attempt: "a stage that checks to see if the
publish url is available before starting a release (this is probably
conditional on type of target publish location)".)

**Why.** Across the night of 2026-10-05 TestPyPI was partly down for
more than nine hours: its upload endpoint and most project pages
answered 503 while a few pages still answered 200. `just release dev
test` passed every probe it has -- the token is set, the tag is free,
and `scripts/index-knows` read the ONE page it asks for,
`cs-image-system`'s, which happened to be among those answering -- then
ran the whole bar, bumped, locked, and failed at the upload, printing
the index's HTML error page. The operator learned after the bar what one
request to the right URL would have said at once, and was left with an
uncommitted bump to discard. Nothing was damaged: the upload comes
before the commit and the tag, by design. The cost was the wait, and the
certainty that a retry would repeat it.

**What it adds.** A probe of the target a release publishes TO, chosen
by the target's type, run before anything else.

1. **The probe, by type.** `scripts/publish-target-ready <target>`,
   beside `index-knows`: exit 0 ready, 75 not ready (the code `--locked`
   already uses for "try again later"), 2 a target it does not know. One
   checker per TYPE of target:
   - *A package index of the PyPI kind* (`test` and `pypi`, the only
     type today). The endpoints are read from the target's
     `[[tool.uv.index]]` entry in `pyproject.toml`, never restated in
     the Justfile. Its `publish-url` (TestPyPI's `/legacy/`, PyPI's
     `upload.pypi.org/legacy/`) must answer below 500 to a request that
     uploads nothing. Its `url`, the simple index, must answer for EVERY
     project the release uploads (eighteen today, the names read from
     the workspace), not for one. The same pass says which projects
     already hold the version: none (a fresh release), all (what
     `index-knows` refuses today), or some (a partial upload, which a
     `publish` re-run completes).
   - *Anything else.* A type with no checker is refused by name, never
     passed. §66's template mirrors are git remotes, and their checker
     is `git ls-remote` with the push token; a private or static index,
     if one is ever declared, is a third. A new publish target owes its
     checker in the stage that adds it.
   What it cannot check: that the token will be accepted. The index
   offers no call that says so without an upload, and the probe says
   that it did not check.
2. **Where it runs.**
   - `just release`: first of the probes, before the bar; and AGAIN
     after the bar, immediately before the bump. The bar takes twenty
     minutes, and an index that went down meanwhile then leaves a clean
     tree, not a bump to discard.
   - `just release ... yes`: the dry form reports it with the other
     probes.
   - `just publish`: first, so CI's `publish` job (a pushed tag) and a
     re-run after a partial upload say "the index cannot take an upload"
     in one line.
   - `just index-ready [test|pypi]`: the probe alone, one line per
     endpoint. **USER**: with a `wait` form that polls until the target
     is ready -- the loop that was run by hand until the index came
     back?
3. **What a failure says.** One line: the target, the URL, the status,
   that nothing was changed, and that it is the index's condition, not
   the release's. `publish` stops printing the index's error page: a
   failed upload prints the status and the first lines of the body. (Its
   closing message also still counts "sixteen packages"; there are
   seventeen.)
4. **Tests.** The checker against a local HTTP server answering by path:
   all up; the upload endpoint 503; one project page 503; nothing
   listening; an unknown target. The recipes' order held by the Justfile
   contract test: the probe before the bar and again before the bump,
   and `publish` begins with it.
5. **Records.** OPERATIONS' release section and the developer chapter of
   the daily driver (section 9) say what the probe checks and what exit
   75 means; the words are written in the open documentation stage.

**Not in this stage**, named so it is not lost: a configuration
repository's CI installs from the same index, so an outage also fails
every consumer's `verify` job (the walk's finding F16). That needs a
different answer -- a final release on PyPI, or a mirror -- and is not a
probe.

**Sizing**: the script and its tests half a day; the recipes and the
contract test two hours.

**Added 2026-10-07 (the walk's finding F31): the branch is a probe
too.** `just release dev test` was run with the checkout on the walk
branch: it probed the token, the index, the version and the clean
tree, cut 0.1.1.dev18 there, and committed and tagged on that branch;
`develop` stayed a version behind and the next release had to be
named by hand. The release refuses, with its other probes and before
anything changes, a branch that is not the integration branch
(`develop`; a final release may want `main`: **USER** decides), and
the dry form says which branch it stands on.

## 92. CI runs on an AlmaLinux 10 image of the system's own, described once for any CI

**Status: LANDED on develop 2026-10-16 (661270f, then 3d33d3c, 6bec81f,
2446038 and 601bf65; branches kept) and PROVED in this repository: `CI`
green inside `ghcr.io/infrastructurebuilder/csis-ci:alma10-20261016.4`
(run 38970158822: `verify`, and `live` with `fixture-live: passed`, 3
modifications tested under docker through the mounted socket), `CI from
scratch` green on GitHub's image, the Runner image workflow publishing
with the job's token. Four images it took to get there, each found by
the next job: `.1` lacked git's `safe.directory` for a checkout owned by
another user, `.2` the `libatomic` pyright's node needs, `.3` the
`community.docker` collection whose `docker` connection the modification
tests use, and a permissions block without `packages: read` pulls as
nobody; each is in docs/CI_RUNNER.md, the probe, or a test. The section
stays until the reference configuration's proof: dev26 (the operator's
release), the reference on it (`init-config --force` moves its jobs into
the image), `live` and `perform` green there with a bake, the
modification tests and a login proof; and the package made PUBLIC in the
organisation's settings before that, since another repository's token
cannot read a private one. Then the section leaves TODO.**

**Why** (the operator, 2026-10-14). CI should run on something close
to the machines the system builds, which are AlmaLinux 10, and the
first consumer is a Red Hat shop. GitHub supplies no RHEL-family
runner image: its custom-image facility is for its paid larger
runners, starts from GitHub's own Ubuntu or Windows images, and GitHub
says it does not plan other Linux distributions; for those it points
to Docker on its hosted runners. So the machine stays GitHub's and
every job runs inside an image this repository builds. AlmaLinux 10
over Fedora: binary-compatible with RHEL 10, supported to 2035 (a
Fedora release lasts about 13 months), and every third-party
repository the jobs need publishes EL builds. The strict alternative,
Red Hat's `ubi10`, is noted for a consumer that wants RHEL itself.

**The operator's answers (2026-10-14, asked before anything was
built):**

- **Everything is baked.** uv, just, OpenTofu, Packer, the clouds'
  CLIs, `sft`, ansible, the session-manager plugin: all in the image at
  pinned versions. The requirements document is the one list.
- **The image has versions of its own.** Built on a schedule and when a
  tool changes, tagged by date (`csis-ci:alma10-YYYYMMDD`); a starter
  pins one such tag, and `init-config --force` moves it with the other
  release-owned lines. A second thing to take beside the release, by
  choice: the image and the release move at different paces.
- **Base `almalinux:10.<minor>` pinned by digest, on
  `ghcr.io/infrastructurebuilder/csis-ci`.**
- **The docker client from Docker's EL repository** (`docker-ce-cli`),
  talking to the host daemon over the mounted socket; `mod_tests`
  calls docker as it does now.
- **All four starters carry the image path.** The from-scratch path
  (GitHub's `ubuntu-24.04` with the install steps, as §91 leaves it)
  lives only in this repository, proved by its own CI, for anyone to
  copy; the starters do not ship it.
- **The requirements document is tested against the Dockerfile and
  `cfg/executables.yml`, and by a build-and-probe**: a `full-test`
  leg builds the image locally and runs each tool's `--version` inside
  it.

**Three outputs:**

1. **The image.** `ci/runner-image/Dockerfile` from the digest-pinned
   base; every tool above at a pinned version; a workflow of this
   repository builds it, probes it, and publishes it to ghcr.io with a
   date tag, on a schedule (monthly) and on any change under
   `ci/runner-image/`. The tag a starter pins is a line `init-config`
   owns.
2. **The requirements document**, `docs/CI_RUNNER.md`: what a CI
   runner for a cs-image-system configuration must provide, written
   for no CI system in particular -- OS family and version, each tool
   with its version floor and source, the network it must reach, what
   it must be able to do (run containers, federate by OIDC, hold the
   secrets the gate reads), and the `just` targets the jobs call in
   order, which are the contract. The Dockerfile is one implementation
   and says so; a GitLab or Azure DevOps runner is another, built from
   the same page.
3. **The from-scratch path, kept in this repository**: a second
   workflow here, `ci-from-scratch.yml`, GitHub's image with the
   install steps, run by this repository's CI beside the image path
   and moved forward by section 9.1 with it.

**What changes in the workflows.** Every starter job gains
`container: {image: ghcr.io/infrastructurebuilder/csis-ci:alma10-<date>,
options: -v /var/run/docker.sock:/var/run/docker.sock}`; the install
steps and the Ubuntu-only lines go; `just` targets are unchanged.

**Proof.** First, before anything else: every dependency installs on
`almalinux:10` (a scratch Dockerfile built locally; Docker's, Google's
and Okta's EL10 repositories answer, or EL9's do, and the proof says
which). Then `just test` and `just full-test` (with the new
build-and-probe leg); this repository's CI on both paths; the reference
configuration on the release: `live` green inside the image, then
`perform` with a bake, the modification tests and a login proof, on the
operator's `main`.

**Sizing**: the dependency proof half a day; the image and its
workflow a day; the workflows and the two variants a day; the
requirements document and its test half a day; the live proof as the
operator's time allows. **USER**: the registry (ghcr.io under the
organisation), the three decisions above, the merge, the release, the
reference configuration's `main`.

## 93. Everything the system makes carries its configuration's id, and the inventory counts its own alone

**Status: LANDED on develop 2026-10-16 (23bb441, squashed from
`feature/stage-93`, branch kept; bar 1557 passed). The section stays
until the live proof: a release carries it (dev26), the reference
configuration takes it, the operator runs `just cloud-relabel aws-
east2-runtime no` and `just cloud-relabel gcloud-east1 no` (the dry plan
of 2026-10-15 named four AWS storages, `coops-model-006`, two GCE
storages and one old GCE image), and a strict state query is green with
every `unavailable` at 0. Then the section leaves TODO.**

**The defect.** `emptiness()` is the runtime's whole inventory (on GCE:
every instance and disk in the zone, every custom image and every bucket
in the project) less this tree's declared storages and released builds.
Two configurations in one project therefore each see the other's
standing storages as leftovers: the reference keeps `gce_data` and
`gce_bucket` in `csis-sandbox`, where the walk's GCE leg ran. It is F11
again (§82 gave images a `csis_config` label), for everything that is
not an image. The same on AWS (F53, stage 16c): a declared storage's
volume and a declared instance's machine are found by the `Name` tag
across the whole account, so two configurations with a storage called
`data` (every starter's name) each see the other's volume: `foreign
storage data: ebs vol-... exists but meta-state has no record of it`, in
CI.

**Plan.**

1. **Everything carries the id.** The instances, disks and buckets the
   GCE modules make, and the volumes and machines the AWS modules make,
   carry `csis_config` (a label or a tag beside the ones they have; a
   label change is in place on a standing resource, never a
   replacement). The golden moves by those lines and is reviewed by
   hand.

2. **Inventories count this configuration's alone.** `emptiness()`,
   `cloud-empty` and the state query count what carries this tree's id
   and say how many of another configuration's things they left alone,
   as the image query does since §82; on AWS every lookup by `Name`
   filters on the tag, so a foreign `data` is "another configuration's
   storage `data`", not a foreign storage of ours. A resource with no id
   at all (made before this stage) is still counted, and named as such,
   until it is relabelled.

3. **`cloud-relabel` learns the new kinds** for what stands already, so
   the reference's storages and machines take the label in place.

4. **Words.** OPERATIONS "GCE cost discipline" and the daily driver's
   3.6 say that two trees may share a project or an account once both
   are on this release, and what the leftover list says of the other's
   things.

**Proof.** Fixture and golden (the label lines); a unit test of each
inventory with a mixed listing (ours, another's, unlabelled); live:
`just cloud-relabel` on the reference's GCE storages and AWS volumes (an
apply, the operator's), then a strict state query green; a scratch tree
in the same project sees zero leftovers of ours.

**Sizing**: two days, plus the operator's live runs. **USER**: the
relabel of standing resources, the merge, the release, the reference
configuration's `main`.

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
