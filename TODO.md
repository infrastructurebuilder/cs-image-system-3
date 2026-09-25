# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **§63 (what the documentation stage found in the code), in progress since 2026-09-24**.

Open stages and their order (revised 2026-09-22, when §59 landed):
**§64**, the release that carries everything a configuration repository
needs and the reference configuration standing alone, and **§63**, the
code defects the documentation found, both planned and waiting on the
operator's word; then **§65**, walking the daily driver from a fresh repository
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
- §30 (the contract package), §64, §65 and §66 are planned, not started; §63
  is in progress since 2026-09-24;
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

## 63. What the documentation stage found in the code

**Status: IN PROGRESS since 2026-09-24** (the operator: "we are now working
on stage 63"; the low-hanging group landed the same day, the medium items
on 2026-09-25; the chains are open). Written during §62 (2026-09-23) under the rule that a
documentation stage changes no code: every item below was found by an
agent reading a package against its README, the manuals and the fixture,
verified in the code, and left as it was. The manuals now say what the
code DOES, with "a code stage names the fix" where the doing is wrong.
This is that stage. An open item is not proved live until its stage
lands; each names the file and function so the fix can be judged before
it is made.

**How the list is ordered** (2026-09-24). Three groups. First the
**low-hanging fruit** (landed): each item was one function and one test,
touching nothing another item touched. Then the **medium items** (landed),
independent of each other but each a small design (a decision to make, a
validation model to write, an API to read). Then the **chains**, where one item's fix decides
another's: those are listed in the order they must be made, with the
dependency named. The dead fields, dead code and misleading messages come
last and follow the same rule: an entry that depends on a chain says so.

**Low-hanging fruit: LANDED** as `720be3a` on develop (2026-09-24, squash of
`feature/defects-low-hanging`, kept). Items 1 to 13 are gone from this
list; the squash message carries them one by one. Each landed with a
test in `tests/test_v2_defects_low_hanging.py` and its README row; items
2, 11, 12 and 13 were proved against the live configuration and item 7 by
a full GCE cycle (run `2026_09_24t12_01_15_155175`, ended empty). The
numbering below keeps its gaps on purpose: the chains and the dead-code
entries cite items by number.

**Medium items: LANDED 2026-09-25** as two squashes on develop, both
branches kept: `e2b40be` (`feature/defect-loading`, items 15, 16, 18, 19)
and `5e920c9` (`feature/defect-gcp`, items 14 and 17). Items 14 to 19 are
gone from this list; the squash messages carry them one by one. Tests
are in `tests/test_v2_defects_loading.py` and `tests/test_v2_defects_gcp.py`.
Items 14 and 17 were proved by a full GCE cycle (run
`2026_09_25t11_28_31_278610`: state query unavailable 0, `gce-test`
verified over the declared gcloud, ended empty). The bar was run on the
two combined (1098 passed).

**Chains, in the order they must be made** (DECIDED 2026-09-25, the
operator by quiz; 20 and 21 needed no decision, each has one fix):

20. **The zone check reads the wrong runtime.** `validate.check_availability_zones`
    resolves a zonal storage's zone against the storage ITEM's `runtime`
    (default: the default runtime) instead of its builder's, so a GCE
    disk with a zone fails unless the item also names the runtime. Read
    the builder's runtime, as every other reader does. Before 21: the
    test for 21 declares a zoned disk on a non-default runtime without
    naming it on the item.
21. **A persistent disk ignores its own zone.** After 20.
    `TofuPdStorageBuilder.module_args` emits the runtime's `zone` and never
    reads `storage.availability_zone`, which `validate` checks and section
    12a promises pins the resource. Emit the storage's zone when declared,
    the runtime's otherwise, as the EBS builder does; the golden moves if
    the fixture's pd declares one.
22. **A runtime's `default_owners` and `default_config_username` are
    unreachable.** `os_builder_runtime_config.get_owners()` and
    `finalize()` look the runtime up by `self.image_builder` (an
    image-builder name) in the RUNTIME namespace and never find it; the
    `finalize()` itself has no caller, so `config_username` and the "ssh
    user could not be inferred" refusal never run either. DECIDE first
    (USER): do the three fields live or die? If they live, the lookup keys
    the runtime by the entry's runtime, the finalize is called from the
    OS builder's own finalize, and ONE function resolves the bake user
    (entry `ssh_username`, else `config_username`, else the runtime's
    `default_config_username`, else the family's user) for every reader.
    If they die, the fields are removed and the family user is the only
    fallback. Before 23 and before the default-os entries below.
    **Decided (USER, 2026-09-25):** all three fields LIVE.
    `config_username` and `default_config_username` feed ONE resolver
    (the order under item 23's decision), `finalize()` gets its caller, and
    the "ssh user could not be inferred" refusal fires. `default_owners`
    lives too (not the recommendation): the owners lookup keys the runtime
    by the entry's runtime, and the runtime's owners join the entry's in
    the AWS image query, deduplicated. The complete example's comments
    ("accepted; not read") change to what each field does.
23. **The GCE bake user can mismatch its provisioner.** After 22. With a
    default runtime `ssh_username` and an OS-entry `ssh_username`, the
    packer source uses the entry's user and the ansible provisioner user
    is `packer`: the mismatch finding 48 fixed for the other path. Both
    the source and the provisioner call the one resolver 22 leaves.
    **Decided (USER, 2026-09-25):** the OS runtime entry's `ssh_username`
    wins everywhere, AWS and GCE alike (not the recommendation, which kept
    the runtime's winning on GCE). The resolver's order, then: the entry's
    `ssh_username`, the OS builder's `config_username`, the runtime's
    `ssh_username`, the runtime's `default_config_username`, the family's
    user (`packer` on GCE, where googlecompute has no vendor default).
    Finding 43 (one bake user per GCE chain) moves to `validate`: a GCE
    chain whose images resolve to different users is refused, naming the
    images and the users. The live tree already declares `ssh_username:
    packer` on the GCE entry, so it resolves unchanged.

**Dead fields, dead code and misleading messages** (each a line in the
READMEs' "accepted, not read" rows or "When it fails" tables; remove the
field, read it, or fix the message; every entry independent unless it
names a chain):

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
- `default-os-plugin` (after chain item 22, which decides the user
  fields): the entry's `image_id`, `image_name`,
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
  builder then raises `AttributeError` instead of a named refusal (the
  same orchestrator lines medium item 15 changed; it landed 2026-09-25).
- `bash-mod-plugin`: `extra_arguments`/`configuration_user` unread;
  `get_target_deferred_type_by_VCT` no caller; `helpers.py` empty; the
  on-image `inline.sh` carries `script` lines only, never `ensure` lines
  (`csis-mods rerun` does not re-apply the declarative form; the ensure
  model medium item 16 validates, landed 2026-09-25).
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

**Records**: the low-hanging group landed on one branch,
`feature/defects-low-hanging`, one commit per item, squash-merged and kept;
each medium item and each
chain on a branch of its own (`feature/defect-<subject>`), kept; the
READMEs' "accepted, not read" rows and "When it fails" tables and the
manuals' "a code stage names the fix" clauses are updated in the same
commits (the rolling documentation stage owes nothing for a change the
READMEs already track). Golden byte-identical except where an item says
it moves; bar green; every item in the first three groups proved by a
test that fails before the fix.

## 64. The release is the whole system: modules, scripts, starter trees, and a configuration repository that stands alone

**Status: PLANNED, not started.** Written 2026-09-23 during the daily
driver's second pass (`feature/daily-driver-redux`), when the operator
corrected the model: a team INSTALLS a release and OWNS a configuration
repository with its own Justfile and CI; this repository is where the
system is developed, not something a user clones beside their tree. The
documentation now says so, and the three example trees under
`docs/examples/` are whole repositories a team copies (Justfile, workflow,
hook, scripts, modules). What the documentation cannot do is make the
release carry those parts, or move the reference deployment onto that
model; both are code, and this is that stage.

1. **The release ships what a configuration repository needs.** The
   `tfmodules/` tree and the three helper scripts (`with-tofu-lock`,
   `opa-workload-token`, `normalise-emission`) become package data of the
   `system` package (or a package of their own), and a command
   `cs-image-system init-config <dir> [--from standard-aws|standard-gce|complete]`
   scaffolds a configuration repository from a starter tree carried in
   the release: the tree, `module_source_base: tfmodules`, the hook, the
   workflow, `.gitignore`, a `.csis-version` pinned to the running
   release. The example trees in `docs/examples/` become the SOURCE the
   release is built from, and `tests/test_docs_examples.py` keeps them
   equal to what the release carries.
2. **The helper scripts become commands** where a script exists only to
   wrap the CLI: `with-tofu-lock` as `cs-image-system --locked ...` (or a
   `lock` subcommand), `normalise-emission` as `config-drift`'s own
   normaliser, `opa-workload-token` as `workload token`. The starter
   Justfile then calls the CLI alone and carries no scripts.
3. **The reference configuration stands alone.** `cs-image-system-testconfig`
   gains its Justfile, workflow, hook, modules and `.csis-version` from
   `init-config` (item 1), its `module_source_base` moves to its own
   `tfmodules`, and its CI performs there: the `live` and `perform` jobs
   leave this repository's workflow, which keeps `verify` and `publish`
   and a `live` leg that only proves the fixture. Proved live: the
   sibling's `verify` job green on a push, its `live` job green with the
   secrets moved over, one performing run on `main` there, the login
   proof as a workload from that repository.
4. **This repository's Justfile shrinks to the developer's**: the five
   contract targets, the bar, the golden, the release recipe, and `just
   cli ...` against the reference configuration for the system's own live
   proofs; the cycle recipes (`cloud-*`, `ci-login-proof`, `sft-install`)
   move to the starter Justfile alone, since a team runs them from its
   own repository.
5. **Records**: DAILY_DRIVER.md section 1.9 loses its "until a release
   ships them" clause; OPERATIONS sections 2 and 3 describe the two
   workflows; the root README's layout paragraph says the reference
   configuration is checked out beside this repository for the system's
   own proofs only. A live proof of `init-config` on a fresh machine with
   nothing but `uv`: install, scaffold, `just init`, `just validate`
   against a real account.

**Sizing**: item 1 a day (package data, the command, the tests); item 2
half a day; item 3 a day with the live proofs, most of it CI secrets and
the first performing run; item 4 an hour.

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
are code go to §63 or §64 as items, never made here (a documentation stage
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
   and the finding goes to §63 with the plugin named. GCP is the
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
   §63 or §64, and the log itself is the stage's evidence in the squash
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
