# TODO

One section per stage in flight. A landed stage's section is removed;
its squash commit is the record, and the history is in git and
[docs/history/](docs/history/README.md). **USER** marks a step only the
operator can take.

**Open**

- §30 landed in two branches (below). Standing: the core's re-export
  shims of the contract stay until the operator commits to it; a WEEKLY
  reminder to remove them stands until then, and removing them is done
  together with moving the package to a repository of its own (DESIGN
  §3P, "Reversibility"). Tier C, the run-context protocol, is a later
  stage and declares without injecting while the contract is
  provisional.
- §94, the F44 review: standing; next on or after 2026-11-09.
- §104 landed (below) and is released in 0.1.5; item 4(d) is done in
  the reference.
- §105, a declared output image name: landed 2026-10-31 (below);
  the reference declares nothing, by the default taken at "do 105".
  Released in 0.1.6.
- §106 landed (below) and is released in 0.1.5; the reference is
  restamped and `basic-rh-10` says what it bakes. Nothing is owed.
- No documentation stage is open.

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
- `STARTER_PUSH_TOKEN` (`cs-image-system-starter-repos-token`) expires
  2027-10-25: renew it before then.

**Landed since 2026-10-05** (newest first)

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
  Macs: this leg ends for this Mac in June 2027.
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

---

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
