# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **§75**, the POSIX identity plugin. Steps 1-7 and 10
merged 2026-10-04 (c02511d) and released in dev13; steps 8 and 9 are
done live the same day (coops-model-005 healed in place; the standalone
proof logged in over real ssh and was torn down). The sibling's first
`perform` on dev13 failed (run 37212963588: `imgfile-basic-cloudflow`
timed out on SSH over SSM on its EL8 parent, and the five builds that
had completed went unrecorded); the five were adopted (sibling
9846a62), and the three defects it exposed are §79, landed. By the
operator's word the sibling's main moves again only after a release
carries §79 and the sibling takes it; §75 lands when that `perform` is
green. No documentation stage is open (the next undocumented change
opens one) and no hygiene bundle is open (the next issue opens XI).
Planned, by the operator's word: §65, §66 and §30.

Releases: dev13 (2026-10-04) carries §75 steps 1-7 and 10; the sibling
is on it (develop and main). The next release (dev14, the operator's)
carries §79.

Recently landed: §78, the documentation stage for §75 and §79
(2026-10-04, 4e40043); §79, hygiene bundle X (2026-10-04, fffef2a; the
branch `feature/hygiene-x` kept): `--only` beside `--only-runtime`
narrows a bake, a failed packer block keeps the records of the builds
that completed, and an adopted build counts as current; §76 (2026-10-03,
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

## 65. Walking the daily driver

**Status: PLANNED, refreshed 2026-10-02; nothing runs until the operator
says "do 65", and the walk's decisions (W1-W5, below) are asked first.**
(The operator, 2026-09-24, on accepting §62: "make a new stage for
walking through the daily driver docs"; refreshed on the operator's word
after §70 landed.)

**Why.** Every proof so far ran in the reference configuration, which
already had its roles, its workload identity pool, its OPA connection
and its secrets. Nobody has gone from nothing -- a release on the index,
an empty directory -- to a green `perform` the way a new team would, and
much has changed since `DAILY_DRIVER.md` was accepted as one attempt:
the release model and `init-config` (§64), the CI guide (§69), the
bootstrap (§70), the refresh rules of hygiene IX. In particular the
bootstrap's CREATE paths -- new IAM roles, a new state bucket, local
state then migrated, the Okta section's guidance on a repository whose
OPA objects do not exist yet -- have passed `tofu validate` and never an
apply. The walk is the proof, and every place the text and reality
differ is a finding.

**What it changes.** Words only. Findings that are words are fixed in
this stage (the daily driver, the guide, the starters' READMEs and
comments); findings that are code go to hygiene bundle X (opened by the
first one) or to a new stage, never made here -- a documentation stage
changes no code. The walk log (`_uncommitted/walk-log.md`, every step
with the exact text followed and what happened) is the stage's evidence,
summarised in its squash message.

**The decisions to ask before "do 65"** (each with the default this plan
assumes):

- W1, where the walk repository lives. Default: a new repository
  `infrastructurebuilder/cs-image-system-walk`, public like the other
  two, created by the operator, deleted (or archived) at the end.
- W2, what the walk may create in NOAA's AWS account. Default: the
  bootstrap's create paths for real -- two new roles
  (`csis-walk-readonly`, `csis-walk-apply`; the OIDC provider is
  account-wide and stands, so it is read) and a NEW state bucket, so the
  local-state-then-migrate path is walked; one base bake, one
  instance-image bake and one EPHEMERAL instance (launched, verified,
  torn down in its run). All of it destroyed at the end.
- W3, OPA. Default: the same team, with walk-prefixed group names
  (`walk_*`) so nothing the reference configuration manages is touched;
  a new workload connection and role for the walk repository, made in
  the console by the operator from what the bootstrap's Okta section
  prints -- which is that section's proof on a repository with nothing
  yet; the walk's groups, policies, connection and role removed at the
  end. The Okta services app and the OPA service user are the reference
  configuration's, reused (read-only lookups; nothing in Okta is
  created).
- W4, the GCE leg. Default: SKIPPED -- GCP is the operator's money, and
  the GCP section's create paths are the only thing it would add; the
  GCE starter is read rather than walked. The alternative is one
  `standard-gce` walk on the operator's project, one cycle, torn down,
  with what it leaves standing reported (it should be nothing).
- W5, how fresh "fresh" is. Default: the operator's Mac under a clean
  shell -- a scratch `HOME`, `UV_TOOL_DIR` and plugin cache, no `CSIS`
  override, no checkout of this repository on `PATH` -- rather than a
  new machine; the tools of 1.2 as installed. A container is the
  alternative, at the cost of the browser-based logins.

**Steps.**

1. **The release and the shell.** The walk installs the newest release
   on TestPyPI, pinned in `.csis-version`, through `uv tool install`
   exactly as 1.1 says, in the W5 shell. A release cut during the walk
   is not taken mid-walk.
2. **The repository, from nothing** (1.9, the AWS starter):
   `cs-image-system init-config walk --from standard-aws`, `git init`,
   the GitHub repository (W1, USER), `just init`. Every `REPLACE-ME`
   filled from the reference account and the W3 names, a fresh age
   identity and `reencrypt`, `just validate`, `just dry`, the emission
   read, the first commit -- typing only what the page says.
3. **The bootstrap, where it can create** (1.8, CI_SETUP.md 3.0): `just
   bootstrap` interactively, every question read against the page; the
   apply with the README's exports (USER) creating the W2 roles and
   bucket on local state; the re-interview that binds the root to the
   new bucket and `tofu init -migrate-state`; `set-secrets.sh` with the
   walk's secret files (USER); the Okta section's by-hand list followed
   to make the walk's OPA connection and role (USER, console), then
   `just bootstrap` again until that list is empty but for what is by
   hand by decision.
4. **CI** (1.8, CI_SETUP.md 3.8): `verify` green on the first push,
   `live` green once the secrets exist, the probe, one `perform` on
   `main` with its records pushed back and the login proof as a
   workload.
5. **Making things** (section 3, within W2/W3): one walk group of one
   test user, one storage, one base image, one instance image with one
   modification and one post-bake test, the ephemeral instance through
   `just cloud-launch`, the login proof. **Changing things** (section 4)
   for one change: a modification, re-baked.
6. **The failure walk** (section 6): provoke five rows on purpose -- an
   expired session, an unsourced shell, a destroy the gate must refuse,
   a pin to an unreleased build outside the grace, a stopped machine --
   and check each row's symptom, meaning and remedy.
7. **Read rather than walked**: the pyproject install form of 1.1; the
   GCE starter if W4 skips it; the developer chapter (section 9) against
   this repository's `just test` and `just release ... yes`.
8. **Teardown, and its proof**: the walk's AWS images and storage
   through the system (`cloud-dispose-images`, the storage undeclared),
   `just cloud-empty` on the walk's runtime; the walk's OPA groups and
   policies through the identity lifecycle with their declarations
   removed; the bootstrap root destroyed (USER: roles, bucket, GitHub
   settings); the OPA connection and role removed and the repository
   deleted or archived (USER). Afterwards the reference configuration's
   strict state query and its `perform` stay green, which is the proof
   the walk touched nothing of it.
9. **The fixes and the records**: every finding in the walk log is fixed
   here (words) or filed (code); `DAILY_DRIVER.md` gains a dated line at
   the top -- walked on <date>, against release <version> -- and so do
   the guide and the starters' READMEs where they were walked.

**Sizing**: the repository and bootstrap half a day; CI half a day, most
of it secrets and the console; section 3 a day, most of it bakes; the
failure walk two hours; teardown two hours; the fixes a day. Costs: two
bakes and one short-lived instance on AWS; nothing on GCP unless W4 says
otherwise.

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

## 75. A POSIX identity plugin, alone and beside Okta

**Status: steps 1-7 and 10 MERGED 2026-10-04 (c02511d; the branch
`feature/posix-identity` kept), released in 0.1.1.dev13, taken by the
sibling's develop (bceb31b, CI green). Step 9 DONE 2026-10-04: the
standalone proof logged in over real ssh, all four checks ok, and was
torn down the same day. Step 8 DONE 2026-10-04 on the machine
(coops-model-005 healed in place), owing only `perform` green, which
waits for the sibling's main. Its first `perform` (run 37212963588)
failed on `imgfile-basic-cloudflow`'s EL8 parent and exposed the three
defects of §79, landed and released in dev14 (the sibling took it,
b8a6983). The second `perform` (run 37290586415, 2026-10-05) failed
the same way: `imgfile-basic-cloudflow` timed out on SSH over SSM
from its EL8 parent pin although the bake machine's SSM agent was
Online; nothing else was baked, nothing left foreign. By the
operator's choice its pin moved to `imgfile-basic-dask`'s EL10 head
(sibling fbbda37). `just full-test` passed 2026-10-04 on the tree
with §79 merged. Left before the stage lands: a green `perform`,
whose login proof of coops-model has not yet run in CI on dev13 or
dev14.** (The
operator, 2026-10-03, on finding the owning group absent on a live
machine: "Plan a second plugin", with the decisions recorded below.)

### Context

**The defect (observed live by the operator, 2026-10-03).** On
`coops-model-005`, `getent group coops` returns nothing. Users synced by
Okta exist, each with their own group (`mykel.alvis:x:150006:`), but the
group that OWNS the instance is absent. The system never creates it:
the instance image bakes only the `tx.group` label
([okta_opa_tf_group_builder.py:111-121](packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py#L111-L121)),
and the launch script only `chgrp`s the group's storage subtree to a
NUMBER ([launch_params.py:284-288](packages/base/src/cs_image_system/base/launch_params.py#L284-L288)).
So the `2770` subtree is owned by a gid no account is a member of.

**The structural finding.** Identity is a plugin by design
([builder_base_group.py](packages/base/src/cs_image_system/base/basic/builder_base_group.py),
DESIGN N1/N20), but Okta is the only implementation and the core knows
`sftd` by name: the launch lines, the ansible launch, the alias script,
the login proof (`sft ssh`) and the workload token.

**The operator's decisions (2026-10-03).**
- A second identity plugin: POSIX groups, users and sudo for admins.
- It must also run BESIDE the Okta plugin handling ONLY groups; the Okta
  plugin uses it to create its groups, and may call it to inject SSH
  keys after users are synced from Okta.
- The group is baked; the users come at launch.
- For Okta groups the bake learns the gid through a packer variable
  filled by the existing gid shim. SUPERSEDED 2026-10-03 after step 1:
  the group is created by the after-apply run only (which must visit
  every machine anyway for the member lists, and is the only thing that
  heals a standing machine); only the login hook is baked, and it needs
  no gid.
- Login proof for the new plugin: real SSH with a proof key.
- Proved by fixture, live, and a starter.
- **Id collisions**: a name known to two sides whose supplied ids differ
  is a CONFIGURATION ERROR; a side that supplies only a name takes the
  other side's id; resolution runs in serial order, id-supplying sides
  (Okta) first, sides that need not supply ids after.

### The design

#### The plugin

New package `packages/posix-identity-plugin` (entry point
`cs_image_system.plugins.group`, type `posix`, identity type `posix`,
gid policy `config-time`). Its whole output is ONE idempotent shell
script, `accounts_script(...)`, built from four parts it also exposes
separately:

| Part | Does | Standalone | Beside Okta |
|---|---|---|---|
| group | `groupadd -g <gid> <name>`, or adopt an equal one | yes | yes |
| users | `useradd -u <uid>`, user-private primary group | yes | no (Okta's) |
| membership | members become supplementary members of the group | yes | yes |
| keys | `authorized_keys` from the user's `public_keys` | yes | opt-in |
| sudo | `/etc/sudoers.d/60-csis-<group>` for the group's admins, `visudo -cf` checked | yes | no |

`User.public_keys` and `Group.gid` already exist
([user.py](packages/base/src/cs_image_system/base/models/user.py),
[group.py:62](packages/base/src/cs_image_system/base/models/group.py#L62)).
Usernames and keys are emitted with `emit()` (stage 49), so the
committed emission carries markers.

#### When

- **Bake (instance image)**: the group part, through the existing
  `activation_commands` hook
  ([v2_provisioners.py:131-143](packages/packer-plugin/src/cs_image_system/packer_plugin/v2_provisioners.py#L131-L143)).
  Standalone: the declared gid, literal. Beside Okta: packer variable
  `group_gid`, filled by the bake's run script from
  `cs-image-system identity-gids`
  ([identity_gids.py](packages/base/src/cs_image_system/base/commands/identity_gids.py))
  just before packer; a dry run touches nothing.
- **Launch (after apply)**: the whole script, as a post-launch task over
  the runtime's session, on the pattern of `register_provider_aliases`
  ([provider_aliases.py:169](packages/base/src/cs_image_system/base/provider_aliases.py#L169),
  `runner.register_after_apply`, `rtb.run_session_command`). Not in
  user-data, on purpose: user-data is 16 KB, and a member list inside it
  would make every membership change a terraform change to the machine.
  It runs on every applying run against RUNNING machines, so a
  membership change is neither a re-bake nor a replacement, and a
  standing machine (coops-model-005) is healed in place. Beside Okta it
  waits (bounded) for a synced account before adding it; an account not
  yet synced is a `note`, finished by the next run.
- The launch script's own `chgrp` is unchanged, plus one assertion: the
  baked group's gid equals `${group_gid}`, else the startup fails.

#### Composition with Okta

Declared, not imported -- no plugin imports another:

```yaml
group_builders:
  - name: oktagroups
    type: okta-tf
    posix: posix-local          # creates this builder's groups on machines
    posix_ssh_keys: false       # opt-in: keys after the Okta sync
  - name: posix-local
    type: posix
```

`GroupBuilderBase` gains a small accounts protocol (default: nothing)
that the posix builder implements and the Okta builder calls through
`ctx.group_builders`. Base images declare `identity_types: [okta, posix]`.

**`posix` is REQUIRED on an `okta-tf` group builder and has no default;
`posix: none` is the explicit way to have no posix configuration**
(operator, 2026-10-03). An opt-in fix would leave the defect as the
silent default, so the line must be written, and what it says is the
team's decision:

- `posix: <name>` names a declared group builder. The field is a foreign
  key declared with `fk_field`, so stage 48's rule applies: a name that
  resolves to no declared builder is refused at `validate`, and one more
  check refuses a target whose type is not `posix`.
- `posix: none` means this builder has no posix configuration. It is
  VALID and is not refused: the builder behaves as it does today (no
  group on the machine, the subtree owned by a number), and `validate`
  and the state query carry a `note` saying so for each group that owns
  an instance image, so the choice stays visible.
- The line absent is refused, naming the builder and the two spellings
  it may take. There is no default to fall back on.
- **No resource in the system may be named `none`.** The string joins
  `OOPS_DEFAULTS`
  ([constants.py:17](packages/base/src/cs_image_system/base/constants.py#L17)),
  beside `default`, `self`, the empty string and null. That is what
  makes `posix: none` unambiguous: it can never be the name of a
  builder.
- The rule that refuses the NAME is §76's, LANDED 2026-10-03: `none` is
  in `OOPS_DEFAULTS`, a reserved name is refused where its file is read,
  and a REFERENCE written `none` is refused at `validate` (a foreign key
  takes its default only by equality with the field's own, so `none`
  names nothing). So this field must declare that it accepts the word
  and handle it before the generic foreign-key check does.
- Because null and `none` are both in that list, the required check
  reads the value AS WRITTEN: a missing line is refused, the word `none`
  is the opt-out. The two are never folded together.
- It is the `okta-tf` GROUP builder that requires the line. The user
  builder of the same type and the lookup-only builder (`okta-tf-ro`),
  which manages no groups, are left as they are: the field is neither
  required nor read there.
- The cost, stated: a tree with an `okta-tf` group builder fails
  `validate` on the release that carries this until the line is written.
  `cfg/` is the team's, so `init-config` cannot add it; the refusal's
  message carries both spellings and the release notes say so. `posix:
  none` is the one-line way to take the release and change nothing; the
  fixture and the three starters declare a posix builder and name it.

#### Id resolution (the operator's rule)

One core pass, `resolve_posix_ids`, used at three moments. Sides are
ordered by the existing `gid_policy()` constants: `creation-only` and
`provider-assigned` first (Okta/OPA), `config-time` after (the
configuration), the machine last.

1. Collect `(side, id or none)` per name (groups: gid; users: uid).
2. Two supplied ids that differ: **refused**, naming both sides.
3. One supplied id: every side takes it.
4. None supplied: **refused** -- a standalone name must declare its id
   (shared storage is owned by number, so ids must be the same on every
   machine). Conservative reading; say so if allocation is wanted.

Moments: `validate` (configuration against configuration, no network);
bake execution (the shim's OPA gid against a declared one, before
packer); on the machine (the script: an existing entry with a different
id exits non-zero with both ids; an equal one is adopted).

#### The decoupling this needs (and no more)

Moved out of the base into the Okta plugin, behind contract methods,
with the emitted text BYTE-IDENTICAL (the golden is the proof):

- `launch_script_lines(params)` / `launch_variables()` replace the
  `"sftd-token"` branches in
  [launch_params.py:290-305](packages/base/src/cs_image_system/base/launch_params.py#L290-L305)
  and [ansible_launch.py:82-90](packages/base/src/cs_image_system/base/ansible_launch.py#L82-L90).
- `prove_login(instance, ...)`: `login_proof` dispatches to the group's
  builder; today's `sft resolve`/`sft ssh` code
  ([login_proof.py:134-190](packages/base/src/cs_image_system/base/commands/login_proof.py#L134-L190))
  becomes Okta's implementation.
- Runtime contract: `ssh_proxy_command(instance)` (AWS:
  `aws ssm start-session --document-name AWS-StartSSHSession`; GCE:
  `gcloud compute start-iap-tunnel --listen-on-stdin`). CI already
  installs session-manager-plugin and the write role already allows the
  document.

NOT moved here (they stay named for §30): the alias script, the
workload token, the user model's Okta wire shape.

#### The proof key

A declared service-account user (`is_service_account: true`) with a
public key; the private key reaches the proof as
`CSIS_PROOF_SSH_KEY` (the PEM or a path, as `OKTA_API_PRIVATE_KEY`
does). `verify login` for a posix group runs `ssh -o ProxyCommand=…
<proof user>@<instance> id` and checks the group is in the answer. The
bootstrap's GitHub section and `set-secrets.sh` gain the secret (the
standing mandate: a new secret owes the bootstrap its question).

### Steps (one commit each; merge on the operator's word at step ends)

1. **Observe.** Done 2026-10-03 by the operator on coops-model-005. (a)
   `getent group coops` exits 2: the group is absent; `/mnt/data/coops`
   (2770) and `/mnt/efs` are owned by the bare gid 180007 (OPA's gid for
   coops), which no account is in -- the operator's own account (uid/gid
   150006, groups 150006 and `sft-admin` 90000) cannot use the group's
   subtree except through sudo. (b) Accounts live in the local files
   (`nsswitch`: `files`, `files [SUCCESS=merge] systemd` for groups; no
   OPA NSS module), written by `sftd`'s "osedit" through `groupadd`,
   `useradd`, `userdel` -- targeted edits, never a rewrite of
   `/etc/group`. (c) The accounts are JUST-IN-TIME: `sftd` created
   `mykel.alvis` at a login (22:20:39) and had deleted it that morning
   (09:07:26); the CI workload account
   `wl_cs_image_system_testconfig_ci` lived from 12:58:47 to 13:00:26.
   On creation it adds the user to its own `sft-admin` only; `userdel`
   removes the user from every supplementary group. What this fixes: a
   group the system creates stands (nothing in `sftd` touches it), but a
   MEMBERSHIP written at apply time does not hold -- at apply time most
   members have no account, and every account `sftd` deletes loses its
   supplementary groups. Beside Okta, members must be added at login,
   not at apply (step 5).
2. **Decoupling.** Done 2026-10-03. The launch steps: a group builder's
   enrollment KIND (recorded in the launch parameters, unchanged) is
   rendered by whichever plugin registered it in the new core module
   `launch_enrollment`; both renderers ask it, and a kind nothing
   renders is refused rather than skipped. The Okta plugin's
   `sftd_launch` registers `sftd-token` with the lines and tasks moved
   there unchanged to the byte (the golden is unchanged, so every
   machine's recorded user-data hash holds). The login proof: the core
   keeps the targets, the skips and the record and asks the group
   builder (`can_prove_login`, `login_identity`, `login_checks`); OPA's
   checks and the `sft` client seam moved to the plugin's `sft_login`.
   The runtime's `ssh_proxy_command` is NOT added here: it is an
   addition, not a move, and lands in step 6 with its first user and its
   tests.
3. **The plugin, standalone.** DONE 2026-10-03, in four commits. (1) the
   gid seam -- the group builder answers `gid_workspace()` and
   `gid_expression(group)`, which the AWS and GCE instance builders and
   the storage builders used to assume (a remote-state reference into an
   identity root every group builder was taken to own); Okta's output is
   byte-identical. (2) The package `posix-identity-plugin` -- a group
   AND a user builder, both `type: posix` (the plan named only the group
   builder, but every user names its builder, and a standalone tree
   needs one to declare uids and keys); a new `uid:` field on `User`,
   the twin of `Group.gid` (not OPA-style `attributes`, which would drag
   posix users into the OPA attribute plan); the accounts script's
   parts; the core resolver `posix_ids.resolve_posix_ids` and
   `validate`'s `check_posix_ids`, with the id floor the `Group` model
   already enforces (1024, not the plan's 1000). Found on the way and
   fixed: the foreign-key handler put the owning `builder` into the
   template context only when a `type:` was DEFAULTED, so a user that
   wrote its `type:` could not render its email template (no user did
   until now). The `complete` starter declares both builders, as it
   declares every type the release ships. (3) The container leg: the
   script on almalinux:10 and debian:12, twice, adopting and refusing, a
   member waiting for its account (`just test-posix-accounts`, a
   `full-test` leg). (4) The fixture: the two builders, `pxgroup` (gid
   3101), the personas Taylor Tango and Unity Uniform, `basic-rhel-9`
   declaring `[okta, posix]`, `imgfile-posix` owned by `pxgroup`; the
   golden moved once, reviewed by hand. The posix group builder answers
   the state query with nothing (it has no provider; each machine is
   checked by the script), and the tests that meant "every OPA group"
   now say so.
4. **The post-launch task.** Done 2026-10-03. `accounts_reconcile`, a
   core post-apply hook beside the provider aliases: after an applying
   instance run, every launched, RUNNING machine whose group builder
   renders an accounts script (the new contract
   `accounts_script(group)`; the posix builder's is the whole script, as
   root) gets it over the runtime's session; a machine off waits, one
   that booted this run is waited for, a failure is an error that never
   stops the run. `validate` gains `configuration_errors()` per group
   builder: a posix group's member must be a posix user with a uid. Two
   plan items are NOT here, on purpose. The launch assertion (baked gid
   equals `${group_gid}`) is dropped: it would change the launch script,
   whose hash is every machine's recorded launch parameter --
   coops-model-005 would read as changed -- and for a posix group it
   compares a number with itself. The `group_gid` packer variable is
   only needed when a provider assigns the gid, so it moves to step 5.
   Noted: the script travels as SSM command text, so usernames and
   public keys stand in the account's SSM command history for its
   retention (public keys are not secret; the names are on the machine
   anyway; CI masks decrypted values in its logs).
5. **Beside Okta** (after §76, which reserves `none` and refuses a
   reference written `none` at `validate`, so the `posix` field declares
   that it accepts the word and handles it before the foreign key does).
   `posix:` (required, no default; a declared posix builder's name, or
   `none` for no posix configuration) and `posix_ssh_keys:` go on the
   `okta-tf` group builder: groups only, with the wait for synced
   accounts. The fixture and the three starters gain a posix builder and
   the line in this same commit, or they no longer validate (golden
   moves once, reviewed by hand). Tests: the line absent, an undeclared
   name and a non-posix target are each refused with the line to add;
   `posix: none` validates, changes nothing in the emission and carries
   its note. **Membership at login (operator, 2026-10-03, after step
   1):** a PAM session hook baked into the image -- an `optional`
   `pam_exec` line in `/etc/pam.d/sshd` runs a small script at each
   login that adds the user to every group whose member list names them;
   the lists (one file per group, e.g. `/etc/csis/groups/coops.members`)
   are kept current by the after-apply run, which also creates the group
   with its OPA gid. It acts in the same login, survives `sftd`'s
   delete-and-recreate of every account, and a failing hook never blocks
   a login. Not chosen: a path unit on `/etc/passwd` and a periodic
   timer (both race the login, so a first session can miss the group),
   and the group alone (members still could not use the 2770 subtree).
   **5a, done 2026-10-03:** the posix plugin's login hook
   (`/usr/local/sbin/csis-group-login`, an `optional` `pam_exec` session
   line in `/etc/pam.d/sshd`, both installed idempotently by
   `login_hook_commands()`), the member lists
   `/etc/csis/groups/<group>.members` and optional keys files
   `/etc/csis/keys/<user>`, and `groups_script()` for groups another
   builder owns (the group with its gid, its list, present members
   joined now, no account created); the contract methods
   `login_hook_commands`, `groups_script` and `configuration_notes` on
   `GroupBuilderBase`. Proved in the container leg on both families: a
   member is added at login, dropped by `userdel`, and added again at
   the next login; an unlisted user never is; the PAM line is written
   once; keys are installed. **5b, done 2026-10-03:** `posix:` and
   `posix_ssh_keys:` on the `okta-tf` group model; the Okta builder's
   `configuration_errors` refuse the line absent or empty, an undeclared
   name and a non-posix builder, and its `configuration_notes` name each
   group `posix: none` keeps off its machines (printed by `validate`,
   carried by the state query); the read-only builder neither requires
   nor reads it. With a delegate, Okta-owned instance images bake the
   login hook (two in-bake checks), and the after-apply script asks OPA
   for the gid (read-only) and has the delegate make the group, its
   member list (members and admins, root admins merged as OPA has them)
   and today's present members -- and install the hook again,
   idempotently, so a machine that stands and is never re-baked
   (coops-model-005) is healed by one applying run. An OPA that cannot
   be asked is an error, never fatal. The fixture's `oktagroups` and the
   three starters name `posix-local`; the golden moved once (the seven
   Okta-owned images gain the hook and its checks; their fingerprints
   move).
6. **Real SSH.** Done 2026-10-04. The runtime contract gains
   `ssh_proxy_command(instance)`: AWS `aws ssm start-session --target
   <id> --document-name AWS-StartSSHSession --parameters portNumber=%p`
   (the path packer bakes through in this account's private subnets: no
   public address, no inbound rule), GCE `gcloud compute
   start-iap-tunnel <name> %p --listen-on-stdin`. The login-proof
   contract widens: `can_prove_login(group)`,
   `login_unprovable_reason(group)`, and `login_checks` receives the
   instance and its runtime. The posix builder proves a group's login as
   its proof user (a posix service-account member with a uid and a key)
   over real ssh through that tunnel, with the private key from
   `CSIS_PROOF_SSH_KEY`: four checks (key, tunnel, login, in its group),
   recorded `as: proof key`; a group without a proof user is skipped
   naming why. The starter workflows hand the secret to the perform
   job's login-proof step (no gate reads it), CI_SETUP.md documents it
   beside the gated table, and the bootstrap's `set-secrets.sh` sets it
   from a file when one is there (the existing rule: a missing file is
   skipped).
7. **The starter.** Done 2026-10-04. `docs/examples/standard-aws-posix`:
   `standard-aws` with the identity swapped -- a posix group builder and
   user builder (both default), one root group `team` with a declared
   gid, two personas and the service-account proof user `csis_proof`,
   the base declaring `identity_types: [posix]`; a workflow with no Okta
   or OPA secrets, gates or client, its login-proof step logging in as
   the proof user; no OPA workload probe; the same guide, Justfile, hook
   and modules as every starter (release-owned, byte-identical). The
   shared Justfile's `ci-login-proof` now mints an OPA token only when a
   builder names a workload connection (`workload describe` is not
   `[]`), so a posix-only tree's proof is not stopped by a token it has
   no use for; trees with Okta behave as before. `init-config --from
   standard-aws-posix`; the release and the wheel carry four starters;
   the daily driver, the system README and the two other READMEs name
   it; the starter tests cover four trees.
8. **Live, beside Okta** (sibling `develop`; applying runs are the
   operator's). The sibling takes the release and, in the SAME commit,
   declares `posix-local` and sets `posix:` on `oktagroups` -- the
   release alone would fail its `validate` (the line is required), so
   the two never land apart. One applying run heals coops-model-005 in
   place. Proof: `getent group coops` shows OPA's gid, members listed,
   the subtree shows the name, `sft ssh` still works, `perform` green.
   DONE 2026-10-04 but for `perform`: the operator's
   `just cloud-launch aws-east2-runtime` (run 2026_10_04t08_13_18_847966,
   `ok`, no new generation -- the machine was not replaced), then
   `just record`; read over `sft ssh coops-model-005`:
   `coops:x:180007:mykel.alvis`; `coops.members` lists both members
   (the second has no account there yet and joins at first login, by
   the hook); the `pam_exec` session line and the hook in place;
   `/mnt/data/coops` and `/mnt/efs` show group `coops`, not a number;
   the login's own `id` carries `180007(coops)`. The run keeps no log
   of the reconcile's lines (the terminal's scrollback is all there
   is), so the machine itself is the record.
9. **Live, standalone** (sibling `develop` only, removed before `main`
   moves). The operator chose (2026-10-04) a dedicated EL10 proof base
   declaring `[posix]` (same vendor image as `basic-rh-10`, AWS only),
   one posix group with a proof user, one posix image and one DURABLE
   proof machine -- `verify login` proves durable machines only --
   baked and launched in scoped runs, proved over real SSH
   (`CSIS_PROOF_SSH_KEY`), then decommissioned and its two series'
   images disposed. Nothing on GCP (the GCE proxy command is
   unit-tested and read, not run).
   DONE 2026-10-04, every applying run the operator's, on the sibling's
   develop (declared af5c3b5, removed ed7b9c4):
   - **Bake** (`--only <series>@aws-east2-runtime` for the two series
     alone; `--only-runtime` beside `--only` would have widened it, see
     §79): base `ami-0237e65c0f8a30b22` (posix only, 9 in-bake
     assertions) and image `ami-0ec88a61e731d36a0` (2, among them
     `getent group pxproof` = `pxproof:x:3101:`) -- the group baked
     with its declared gid.
   - **Launch** (`just cloud-launch aws-east2-runtime`):
     `posix-proof-001`, durable generation 1, `i-0d09fa2a1b5a5cf30`,
     alias `koi`, private subnet only, no enrollment; the reconcile
     made `csis_proof` (uid 3999, its key) on it, and coops-model's
     accounts stood again, untouched.
   - **Proof** (`CSIS_PROOF_SSH_KEY=~/.ssh/csis_proof just
     ci-login-proof posix-proof`): proof key, tunnel (`aws ssm`
     `AWS-StartSSHSession`), login as `csis_proof`, in its group --
     all ok; evidence `uid=3999(csis_proof) gid=3999(csis_proof)
     groups=3999(csis_proof),3101(pxproof)`; recorded in the sibling's
     `meta-state/login-proofs.yaml`.
   - **Teardown**: `cloud-decommission` closed generation 1 (`why:
     decommission`; EC2 reports it terminated), then `dispose image`
     deregistered both AMIs and deleted their snapshots.
   - **Found**: removing the declarations was refused by DESIGN N19 --
     a group the system once managed never leaves the configuration --
     so `pxproof` stays in the sibling as an `unmanaged: true` entry
     with no members (its gid 3101 stays claimed by the name); the
     rest left.
10. **Records.** Done 2026-10-04, as far as the code goes: the posix
    plugin's README (standalone, beside Okta, the login proof, its
    failures), the Okta README and CONFIGURATION 9.2 (`posix:`,
    `posix_ssh_keys:`), the guide (`CSIS_PROOF_SSH_KEY`), DESIGN N20
    (two identity types), and OPERATIONS' identity rules (ids, what the
    accounts script never deletes, membership at login, the proof key).
    The documentation stage §78 is opened for what the daily driver
    owes. The live results of steps 8-9 are added here when they stand.

### Verification

- `just test` after every code step (exit code checked); golden
  byte-identical after step 2, moved once each in steps 3 and 5.
- Container tests run the script twice (second run changes nothing),
  against a pre-existing equal group (adopted) and a differing one
  (refused with both ids).
- `just full-test` before the stage is declared done.
- Live: steps 8 and 9 above; the reference configuration's strict state
  query and `perform` stay green; a release carries it and the sibling
  takes the release.

### Open risks, stated

- **sftd and a foreign `/etc/group` entry** is unobserved: step 1
  exists to find out, before any code depends on it.
- **Membership of a not-yet-existing account**: whether the group line
  may name it early or must wait is decided by step 1 and the container
  test; the plan assumes waiting.
- **A breaking release, by decision**: every tree with an `okta-tf`
  group builder must write the `posix:` line when it takes the release
  that carries step 5 -- a builder's name, or `none`. Today that is the
  reference configuration alone.
- **`none` is reserved system-wide** (§76): no item may carry the name,
  and a reference written `none` is refused everywhere except where a
  field, like this one, gives the word a meaning and says so.
- **`posix: none` keeps the defect, on purpose and in sight**: the
  owning group stays absent on those machines. The note is the only
  thing that says so.
- **Size**: about ten working days. Steps 2-4 are useful on their own
  (the defect is fixed for standalone); step 8 is the one that fixes
  coops.
- **Order against §65**: the walk would be simpler on the Okta-free
  starter this stage produces; that is the operator's call, not assumed.

## 80. Hygiene bundle XI

**Status: OPEN 2026-10-05, one item; a plan -- nothing here runs until
the operator says "do 80".**

1. **The reference configuration bakes on a 1 GB t2.micro by default.**
   Found 2026-10-05 while proving §75: the three SSH-over-SSM bake
   timeouts of the sibling's `perform` runs (37212963588, 37290586415,
   37296813122) were all on t2.micro bake hosts -- an instance image
   that names no `machine_type` on its runtime entry falls back to its
   runtime's `default_machine_type`, which is `t2.micro` on the
   sibling's AWS runtimes. The same RHEL 9 parent that timed out under
   `imgfile-basic-cloudflow-notdocker` baked two other images on an
   r5.4xlarge the day before, and the bake machine's SSM agent was
   Online during a timeout. The system already knows the shape: the
   instance model records a t2.micro OOM-killing the SSM agent
   ([instance.py](packages/base/src/cs_image_system/base/models/instance.py)),
   and every starter ships `default_machine_type: t3.medium` with "`dnf
   update` OOMs a 1 GB t2.micro during a bake". The sibling predates the
   starters. Done for notdocker alone, by the operator's choice
   (sibling 3c1638f: `machine_type: t3.medium` on its runtime entry).
   Fixed looks like: **USER** -- the sibling's AWS runtimes declare
   `default_machine_type: t3.medium` as the starters do (it touches only
   bakes and instances that name no machine type; machine type is
   outside the fingerprint, so nothing re-bakes for it). Optional, also
   the operator's call: `validate` notes a bake host that falls back to
   a runtime default, so the choice is visible where it is made.
