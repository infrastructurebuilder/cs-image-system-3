# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **§62 (the daily driver), in progress since 2026-09-23** on `feature/daily-driver`.

Open stages and their order (revised 2026-09-22, when §59 landed):
**§62 (the daily driver)**, in progress since 2026-09-23; then **§63**, the
code defects the documentation found, planned and waiting on the
operator's word; §30 waits on the operator's decision. (§61, hygiene
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
- A documentation stage modifies no code (operator, 2026-09-23): its diff
  is markdown, example configuration trees and the tests that hold the
  documentation contract; a code change it would need is a new stage,
  written as a plan, never a side edit.
- §30 (the contract package) is planned, not started; §62 (the daily
  driver) is in progress since 2026-09-23; a stage is a plan in this file
  until the operator says to execute it (2026-09-23).
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

## 62. The daily driver: how a person actually uses the system

**Status: steps 1 to 6 LANDED on `feature/daily-driver` 2026-09-23** (the
operator said "execute stage 62" that morning, after §61 landed): the
contract test, sixteen READMEs one commit each, seven passes of manual
corrections, `DAILY_DRIVER.md`, the three example trees with their test,
the root README. Step 7 is the standing convention. What remains is the
bar on the branch head and the operator's word to squash-merge; the code
defects the work found are §63. An execution begun before the plan
was written was reverted; its draft of `DAILY_DRIVER.md` and its contract
test are the starting points for steps 4 and 1.

**A documentation stage changes no code** (operator, 2026-09-23): the diff
is markdown, the two example trees and the tests that hold the contract.
Where a doc and the code disagree, the doc is corrected. Where the code
itself must change, that is a NEW stage, written as a plan and named in
this stage's records; it is not made here.

**Why**: the documentation describes the system -- every file, every field,
every rule, every run -- and still a person sitting down to USE it on a
Monday has no page that starts where they are. Nothing says what has to
exist before the first command (accounts, roles, keys, sessions, tools, a
configuration repository), nothing walks through making an image, a
storage and an instance and then changing each, nothing collects the
failures the system produces into "this is what that means and what to do",
and the plugin READMEs -- good, and differently shaped -- do not all say what
a plugin needs from outside, every knob it reads, every variation it
performs, what it tests, and how it fails. The standard (operator,
2026-09-22): **no one should be surprised by the system's behaviour if
they read the docs.** And its corollary (operator, 2026-09-23): where the
choice is between a little more explanation and a little less, err on
the side of more -- a reader who already knows can skip a sentence; a
reader who does not cannot supply one.

**What exists already, and what the plan builds on**: a 1790-line
configuration reference ([CONFIGURATION.md](docs/CONFIGURATION.md), every
file and field), a 2042-line operations manual
([OPERATIONS.md](docs/OPERATIONS.md), every run, rule and procedure),
[DESCRIPTION.md](DESCRIPTION.md), [PLUGINS.md](docs/PLUGINS.md), and a
README in all sixteen packages (80 to 1125 lines each, in a shared shape:
what it registers, models, the builder, emission, an example). The gap is
the narrative that ties them together for a person doing the work, and a
uniform closing contract in every README.

**Known disagreements between the docs and the code**, found while reading
for this plan on 2026-09-23 and to be fixed in step 3 (the code wins):
[CONFIGURATION.md](docs/CONFIGURATION.md) section 4 says `ena_support` is
passed to the packer source (nothing reads it), `default_owners` is not
read by the cloud plugins (it is appended to every vendor query's owners),
`security_group_ids` are groups for build VMs and instances (checked and
counted at load, emitted nowhere), and `default_image_builder` is the
image builder used when a runtime entry names none (nothing reads it;
`image_builder: default` resolves to the registry's default); section 11.2
says `Image.variables` is emitted as packer variables (only the retired
`gen_packer.py` reads it; the builder emits `release` and
`base_image_version`); section 11.3 says an instance's `userdata` is not
read by the tofu roots (the launch script appends it before the completion
marker and records it as a launch parameter); and the embedded
`executables.yml` shows the `gcloud` floor as a date-shaped version while
the fixture pins `>=500`, the SDK version the checker matches.

1. **The README contract, and the test that holds it.** Every package
   README keeps what it has and ends with four sections in a fixed form,
   so a reader can find the same thing in the same place in every package
   (only a `## Related` section may follow them):
   - `## Prerequisites and integration` -- what must exist outside the
     system before this plugin works (accounts, roles, APIs, tools,
     credentials, network), and how the plugin finds it (which field or
     variable); "nothing" is an answer.
   - `## Configuration reference` -- every field the plugin reads, its
     type, default and meaning, in tables; fields accepted but not read
     named as such; then the VARIATIONS: what the plugin does differently
     by declaration (ephemeral or durable, pinned or follow, ensure or
     script, encrypted or clear, one runtime or another, dry or real).
   - `## What it tests and verifies` -- what the plugin checks, when (at
     load, validate, generation, apply, after apply, in the state query),
     and where the verdict lands; "nothing" is an answer.
   - `## When it fails` -- the failures the plugin produces, what each
     means, where to look, what to do; failures that have actually
     happened first, with their dates.
   `tests/test_docs_contract.py` holds every package README to the four
   headings in order and checks that every relative link in the READMEs,
   [PLUGINS.md](docs/PLUGINS.md), [README.md](README.md),
   [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md) and `DAILY_DRIVER.md`
   resolves. PLUGINS.md names the contract. Lands first, with the test
   red for every package until step 2 turns each green.
2. **Sixteen READMEs against the contract**, one commit per package,
   written from the package's models, builders, tests and `pyproject.toml`
   and from the two manuals, never from memory; where a README and the
   code disagree, the code wins and the README is corrected. Expect this
   to surface more disagreements like the list above; each goes into
   step 3's list. Order: the three core packages (base, system,
   hashicorp-utils) last, since they cite the plugins.
3. **The reference manuals corrected** where the code contradicts them:
   the list above, plus whatever step 2 finds. PARITY.md's method applies;
   nothing is reworded that the code does not contradict.
4. **`DAILY_DRIVER.md`**, at the root, the narrative in the order a person
   meets it, linking to the manuals and the READMEs rather than repeating
   them:
   - *Before the first command*: what must exist outside the system --
     the AWS account, the SSO portal and the `sso-session` profile, the S3
     state bucket, the VPC, private subnets and security groups the
     constraints assume, the SSM instance profile, the two OIDC roles;
     the GCP project, ADC with impersonation, IAP; the Okta API services
     app; the OPA team, its API key pair, the resource group, the gateway,
     the workload connection and role; the age identities and who holds
     them; the tools and their floors; the shell (`.envrc`, the profile);
     the configuration repository beside this one and what it starts
     with, file by file.
   - *The first run*: validate, a dry run, reading the runner scripts and
     the summary, the first commit and push.
   - *Making things*: a group and its access, a storage (each kind), a
     base image, an instance image (modifications, tests, release), an
     instance (durable and ephemeral, the launch, the names it answers
     to, the verify, the login) -- each with the commands, what to
     expect, and what the records show afterwards.
   - *Changing things*: a modification and the second release, a base
     upgrade, an instance upgrade and the gated replace, a storage detach
     or archive, a membership, a decommission, the admin key, a state
     move, an adoption -- the procedures OPERATIONS holds, in the order a
     change is made.
   - *What specifies and what tests*: one table -- every declaration that
     states an intent (`tests:`, `post_bake`, `modifications`, `release`,
     `require_released_builds`, `parent_policy`, `image_policy`,
     `ephemeral`, storage `state` and `lifecycle`, `apply_*`, `members`,
     the workload objects, the names) beside the mechanism that proves it
     (in-bake tests, post-bake tests, mod tests, verify, the login proof,
     the state query, the gate, the golden, public-safe) and where each
     records its verdict.
   - *When it fails*: symptom -> meaning -> what to do, from the runs the
     system has actually failed: the session that lapsed, the plan on
     ciphertext, the stale attachment, the gate refusing an attachment,
     the alias that was not written, the released-builds window, the
     unaskable group, the hard drift that refused its own repair, the
     client with no session, one tofu at a time, the temp volume, the
     exit codes, where the logs and the records are.
   - *Every plugin*, one paragraph each, linking to its README's contract
     sections; and *the daily habits*, a short checklist.
5. **Two example configurations, both real** (operator, 2026-09-23):
   - a **standard** configuration per plugin set -- the smallest tree a
     team writes to get going, one per set the system supports (the AWS
     set: the `aws` runtime, the `s3` state backend, one OS builder, the
     EBS packer builder, the ansible and bash mod builders, the terraform
     instance and storage builders, the OPA group builder; the GCE set
     likewise), with one group, one storage, one base image, one instance
     image and one instance each, every value a placeholder a team
     replaces, and a comment on every line that is a decision;
   - a **complete** configuration -- every plugin, every field, every
     variation (`pinned` and `follow`, `ephemeral` and durable, `ensure`
     and `script`, each storage kind and state, encrypted and clear,
     overlays), commented, so that the reference manual's field tables
     have one living example of every row.
   Both live under `docs/examples/<name>/` in the shape of a configuration
   root, carry the fixture's TEST identity and synthetic personas and
   never a real value, and both LOAD and VALIDATE in a test (as the
   fixture does, with every cloud stubbed), so they cannot drift from the
   code without the bar saying so. `DAILY_DRIVER.md`'s "from scratch"
   chapter starts from the standard tree; CONFIGURATION.md's per-field
   examples point at the complete one. A third tree is not written: the
   live configuration is the worked example, and stays in its own repo.
6. **Records**: the root README's "Where to start" names `DAILY_DRIVER.md`
   first; the code defects the stage found are §63, a plan, not made here. Feature branch `feature/daily-driver`, squash-merged, kept.
   Documentation only, plus the two example trees and the tests that load
   them: the bar runs for those, nothing else reads markdown; `just
   full-test` is not owed by a docs stage.
7. **From here on, documentation is kept current by stage** (standing
   decision above): when §62 lands, the first stage that changes
   behaviour afterwards opens the rolling documentation stage, which
   lists the stages it covers and what each changed, and lands as one.

**Sizing**: step 1 is an hour; step 2 is the bulk, roughly an hour per
package read against its code, and it parallelises by package; steps 3
and 4 are a day together; step 5 is a day, most of it the complete tree
and its loading test. Nothing in it touches a cloud or a credential.

## 63. What the documentation stage found in the code

**Status: PLANNED, not started.** Written during §62 (2026-09-23) under the
rule that a documentation stage changes no code: every item below was
found by an agent reading a package against its README, the manuals and
the fixture, verified in the code, and left as it was. The manuals now
say what the code DOES, with "a code stage names the fix" where the doing
is wrong. This is that stage. Nothing here is proved live yet; each item
names the file and function so the fix can be judged before it is made.
Items marked **[likely to bite]** stand between a declared feature and its
working; the rest are dead fields, misleading messages and unreachable
branches, which cost nothing until someone trusts them.

**Likely to bite:**

1. **A state migration's previous-location file may not initialise.**
   `state_migration.render_record` drops `backend`, `type` and `run` from
   the meta-state record when it writes `<ws>.tfbackend.previous.hcl`,
   but every record since stage 47 also carries `location`, so the file
   would carry `location = "..."`, an argument no tofu backend accepts,
   and `init_against(previous)` in `begin` would fail for any migrating
   root. The test's fake tofu validates no arguments. Unverified live;
   check before the next `--migrate-state`.
2. **A GCE instance never receives the build its own run baked.**
   `TofuGceInstanceBuilder` inherits `pre_finalize_phase`, which writes
   `<label>_ami_id` into `instances.auto.tfvars`, while the GCE root
   declares `<label>_image`; tofu warns of an undeclared variable and the
   instance launches through `image_family`. Override `_ami_var` (or the
   hook) to name `_image_var`.
3. **A declared `type: dummy` builder fails the identity lifecycle.**
   `DummyGroupBuilder.generate_items_during` and the user builder's return
   `[]` where the contract wants an `AssetSet`; `gen_users`/`gen_groups`
   call `sort_and_write` on it (reproduced 2026-09-23). The template
   plugin should at least load and emit nothing.
4. **`mask` hides its own failure.** `cli.mask_command` swallows every
   per-file exception, `MissingIdentityError` included, so with the
   identity unset or wrong it prints no `::add-mask::` line and exits 0;
   a CI log would then show every plaintext with no signal. Refuse loudly.
5. **The attributes probe step cannot load.** The okta group builder emits
   `identity-attributes --probe --dry-run-apply` with
   `system_cli_executable` (no `--root-dir`), and the command loads the
   configuration from its working directory, the root's mirror, which has
   no `cfg/`; a real run of a tree that declares attributes fails after
   the identity apply. Use `system_cli_executable_with_config`.
6. **`use_state_backends: false` cannot produce a valid instance or storage
   root.** The instance and storage builders emit `terraform_remote_state`
   references unconditionally while the data sources are gated on the
   flag; refuse the flag off when a root needs a producer, or gate the
   references the same way.
7. **A runtime's `default_owners` and `default_config_username` are
   unreachable.** `os_builder_runtime_config.get_owners()` and
   `finalize()` look the runtime up by `self.image_builder` (an
   image-builder name) in the RUNTIME namespace and never find it; the
   `finalize()` itself has no caller, so `config_username` and the
   "ssh user could not be inferred" refusal never run either. Decide
   whether the fields live (fix the lookup, call the finalize) or die.
8. **An alias on a modification item's `type` fails at generation.** The
   orchestrator keeps the alias in `mod_data["type"]` (its comment says it
   swaps the canonical name; it does not) and `packer_ebs_builder` asserts
   on `ctx.mod_builders.get(...)`, a name-only map; `validate` does not
   catch it and the run reports `ok: false` with no validation error.
9. **A bash `ensure` entry is validated by its keys only.** A malformed
   entry raises `KeyError` at generation; `packages: git` iterates the
   letters; an unquoted `mode: 0644` renders `install -m 420`; the
   packages line falls through `dnf`, `yum`, `apt-get` and shows
   `apt-get: command not found` on an EL host, hiding the real error; an
   all-empty `ensure` passes load, is recorded `idempotent: declared` and
   emits nothing. Validate the entries at load.
10. **Filestore vanishes from the state report.** `TofuFilestoreStorageBuilder`
    has no `_lookup`, so `query_state` raises `NotImplementedError` and the
    query drops the builder silently (no `unavailable:` line, no
    `missing`), while the module's docstring says it reports unavailable.
    A `tf-gcp` builder entry loads and fails at generation because
    `TofuGcpStorageBuilder` cannot emit.
11. **A persistent disk ignores its own zone.** `TofuPdStorageBuilder.module_args`
    emits the runtime's `zone` and never reads `storage.availability_zone`,
    which `validate` checks and section 12a promises pins the resource.
12. **The zone check reads the wrong runtime.** `validate.check_availability_zones`
    resolves a zonal storage's zone against the storage ITEM's `runtime`
    (default: the default runtime) instead of its builder's, so a GCE
    disk with a zone fails unless the item also names the runtime.
13. **`iam_instance_profile` overrides the SSM profile.** In
    `amazon_ebs_source()` the `iam_instance_profile` assignment runs after
    the SSM block, so a runtime that sets both bakes under the wrong
    profile; the fallback `ssm_profile = session_instance_profile or
    iam_instance_profile` implies the reverse was meant.
14. **The OPA listing reads one page.** `opa_gids._listing` returns the
    first page only; with more security policies than one page the
    workload reconcile sees no standing CI policy and creates a duplicate.
15. **The RO group builder inherits every managed-group hook.**
    `OktaTfGroupRoBuilder`'s `query_state` asks OPA for groups it never
    made (a group on it would read `missing [HARD]`),
    `enrollment_token_reference` points into an output the RO root never
    emits, and the read-model records it as managed. Latent: no live or
    fixture RO group builder.
16. **A packer string variable's default is emitted unquoted.**
    `hashicorp.packer_variable` renders `default = 1.0.0` for a string
    default, invalid HCL; only `env_var` and booleans render right (no
    consumer hits it today: the one string variable uses `env_var`, and
    its `default="1.0.0"` is dropped in favour of `env("BASE_IMAGE_VERSION")`,
    empty when unset, while its description promises `1.0.0`).
17. **`state rm` addresses and a failed backup.** `gated_apply_commands`
    ignores `pre_plan_backup=True` when `pre_plan` is empty, so a caller
    that removes state through `pre_commands` gets no backup from the
    flag (the prune step takes its own; no live effect today).
18. **The gcloud runtime calls a bare `gcloud`.** `run_session_command`,
    `inventory`, the pd and GCS scripts call `gcloud` from `PATH`, not the
    binary `cfg/executables.yml` declares and `validate` checks; and
    `run_session_command` ignores `session_mechanism()`, so a runtime
    without `iap` still tunnels through IAP and fails as IAP's problem.
19. **The GCE bake user can mismatch its provisioner.** With a default
    runtime `ssh_username` and an OS-entry `ssh_username`, the packer
    source uses the entry's user and the ansible provisioner user is
    `packer`: the mismatch finding 48 fixed for the other path.
20. **The configuration is loaded with `yaml.unsafe_load`.**
    `global_context.read_and_process` reads every `cfg/` file with
    `unsafe_load`, which constructs arbitrary Python objects from a
    PUBLIC configuration tree; every other reader uses `safe_load`.
21. **A dry run can call the registry.** `launch_params.validate_claimed_hostnames`
    gates on the lifecycle and `apply_instances`, not on the dry-run
    flag, so a dry run with the flag on asks OPA and can refuse on
    silence; its docstring and the manual promised otherwise.
22. **Preflight reads one file name.** `preflight.raw_session_infos` reads
    `cfg/runtime-builders.yml` by that exact name while the loader accepts
    `runtime_builders:` in any `cfg/*.yml`; a runtime declared elsewhere is
    never preflighted and the pre-load expired-session refusal never
    fires for it.
23. **A registry refusal dumps the model.** A duplicate backend name after
    normalisation is refused at load with `Object TofuS3StateBuilderModel(...)
    has no unique 'id' or 'name' field for registry key`, the whole repr
    included, which would print `access_key`/`secret_key` if anyone set
    them. Name the collision and print no repr.

**Dead fields, dead code and misleading messages** (each a line in the
READMEs' "accepted, not read" rows or "When it fails" tables; remove the
field, read it, or fix the message):

- `TofuS3StateBuilderModel`: 24 accepted-not-read fields (`assume_role`,
  `endpoints`, the proxies, `access_key`/`secret_key`, the `skip_*`,
  `use_*_endpoint`, `required_plugins`, `executable`), and
  `skips_credentials_validation` misspelled against terraform's name;
  `TofuVersionChecker` defined and never registered; the three state
  models' `executable` never version-checked; `LocalBackendKind` neither
  refuses nor normalises `.`/`..` segments (`a/../b` and `b` are two
  locations to the collision check) and renders `//ws.tfstate` for
  `path: /`; `GcsStateBuilderModel.__post_init__`'s dead `None` guard;
  the backend kinds render a `Decrypted` setting in clear (only the
  plaintext guard catches it); `Registry.get_instance_by_name_or_alias`
  never reads the alias table (a state backend's alias cannot be bound).
- `AwsCloudBuilderModel.ena_support`/`sriov_support` read nowhere;
  `security_group_ids` validated, counted, never emitted;
  `update_networking` never checks `subnets[].subnet_id` against the VPC;
  `aws_utils.remap_for_image_query` mutates the model's own `query`,
  `query_image`'s docstring documents keys it does not implement and its
  trailing `raise` is unreachable, `_query_by_ami_id`, `_query_by_name`,
  `_build_ami_filters`, `get_ami_ssh_user` (ignores the profile) and
  `remap_for_aws` unused; `query_provider_image`'s "Could not get owner"
  branch unreachable.
- `gcp_runtime_builders.query_images(series)` ignores `series`;
  `update_networking`'s warning names a key-file path no field can
  reach; `GCP_CLI`, `get_image_ssh_user` and the stray
  `DummyGroupBuilderModel` copies in BOTH runtime model modules dead;
  `gce_label` does not force a leading letter (a tag key `2024` fails at
  apply); the pd scripts embed the literal `None` for a missing
  `project_id`/`zone` instead of refusing at generation.
- `default-os-plugin`: the entry's `image_id`, `image_name`,
  `default_primary_disk_size`, `config` and `RhelOsBuilderModel.subscription_id`
  read nowhere; `Apt`/`Fedora` `get_command_to_update()` unreachable from
  the bake (`test_os_update_hook` pins a form no bake emits); the rhel
  8/9/10 check runs only when commands are generated (`policy: none` with
  an unsupported major is never refused); `OsBuilderModel.__post_init__`'s
  duplicate message names the wrong field; an unreachable branch in
  `generate_resolved_image`; the `UBUNTU_TYPE` service order; `debian_type`
  without `kw_only`; apt commands without `DPkg::Lock::Timeout`;
  `OsBuilderModel.update` typed `dict | None` makes
  `UpdatePolicy.from_config`'s bare-name branch dead.
- `packer-plugin`: `PackerEbsImageBuilder.generate_items_before` computes
  `super_items` and drops it; `PackerImageBuilder.generate_items_during`
  names `.pkl.hcl`; `gen_packer.py` dead (the only reader of
  `Image.variables`); `PACKER_EBS` redefined; `image_to_source` fetches
  the subconfig twice; `ImageBuilderModel.default_machine_type` read by
  nothing.
- `ansible-plugin`: `from zipfile import Path` as an annotation; HCL
  strings unescaped (a `"` in `extra_arguments`, `ansible_connection` or
  a path breaks packer); a missing relative playbook emitted silently;
  `configuration_user` unread; `helpers.py` empty; the orchestrator
  leaves an item a dict when no mod builder is default and the packer
  builder then raises `AttributeError` instead of a named refusal.
- `bash-mod-plugin`: `extra_arguments`/`configuration_user` unread;
  `get_target_deferred_type_by_VCT` no caller; `helpers.py` empty; the
  on-image `inline.sh` carries `script` lines only, never `ensure` lines
  (`csis-mods rerun` does not re-apply the declarative form).
- `okta-opa-plugin`: `okta_tf_workspace.finalize` cites a "credentials
  runbook in PLAN.md" that no longer exists; `_require_tfvar` is a bare
  `assert` (stripped under `-O`) and runs at load; `retire_server` matches
  `"404"` by string; `api_host` metadata says required with a default;
  `query_existing_users` an empty seam.
- `tf-ebs-instance-plugin`: `TofuS3StorageBuilder._lookup` reads the
  builder's `bucket_name`, never the storage's (two S3 storages on one
  builder report the same bucket); the instance builder's
  `pre_`/`post_finalize_phase` ignore root scope (under `--only-runtime`
  with `apply_instances: true` another runtime's builder binds pins and
  writes tfvars for a root that emitted nothing); the S3 builder's type
  parameter; `_aws_cli_flags`' dead fallback to `rtb.model.profile`.
- `hashicorp-utils`: `QString.__new__`'s dead `quoted=False`;
  `roots.terraform_commands`' unreachable `ValueError`.
- `base`: `Instance.__post_init__` warns that an instance without `image`
  "will be ignored" while `finalize()` then refuses it; `ExecutableModel.execute`
  builds a command list and discards it; `sleep_before_finalization` and
  the model's `dateformat` default read by nothing that runs.
- `system`: `encrypt`/`reencrypt` call `recipients_from_config` and
  `identities_from_env` outside their `try` (a traceback instead of the
  message); `--only-providers` help says "comma-separated" for a value
  never split; `--force` is stored and read by nothing;
  `preflight.raw_session_lines`' `(minutes_left or 1) <= 0` misses exactly
  `0.0`; `Registry.get_builder()` has no callers (the template's
  `builders_for_models` map is decorative); root `pyproject.toml` lists a
  `packages/dummy-plugin/tests` path that does not exist.
- `dummy-plugin`: `type = DUMMY` class attribute inert; docstrings name
  attributes that do not exist; `key`/`secret`/`api_host`/`org`/`team`
  read nowhere; the user builder emits `Dummy-tf/dummy_users.tf` beside
  the other builders' directories.

**Records**: one branch per group of related items, each squash-merged and
kept; the READMEs' "accepted, not read" rows and "When it fails" tables
are updated in the same commits (the rolling documentation stage owes
nothing for a change the READMEs already track). Golden byte-identical
except where an item changes the emission by design; bar green; every
"likely to bite" item proved by a test that fails before the fix.
