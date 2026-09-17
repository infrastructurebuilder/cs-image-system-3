# TODO

Execution worksheet: the stages of work in flight, one section per stage.
A section is removed when its stage lands, and the squash commit that
lands it is the record; how the system got here lives in git history and
in the frozen [docs/history/](docs/history/README.md). Steps marked
**USER** need the operator: a decision, or a console or IAM action the
system must not take itself.

Current stage: **none in progress**.

Open stages and their order: §45, which makes CI perform rather than only
record and needs a generation fix first; §41, §43 and §46 whenever
convenient (§46 is correctness work on state isolation and pairs naturally
with §43); §47, state backends beyond S3, follows §46; §19 and §30 wait on
the operator's decisions.

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
- The release publish target is the tag until §41.
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

1. **USER — the model**: which one first (the groups are named for them:
   coops, stofs, secofs, tcmet); what its image must contain (packages,
   model source or binaries, data paths); what "correct" means as tests
   (a smoke run of the model, expected files and services); who its users
   are (the group's members); the instance size and the standing hours it
   may cost on the AWS account; its storage (the existing `mnt_data` /
   `efs-storage` / bucket, or new declarations).
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

## 41. Releases publish to an index through `uv publish`

**Why**: `just release <version>` ends at an annotated tag and `dist/`
(the fourteen workspace packages, `uv build --all-packages`); its publish
leg exists but runs only with `UV_PUBLISH_URL` set, which nobody sets —
§39.2 decided 2026-09-15 that the tag is the release until this stage. A
tag is a source of truth, not a distribution: a second operator, CI, or a
plugin author writing against §30's contract installs from an index, and
a published version is immutable in a way a tag is not. This stage picks
the index and makes the leg real, at the endpoint `uv publish
--publish-url` (`UV_PUBLISH_URL`) takes. It depends on no other stage; if
the index is PyPI it follows §40.

1. **USER — the index.** Two shapes fit the endpoint: (a) **AWS
   CodeArtifact**, a PyPI-format repository in the account already in
   use — free tier 2 GB stored and 100k requests a month, cents beyond;
   authenticated with `aws codeartifact get-authorization-token` (twelve
   hours), so the operator's SSO session and CI's federated role both
   reach it with no long-lived secret; usable while the repositories are
   private and after — the recommendation. (b) **PyPI** once the
   repositories are public (§40), with trusted publishing from GitHub
   Actions (OIDC, no token at all; the fourteen `cs-image-system-*` names
   must be free there). GCP Artifact Registry is out by the GCP decision.
   For (a): one domain, one repository, and an external connection to
   `pypi` so a consumer resolves the packages' dependencies from the same
   index (otherwise `--extra-index-url`).
2. **A `publish` recipe, split out of `release`**: `just publish <version>`
   uploads `dist/` for that version only (`dist/` is cleaned before
   `just build` — today `uv publish dist/*` would upload every stale
   wheel left from an earlier version), with `--check-url` so a re-run
   after a partial failure skips what is already there; the index URL is
   the Justfile's default (`publish_url := env("UV_PUBLISH_URL", "<the
   decided index>")`), the credential comes from the environment
   (`UV_PUBLISH_TOKEN`, or for CodeArtifact `UV_PUBLISH_USERNAME=aws` and
   the token as `UV_PUBLISH_PASSWORD`) and is never in the Justfile.
3. **`release` publishes, and cannot half-release**: the credential and
   the index are probed BEFORE the version bump (today the publish leg is
   the last step, after the commit and the tag, so a failure there leaves
   a tagged, unpublished release); with them present `release` ends with
   `just publish`, without them it refuses up front — the SKIPPED path
   goes, since the target is decided. The contract test's needles
   (`tests/test_v2_justfile_contract.py:66`: `uv publish`,
   `UV_PUBLISH_URL`, `SKIPPED`) follow.
4. **CI publishes the tag**: a `publish` job in `.github/workflows/ci.yml`
   on `push` of a `v*` tag — `just init`, the federated identity (the
   read-only AWS role gains `codeartifact:GetAuthorizationToken`,
   `codeartifact:PublishPackageVersion` and `codeartifact:ReadFromRepository`
   on that one repository; or PyPI's trusted publisher), `just publish
   <tag>`. The operator's flow stays `just release <v>` then `git push
   --follow-tags`; the push is what publishes, and a local publish is the
   fallback when CI cannot. The workflow test pins that only this job
   runs `uv publish` and only on a tag.
5. **Consumers**: the index declared for installs in the root
   `pyproject.toml` (`[[tool.uv.index]]`, credentials via
   `UV_INDEX_<NAME>_USERNAME`/`_PASSWORD`), and OPERATIONS gains
   "installing a release": the two commands a stranger with access needs.
   Proof from a clean virtualenv on a machine that is not the operator's:
   `uv pip install --index-url <index> cs-image-system-system==<version>`,
   then `cs-image-system --help` and `cs-image-system decrypt` run.
6. **USER — the first version**: every package is `0.1.0` today and
   nothing has been published; the first `just release` after this stage
   publishes a version that can never be replaced, so it runs after a
   green `full-test` with docker (the recipe requires it) and on a clean
   live configuration.
7. Records: ledger; OPERATIONS "CI shape" (the fourth job) and the release
   paragraph; §16's open item closed for good. Feature branch
   `feature/publish-index`, squash-merged, kept. A day, plus the USER
   decision; the CodeArtifact setup is a dozen CLI commands.

## 43. Hygiene bundle II: the small things noted since §39

**Why**: each of these was found while doing something else between
2026-09-15 and 2026-09-16 and left alone because it was not that stage's
business. None is large; together they are a day. Each item lands with
its own proof, in one branch, and the golden may move where an item says
so. Whenever convenient; nothing else waits on it.

1. **A run commits no run-local file.** The live configuration tracks
   `generated/run-summary.json` and `generated/state-report.json` (four
   run-local files in all; `meta-state/runs.yaml` and
   `generated/final_execution.sh` are records and stay). The strict query
   rewrites the report outside any run, so every `just cloud-preflight`
   dirties the checkout and `publish-tree` rightly refuses it (found in
   §40.2). The run's commit pathspecs exclude the two files, the emitted
   ignore policy names them, and one dry `--commit` run removes them from
   the sibling's index (pushed). Proof: `just cloud-preflight` leaves
   `git status` clean; config-drift current.
2. **A modification that declares only `config:` is refused.** Two
   fixture and live items (`dask-setup2`, `data-science-workstation-two`
   on `imgfile-basic-dask-two`) carry config keys and no playbook or
   script; the ansible builder emits one provisioner per playbook, so they
   render nothing and only log a warning, while lineage, the on-image
   bundle and the modification tests all record them as present. Decision
   (recommended): a modification item with neither `playbooks` nor
   `script`/`scripts`/`ensure` fails validation with a message that names
   the item; the two items either gain a playbook that reads their config
   keys as variables or are deleted along with the two "stage 22.4
   REMOVED" comments beside them. **USER** chooses; either way a test pins
   the refusal, and the golden moves if the fixture's items change.
3. **The unused placeholder backend goes.** `cfg/state-backends.yml`
   declares `s3-east1` on `my-east1-tfstate-bucket` in both trees; no
   workspace binds to it and nothing references it. **USER** confirms it is
   a placeholder; then it is removed from both trees (the golden should not
   move: no workspace emits it).
4. **The looser `ci` recipe goes.** `just ci` (pyright non-blocking) is
   referenced by nothing since CI runs `just verify`, and the standing rule
   says such a target must not be the bar. Removed, with the contract test
   asserting it stays gone.
5. **Warnings the bar and the CLI print for no one**: pyright's
   `orchestrator.py:515` (a `@staticmethod` declared with `cls` — make it a
   classmethod or drop the parameter); the FK warning `golden-regen`
   prints for `gcloud-east1` against `os_builder_model` (a runtime name
   where an OS builder is expected in the fixture, or a wrong FK target —
   find which and fix it; the golden may move); `validate`'s per-tool "No
   valid version checker class found" and per-provider "No executable
   specified" lines (either implement the checkers the executables file
   promises or collapse them to one INFO line). Proof: the bar and
   `just cli validate` print none of them.
6. **One tofu process at a time, by construction.** A sibling run that
   overlapped the bar's tests failed on the shared plugin cache (ledger
   93). The suite's real-tofu tests use a private `TF_PLUGIN_CACHE_DIR`
   under their temporary directory, so the bar never contends with an
   operator's run; the tofu-using recipes (`config-drift`, `v2-dry-run`,
   `cloud-*`, `gce-*`) take a simple lock directory under
   `.tofu-plugin-cache/` and refuse with a clear message when another holds
   it. Proof: two concurrent `just config-drift` invocations, one refuses.
7. **CLI help that lags behaviour.** `--only-runtime`'s help names the
   bake surface only; the operating record says it has scoped the
   terraform roots too since 2026-09-10. Read the code, make the help say
   what the flag does, and add the missing test if the record is right.
   While there, every option's help is read once against its behaviour.
8. **`publish-tree` builds a tree with the wrong git identity.** The
   recipe's `git init` in a fresh directory takes the GLOBAL git identity,
   not the source repository's, so the tree's single commit can carry an
   address the operator does not push with. GitHub refused the first
   publication push for exactly that, and the commit had to be
   re-authored by hand. The recipe reads `user.name` and `user.email`
   from the source repository (falling back to the global values) and
   writes them into the new repository before committing; its test pins
   that a source repository with a distinctive `user.email` produces a
   commit carrying it.
9. **USER — the read-only GCP service account cannot describe the GCS
   bucket**, so every state query reports `storages/gcp-gcs` unavailable.
   It is the GCP twin of a gap already fixed on AWS, where the role was
   missing `s3:GetBucketTagging` and `s3:GetLifecycleConfiguration`: a
   missing read permission, not a real drift. The fix is one grant of a
   bucket-read role to `csis-github-readonly@csis-sandbox`; it is free and
   read-only, but it is a GCP change, so it waits on the operator's word
   under the standing rule.
10. **A secret that exists but is empty reads as absent, and the job
   passes.** The `live` job skipped every step across three runs on the
   published repository and reported success each time, because
   `OKTA_API_PRIVATE_KEY` had been set from a checkout where the file
   `.envrc` reads it from was missing: the secret existed and its value
   was the empty string. The gate is right to skip when nothing is
   configured, but it cannot tell that from configured-and-broken, and a
   reader of the job's conclusion cannot either. The `apply` job now
   fails rather than skips when a real run is asked for, and the same
   distinction belongs in `live`: a gate item whose secret exists but is
   empty is a failure, not an absence. While here, make `just preflight`
   report the same way, and never read a job's conclusion as proof that
   its steps ran.
11. Records by whatever convention is current when this lands. Feature
   branch `feature/hygiene-two`, squash-merged, kept. A day.

## 45. CI performs on `main`

**Why**: §37 records but does not perform, because generation prunes
whatever a run does not emit, so only a full run may be committed, and a
full REAL run would bake on every runtime including one CI must never
write to. Fixing the pruning is what lets CI bake, release and dispose
under a scope, which is the operator's original "main applies".

1. **The prerequisite: a scoped run stops deleting out-of-scope
   emission.** Generation prunes `generated/` to what the current run
   emitted. It should prune only within the scope the run was given, so
   that `run --all --only-runtime aws-east2-runtime` leaves the GCE roots
   exactly as committed. Decide whether that is a property of generation
   or of the commit (the run could stage only the paths it emitted), and
   pin it with a test that a scoped run followed by `--commit` deletes
   nothing.
2. **Then the job performs**: `--no-dry-run --commit` under
   `--only-runtime aws-east2-runtime`, with `AWS_APPLY_ROLE_ARN` and the
   Okta triple, which already exist. The write role trusts
   `ref:refs/heads/main` alone and carries the bake's EC2 and image
   actions plus read/write on this configuration's state prefix, and
   nothing else.
3. **The GCE runtime stays out of CI** by the cost decision, so a GCE
   declaration change must fail the job loudly rather than bake.
4. **Proof**: a dispatch that performs with nothing to do (every image
   current) commits an unchanged emission; then one that has something to
   do, watched, with what it left standing reported.
5. Records by the convention current when it lands. Feature branch
   `feature/ci-perform-on-main`, squash-merged, kept.

## 46. Multiple state backends, used and proven collision-proof

**Why**: the system is already capable of putting each terraform workspace
in its own state location — every terraform builder carries a
`state_configuration` foreign key, the collector binds each workspace
independently, and a `terraform_remote_state` reference resolves the
PRODUCER's backend, so a root in one bucket can read a root in another.
None of it is exercised: two backends are declared, everything resolves to
the default, all nine emitted backend configurations name one bucket, and
no test covers two backends at once. Nothing stops a deployed workspace
being pointed at a different location either, which is the most
destructive thing in this area and gets its own step. Three defects sit in that unexercised
path, each of which would silently share or overwrite state:

- **A rebinding wins silently.** `set_backend` assigns, so a workspace bound
  twice to different backends keeps the last one, with no error.
- **Two workspace names can collapse to one state file.** The object is
  `<key prefix><super_safe_name(workspace)>.tfstate`, and that function
  maps `-` and `.` to `_` and lowercases, so `aws-ebs` and `aws_ebs` both
  write `aws_ebs.tfstate`.
- **Key prefixes are not normalised against each other.** `__post_init__`
  only strips a trailing slash, so `statefiles//x` and `statefiles/x` are
  treated as different locations.

**The rule, as the operator stated it.** A configured provider stores its
state in exactly one location, and no two providers may write the same
state object. A location is the tuple (backend type, bucket, normalised key
prefix, state file name). Two locations collide when that tuple matches
after normalisation, where normalisation collapses repeated slashes and
strips a trailing one. The operator's example, which becomes the test:

| Provider | Declared location | Collides? |
| --- | --- | --- |
| A | `BUCKET1/abc` | no |
| B | `BUCKET2/xyz` | no, different bucket |
| C | `BUCKET1//xyz` | no, and normalises to `BUCKET1/xyz` |
| D | `BUCKET1/xyz` | **yes, with C** |

Collapsing `//` is the conservative reading: S3 would treat those as two
distinct keys, but nothing should depend on that, so the emission
normalises the key as well and the pair is refused.

Scope: only the S3 backend type exists, so this is several S3 locations,
not S3 beside another kind. The live configuration does not change and no
state is migrated: the standing decision keeps its state where it is, and
the placeholder `s3-east1` stays declared and unbound by the operator's
decision.

1. **The location, as a value.**
   1. A `StateLocation` (type, bucket, key prefix, object name) with a
      normalising constructor: collapse repeated slashes, strip leading and
      trailing ones, keep case (S3 keys are case-sensitive), and reject `.`
      and `..` segments.
   2. `BackendRegistration.state_file_path` returns it rather than a
      string, and the emitted `key` uses the normalised prefix, so
      `statefiles//x` can never reach a backend configuration file.
   3. Unit tests over the table above, plus the empty prefix, a prefix with
      no trailing slash, and a prefix that is only slashes.
2. **One location per provider.**
   1. `set_backend` refuses a second binding of the same workspace to a
      different backend, with a message naming the workspace and both
      backends; rebinding to the same one stays a no-op.
   2. **DECIDED — the field is used when provided, and inherited when it is
      not.** `state_configuration` has always meant "this backend, or the
      default defined a level above", so the resolution is a chain: the
      builder's own value when it names a backend, else its runtime's when
      that names one, else the single backend marked `is_default`.
      "Provided" means a value outside the sentinels the loader already
      treats as absent (`OOPS_DEFAULTS`: `default`, `self`, empty, unset) —
      the same set `resolve_backend` keys on today, so the chain is an
      extension of existing behaviour rather than a new rule.
   3. That makes the runtime's field real. It is declared on both runtime
      models and read by nothing, so "everything on this runtime keeps its
      state in that bucket" is a sentence the configuration can already
      write and the system currently ignores. A test covers each rung: a
      builder naming its own backend, a builder inheriting its runtime's,
      and a builder whose runtime is silent too, falling through to the
      default.
3. **Collisions refused at validation**, before anything is emitted.
   1. Compute every bound workspace's `StateLocation` and refuse duplicates
      with a message naming both workspaces and the object they share.
   2. That catches all three defects above: two backends whose bucket and
      normalised prefix match, two workspace names that collapse under
      `super_safe_name`, and `//` against `/`.
   3. The existing guards stay: a backend registered twice with different
      configurations, and more than one `is_default`.
   4. The check runs in `validate` as well as during a run, so a
      configuration error is caught without generating anything.
4. **A bound workspace cannot silently move.** Changing where a deployed
   workspace keeps its state is destructive in a way nothing else here is:
   the new location is empty, so the next plan proposes to create
   everything that already exists, and the old state is stranded with no
   owner and no one watching it.
   1. Each run records every workspace's resolved location in meta-state,
      beside what that workspace has live. The record, not the emission, is
      the memory: `generated/` can be pruned or regenerated, and was seen
      to be during §37.
   2. Validation refuses when a workspace's resolved location differs from
      its recorded one AND the records show live resources for it, naming
      the workspace, both locations and what is deployed. A workspace with
      nothing deployed moves freely, because nothing is at risk; that
      distinction is the whole rule.
   3. **The escape is an operation, not an override.** `--migrate-state
      <workspace>` (repeatable) PERFORMS the move; there is deliberately no
      flag that merely proceeds past the refusal. A bare override would let
      one word do the destructive thing, while a migration flag makes the
      safe path the easy one, and the refusal message names it.
      1. It requires `--no-dry-run`: a dry run never moves state.
      2. The target is named. A blanket form that migrates every rebound
         workspace at once is nearly as dangerous as no guard at all.
      3. **It changes the root's `init`.** Every run emits `-reconfigure`
         today, which means "discard the previous backend record and do NOT
         migrate" — right for every normal run and exactly wrong for this
         one. Under the flag that root inits with `-migrate-state
         -force-copy` instead, which is the whole reason this cannot be a
         documented procedure alone: the flags the system emits actively
         defeat a by-hand migration.
      4. Backup first, verify after. The old state is pulled to a file that
         is kept, the new location must be empty (a non-empty one is
         already a collision and refused), the old state is never deleted
         by this operation, and the move is accepted only when a plan
         against the new location reports no changes. That plan is the real
         proof the state survived.
      5. The migration is recorded in meta-state — from, to, when, and the
         state serial — so the binding record moves with it and the history
         is auditable.
      6. CI never migrates: the recording job is dry, and §45's performing
         job refuses the flag outright.
   4. **Abandoning resources is a different act**, and stays one. When the
      resources are gone or are being given up deliberately, the honest fix
      is to correct the records (the state query's import and forget paths),
      not to bypass the guard. The refusal message says so, because the
      person hitting it usually wants one of these two things and should be
      told which is which.
   5. Tests: rebinding with nothing deployed passes; the same rebinding
      with a live resource recorded is refused; the message names both
      locations and both routes; `--migrate-state` on a dry run is refused;
      a migration run leaves the old state readable, records the move, and
      plans clean at the new location; re-running under the original
      binding is clean.

5. **The cross-backend read, proven.** A consumer workspace in backend A
   referencing a producer in backend B must emit a
   `data "terraform_remote_state"` carrying B's bucket, key and region. The
   code already resolves the producer's backend; a test now holds it, with
   a second test for the explicit `backend_name` override on the reference.
6. **Exercised in the frozen fixture**, so the golden proves it rather than
   a unit test alone.
   1. The fixture declares a second, genuinely used backend — a different
      bucket and prefix — and binds one family of roots to it (the storage
      roots are the natural choice, since instances already read storage
      state across workspaces).
   2. The golden then carries backend configuration files naming two
      different buckets, and at least one remote-state data source pointing
      at the other backend. The golden moves by design.
   3. `tests/test_v2_gate4_identity_storage.py` and the storage tests get
      the one assertion each that the isolation is real.
7. **Documentation.** [docs/CONFIGURATION.md](docs/CONFIGURATION.md)'s
   state-backend section gains the rule, the resolution order and the
   collision examples; [docs/OPERATIONS.md](docs/OPERATIONS.md) gains
   "where state lives", including how to read a workspace's location from
   its `.tfbackend.hcl` and that `use_state_backends` gates the whole
   mechanism.
8. **What this stage does not do**: migrate any live state, create any
   bucket, or add a second backend type. Types beyond S3 are §47, which
   follows this one; the standing decision keeps all LIVE state in S3
   either way.
9. **Acceptance**: the bar green; the golden moved once and reviewed; a
   test for each row of the table; a test that a rebinding raises; a test
   that two workspaces colliding under `super_safe_name` are refused; a
   test that the cross-backend data source names the producer's bucket;
   `just cli validate` on the live tree unchanged and still passing.
   A rebinding of a workspace with live resources is refused and names both
   locations; the same rebinding with nothing deployed passes. Feature
   branch `feature/multi-state-backends`, squash-merged, kept. Three days.

## 47. State backends beyond S3

**Why**: an S3 bucket is not the only place terraform state can live, and
the system currently behaves as though it were. One plugin implements one
type, and the type-agnostic-looking machinery is S3-shaped underneath:
`BackendRegistration` carries `bucket`, `region`, `key_prefix`, `encrypt`,
`use_lockfile` and `profile` as fields; the partial configuration writer
emits exactly those keys; the `terraform_remote_state` data source writes
`bucket`, `key`, `region` and `profile`; and a state object's path is
assumed to be `<key prefix><safe workspace name>.tfstate`. A second type
cannot be added without changing all four. This stage makes the backend
contract genuinely type-agnostic and proves it with two more types.

It follows §46, which proves multiple *locations* of one type and whose
collision rule already keys on the backend type, so the two compose. It
does **not** contradict the standing decision that all live state stays in
the S3 backend: that decision is about where the live configuration's
state lives, and this stage is about what the system can express. No live
state moves.

1. **The backend contract becomes type-agnostic.**
   1. `BackendRegistration` stops being a record of S3 fields. It carries
      what every backend has — `name`, `type`, `is_default` — plus the
      type's own settings as an opaque mapping, and it asks the type for
      two things: the settings a workspace's partial configuration needs,
      and the settings a consumer's remote-state data source needs. Those
      differ: a data source has no `encrypt` or `use_lockfile`.
   2. The state location of a workspace becomes the type's business too,
      because `<prefix><name>.tfstate` is an object-store idea. A local
      backend addresses a path, an azurerm backend a container and a blob.
      §46's `StateLocation` gains the type as its first element, which it
      already has in its collision tuple.
   3. `generate_backend_config` and `generate_remote_state_datasources`
      stop naming S3 keys and render whatever the type returns.
   4. The golden must not move for this step: the S3 type renders exactly
      what it renders today. That is the proof the refactor is faithful.
2. **The S3 type becomes one implementation among others**, moving its
   field knowledge out of the collector and into
   `tf-s3-state-plugin`, where its model already lives.
3. **`local`, the type that needs nothing.** A state file on disk, with a
   `path`. It is worth having for its own sake — a developer or a test can
   run a real `tofu init` with no cloud and no credentials — and it is what
   lets the fixture exercise two types without inventing a second cloud
   account. Fields: `path` (a directory), and the workspace's file within
   it; `workspace_dir` if OpenTofu's convention is wanted.
4. **`gcs`, the obvious second cloud.** Fields: `bucket`, `prefix`,
   optional `credentials` (a path, never a value) and `impersonate_service_account`.
   Declaring the type is not the same as moving the GCE roots onto it: that
   remains the deferred, very-last-priority decision, and nothing in this
   stage binds a GCE root to it. **USER** confirms that reading before the
   type is added, since it is the one place this stage brushes against a
   standing decision.
5. **The shape admits more without this stage adding them**: `azurerm`,
   `http`, `pg`, `kubernetes`, `consul`, `oss`, `cos`. Each is a model plus
   two renderings once step 1 lands, so the next one is a day rather than a
   refactor. Record that in the plugin's README as the recipe.
6. **Proven in the fixture.**
   1. The fixture declares an S3 backend and a `local` backend, and binds
      at least one root to the local one, so the golden carries two
      genuinely different backend types, two differently shaped partial
      configurations, and a remote-state data source pointing across types.
   2. A real-tofu test does `init` against the local backend with no
      credentials at all, which nothing in the suite can do today.
   3. §46's collision check is exercised across types: the same logical
      name under two types is not a collision, and two workspaces on one
      local path are.
7. **Documentation**: [docs/CONFIGURATION.md](docs/CONFIGURATION.md) gains
   a section per type with its fields and an example; the state plugin's
   README gains "adding a backend type" as a recipe;
   [docs/OPERATIONS.md](docs/OPERATIONS.md)'s "where state lives" covers
   more than one kind.
8. **Acceptance**: the golden byte-identical after step 1 and moved once,
   deliberately, after step 6; a `tofu init` against the local backend with
   an empty environment; `just cli validate` unchanged on the live tree;
   the bar green. Feature branches `feature/state-backend-contract` (steps
   1–2) and `feature/state-backend-types` (steps 3–6), each squash-merged
   and kept. Three to four days, most of it step 1.
