# TODO

One file per stage in flight, `STAGE-<n>.md` beside this one; this file
holds the open list, the release state, what landed and the standing
decisions. A stage's file is its plan, read and validated by the
operator before its "do N"; a landed stage's file is removed, its
squash commit is the record, and the history is in git and
[docs/history/](../docs/history/README.md). **USER** marks a step only
the operator can take.

Stages from the re-examination of 2026-11-03.
[REEXAMINE4.md](REEXAMINE4.md) digests the three reviews
([REEXAMINE1.md](REEXAMINE1.md), [REEXAMINE2.md](REEXAMINE2.md),
[REEXAMINE3.md](REEXAMINE3.md)); each stage file
([§132](STAGE-132.md); §118 to §131
landed) cites the review section
it answers. The conventions are the ones above: one file per stage; a
stage is a plan until the operator says "do N"; **YOUR DECISION** marks
an operator choice and states the default; **USER** marks a step only
the operator can take; a landed stage's file is removed and its squash
message is the record. Numbering starts at §118. §117 is
reserved by [§116](STAGE-116.md) item 7 (the contract to its own
repository).
§131, from a finding of §120, was the first stage planned after the
review's set; it landed 2026-11-06.

**Scope** (the operator, 2026-11-04): separation of layers,
consolidation of the base classes, and the documentation. Out of
scope for this file: the model image (the purpose; "hygiene before
purpose" stands) and populating the Azure and Google Cloud
repositories.

**Order, and the relation to [§113](STAGE-113.md) to
[§116](STAGE-116.md).** All three reviews find that
[§113](STAGE-113.md)'s closure line is crossed by the imports it claims
to follow (REEXAMINE1 §5.2, REEXAMINE3 §3.1) and that
[§116](STAGE-116.md)'s proof as planned would install the AWS runtime
under the GCE one (REEXAMINE1 §5.3, REEXAMINE3 §3.1 flaw 1). The
proposal: §118 to §125 land before
[§113](STAGE-113.md) is executed, each small and each proved by the
golden; [§113](STAGE-113.md) is then re-planned on the numbers
§124 prints, and §125 absorbs
§114 and §115. **YOUR DECISION:** that
order (the default), or [§113](STAGE-113.md) first as its file plans it.


**Open**

- §118 and §119, the documents, landed 2026-11-04; the rolling
  documentation stage is not open.
- §120 to §125, the six seams, landed 2026-11-04 to 2026-11-05; §125
  absorbed §114 and §115, so the contract holds the run context, its
  services and its own version, and the §30 shims are gone.
- §126, the package shape: landed 2026-11-06 under shape (b), the
  twenty-two projects kept; it re-scoped [§112](STAGE-112.md) (whole)
  and [§116](STAGE-116.md) (the external-repository proof, docker
  first). Its release proof, a development release on TestPyPI, is the
  operator's box.
- §127, loading once, without the cloud: landed 2026-11-06. A load
  reaches no cloud (the networking check is `validate --online` and every
  real run, recorded in `meta-state/runtime-facts.yaml`); one parse; the
  deferred system steps run in process. The reference's record was
  committed on its develop by the operator (6b709d3).
- §128, tests named for behaviour: landed 2026-11-07. Every test file
  is named for the behaviour it pins and a rule test holds it; the
  golden covers docker (148 files).
- §129, the sources stop narrating: landed 2026-11-07. No comment or
  docstring names a stage, a bundle, a finding or a date; a rule test
  holds zero.
- §130, hygiene bundle XXIV: landed 2026-11-07. The lint bar (ruff's
  bugbear, import sorting, a complexity ceiling and unused locals;
  pyright standard over the whole tree), the release family as
  `scripts/release.py`, and twenty other small findings; the contract
  is 0.4.0. Its items 19 and 27 moved to [§132](STAGE-132.md).
- §131, registrations carry their plugin's namespace: landed
  2026-11-06; the contract is 0.2.0 (a minor bump for the new
  `PluginMetadata.namespace` field).
- [§132](STAGE-132.md), hygiene bundle XXV: the open bundle for the
  small findings; opened 2026-11-07 with §130's items 19 and 27 and
  three of its findings. Waits for "do 132".
- [§112](STAGE-112.md), a release in two boxes: planned 2026-11-03; waits for
  "do 112".
- [§113](STAGE-113.md) and [§116](STAGE-116.md), the decomposition that
  remains (the kit and the engine; a runtime installed from outside):
  planned 2026-11-03, §113 re-planned 2026-11-05 on §124's numbers;
  §114 and §115 landed inside §125; each waits for its "do N".
- §110 and §111 are landed and released in 0.1.7.dev1 (TestPyPI,
  2026-11-03); the reference's `develop` and `main` run it. The final
  0.1.7 is not cut.
- Interval checks (the F44 review, the `STARTER_PUSH_TOKEN` renewal)
  live in [REMINDERS.md](../REMINDERS.md).

**Stage files** (one per stage, in this directory; the plan is read
and validated by the operator before its "do N")

- [§112, A release in two boxes](STAGE-112.md)
- [§113, The kit and the engine: `base` splits where the plugins stop](STAGE-113.md)
- [§116, A runtime installed from outside](STAGE-116.md)
- [§132, Hygiene bundle XXV](STAGE-132.md)

**Release**

- 0.1.6, the latest final release: PyPI and TestPyPI, tag `v0.1.6`
  (8ea1dc4), 2026-11-02, the second final release cut from `main` by
  the §107 walk. Carries §103 (the container runtime and its two new
  PyPI projects), §105, §108 and §109. Its tag published the five
  template repositories, the first `standard-docker` one included.
- The reference configuration runs 0.1.6 (take 0f7773d, tag
  `v0.1.6-before` = 084cb6a, CI green on `develop`); it declares the
  runtime `docker-orbstack` on the local OrbStack's context (pushed
  with the take of 0.1.6.dev2, 7bc3802). Its `main` took 0.1.6 on
  2026-11-02 (the operator's push; `perform` green, nothing baked,
  records to 933d6fb).
- 0.1.5, the previous final release: PyPI and TestPyPI, tag `v0.1.5`
  (ff2b776), 2026-10-31, cut straight from 0.1.4 on `develop`. Carries
  §106 (the image-source catalog), §104 (hygiene XX) and the §107 plan.
  Its tag published the four template repositories again.
- The reference configuration ran 0.1.5 until 0.1.6 (take 7a687cd; `basic-rh-10`
  says `family: alma-linux`, f25e967; records to 4caf469). Before its
  `main` moved, `lineage restamp` re-stamped the ten AWS heads and the
  one GCE head and the operator's own `just record` carried the moved
  fingerprints, so CI's guard read `gcloud-east1` as unchanged;
  `perform` green on 2026-10-31, nothing baked. Its tag `v0.1.5-before`
  (b4b982a) marks the state before the move; the release tag is the
  after marker. The hand-written vendor queries stay by the operator's
  choice (the RHEL 9 one pins 9.5, which the catalog's would not).
- The §66 proof was not rerun on 0.1.5; it passed whole on 0.1.3 and
  0.1.4 (a private copy of `standard-aws`, its first push, a dispatched
  dry run, `uv tool install` from PyPI, `just init` naming the release).
- Last development release before 0.1.6: 0.1.6.dev1, TestPyPI, tag `v0.1.6.dev1`
  (6e8a314), 2026-10-31: the §107 proof, the first release cut from
  `main` (fast-forward to `develop`, `just release patch test`, the
  push with tags, CI's bar and tag job green, `develop` fast-forwarded
  back; all four refs at 6e8a314).
- The §66 proof passed whole on 0.1.4 (2026-10-29): a private copy of
  `standard-aws`, its first push and a dispatched dry run green with
  `live` and `perform` SKIPPED, `uv tool install
  cs-image-system==0.1.4` from PyPI (the contract included), and `just
  init` naming the release (`init: cs-image-system 0.1.4 ready against
  ...`, §101). The copy was deleted afterwards.

**Landed since 2026-10-05** (newest first)

- §130, hygiene bundle XXIV: 2026-11-07, its squash commit
  (feature/hygiene-xxiv kept). Twenty-two items landed, each its own
  commit on the branch: the lint bar (ruff gains bugbear, import
  sorting, unused locals and a complexity ceiling of 49, the measured
  maximum; pyright standard over the whole tree, which found one real
  unbound-variable crash); the release family as `scripts/release.py`
  behind one-line recipes, appending its `docs/CHANGES.md` row; the
  meta-state file list whole and its writes atomic; one context
  manager for the working directory; a plugin that fails to import is
  skipped; the entry-point groups name the kind they register; the
  image-source catalog per run; the launch credential's variable is
  `enrollment_token`; the instance roots' storage map from the hooks;
  the narration rule over the workflows and scripts. The contract is
  0.4.0 (two members left `LaunchServiceProtocol`). Three emission
  moves regenerated the golden. Items 9, 11, 18 and 23 closed with no
  commit; items 19 and 27 moved to [§132](STAGE-132.md). The
  reference's item 14 commit (a9d8414, the one `packer` key) waits on
  its develop for the operator's record and push.
- §129, the sources stop narrating: 2026-11-07, its squash commit
  (feature/sources-stop-narrating kept). The comments and docstrings of
  the sources and the tests, the comments of the terraform modules, the
  Justfile, pyproject.toml and the fixture's YAML comments no longer say
  which stage, bundle, finding or date produced them: each token became
  the behaviour's name or went, ten decisions cite a `docs/CHANGES.md`
  anchor, DESIGN page references stay, and a test module keeps one
  closing `history:` line. `tests/test_sources_do_not_narrate.py` holds
  zero over six areas (the IAM policy's dated `Version` literal and the
  fixture's four hashed modification files excepted). Only comments
  changed (an AST comparison proves it); the golden is byte-identical.
  Carried the two develop CI fixes of the day (typer's colour under
  GitHub Actions; the live leg binds the fixture's docker context to the
  machine's daemon).
- §128, tests named for behaviour: 2026-11-07, its squash commit
  (feature/tests-named-for-behaviour kept). The fifty-two test files
  named after a stage, a bundle, a gate, a defect list or an exploration
  were regrouped into behaviour-named files, the `v2_` prefix left every
  test file but the golden's, the support module became
  `tests/harness.py`, and `tests/test_tests_named_for_behaviour.py`
  holds the rule. Prose pins fell from 185 sentence and 93 document pins
  to 37 and 27, with a ceiling test that only lets them fall. The
  fixture declares a docker runtime, so the golden covers the four
  docker roots (148 files, re-frozen once); `golden-regen` works again.
  The five parity tests PARITY.md promised exist; every package has a
  test; the `v2-test` recipe is retired. 2070 passed, 29 skipped; 2099
  collected.
- §127, loading once, without the cloud: 2026-11-06, its squash commit
  (feature/loading-once-without-the-cloud kept). The cloud runtime
  models' `finalize()` is pure; two optional builder hooks check the
  networking online (`validate --online`, every real run) and adopt the
  recorded `meta-state/runtime-facts.yaml` offline; the raw preflight
  readers are gone (preflight loads). Each `cfg/*.yml` is parsed once and
  the string stage walks the tree; unresolved foreign keys ride on the
  context. One executor runs the deferred `cs-image-system` steps in the
  running process through `base/in_process.py`; the Finalizer's mirror
  wrapper is gone. `validate` fell from ~20 s to ~5.7 s.
- §126, the package shape: 2026-11-06, its squash commit
  (feature/stage-126-package-shape kept). Each plugin's terraform
  modules are package data inside its wheel, declared by the entry
  point group `cs_image_system.modules` (contract 0.3.0); the root
  `tfmodules/` and the starters' copies are gone; `base.modules`
  materialises them with a `.csis-module` stamp, `init-config` never
  overwrites an edited copy, and `config: module_sources` overrides
  one module. The umbrella installs no runtime: `[aws]`, `[gcloud]`,
  `[docker]`, `[okta]`, `[all]`; dummy-plugin and
  contract-example-plugin are workspace-only (twenty projects
  published); `validate` names the extra a missing plugin needs, from
  the umbrella's own table (`src/cs_image_system/extras.py`); a tree's
  Justfile reads its extras from its `type:` words. The starters are
  one skeleton (`docs/examples/_skeleton`) and five overlays, rendered
  by `starters.write_starter`. The docker legs follow the docker
  command's active context. Finding: hygiene XXIV item 24.
- §131, registrations carry their plugin's namespace: 2026-11-06, its
  squash commit (feature/stage-131-registration-namespaces kept).
  Every registration is keyed by classification, namespace and name;
  the namespace derives from the plugin's distribution name
  (`aws-runtime`, `tf-ebs-instance`, the core's `base`) unless
  `PluginMetadata.namespace` names one. A same-key, different-class
  collision is refused for models, services, injected models and
  builders; one class under several namespaces is one registration.
  A bare `type:` word resolves when one class answers; when several
  do, `validate` names every qualified form (`<namespace>/<name>`).
  Nothing recorded moved. Contract 0.2.0; 23 tests in
  `tests/test_registration_namespaces.py`.
- §125, the contract's surface, its services and its version:
  2026-11-05, its squash commit (feature/stage-125-contract-surface
  kept); absorbed §114 and §115. The run context is the contract's
  (`RunContextProtocol`, `MetaStateProtocol`, thirteen services reached
  as `ctx.services`); a plugin imports from the core only its base
  classes, models and the two metadata abstractions
  (`tests/test_plugin_imports.py`, four exceptions with reasons); the
  vocabulary, the hooks entry point, the bootstrap facts protocol and
  the enrollment registry are contract modules; the §30 shims are
  deleted and the weekly reminder retired; the contract is versioned
  0.1.0 on its own (0.x until the operator decides), dependents pin
  `>=0.1,<0.2`, the release bump excludes it; 64 kit-internal members
  left the protocols and conformance is checked when the plugins are
  discovered.
- §124, the run context and the engine part ways: 2026-11-05, its
  squash commit (feature/stage-124-run-context kept). The context is
  what a run knows (`run_context.py`); the loader (`config_loader.py`)
  makes one per load and binds every builder to it; the finalizer
  (`finalizer.py`) owns the deferred commands; the context and the
  registry are no singletons (one registry per run, `ctx.reg`); the
  old name stays one release as a shim. The lazy-import web is gone
  where no cycle needs it (core function-local imports 137 to 13) and
  `tests/test_import_closure.py` holds the import-graph ceilings;
  §113 is re-planned on the honest closure (plugins reach 118 of 138
  core modules, 20 are engine-only, four doors). Found on the way: a
  model copy cloned the whole run through the bound context (cured
  by identity on copy), and thirteen tests patched names where they
  are defined rather than read.
- §123, hashicorp-utils stops reaching back: 2026-11-05, its squash
  commit (feature/stage-123-hashicorp-utils-leaf kept). The library
  imports only the contract; the provider-neutral roots and the root
  mixin are the new tofu-roots package (the twenty-second), also a
  hook plugin carrying the state-location check, the records and the
  state-isolation evidence, so the core imports no terraform library;
  the collectors are per-run instances beside the context; the
  direction and DAG tests hold the order. Golden and reference
  emission byte-identical. Not yet released (the release registers
  tofu-roots on the indexes: one of the day's four new projects).
- §122, storage and identity leave the core: 2026-11-05, its squash
  commit (feature/stage-122-storage-identity-leave-core kept). The
  storage protocol asks a builder for its mount record, its launch
  script block, its playbook tasks and the variables it reads; the
  User model keeps what every identity reads and okta-opa injects
  its profile fields; the workload token, the alias script and the
  OPA sentences are okta-opa's; plugins register CLI commands
  (`workload` from okta-opa, `verify login` from both identity
  plugins as one shared callback); the login hook path is one
  contract constant; the OS type's class answers the package-manager
  hooks and alpine works by construction; the rule test forbids the
  identity, package-manager and storage-kind words with one excused
  line. Golden and reference emission byte-identical. Opened XXIV
  items 15 to 17. Not yet released.
- §121, the core names no runtime: 2026-11-05, its squash commit
  (feature/stage-121-core-names-no-runtime kept). The contract asks a
  runtime's class for its session, its credential prefixes, its part
  of the image catalogue, its local test target and its key shapes,
  a backend's class for its session, every builder for its own load
  failure's one line; preflight, the load-failure classifier, the
  catalogue, the modification tests, the public-safety scan, the
  bootstrap's secrets and variables and the starter list read the
  installed plugins; packer is one `packer` key with three older
  names kept for one release; a rule test forbids the clouds' words
  in the core's sources, two storage-mount lines excused until §122.
  Golden and reference emission byte-identical. Not yet released.
- §120, a provider-neutral terraform root: 2026-11-04, its squash
  commit (feature/stage-120-neutral-tofu-root kept). hashicorp-utils
  holds the provider-neutral instance and storage roots and the tofu
  version checker; the AWS, GCE and docker roots answer provider
  hooks and nothing else; installing the GCE or docker root no longer
  installs the AWS one or boto3 (an isolation test proves it from the
  lock); the registry takes one class registered by several plugins
  as one registration. Golden and reference emission byte-identical.
  Not yet released. The §131 plan file rode in the same squash (the
  operator's commit on the branch).
- §119, the stage index and the end of narration: 2026-11-04, its
  squash commit (feature/stage-119-narration kept). 1,362 narration
  tokens on the current pages became the present rule with its reason;
  docs/CHANGES.md (the stage index, anchored), docs/INCIDENTS.md (116
  entries) and docs/GLOSSARY.md (38 terms) exist; REMINDERS.md is one
  document; the frozen history is marked whole and its links say where
  they lead; OPERATIONS has a table of contents and, with
  CONFIGURATION, owns each shared table; nine page disagreements were
  settled against the code. Documentation only.
- §118, the summary layer comes current: 2026-11-04, its squash commit
  (feature/stage-118-summary-layer kept). Every row of REEXAMINE1 §4.2
  and REEXAMINE3 §2.3 checked against the tree and fixed or refuted,
  row by row in the squash message: README, DESCRIPTION, DESIGN, GOALS
  (a preface mapping the goals), GOLDEN, PARITY, OPERATIONS,
  CONFIGURATION, the daily driver, two starters, fourteen package
  READMEs; the reference's README points at the records (53f8a8f on
  its develop). Four code-side findings went to bundle XXIV (items 10
  to 13). Documentation only.
- §111, hygiene bundle XXIII: 2026-11-02, its squash commit
  (feature/stage-111-hygiene-xxiii kept). `preflight` judges an
  sso-session profile whose cached token has lapsed with one read-only
  `aws sts get-caller-identity`: a refresh that works stays present, one
  that fails is EXPIRED with the login command (exit 2), and the PyPI
  release probe refuses a token already lapsed; the docs-examples test
  skips a Finder `.DS_Store`. Not yet released.
- §110, hygiene bundle XXII: 2026-11-02, its squash commit
  (feature/stage-110-hygiene-xxii kept). `just take` names the
  checkout and `just init` when `CSIS` lies in a venv that lags the
  release, and puts `.csis-version` back when `just init` or `just
  validate` fails after it was written; the PyPI release's probe line
  says the minutes the AWS session has left
  (`scripts/sso-minutes-left`, since §121 `scripts/session-minutes-left`,
  read from the cached token's own expiry; said, never refused on); `scripts/index-knows` prints its
  usage for a label. Not yet released; the reference takes it with the
  next release.
- §103, a container runtime: 2026-10-31 to 2026-11-01 in three
  branches (fa16a12, e651898, a2ed18c; feature/container-runtime,
  feature/container-instances and feature/container-operations kept),
  RELEASED in 0.1.6 (2026-11-02). `type: docker` is a runtime beside
  the clouds: the bake and the instances reach a container daemon
  (OrbStack, Docker Desktop, colima, Podman's API service) by a
  docker context or a host; two new PyPI projects
  (docker-runtime-plugin, tf-docker-plugin); the bootstrap interview
  has a docker section; `standard-docker` is the fifth starter and
  its template repository was first published by the tag. The
  reference declares `docker-orbstack` (context `orbstack`) and its
  three builders; none is a default.
- §107, releases are cut on `main`: merged 2026-10-31 (cda0f43),
  proved by 0.1.6.dev1 the same day and by the final 0.1.6, cut from
  `main` by the same walk (fast-forward, `just release stage pypi`,
  the push with tags, `develop` fast-forwarded back).
- §108, hygiene bundle XXI: 2026-11-01, its squash commit
  (feature/hygiene-xxi kept). `release` asks, first and in one line
  each, that the venv is in step with the lock and (for PyPI) that
  docker answers and every runtime session is present, and its dry
  form prints the same verdicts; the IDE's root workspace file is no
  longer tracked; every starter's Justfile carries `just take
  <version>` (the catch-up guard, the install, `init-config
  --changes-since`, a stop for the by-hand refresh, then init,
  validate, commit, push of `develop`); and `GUARD_RUNTIME` takes
  several runtimes. Released in 0.1.6; the reference took the Justfile and the
  workflow with it (0f7773d).
- §109, Podman Desktop in the test cycle: 2026-11-01, its squash commit
  (feature/podman-desktop kept). `just test-podman-desktop-cycle` names
  the running Podman Desktop machine and runs `test-podman-cycle`
  against it; it never starts or stops the machine and skips, said so,
  without one. Proved on Podman 5.8.9 (rootful) beside OrbStack: both
  live legs passed with no difference found. Podman 6 dropped Intel
  Macs: this leg ends for this Mac in June 2027 (reviewed monthly in
  [REMINDERS.md](../REMINDERS.md)).
- §105, a declared output image name: 2026-10-31, its squash commit
  (feature/output-image-name kept). `output_image_name` is real at
  the OS builder, its runtime entry and an image's runtime entry,
  each overriding the one above; the declared value is the PREFIX
  and the run's timestamp is still appended; a tree that declares
  nothing keeps today's names. `validate` refuses a prefix naming
  the timestamp, one that begins another's on the same runtime as
  the runtime makes them, and a name the runtime cannot take (two
  runtime hooks carry the rules); one INFO line per image and
  runtime prints the prefix. Fixture declarations of stage 22.3
  restored without the timestamp; golden moved on ten lines.
- §104, hygiene bundle XX: 2026-10-30, its squash commit
  (feature/hygiene-xx kept). The bootstrap makes every declared S3
  backend's bucket that a root is bound to, and the GCS state bucket;
  every section renders its coverage audit (MADE, READ, ADOPTED, BY
  HAND with the reason) into the generated README, and OPERATIONS
  carries the standing table; `validate` prints each OS builder's
  mod-test stand-in and warns when a query names another family than
  the token.

- §106, the image-source catalog: 2026-10-30, its squash commit
  (feature/image-sources kept). Where a vendor image comes from is a
  catalog in the system's own query vocabulary, two layers (the
  release's, the tree's), translated by each runtime through two new
  contract hooks; a family may say what it IS; `validate` refuses an
  unknown key, an entry with no source and a key the runtime cannot
  translate, and prints every resolved query in both vocabularies; the
  fingerprint hashes the effective query. Bundle XX item 4(a) landed
  with it.

- §102, hygiene bundle XIX: 2026-10-29, its squash commit. pyright's
  override check (`reportIncompatibleMethodOverride`) is on as an error
  over the whole workspace, and the nineteen places it named are fixed;
  the terraform root mixin reaches the run context through the builder's
  accessor, so the okta builder tests stand alone.
- §30, the plugin contract package: 2026-10-29, two squashes. Branch 1
  (41f5f3a, tags `s30-1-before`/`s30-1-after`): `cs-image-system-contract`,
  one package with a module per kind, upstream of the core, which
  implements its protocols nominally; the old paths in `base` re-export
  it (the shims); the collector takes the declared state backends from
  the core at load; every plugin depends on the contract and `base`,
  none on `system`. Branch 2 (its squash, tags `s30-2-before`/
  `s30-2-after`): the proof, `cs-image-system-contract-example-plugin`,
  OpenTofu's `inmem` state backend written against the contract alone,
  loaded, structured and run in a dry `run --all`; the core's one
  nominal gate on builder models became the protocol's.
- §101, hygiene bundle XVIII: 2026-10-28, its squash commit. The CLI
  takes `--version` and prints the installed release before anything
  loads, so a starter's `just init` line names the release it found.
- §100, hygiene bundle XVII: 2026-10-28, its squash commit. CI's
  guard (`runtime-unchanged`) passes the vendor's newest image moving
  under a base with no build yet, as `config-drift` does, and names
  the move; a diff cut short is never read as one.
- §98, hygiene bundle XVI: 2026-10-27, its squash commit.
  `config-drift` says what it is doing as it goes and leaves the
  provider cache out of its copy, as every `full-test` copy now does
  too; an unconfigured copy of a starter skips `perform` on its first
  push to `main`.
- §99, a development pin installs from TestPyPI again: 2026-10-26, its
  squash commit (every install line names `--index-strategy
  unsafe-first-match`).
- §97, hygiene bundle XV: 2026-10-24, its squash commit. A tree
  `init-config` writes links out of the starter at the release's tag.
- §66, starter repositories on GitHub: 2026-10-24, its squash commit.
  Four public template repositories generated from `docs/examples/`
  per final release; every CI job reads its image from
  `vars.CSIS_RUNNER_IMAGE`; the runner image is public.
- §96, hygiene bundle XIV: 2026-10-23, its squash commit. A release
  resumes after a partial upload (`release-finish`), uploads one project
  at a time, reads PyPI's new-project limit as "not now" and proves its
  token; the strict query reads each group's OPA objects back.
- §83, a release asks its publish target first: bbb7ee4, 2026-10-17.
- §95, hygiene bundle XIII: 8cdc07c, 2026-10-17.
- §92, CI runs in the system's own AlmaLinux 10 image: 661270f and four
  follow-ups, 2026-10-16.
- §93, everything carries its configuration's id: 23bb441, 2026-10-16.
- §81, hygiene bundle XII: 64c3bc7 to ca7127d, item 33 b28d50b,
  2026-10-14.
- §65, the walk of the daily driver: 8afd4ef, 2026-10-14.
- §84 to §91, the walk's findings: 4fb338b, b0494fa, c6af4b2, 9655327,
  20206e8, 7eb5962, cdb80bf, e72cc1b, 2026-10-07 to 2026-10-14.
- §82, an image says which configuration owns it: 0d1850c, 2026-10-05.

**Standing decisions** (the operator's)

- Documents describe what is and carry no commit hash; a landed stage's
  record is its squash message.
- A non-critical issue goes into the open hygiene bundle (start one if
  none is open); large or blocking work gets its own stage.
- A stage is a plan until the operator says to execute it.
- A documentation stage changes no code; a code change it needs is a new
  stage.
- Documentation stays current: work that changes behaviour,
  configuration, tests or procedure and lands undocumented opens the
  rolling documentation stage, which lists what changed since the last
  update.
- Both repositories are public, each from one redacted commit. Account,
  project, network, image and bucket ids and the Okta org and team are
  public by decision; live rosters are encrypted to the four recipients;
  fixture people are synthetic.
- A configuration declares its state managers (`state_backends:`) and
  every terraform root lives in exactly one of them, resolved through
  the chain (its own, its runtime's, the default); a tree may use
  several at once. The system's own metadata (`meta-state/`) is
  committed local files in the configuration repository. The
  reference's choice, not a system rule: its roots, the GCE ones
  included, sit on its default S3 backend for now, and `gcs` is
  declared and bound to nothing. Moving the GCE roots to GCS and
  per-runtime network checks are last, and not stages. (Reworded
  2026-10-30: the earlier "all terraform state stays on S3" was a
  gloss, never the operator's words.)
- GCP is the operator's money: no new GCP work unless a change could
  break the GCP code; then the GCE cycle runs on the operator's account
  and is torn down.
- `main` performs (stage 45): it records, bakes, releases and applies
  retention on AWS under the write role, then records again. GCE stays
  out of CI. A push to `main` is the operator's.
- Releases: `just release <part|version> [test|pypi]`, TestPyPI first; a
  deleted version is never re-cut; trusted publishing replaces the
  tokens once package names are stable. Since stage 107 a release is
  cut on `main`: `develop` is where work is done and `main` is where
  releases live; `main` takes `develop` by fast-forward before, the
  release commit and tag land on `main`, `develop` takes `main` back by
  fast-forward after; a failed release leaves its evidence on `main`
  alone; a maintenance branch `release/<major.minor>` serves an old
  version's fix. (`develop` alone from stage 83 to 0.1.5.)
- The plugin contract (§30) is provisional until the operator commits
  to it: Tier C declares the context protocol without injecting it, and
  the contract stays 0.x until the operator says. The core's re-export
  shims were removed in §125 (the operator, 2026-11-05); moving the
  contract to its own repository is §117, reserved by §116.
- The bootstrap is ongoing work: a new release-owned part, runtime or
  secret owes it a section, module or question in the same stage.
  Keeping its state in GitHub is not built. The operator's words (§70):

  > Initially, the user must install the base application (generally using `uv`).
  > Then the user would fork and clone the starter repository.  This would give them
  > a place to land the bootstrapping code.  They would then start the bootstrapping
  > interview, and should end up with a runnable copy of the application, as well
  > as a configured set of dependencies, bootstrap code, and target locations for
  > state management (including, possibly, storing state in github [not recommended]).
  >
  > Once landed, the §70 work should be considered part of the ongoing updates of the application
  > and the starter repository, such that any new items are part of the process.
