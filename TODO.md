# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **§65**, walking the daily driver, started 2026-10-05
on `feature/walk-daily-driver`: the operator types each stage from
[DAILY_DRIVER_EXECUTE.md](DAILY_DRIVER_EXECUTE.md) on a Fedora 43
container. §81, hygiene bundle XII, is open (four items the walk
found; 3 and 4 landed with §82, 1 and 2 a plan). §82, an image says
which configuration owns it, LANDED 2026-10-05 (0d1850c): the
release that carries it (dev15) is the operator's, and the reference
configuration then relabels its images. No documentation stage is
open. Planned, by the operator's word: §66 and §30.

Releases: dev14 (2026-10-04) carries §79 and is the reference
configuration's, develop and main, performing green on it (run
37301986059, 2026-10-05); dev13 carries §75.

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

## 65. Walking the daily driver

**Status: IN PROGRESS since 2026-10-05 ("do 65"). W5 was replaced by
the operator the same day: the walk runs on a Fedora 43 container
(`csis-walk`), as user `mykel.alvis`, on the operator's clone of the
walk repository mounted as a volume, with AWS access keys supplied
by hand; the operator types each stage from
[DAILY_DRIVER_EXECUTE.md](DAILY_DRIVER_EXECUTE.md) and Claude reads
the shell history and the tree. Findings F1-F6 so far (the walk
log); the code ones are §81.** (The operator,
2026-09-24, on accepting §62: "make a new stage for walking through the
daily driver docs"; refreshed on the operator's word after §70 landed
and again after §80.)

**Why.** Every proof so far ran in the reference configuration, which
already had its roles, its workload identity pool, its OPA connection
and its secrets. Nobody has gone from nothing -- a release on the index,
an empty directory -- to a green `perform` the way a new team would, and
much has changed since `DAILY_DRIVER.md` was accepted as one attempt:
the release model and `init-config` (§64), the CI guide (§69), the
bootstrap with its four sections (§70: GitHub, AWS, GCP, Okta and OPA),
the refresh rules of hygiene IX, the POSIX identity plugin (§75: a
required `posix:` line on every Okta group builder, the login hook, a
fourth starter `standard-aws-posix`, the proof key
`CSIS_PROOF_SSH_KEY`), the reserved names (§76), the narrowing of
`--only` beside `--only-runtime` and the records a failed bake now keeps
(§79), and the starters' t3.medium bake hosts (§80). In particular the
bootstrap's CREATE paths -- new IAM roles, a new state bucket, local
state then migrated, the Okta section's guidance on a repository whose
OPA objects do not exist yet -- have passed `tofu validate` and never an
apply: the reference configuration's bootstrap root was applied, but
ADOPTING what stood. The walk is the proof, and every place the text and
reality differ is a finding.

**What it changes.** Words only. Findings that are words are fixed in
this stage (the daily driver, the guide, the starters' READMEs and
comments); findings that are code go to hygiene bundle XII (opened by
the first one) or to a new stage, never made here -- a documentation
stage changes no code. The walk log (`_uncommitted/walk-log.md`, every
step with the exact text followed and what happened) is the stage's
evidence, summarised in its squash message.

**The decisions** (answered by the operator, 2026-10-05; W1, W2, W3
and W5 took the default, W4 and W6 did not):

- W1, where the walk repository lives. Default: a new repository
  `infrastructurebuilder/cs-image-system-walk`, public like the other
  two, created by the operator, deleted (or archived) at the end.
- W2, what the walk may create in NOAA's AWS account. Default: the
  bootstrap's create paths for real -- two new roles
  (`csis-walk-readonly`, `csis-walk-apply`; the OIDC provider is
  account-wide and stands, so it is read) and a NEW state bucket, so the
  local-state-then-migrate path is walked; one base bake, one
  instance-image bake (both on the starter's t3.medium bake host) and
  one DURABLE instance -- durable because the login proof skips
  ephemeral machines and CI's `perform` proves only standing ones --
  launched by `just cloud-launch`, standing for the walk (a t3.medium,
  cents an hour), decommissioned at the end. All of it destroyed at the
  end.
- W3, OPA. Default: the same team, with walk-prefixed group names
  (`walk_*`) so nothing the reference configuration manages is touched;
  a new workload connection and role for the walk repository, made in
  the console by the operator from what the bootstrap's Okta section
  prints -- which is that section's proof on a repository with nothing
  yet. The Okta services app and the OPA service user are the reference
  configuration's, reused (read-only lookups; nothing in Okta is
  created). At the end: the system never destroys an OPA group (a group
  once managed stays in the YAML, `unmanaged: true`, DESIGN N19), so the
  walk's groups, their policies, the connection and the role are removed
  by hand in the OPA console (USER), after the walk's tree releases
  them.
- W4, the GCE leg. **Decided: walked**, one cycle, in the SAME walk
  repository after the AWS walk: the GCE runtime added to the tree the
  way `complete` declares it, the bootstrap's GCP section re-run (the
  operator's project already has the workload pool and provider, which
  the section only reads; what it creates is the walk repository's own
  bindings and grants), one base and one image bake on the project, an
  EPHEMERAL instance launched, verified and torn down in its cycle,
  then the walk's GCE images disposed. GCP is the operator's money:
  anything left standing at the end of a GCE step is reported (what,
  id, cost) the moment it is seen; it should be nothing.
- W5, how fresh "fresh" is. Default: the operator's Mac under a clean
  shell -- a scratch `HOME`, `UV_TOOL_DIR` and plugin cache, no `CSIS`
  override, no checkout of this repository on `PATH` (today the
  operator's `cs-image-system` IS this repository's `.venv`) -- rather
  than a new machine; the tools of 1.2 as installed. A container is the
  alternative, at the cost of the browser-based logins.
- W6, which starter is walked. **Decided: both**, `standard-aws` first
  (Okta and OPA, with its `posix: posix-local` delegate: the path the
  team uses, and the only one that walks the bootstrap's Okta section
  and the console steps), then `standard-aws-posix` as a second,
  shorter walk: its own repository
  (`infrastructurebuilder/cs-image-system-walk-posix`, USER), whose
  bootstrap ADOPTS the first walk's AWS roles and adds its own trust
  -- so the adopt path is walked too -- with no OPA, the proof over ssh
  with `CSIS_PROOF_SSH_KEY`, and one durable posix machine.

**Steps.**

1. **The release and the shell.** The walk installs the newest release
   on TestPyPI (0.1.1.dev14 today), pinned in `.csis-version`, through
   `uv tool install` exactly as 1.1 says, in the W5 shell. A release
   cut during the walk is not taken mid-walk.
2. **The repository, from nothing** (1.9, the W6 starter):
   `cs-image-system init-config walk --from standard-aws`, `git init`,
   the GitHub repository (W1, USER), `just init`. Every `REPLACE-ME`
   filled from the reference account and the W3 names (the Okta group
   builder's `posix:` line stays as the starter writes it), a fresh age
   identity and `reencrypt`, `just validate`, `just dry`, the emission
   read, the first commit -- typing only what the page says.
3. **The bootstrap, where it can create** (1.8, CI_SETUP.md 3.0): `just
   bootstrap` interactively, every question read against the page (the
   GCP section answered "none" under W4); the apply with the README's
   exports (USER) creating the W2 roles and bucket on local state; the
   re-interview that binds the root to the new bucket and `tofu init
   -migrate-state`; `set-secrets.sh` with the walk's secret files
   (USER), `CSIS_PROOF_SSH_KEY` among them if W6 walks the posix
   starter; the Okta section's by-hand list followed to make the walk's
   OPA connection and role (USER, console), then `just bootstrap` again
   until that list is empty but for what is by hand by decision.
4. **CI** (1.8, CI_SETUP.md 3.8): `verify` green on the first push,
   `live` green once the secrets exist, the probe, one `perform` on
   `main` with its records pushed back.
5. **Making things** (section 3, within W2/W3): one walk group of one
   test user, one storage, one base image, one instance image with one
   modification and one post-bake test, the durable instance through
   `just cloud-launch`; on the machine, the group exists with OPA's gid
   and the member's `id` carries it (3.1, "The group on its machines");
   the login proof by hand, then as the workload in the next `perform`.
   **Changing things** (section 4) for two changes: a modification,
   re-baked; a membership, reaching the machine at the next applying
   instance run and the member's next login.
5a. **The GCE leg** (W4): the GCE runtime and its storage declared in
   the walk tree from CONFIGURATION and the `complete` starter, the
   bootstrap's GCP section re-interviewed and applied (USER), `just
   cloud-cycle <gce runtime>` once -- bakes, the ephemeral instance,
   its verification and teardown in one run -- then the walk's GCE
   images disposed and `just cloud-empty <gce runtime>` (GCE has an
   inventory, so emptiness is provable there).
5b. **The posix walk** (W6): steps 2-5 again, shorter, from
   `init-config walk-posix --from standard-aws-posix`: the bootstrap
   adopting the walk roles, `CSIS_PROOF_SSH_KEY` among the secrets, a
   posix group with its proof user, one durable machine, `perform`'s
   login proof over ssh.
6. **The failure walk** (section 6): provoke rows on purpose and check
   each one's symptom, meaning and remedy -- an expired session, an
   unsourced shell, a destroy the gate must refuse, a pin to an
   unreleased build outside the grace, a stopped machine, a reserved
   name (`name: none`) refused at load, an `--only` name that
   `--only-runtime` cannot honour.
7. **Read rather than walked**: the pyproject install form of 1.1; the
   GCE starter if W4 skips it; the other starter if W6 picks one; the
   CI guide's GitLab section (section 4: "Not written yet" -- a finding
   only if any page claims more); the developer chapter (section 9)
   against this repository's `just test` and `just release ... yes`.
8. **Teardown, and its proof** (both walk repositories): the durable
   instances through `just cloud-decommission`; the walk's images
   through `just cloud-dispose-images` (the walk repository's lineage
   holds only the walk's builds); the storage undeclared through the
   gate; the walk's OPA groups released (`unmanaged: true`) and then
   removed by hand with their policies, the connection and the role (W3,
   USER, console); the bootstrap roots destroyed (USER: roles, bucket,
   the GCP bindings and grants, GitHub settings); both repositories
   deleted or archived (USER). `just cloud-empty` cannot prove an AWS
   runtime empty (it has no inventory there), so the proof is the walk's
   strict state query with nothing declared, plus a read of the account
   for anything tagged with the walk's names. Afterwards the reference
   configuration's strict state query and its `perform` stay green,
   which is the proof the walk touched nothing of it.
9. **The fixes and the records**: every finding in the walk log is fixed
   here (words) or filed (code); `DAILY_DRIVER.md` gains a dated line at
   the top -- walked on <date>, against release <version> -- and so do
   the guide and the starters' READMEs where they were walked.

**Sizing**: the repository and bootstrap half a day; CI half a day, most
of it secrets and the console; section 3 a day, most of it bakes; the
failure walk two hours; the GCE leg half a day; the posix walk half a
day; teardown three hours; the fixes a day -- about five working days.
Costs: on AWS four bakes and two t3.medium machines standing for the
walk's days; on GCP (the operator's) two bakes, one ephemeral machine
for its cycle, and the images until they are disposed.

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

## 81. Hygiene bundle XII

**Status: OPEN 2026-10-05, four items found by the §65 walk. Items 3
and 4 LANDED with §82 (0d1850c, 2026-10-05) by the operator's word;
items 1 and 2 are a plan -- nothing more runs until the operator says
"do 81".**

1. **A starter's own hook refuses its first commit.** The tree
   `init-config` writes carries the copyright holder's address in the
   SPDX header of every release-owned file (`tfmodules/*`,
   `.githooks/pre-commit`), and the starter's `public_safe.allow` does
   not allow it: `git commit` of the untouched tree is REFUSED with 46
   findings. The reference configuration allows the address by hand, so
   nothing caught it. Fixed looks like: every starter's allow list
   carries the address with its reason (or the scan exempts SPDX header
   lines), and a test runs public-safe over each starter as written.
2. **`init-config` in a cloned repository writes no configuration.**
   Only a directory with no entries counts as new
   ([starters.py](packages/system/src/cs_image_system/system/starters.py)),
   and a clone always has `.git`, so a team that creates its repository
   on GitHub and clones it -- the usual order -- gets the release-owned
   files and no `cfg/`, with a message that reads like success. Fixed
   looks like: a directory holding only `.git` (**USER**: and a README
   or LICENSE GitHub made?) takes the whole starter; the message of the
   release-owned form says no configuration was written; a test for
   both.
