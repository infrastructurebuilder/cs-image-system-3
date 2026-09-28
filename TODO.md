# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress** (§69 LANDED 2026-09-28; §63, §67 and §64 LANDED 2026-09-26). Next by the operator's word: §68 item 1 (decide), §70.

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
on none of this. **Hygiene bundle VII (§68) is open since 2026-09-26**
(§67, bundle VI, LANDED 2026-09-26); the next non-critical hygiene issue
joins it.

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
- §30 (the contract package), §65, §66 and §70 (the bootstrap: the one-time
  initialisation as terraform from an interview) are planned, not started;
  §69 (the CI-from-scratch guide) landed 2026-09-28, its step 5 (the
  reference configuration's secrets and trust, by the guide) the operator's;
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

**Status: PLANNED, not started** (the operator, 2026-09-24, on accepting
§62: "make a new stage for walking through the daily driver docs").

**Why**: `DAILY_DRIVER.md` was written from the code and the manuals and
accepted as one attempt; nobody has yet sat down with it, a fresh
configuration repository and the prerequisites, and done what it says from
section 0 to section 8. A page held to "no one should be surprised" is only
as good as its first walk. The walk is the proof, and every place the text
and reality differ is a finding: a command that does not exist or says
something else, a step out of order, a prerequisite the text forgot, a
message the failure table lacks, a decision the starter tree comments
wrongly. Findings that are words are fixed in this stage; findings that
are code go to §64, a new code stage or the open hygiene bundle as items, never made here (a documentation stage
changes no code).

1. **The preconditions, before anyone walks.** A release on the index that
   carries what the page describes: the one on TestPyPI (`0.1.1.dev1`,
   2026-09-17) predates the prune step, the release grace and
   `cloud-upgrade`, so `just release dev test` (the operator's act) comes
   first, and the walk installs THAT version (`.csis-version`). A machine
   or a user profile with nothing of the system on it: `uv`, `just`,
   `git`, the tools of section 1.2 at their floors, and no checkout of
   this repository. The accounts of sections 1.3 to 1.5, as they are for
   the reference deployment, and a fresh age identity.
2. **The AWS walk.** Copy `docs/examples/standard-aws/` into a new git
   repository, then follow sections 1.1 to 1.9 and 2 exactly as written,
   typing only what the page says: `uv tool install`, `just init`, the
   identity replaced and the tree re-encrypted, every `REPLACE-ME` filled
   from the reference account, `just validate`, `just dry`, the emission
   read, the first commit. Then section 3 as far as the account allows
   without touching what the reference deployment owns: a group of one
   test user, one storage, one base image, one instance image with one
   modification and one post-bake test, one ephemeral instance through
   `just cloud-launch`, the login proof. Section 4 for one change (a
   modification, then `cloud-upgrade` on a durable instance if one is
   declared for the walk). Every step's outcome goes in the walk log
   beside the exact text that was followed.
3. **The GCE walk.** The same from `docs/examples/standard-gce/`, on the
   operator's project: this is also the first live root on the `gcs`
   state type. If it does not hold, the starter falls back to `local`
   and the finding goes to a new code stage with the plugin named. GCP is the
   operator's money: the walk ends with `just cloud-empty` and nothing
   standing.
4. **The CI walk.** Push the walk repository to GitHub, set the secrets
   the starter workflow names, and watch the three jobs: `verify` green
   on the first push, `live` green once the secrets exist, one `perform`
   on `main`, its records pushed back, the login proof as a workload. The
   `REPLACE-ME` steps the workflow leaves for packer and tofu are filled
   in the starter from what worked.
5. **The failure walk.** Provoke five rows of section 6 on purpose (an
   expired session, an unsourced shell, a destroy the gate must refuse, a
   pin to an unreleased build outside the grace, a stopped machine) and
   check each row's symptom, meaning and remedy against what was seen.
6. **The other paths, read rather than walked**: the pyproject install
   form (`uv init --bare && uv add cs-image-system`, `CSIS="uv run
   cs-image-system"`) on the AWS walk's repository; the developer chapter
   (section 9) against `just test` and `just release ... yes` in this
   repository.
7. **The fixes and the records.** Every finding in the walk log becomes
   a documentation fix here, a starter-tree fix here, or a code item in
   §64, a new code stage or the open hygiene bundle, and the log itself is the stage's evidence in the squash
   message (the records convention: no ledger). `DAILY_DRIVER.md` gains
   a dated line at the top: walked on <date>, against release <version>.
   The walk repositories are deleted afterwards, their clouds emptied.

**Sizing**: a release, half an hour; the AWS walk a day, most of it the
bakes and the launch; the GCE walk half a day; the CI walk half a day,
most of it secrets; the failure walk two hours; the fixes a day. Nothing
here changes code.

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

## 68. Hygiene bundle VII

**Status: OPEN since 2026-09-26.** Non-critical hygiene issues join this
bundle; none is a stage of its own.

1. **The fixture's Debian 11 chain is archived upstream.** `just
   fixture-live` (stage 64) runs the fixture's modification tests under
   docker, and `imgfile-data-science/data-science-setup` on `my-deb-11`
   fails at target preparation: `apt-get` in the `debian:11` container
   gets `404 Not Found` from `deb.debian.org/debian-security/pool/updates/`
   (bullseye left the mirrors when its LTS ended; its packages are on
   `archive.debian.org`). Reproduced twice on 2026-09-26, deterministic.
   Until this lands the docker leg of `fixture-live`, and so this
   repository's CI `live` job, is red; `validate` and the dry run pass.
   Fix: move the fixture's Debian OS builder to `debian-12` (bookworm;
   the golden moves), or teach the debian target preparation to point an
   archived release at `archive.debian.org` (a behaviour change worth
   having anyway, since every release archives eventually). Decide, then
   do.

## 70. Bootstrap: the one-time initialisation, as terraform from an interview

**Status: PLANNED, not started** (the operator, 2026-09-28: "a one-time
initialization of assets for using the starter-tree repo ... code that
lives in the main repo, called by some specific subcommand of
cs-image-system and produces terraform based on interview questions ...
a --quiet option that selects all the defaults ... generated/bootstrap ...
an auto tfvars file ... as much IaC for the initialization effort as is
possible, per the README in the starter tree, but allow for existing
infrastructure ... ask if you want a specific type of resource, like AWS or
GCP or Okta, and if so ask any questions needed for those. We will
probably iterate on this several times").

**Why.** §69's guide tells a team what to make by hand before CI can run:
the OIDC provider and two roles in AWS, the workload identity pool,
provider and service accounts in GCP, the Okta app and the OPA workload
objects, the repository's settings and secrets. Most of that is
infrastructure, and infrastructure here is declared and applied through
gates, never clicked. This stage turns the guide's sections into terraform
the team applies once, from answers it gives once, with the existing
pieces of its accounts taken as they are.

**The shape.**

- **The command**: `cs-image-system bootstrap [--quiet] [--section
  aws|gcp|okta|github ...]`, run in a configuration repository. It loads
  no configuration (the sessions and federation it makes may not exist
  yet); it reads the raw tree (`cfg/*.yml`, like `preflight` does) and the
  checkout (`git remote`, `gh api` for the repository and owner ids when
  `gh` is present) for the interview's defaults.
- **The interview** is a declared list of questions, each with an id, a
  prompt, a type (text, choice, yes/no, path, secret-path), a default (a
  literal, or a function of the tree and the earlier answers), a
  `when` condition on earlier answers, and the terraform variable it
  feeds. Sections open with "Do you want AWS? GCP? Okta and OPA? GitHub?"
  and each section's questions follow only when it is wanted. Every
  "existing" question is a fork: "Does the account already have a GitHub
  OIDC provider?" yes takes its ARN and emits a data source, no emits the
  resource; the same for the state bucket, the VPC and subnets, the SSM
  instance profile, the workload identity pool, the service accounts, the
  Okta app. `--quiet` takes every default; a question whose default cannot
  be derived (an account id with no session, a repository id with no `gh`)
  is refused by name under `--quiet` instead of guessed.
- **Where the questions live**: the framework and the GitHub section in
  base (`base/bootstrap/`: the question model, the interview runner, the
  HCL writer); the AWS, GCP and Okta sections contributed by their
  plugins through a new entry-point group (`cs_image_system.bootstrap`),
  each plugin owning the questions and the terraform for its cloud, as
  each owns its runtime today. A section absent from the installed
  plugins is absent from the interview.
- **Regenerable, and committed, like the emission** (the operator,
  2026-09-28: "the command should be able to re-generate the backing setup
  in the same way that the system itself does; once it generates the
  bootstrap, it should be committable and retainable within the repo").
  `bootstrap.yaml` at the root of the tree, beside `cfg/`, is the
  committed source, as the YAML tree is for the lifecycles (decided
  2026-09-28: the source is hand-editable, so it lives with the
  declarations, never under `generated/`, which the system writes and
  nobody edits; the output stays at `generated/bootstrap/`, so every rule
  the emission already has -- the commit, config-drift, the `.gitignore`
  policy, pruning, the mirror -- applies unchanged, and the golden moves
  only when the frozen fixture carries a `bootstrap.yaml`, which it does
  not in iteration one); `bootstrap` interviews and writes it, and every
  `run`, dry or real, regenerates `generated/bootstrap/` from it
  deterministically
  (the same answers and tree give the same bytes), generation only: no
  run ever plans or applies the bootstrap root. So a `--commit` run
  commits it with the rest of the emission, `config-drift` reports a
  stale root as drift, and a clone regenerates it without an interview.
- **The output**, under `generated/bootstrap/` (a new lifecycle-shaped
  directory beside the lifecycles', with the same `.gitignore` policy:
  tool residue, plans and state out, everything else in):
  - `main.tf`, `providers.tf`, `variables.tf`, `outputs.tf`: one root
    module calling the release's modules `tfmodules/bootstrap_<section>`
    (shipped with the starters like every module; `module_source_base`
    reaches them), with `count` toggles from the answers and data sources
    for what exists;
  - `bootstrap.auto.tfvars`: every answer, so `tofu init && tofu apply`
    in that directory needs nothing typed again; regenerated from the
    saved answers, never edited by hand (`bootstrap` says so in its
    header); committed;
  - (the answers are NOT here: `bootstrap.yaml` at the tree's root is
    the input every regeneration reads and `bootstrap` reads back on a
    second interview so a team re-answers only what changed; the same
    shape a `--answers FILE` option takes; edit it, or re-interview, and
    the next run regenerates this directory);
  - `set-secrets.sh`: the `gh secret set` lines of guide section 3.7,
    each reading its value from a file the interview named or from the
    root's outputs (the role ARNs, the provider name, the service
    account addresses), so no secret VALUE enters the tfvars or the
    terraform state;
  - `README.md`: what was generated, what is left by hand (below), and
    the apply and verification commands in order.
- **What terraform makes, per the guide**: AWS, the OIDC identity
  provider, the read-only role and the write role with their trust
  documents (the `sub` forms the interview chose: plain, id-bearing, or
  both) and permission policies (the guide's, with the interview's
  bucket, prefix, region, account and instance profile filled in), and
  optionally the state bucket (versioned, encrypted, lock files) and the
  SSM instance profile when the account lacks them; GCP, the workload
  identity pool and the GitHub provider with the attribute mapping and
  condition, the read-only service account and its roles, the optional
  write account, the `workloadIdentityUser` bindings; GitHub, the
  repository's default branch, the branch protection or ruleset that
  lets `github-actions[bot]` push to `main`, Actions permissions, and the
  variables that are not secret; Okta, the API services app
  (`okta_app_oauth`, service type, key-based auth, the read scopes
  granted) with its generated key, when the operator has an admin token
  to run the provider with. Every resource carries the tags the system's
  other roots carry.
- **What stays by hand, and is printed**: the OPA workload connection and
  role (the oktapam provider has no workload resources; guide section 3.5
  steps 1-2 and 4-6), the age identity for CI (`age-keygen`, then
  `reencrypt`; the script does the `gh secret set`), the network rules
  that are the team's (never modified by the system), and the first
  performing run. The bootstrap never applies anything itself: the
  operator runs `tofu apply` in `generated/bootstrap`, the same act as
  every other IAM write in this system.
- **The bootstrap's state** binds to the tree's declared backend like
  every other root when the interview says the state bucket exists; when
  the bootstrap creates the bucket, the first apply uses local state
  (ignored: `terraform.tfstate` and `.terraform/` never enter a commit)
  and the printed next step moves it to the bucket with the system's
  existing `state-migration` machinery, after which the root is bound
  like the others. The state holds no secret value by construction (the
  secrets script keeps them out). A regenerated root and the state
  carry over, so the root is re-applyable.

**Decided 2026-09-28** (the operator): D1, iteration one is the framework
and the GitHub section alone (the interview, `--quiet`, `bootstrap.yaml`,
the tfvars, the secrets script, the repository settings); every cloud
section is a later step, AWS first; D2, `set-secrets.sh`, no secret value
in the tfvars or the state; D3, `bootstrap.yaml` and `bootstrap.auto.tfvars`
are both committed (the answers as `bootstrap.yaml` at the tree's root,
decided 2026-09-28; the starters' `.gitignore` stops ignoring `*.tfvars`
under `generated/bootstrap`; public-safe runs on them); D4 and D5, the OPA
workload objects and the Okta services app are decided when the Okta
section is built (step 6), not now: iteration one prints nothing about
Okta; D6, the name is `bootstrap`.

**Decided 2026-09-28, second round** (after the operator's regenerability
clarification): D7, every run regenerates `generated/bootstrap` from the root's
`bootstrap.yaml`, generation only, so `--commit` and `config-drift` cover
it;
D8, the root's state is the tree's declared backend when the bucket
exists, else local for the first apply and then migrated with the
existing `state-migration` machinery.

**The decisions, as asked** (for the record; D4 and D5 return at step 6):

- **D1, the first iteration's scope.** AWS + GitHub + the interview
  framework + the tfvars and secrets script (the reference deployment's
  own shape, provable against its account), with GCP and Okta as steps 2
  and 3; or all four sections at once.
- **D2, the GitHub secrets.** The `set-secrets.sh` script (values never in
  terraform state; recommended) or `github_actions_secret` resources fed
  by `TF_VAR_*` at apply time (one apply does everything; the local state
  then holds every secret value in clear).
- **D3, `bootstrap.yaml` and the tfvars in the repository.** Both under
  `generated/bootstrap/` and committed (they hold account ids, ARNs,
  repository names: public-safe must pass, and the starters' `.gitignore`
  ignores `*.tfvars` today), or ignored and kept by the operator. The
  secrets script names files by path and never holds a value either way.
- **D4, the OPA workload objects.** Printed by-hand steps only (the
  provider cannot make them), or a `bootstrap` that calls the OPA API the
  way the system already reconciles CI policies (`opa_gids`,
  `workload_policy`), if the API exposes connection and role creation to
  the service user; to be checked against the API before deciding.
- **D5, the Okta API services app.** In scope with the okta provider (an
  admin token or an existing app with the manage scopes is needed to make
  it, a chicken-and-egg the interview must ask about), or by hand in
  iteration one.
- **D6, the name.** `bootstrap`, or `init-ci`, or a subcommand of
  `init-config`.
- **D7, regeneration.** Every run regenerates the root from
  `bootstrap.yaml`, or only `bootstrap` does, or split.
- **D8, the root's state.** The declared backend when the bucket exists
  and local-then-migrate when the bootstrap creates it; or always local;
  or split.

**Steps.** Iteration one is steps 1-3 and the parts of 7-9 they need;
each later step is its own iteration, proved before the next.

1. The decisions, recorded here (D4 and D5 at step 6).
2. The framework in base: the question model, the interview runner (a
   terminal prompt with the default shown, `--quiet`, `--answers FILE`,
   `--section`), the answers file, the HCL writer (the root module, the
   tfvars, the outputs), the entry-point group, the `bootstrap`
   subcommand exempt from loading the configuration, the regeneration
   of `generated/bootstrap` from the root's `bootstrap.yaml` inside every run
   (generation only, before the lifecycles, pruned like theirs when the
   answers file is absent), the root's backend binding (D8), `just
   bootstrap` in the starter Justfile, and `generated/bootstrap` known to
   the emitted `.gitignore` (tfvars and answers in, state and plans out)
   and to `public-safe`.
3. The GitHub section and module (repository settings, protection,
   variables) and the secrets script.
4. The AWS section and module (`tfmodules/bootstrap_aws`): the provider,
   the two roles, the optional bucket and instance profile, every
   "existing" fork.
5. The GCP section and module (`tfmodules/bootstrap_gcp`).
6. The Okta section, after D4 (the OPA workload objects: printed
   by-hand steps, or a spike against the OPA API the system already uses
   for CI policies, then creation through it) and D5 (the services app:
   by hand, or `okta_app_oauth` with an admin credential used once) are
   asked, and the printed by-hand remainder.
7. Tests: the question model (defaults, `when`, `--quiet` refusals); the
   fixture's quiet interview against a private copy of a starter tree
   produces a root that `tofu validate` accepts (the suite's real-tofu
   pattern, private plugin cache) and a tfvars equal to a pinned snapshot;
   a run over a fixture copy carrying `bootstrap.yaml` regenerates the same
   bytes (the frozen fixture carries none, so the golden is still; a
   later iteration may add one and move the golden by decision), a
   `--commit` run stages it, and `config-drift` reports an edited root as
   drift;
   every guide secret name appears in the secrets script; the modules
   under `tfmodules/bootstrap_*` are shipped in the starters like the
   others (`test_docs_examples` already holds `tfmodules/` byte for
   byte); `public-safe` over a generated `generated/bootstrap`.
8. Docs: CI_SETUP.md gains "3.0 The bootstrap" saying which of its steps
   terraform does and which remain by hand, with the apply commands; the
   starter READMEs and DAILY_DRIVER 1.8; the system README's command
   entry; OPERATIONS section 3.
9. The live proof: `bootstrap` in the reference configuration against the
   NOAA account and the operator's GitHub, with every "existing" answer
   yes (the provider, the bucket, the roles all exist), so the plan shows
   nothing to create beyond what the repository lacks; then the guide's
   proofs (§69 step 5) done by the script. Applying is the operator's
   act; the harness prepares and never applies IAM.

**Sizing**: the framework a day; each cloud section half a day to a day
(the AWS one is the longest: the policies are already written in the
guide); the Okta section depends on D4/D5; the tests a day; iterations
after the first as the operator finds them.
