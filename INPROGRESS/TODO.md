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
([§119](STAGE-119.md) to [§130](STAGE-130.md); §118 landed) cites the review section
it answers. The conventions are the ones above: one file per stage; a
stage is a plan until the operator says "do N"; **YOUR DECISION** marks
an operator choice and states the default; **USER** marks a step only
the operator can take; a landed stage's file is removed and its squash
message is the record. Numbering starts at §118. §117 is
reserved by [§116](STAGE-116.md) item 7 (the contract to its own
repository).

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
proposal: §118 to [§125](STAGE-125.md) land before
[§113](STAGE-113.md) is executed, each small and each proved by the
golden; [§113](STAGE-113.md) is then re-planned on the numbers
[§124](STAGE-124.md) prints, and [§125](STAGE-125.md) absorbs
[§114](STAGE-114.md) and [§115](STAGE-115.md). **YOUR DECISION:** that
order (the default), or [§113](STAGE-113.md) first as its file plans it.


**Open**

- [§119](STAGE-119.md), the documents: no code; may start now (§118 landed).
- [§120](STAGE-120.md) to [§125](STAGE-125.md), the seams: in that
  order; each waits for its "do N".
- [§126](STAGE-126.md), the package shape: a decision stage; before
  [§112](STAGE-112.md) and [§116](STAGE-116.md).
- [§127](STAGE-127.md), loading once: after [§124](STAGE-124.md).
- [§128](STAGE-128.md) and [§129](STAGE-129.md), the tests and the
  sources stop narrating: any time after [§119](STAGE-119.md).
- [§130](STAGE-130.md), hygiene bundle XXIV: the open bundle for the small findings.
- [§112](STAGE-112.md), a release in two boxes: planned 2026-11-03; waits for
  "do 112".
- [§113](STAGE-113.md) to [§116](STAGE-116.md), the decomposition (the kit and the engine, the run
  context's protocol, the services behind it, a runtime installed from
  outside): planned 2026-11-03 (their files), in that order; each waits for
  its "do N". [§114](STAGE-114.md) is the commitment to the contract in substance.
- §110 and §111 are landed and released in 0.1.7.dev1 (TestPyPI,
  2026-11-03); the reference's `develop` and `main` run it. The final
  0.1.7 is not cut.
- Standing: the core's re-export shims of the contract (§30) stay until
  the operator commits to it (Standing decisions, below).
- Interval checks (the F44 review, the §30 shims reminder, the
  `STARTER_PUSH_TOKEN` renewal) live in [REMINDERS.md](../REMINDERS.md).

**Stage files** (one per stage, in this directory; the plan is read
and validated by the operator before its "do N")

- [§112, A release in two boxes](STAGE-112.md)
- [§113, The kit and the engine: `base` splits where the plugins stop](STAGE-113.md)
- [§114, Tier C: the run context is a protocol](STAGE-114.md)
- [§115, The services behind the context](STAGE-115.md)
- [§116, A runtime installed from outside](STAGE-116.md)
- [§119, The stage index and the end of narration](STAGE-119.md)
- [§120, A provider-neutral terraform root](STAGE-120.md)
- [§121, The core names no runtime](STAGE-121.md)
- [§122, Storage and identity leave the core](STAGE-122.md)
- [§123, hashicorp-utils stops reaching back](STAGE-123.md)
- [§124, The run context and the engine part ways](STAGE-124.md)
- [§125, The contract's surface, its services and its version](STAGE-125.md)
- [§126, The package shape](STAGE-126.md)
- [§127, Loading once, without the cloud](STAGE-127.md)
- [§128, Tests named for behaviour](STAGE-128.md)
- [§129, The sources stop narrating](STAGE-129.md)
- [§130, Hygiene bundle XXIV](STAGE-130.md)

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
  (`scripts/sso-minutes-left`, read from the cached token's own
  expiry; said, never refused on); `scripts/index-knows` prints its
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
  to it: the core's re-export shims stay, Tier C declares the context
  protocol without injecting it, and the stage may be undone by the
  soft route (DESIGN §3P). Removing the shims is the commitment, done
  together with moving the contract to its own repository.
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
