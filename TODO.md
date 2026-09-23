# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order (revised 2026-09-22, when §59 landed):
**none but §30**, which waits on the operator's decision, and §61, the open
hygiene bundle. (§59 LANDED 2026-09-22: `meta-state/aliases.txt` is the
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
on none of this. §61 is the open hygiene bundle (V); a new hygiene issue
goes there.

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

## 61. Hygiene bundle V

Non-critical items, each small enough that a stage of its own would be
ceremony. Landed together on `feature/hygiene-v`, squash-merged, kept.
Each item below says, in this order: what is wrong (the exact path), the
evidence, the recommendation, its effects (what the operator sees
afterwards, what changes in the records and in CI, what it risks), and the
decision it needs from the operator, if any. Sizes are honest guesses.
**Decided 2026-09-23**: the operator accepted every recommendation (item 2
shape (a), item 4 shapes (a) and (c)); each item's *Decision* line records
the choice. The bundle is ready to execute on the operator's word.

1. **A group the provider could not be ASKED about is reported as MISSING.**

   *What is wrong.* `OktaTfGroupBuilder.query_state`
   ([okta_opa_tf_group_builder.py](packages/okta-opa-plugin/src/cs_image_system/okta_opa_plugin/okta_opa_tf_group_builder.py),
   the `except Exception` around `resolver.group_attributes`) records
   `{"present": False, "error": "<the exception>"}` for a group whose
   lookup raised -- a 401 from a wrong or lapsed key pair, a network
   failure, a missing `.envrc`. `group_drift` in
   [state_query.py](packages/base/src/cs_image_system/base/state_query.py)
   turns every `present: False` into `missing group <g>: managed group is
   not known to the identity provider [HARD]`. It never looks at the
   `error` key. So an unreachable OPA reads as "every managed group was
   deleted", the strict query exits 1, and every run refuses to start
   (a run refuses on hard drift).

   *Evidence.* 2026-09-21, proving §57: `just full-test` launched without
   `source .envrc` reported all five groups missing; all five stood the
   whole time. The same conflation §57 removed for instances ("cannot
   answer" reported as a state).

   *Recommendation.* In `query_state`, keep the record as it is (it already
   carries the distinction). In `group_drift`, before the `present` check:
   a record with an `error` key is routed to `report.unavailable` as
   `groups/<g>: <error>` and skipped -- the same class `instances/gce-test:
   booted image (runtime … could not answer)` uses. `present: False`
   WITHOUT an error stays `missing [HARD]`. `group_drift` needs the report
   to append to, so its signature gains it (one caller, `query_state`).
   One test: an errored record is unavailable, not drift; a plain absent
   one is still hard.

   *Effects.* A lapsed key pair now prints five `unavailable:` lines naming
   the error (`HTTP 401`, `Connection refused`) instead of five `missing`
   lines; `state query --strict` still exits 1 on it (any class but
   `stale` fails strict), so the cycles still refuse to start, but for the
   stated reason; a plain `run` warns and continues, as it does for an
   unreachable cloud. A real deletion is reported exactly as today. CI's
   `live` job behaves the same (it fails strict either way) but its log
   says why. Risk: none to records; nothing is written. Size: an hour.

   *Decision.* None needed; accepted 2026-09-23.

2. **Preflight's window check, per command, cannot see the number that
   binds.**

   *What is wrong.* Every command that loads the configuration runs the
   session check for itself ([preflight.py](packages/base/src/cs_image_system/base/commands/preflight.py):
   `raw_session_lines`, against `config.preflight.expected_run_minutes`,
   default 30). A run of several legs passes at minute zero and one leg
   refuses at minute fourteen with eleven minutes left. Since the `noaa`
   profile became an `sso-session` profile (2026-09-21 19:19) the cache's
   `expiresAt` is the ACCESS token's one hour, renewed silently, and
   preflight reads it as "present; refreshes itself (no fixed expiry
   readable)": the number that actually ends a run, the portal session's
   end (about 8h from a browser sign-in, less if the CLI token was minted
   mid-session), is written nowhere the system can read.

   *Evidence.* 2026-09-21 16:04Z, a full-test died on its last leg; the
   same day 19:0x a second one was refused with 7 minutes left;
   2026-09-22 19:43Z the portal session ended sixteen minutes before the
   live legs of a green bar ran, and all three failed on "Token has
   expired and refresh failed".

   *What has landed.* The reader half (stage 55 step 4): a refreshable
   token counts as present and never blocks a run on its own. The recipe
   half (stage 59's branch): `just full-test-legs` re-runs the three live
   legs alone, so a lapse after the bar costs ten minutes, not forty.

   *What remains, and the recommendation.* The original ask -- one
   up-front check with the whole estimate -- cannot be honoured for a
   profile that reports no fixed expiry, which the live profile now is.
   Two honest options: (a) close the item as overtaken, keeping only a
   sentence in OPERATIONS that a lapse mid-run is environmental, costs the
   legs, and is repaired by `aws sso login` then `just full-test-legs`;
   or (b) keep a `--needs <minutes>` check for profiles that DO carry a
   fixed expiry (static-key profiles and non-session SSO caches), which
   the live tree does not use. I recommend (a).

   *Effects of (a).* No code; the documentation sentence; the item closes.
   The operator's experience is unchanged from today. *Effects of (b).*
   A flag nobody passes on the live tree; a test; dead weight until a
   fixed-expiry profile returns. Size: (a) minutes; (b) two hours.

   *Decision.* (a), 2026-09-23: the item closes as overtaken with the
   OPERATIONS sentence; no `--needs` flag.

3. **A membership the YAML dropped and OPA already lacks blocks every
   identity plan.**

   *What is wrong.* The oktapam provider's refresh of an
   `oktapam_user_group_attachment` ERRORS (`user "x" is not present within
   group "g"`) instead of dropping the resource from state when the
   membership is gone. The identity root's plan never reaches the point
   where it would have destroyed the attachment, so a group whose YAML
   membership was conformed to what OPA holds by hand cannot be planned
   at all until someone removes the attachment from terraform state by
   hand.

   *Evidence.* 2026-09-22 08:01, the first real identity run after the
   coops declaration was conformed to OPA on 2026-09-18: two stale
   attachments (`coops_user|mykel.alvis`, `coops_admin|zachary.wills`),
   the plan died on both, the repair was a state backup and `tofu state rm`
   of each in the mirror root, done by the operator.

   *Recommendation.* The identity builder already removes state entries
   before the plan for groups that became unmanaged (`_newly_unmanaged_groups`
   feeds `pre_plan` `state rm` lines into `gated_apply_commands`). Extend
   that pre-plan step: for every managed group, every
   `module.group_<g>.oktapam_user_group_attachment.members["<u>"]` and
   `.admins["<u>"]` address whose user the YAML no longer lists AND whom
   OPA no longer holds in that group (`resolver.group_users`, which
   returns None when OPA cannot be asked -- then nothing is removed and
   the plan proceeds as today) gets a `state rm` line before the plan.
   The addresses come from the previous identity read-model (which lists
   members and admins as last applied) minus the declaration, so no state
   read is needed. When OPA STILL holds the membership, nothing is
   removed: the plan shows the destroy and the gate sees it, which is the
   explicit decision the operations rules require. Before the first
   `state rm` of a run, the runner takes the same-day state backup the
   rules ask of a hand edit (`tofu state pull` into the workspace's
   `state-backups/`, gitignored), the way `--migrate-state` backs up
   before it moves.

   *Effects.* The operator conforms a roster to OPA, runs identity, and
   it plans; the run log lists each attachment it dropped from state and
   why. `identity.yaml` is unchanged in shape. Nothing in OPA is written by
   this step. Risk: a `state rm` on a wrong address leaves a real
   attachment unmanaged (not destroyed); the double condition (YAML dropped
   it AND OPA lacks it) and the backup bound that. CI's `live` job never
   plans identity, so it is unaffected; `perform` does not run identity
   either. Size: half a day with tests.

   *Decision.* Accepted 2026-09-23: the automatic `state rm` takes the
   backup first, every time.

4. **A durable instance cannot take its own image's second release without
   a rule being switched off by hand.**

   *What is wrong.* Two rules that are each right on their own deadlock
   for a durable instance. `release` refuses a build until its post-bake
   tests have passed on a launched machine
   ([release.py](packages/base/src/cs_image_system/base/release.py),
   `config.require_image_tests`, default on). `validate_released_pins`
   (same file) refuses EVERY run while any instance is pinned to an
   unreleased build (`config.require_released_builds: true` in the live
   tree). An ephemeral instance resolves this inside one run: launch,
   verify, tear down, release. A durable instance whose volume allows one
   attachment (`mnt_data`) cannot be proved on a proof instance -- the
   image's `post_bake.mounts` names that volume -- so the proof can only
   run on the instance itself, after `upgrade instance` pins it to the
   unreleased build, which the second rule refuses.

   *Evidence.* 2026-09-22, the coops image's second build (stage 19 step
   5): `upgrade instance` then `cloud-launch` refused with `instance
   'coops-model' is pinned to build ami-08b0… which is not a released
   build`; the first release on 2026-09-20 went the same way. The
   procedure that works, written in OPERATIONS "A model image, end to end:
   the second release", sets `require_released_builds: false` in the
   committed configuration for steps 4 to 7 and back to `true` after.

   *Recommendation, three shapes.* (a) **An automatic grace**:
   `validate_released_pins` accepts an unreleased pin when the build is
   the head of the instance image's series on that runtime, its in-bake
   tests passed (lineage records the build only then), and the instance
   is a pending replacement (`meta-state/pins.yaml`
   `pending_replacements`) or was launched from that build in the previous
   run and has no post-bake record yet; the grace ends when the release
   is recorded or after the next run, whichever first, and the refusal
   returns with a message naming the missing proof. (b) **A per-instance
   window** the system flips: `upgrade instance` writes
   `release_window: <build>` beside the pin and `release` clears it; the
   validator honours the window and nothing else. (c) **One recipe**,
   `cloud-upgrade <rt> <instance>`, that runs upgrade, replace, verify and
   release as one gated sequence and relaxes the rule only inside it. I
   recommend (a) plus (c): the grace makes the sequence legal, the recipe
   makes it one command, and the flag in the configuration is never edited
   by hand again.

   *Effects of (a).* The operator runs `upgrade instance`, `cloud-launch`,
   `cloud-verify`, then a release run, with the flag left at `true`
   throughout; a pin that stays unreleased for more than one run is
   refused as today, so the rule still holds. `pins.yaml` gains nothing;
   the grace is computed. Risk: the window between the replace and the
   release is the same one the hand procedure has today; nothing new is
   reachable in it. *Effects of (c).* The eight steps in OPERATIONS become
   one recipe with the same gates inside it; the procedure text shrinks to
   the recipe and its preconditions. Size: (a) half a day; (c) a day;
   (b) half a day.

   *Decision.* (a) plus (c), 2026-09-23: the grace in `validate_released_pins`
   and the `cloud-upgrade <rt> <instance>` recipe; shape (b) is not built.
   Lands before the third release.

5. **The release and retention lifecycles emit an instance root's variable
   file they never run.**

   *What is wrong.* `TofuInstanceBuilder.pre_finalize_phase`
   ([tf_instance_builder.py](packages/tf-ebs-instance-plugin/src/cs_image_system/tf_ebs_instance_plugin/tf_instance_builder.py))
   writes `instances.auto.tfvars` (the resolved AMI id per instance) into
   the builder's `instance-generation` directory of WHATEVER lifecycle is
   finalising the `INSTANCE_GENERATION` phase. The release and retention
   lifecycles both extend that phase with their own one deferred step
   ([release.py](packages/base/src/cs_image_system/base/release.py),
   [retention.py](packages/base/src/cs_image_system/base/retention.py)),
   so the hook fires for them too and writes the file under
   `generated/release/…` and `generated/retention/…`, where no instance
   root exists and nothing reads it. The commit gate refuses every
   `*.tfvars` by pattern (they may carry decrypted values), so the file
   is never staged and stays untracked: after every release run the
   operator sees a stray `??` in the configuration checkout.

   *Evidence.* 2026-09-22, the release run: the run's own warning named
   both files ("never staging generated/release/…/instances.auto.tfvars,
   generated/retention/…"), and `generated/retention/open-tofu/` stayed
   untracked afterwards; its one line is `coops_model_ami_id = "ami-…"`.
   Not a leak (an AMI id), but a file nothing runs.

   *Recommendation.* Guard the hook on the lifecycle: write the file only
   when the lifecycle being finalised is `instance-image` (the context
   knows the running lifecycle; the release and retention runners read
   the pins from meta-state, never from the root). A stale copy under
   `generated/release/` or `generated/retention/` from an older run is
   removed by the next generation of that lifecycle, which wipes its
   directory. One test: a release run over the fixture writes no tfvars
   under `generated/release/`.

   *Effects.* No stray file after a release or retention run; the
   never-staged warning no longer names those two paths; the
   instance-image lifecycle is unchanged. Risk: none; nothing consumed the
   file. Size: an hour.

   *Decision.* None needed; accepted 2026-09-23.
