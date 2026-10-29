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
- No hygiene bundle is open; the next non-critical issue opens bundle
  XX.
- No documentation stage is open.

**Release**

- 0.1.4, the latest final release: PyPI and TestPyPI, tag `v0.1.4`
  (2480c76), 2026-10-29, cut straight from 0.1.3. Carries §30 (the
  contract package and its proof plugin: two new PyPI projects, now
  twenty), §101 and §102. Its tag published the four template
  repositories again (tag `v0.1.4`).
- The reference configuration runs 0.1.4 (take c837606, records to
  217b258); `perform` green on 2026-10-29, nothing baked. Its tag
  `v0.1.4-before` (b80b27e) marks the state before the move; the
  release tag is the after marker (the operator's rule since 0.1.4,
  so no `-after` tag).
- Last development release: 0.1.2.dev2.
- The §66 proof passed whole on 0.1.4 (2026-10-29): a private copy of
  `standard-aws`, its first push and a dispatched dry run green with
  `live` and `perform` SKIPPED, `uv tool install
  cs-image-system==0.1.4` from PyPI (the contract included), and `just
  init` naming the release (`init: cs-image-system 0.1.4 ready against
  ...`, §101). The copy was deleted afterwards.
- `STARTER_PUSH_TOKEN` (`cs-image-system-starter-repos-token`) expires
  2027-10-25: renew it before then.

**Landed since 2026-10-05** (newest first)

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
- All terraform state stays on the S3 backend. Backends `s3`, `local`
  and `gcs` exist; `gcs` is declared and bound to nothing. Moving the
  GCE roots to GCS and per-runtime network checks are last, and not
  stages.
- GCP is the operator's money: no new GCP work unless a change could
  break the GCP code; then the GCE cycle runs on the operator's account
  and is torn down.
- `main` performs (stage 45): it records, bakes, releases and applies
  retention on AWS under the write role, then records again. GCE stays
  out of CI. A push to `main` is the operator's.
- Releases: `just release <part|version> [test|pypi]`, TestPyPI first; a
  deleted version is never re-cut; trusted publishing replaces the
  tokens once package names are stable.
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
