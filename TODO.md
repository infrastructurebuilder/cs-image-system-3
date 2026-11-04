# TODO

One section per stage in flight. A landed stage's section is removed;
its squash commit is the record, and the history is in git and
[docs/history/](docs/history/README.md). **USER** marks a step only the
operator can take.

**Open**

- §112, a release in two boxes: planned 2026-11-03 (below); waits for
  "do 112". No hygiene bundle or documentation stage is open.
- §113 to §116, the decomposition (the kit and the engine, the run
  context's protocol, the services behind it, a runtime installed from
  outside): planned 2026-11-03 (below), in that order; each waits for
  its "do N". §114 is the commitment to the contract in substance.
- §110 and §111 are landed and released in 0.1.7.dev1 (TestPyPI,
  2026-11-03); the reference's `develop` and `main` run it. The final
  0.1.7 is not cut.
- Standing: the core's re-export shims of the contract (§30) stay until
  the operator commits to it (Standing decisions, below).
- Interval checks (the F44 review, the §30 shims reminder, the
  `STARTER_PUSH_TOKEN` renewal) live in [REMINDERS.md](REMINDERS.md).

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
  [REMINDERS.md](REMINDERS.md)).
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

## 112. A release in two boxes

**Status: OPEN 2026-11-03, from the 0.1.7.dev1 walk. Waits for "do
112".**

The principle (the operator, 2026-10-31, restated 2026-11-03): a
release walk is as few boxes as the recipes allow, and a recipe that
cannot proceed says exactly what to do next and leaves nothing
half-done. The 0.1.7.dev1 walk on 2026-11-03 was ten boxes and a
login. Eight of the ten were mechanical: each one did a thing a recipe
had already decided, and was a box only because the recipe refused
where it could have acted. The walk, with what each box was:

| # | Box | Source |
| --- | --- | --- |
| 1 | checkout `main`, fast-forward from `develop` | branch dance |
| 2 | `just release patch test yes` | the dry form, a habit |
| 3 | `just release patch test` | the release |
| 4 | push `main` with the tag; checkout `develop`, ff, push | branch dance |
| 5 | `just init` in the system checkout | the venv behind the lock |
| 6 | `just take 0.1.7.dev1` | refused: release-owned files changed |
| 7 | `init-config . --force`, `git status` | the refresh |
| 8 | `git diff` | the human read |
| 9 | `just take 0.1.7.dev1 patched` | the take |
| 10 | push `develop:main` in the reference | the one cloud act |

After this stage the walk is `just release <part> <index>`, the login
when the token has lapsed, and `just take <version>` in the reference;
the reference's `main` push stays a decision. Every item below names
the gate that makes the fewer boxes as safe as the many.

1. `release` does the branch dance itself (boxes 1, 2 and 4). Today
   the recipe refuses unless the checkout is on `main` (stage 83, F31:
   dev18 was cut on a walk branch). The guard stays a guard and acts:
   from `develop` with a clean tree, `release` checks out `main`,
   fast-forwards it to `develop` (refusing if it cannot), cuts the
   release as now, pushes `main` with `--follow-tags`, checks out
   `develop`, fast-forwards it to `main` and pushes it. From `main` it
   runs as today. From any other branch (a maintenance branch
   excepted) it refuses, as today. The dry form prints the branch
   moves it would make. `release-finish` gets the same ending.
   **YOUR DECISION:** the push is part of the recipe (the default), or
   stays the operator's and the recipe ends where it does now. The
   case for the default: the irreversible act is the upload, which the
   recipe already does; a version on the index whose commit and tag
   are unpushed is the wrong state, and the push is the only sane
   continuation. A branch checkout leaves ignored, untracked files
   alone (the squash finish, not a checkout, is what deleted the
   workspace file twice).
2. `release` resyncs the venv (box 5). After `uv lock` the venv's
   metadata is behind the checkout, so a tree's `.envrc` that points
   `CSIS` into the venv answers `--version` with the previous release
   until `just init` runs here. `release` runs `uv sync --all-extras`
   as its last act, before the closing line, and the closing line
   says so. The §110 refusal that names the checkout stays, for a
   `CSIS` that points somewhere else.
3. `take` refreshes what it already knows is safe (boxes 6 to 9).
   `init-config --changes-since` sorts a changed release-owned file
   into three classes (`ChangesReport` in
   [starters.py](packages/system/src/cs_image_system/system/starters.py)):
   `refresh`, changed by the release while the tree's copy is still
   the previous release's own text (byte for byte, or a workflow with
   the team's values where that release had REPLACE-ME); `edited`,
   changed by the release AND edited in the tree; `added`, new in the
   release. Today `take` stops on any of the three, and the
   0.1.7.dev1 stop was two `refresh` files (`Justfile`,
   `CI_SETUP.md`): boxes 7 to 9 verified by eye what the tool had
   proved by comparison. The change, in the five starters' Justfiles
   (byte-identical): `--changes-since` gains a porcelain form the
   recipe can read (one line per file, `<class> <path>`, and an exit
   code that says whether any file is `edited`); when no file is
   `edited`, `take` runs `init-config . --force` itself, prints the
   list with each file's class, and goes on to `init`, `validate` and
   the commit, whose message carries the list ("Take 0.1.7.dev1;
   refreshed: Justfile, CI_SETUP.md"); when any file is `edited` it
   stops as today, naming those files alone, and `patched` is the way
   past. The pin `--force` writes is the one `take` would write; the
   restore on a later failure (§110 item 2) reads the prior pin from
   `HEAD`, not from the tree, since `--force` has moved it (the
   2026-11-03 walk restored it by hand before `patched`). **YOUR
   DECISION:** this reverses "refreshing release-owned files: by hand,
   decided" of §110's scope. The case: the by-hand read compares two
   texts a person can see; the tool's rule compares against the
   previous release's exact text, which the eye cannot, and stops on
   exactly the case where a person's judgement is needed.
4. `take` probes before it writes. The 0.1.6 take failed in
   `validate` on a lapsed token after the pin was written (§110 item
   2 put the pin back). `take` asks the tree's runtime sessions first
   (`preflight`, as the system's release probes do) and refuses with
   the login command before anything changes. **YOUR DECISION:**
   refuse and name the command (the default), or run `aws sso login`
   itself; the browser's click stays the operator's either way.
5. `take` offers the `main` push as an argument (box 10): `just take
   <version> main` (or `patched main`) ends with `git push origin
   develop:main`, after the take's own push of `develop`, and says
   that `main` performs. **YOUR DECISION:** the default stays no push
   of `main` (standing: a push to `main` is the operator's; it bakes
   and applies under the write role), and the argument is the
   operator saying so in the same breath.
6. `release-take`: one recipe for both repositories, `just release-take
   <part> <index>`: item 1's release here, then `just take <version>`
   in the live configuration (`config_root`, where `release` already
   commits the modification-test evidence), with item 5's `main`
   passed through when given. **YOUR DECISION:** a separate recipe
   (the default: `release` alone serves a tree that takes at its own
   pace), or `release` itself chaining into `config_root`.
7. `release-watch <version>`: waits on the runs the walk starts (the
   tag's, `main`'s, `develop`'s and "CI from scratch" here; the
   reference's `develop` and, when pushed, `main`) with `gh run watch`
   and prints one verdict line each, so the walk's end is a recipe's
   closing line and not a person polling `gh run list`. Separate from
   `release`: the runs take twenty to thirty minutes.
8. The documents say the new walk: the release walk in OPERATIONS
   ("`just build`, `just release`, `just publish`"), the release and
   take paragraphs of DAILY_DRIVER, the five CI_SETUP copies, and the
   Releases standing decision above (the fast-forwards are the
   recipe's, the push of `main` with the tag is the recipe's when so
   decided). The time estimates stay (a release about an hour).

**Out of scope**: the login itself (a browser); any change to CI; the
reference's `main` push by default; the release gate's legs; a
release from a maintenance branch (unchanged).

**Acceptance**: in the take harness (`tests/test_v2_take_recipe.py`),
a release whose changed files are all `refresh` is taken in one box
with the files named in the commit, a release with an `edited` file
stops naming it alone and commits nothing, and a `validate` failure
after `--force` leaves the pin at `HEAD`'s; `init-config
--changes-since` has a test per class in its porcelain form; `just
release patch test yes` from `develop` prints the branch moves and the
push it would make and changes nothing; the Justfile text tests
(`tests/test_v2_release_probes.py`, `tests/test_v2_hygiene_xxi.py`)
cover the new recipes' presence and the five Justfiles' identity; the
docs tests are green. The live proof is the next release walked in two
boxes and a login: `just release <part> <index>`, `just take
<version>` in the reference (0.1.7.dev2 or the final 0.1.7, the
operator's call). Records: the squash message; this section goes at
"merge 112".

---

## 113. The kit and the engine: `base` splits where the plugins stop

**Status: OPEN 2026-11-03. Waits for "do 113". First of the four
decomposition stages (§113 to §116); the measurement that shaped them
is below.**

The goal (the operator, 2026-11-03): decompose the system until a
runtime is defined outside it, so the system installs without any
runtime and a runtime installs without the system's engine. The
contract (§30) is the leaf every plugin is written against and stays
one: `base` depends on it, never the reverse, and
`tests/test_v2_contract.py` holds the direction. What a plugin needs
beyond the contract today is a part of `base`, and that part is
measurable. Over the 136 modules of `base` (24,649 lines), the
transitive closure of what the sixteen plugins and hashicorp-utils
import is 70 modules (13,932 lines), and the closure is closed: none of
the 70 imports any of the other 66 (10,717 lines). So `base` splits
into two packages today with no cycle, along a line nobody drew but the
imports already keep.

The two halves, by name. **The kit** (what a plugin needs): the base
classes (`basic/*`), the models (`models/*` but the six engine-only
ones below), `global_context`, `registry`, `lineage`, `launch_params`,
`launch_enrollment`, `encryption`, `public_safe`, `capabilities`,
`materialize`, `bake_steps`, `bake_user`, `launch_delivery`,
`power_state`, `posix_ids`, `identity_attributes`, `image_sources`,
`image_tests`, `storage_state`, `singleton`, `utils`,
`helpers/{field_helpers,field_kinds,plugin_config}`, the bootstrap
vocabulary (`bootstrap/facts`, `bootstrap/questions`),
`commands/run_lifecycles` (for `HookSet` alone; item 3 moves it). **The
engine** (what only the system runs): every other `commands/*` module
(validate, emission, preflight, dispose, relabel, resolve, restamp,
gate, the five generators, login_proof, workload_token, runtime_facts,
run_scope, state_migration, unmount, upgrade, load_failures,
finalization, identity_gids), `orchestrator`, `meta_state`,
`state_query`, `template_utils`, `release`, `retention`, `mod_tests`,
`generations`, `provider_aliases`, `alias_pool`, `loader`,
`read_models`, `v2_validation`, `reserved_names`, `workload_access`,
`tofu_lock`, `image_names`, `accounts_reconcile`, `ansible_launch`,
`init`, `lifecycle`, `lifecycles`, `helpers/{async_utils,config,
resolution_stages,yaml_process}`, `models/{container,encryption_config,
ia_config,public_safe_config,root_item,runtime_builder_item}`, and the
bootstrap engine (`bootstrap/{answers,generate,github,hcl,interview,
sections}`). The list is the measurement's, read again at "do 113":
the stage's first act is the script that computes it, kept as the test
of item 1.

1. The engine moves out of `base` into a package of its own. `base`
   keeps its name and its import paths and becomes the kit, so **no
   plugin changes an import or a dependency**; the engine's modules
   move to `cs_image_system.engine` (package
   `cs-image-system-engine`, depending on the kit), and `system` and
   the tests rewrite their imports to it. Every old path
   (`cs_image_system.base.commands.validate` and the rest) stays as a
   re-export of the new one, the §30 shim pattern, so the undo is a
   swap. **YOUR DECISION:** the engine package's name (`engine`, the
   default; or the engine goes into `system`, which blurs "no plugin
   depends on `system`"). The test: the closure script runs over the
   workspace and asserts that no kit module imports the engine and
   that every `cs_image_system.base` name a plugin imports resolves
   inside the kit; the seam stays measured, not remembered.
2. The kit reaches the terraform library nowhere.
   `register_declared_backends` in `global_context` imports
   `cs_image_system.hashicorp_utils.collector` lazily: the kit reaching
   into the library that depends on the kit, a cycle the lazy import
   hides. It is the engine's act at load (the orchestrator hands the
   state backends' registrations to the collector) and moves to the
   engine beside the three other lazy imports of the collector
   (`run_lifecycles`, `validate`), which are the engine's and stay as
   they are. hashicorp-utils then depends on the contract and the kit
   alone, as a plugin does; the engine's dependency on it stays
   optional and lazy (DESIGN §3P: "the library is optional to the
   core").
3. The declaration vocabulary that still lives in `base` moves down
   into the contract, finishing the "deferred" list of DESIGN §3P. (a)
   `contract.bootstrap`: `Facts`, `Question`, `Section`, `Rendered`,
   `Secret`, `Raw`, `Refused`, `Answers`, the four coverage marks
   (`MADE`, `READ`, `ADOPTED`, `BY_HAND`) and `ENTRY_POINT_GROUP`; the
   two modules they come from import nothing from `base` already.
   `gather`, the interview, the generation, the GitHub section and the
   HCL writer stay in the engine. (b) `contract.hooks`: `HookSet` and
   `HOOK_ENTRY_POINT_GROUP`, out of `commands/run_lifecycles` (a
   plugin-facing type in a 734-line command module; dummy-plugin is
   its one user). (c) The plugin entry-point group names
   (`cs_image_system.plugins.<kind>`), where `contract.constants` does
   not hold them yet. The old paths re-export (shims), `assert_conforms`
   covers the new kinds, the contract README's "What moved where"
   table grows.

**Out of scope**: any change to what a plugin imports (§114, §115);
the umbrella package's dependencies (§116); removing the §30 shims;
the contract's own repository; any YAML key, record, emission or cloud
state.

**Acceptance**: code only; the emission of the reference and of every
fixture is byte-identical before and after (the bar's golden tests);
`tests/test_v2_contract.py` holds the direction for the three packages
(contract imports nothing from kit or engine; kit imports nothing from
engine); the closure test of item 1 is green and lists its two sets;
no plugin's `pyproject.toml` changes; `uv tool install` of the umbrella
installs the engine; the §30 reversibility bracket is repeated
(`s113-before`/`s113-after` tags whose messages carry the undo). One
squash, branch kept. Records: the squash message; this section goes at
"merge 113".

---

## 114. Tier C: the run context is a protocol

**Status: OPEN 2026-11-03. Waits for "do 114", after §113. This is
the commitment to the contract in substance: DESIGN §3P names it the
one stream an undo of §30 would have to reverse.**

Seven plugins and hashicorp-utils import `GlobalTypeContext` (1,588
lines in the kit) and reach it at 61 `_get_context()` sites (32 in
tf-ebs-instance, 9 in tf-gcp, 7 in okta-opa, 5 in tf-docker, 3 each in
docker-runtime and gcloud-runtime, 1 each in aws-runtime and
posix-identity). The surface they touch is about twenty names, read
from the sources on 2026-11-03: `runtime_builders` (17 uses),
`meta_state` (10), `generation_path` (10), `os_builders` (8),
`get_provider_specific_image` (7), `run_id` (5), `mod_builders` (4),
`storage_builders`, `images_map`, `group_builders` (3 each),
`start_time`, `executables` (2 each), `working_path`, `users`,
`user_builders`, `storages`, `root_group`, `read_config`, `instances`,
`extend_finalization_phase` (1 each). Of `meta_state` they use four
members: `storage_state`, `storage_states`, `state_locations`,
`current_generation`. That is the protocol's whole size.

1. `contract.context`: `RunContextProtocol` with exactly those members,
   typed by the contract's own protocols (the builder collections as
   the contract's builder protocols, the provider-specific image as its
   `image` protocol, the paths as `Path`, the executables as the
   contract's executables) and a `MetaStateProtocol` of the four
   members; nothing typed `Any`, nothing named after a kit class. The
   list is re-read from the sources at "do 114" and the protocol holds
   what is used, not what `GlobalTypeContext` has.
2. The kit's `GlobalTypeContext` implements the protocol nominally (it
   lists it as a base, so pyright's override check compares every
   member), `assert_conforms` covers it, and `BuilderBase._get_context`
   returns the protocol type. **YOUR DECISION:** the accessor stays and
   is retyped (the default: the 61 call sites keep their text, the
   plugins change only their 18 imports and annotations from the kit's
   class to the contract's protocol), or the context is injected
   (`bind(ctx)`, DESIGN's phrase) and the sites become a field. The
   default is the smaller diff with the same end: a plugin names no
   kit type for the context.
3. The proof: `contract-example-plugin` gains a builder that reads the
   run context through the protocol alone (its test
   `test_the_sources_import_nothing_from_the_core` keeps holding) and
   is exercised in the dry `run --all` the plugin already runs in.
4. A test that no plugin and not hashicorp-utils names
   `GlobalTypeContext`, beside the direction test.
5. DESIGN §3P: the deferred list loses "the run context's protocol";
   the Reversibility paragraph records that Tier C is landed and the
   soft undo of §30 no longer applies; the plugin author's page in
   OPERATIONS names the protocol. **YOUR DECISION:** this stage is the
   commitment the standing decision speaks of. The standing decision
   says the shims go together with the contract's own repository; both
   are left to §116's last item, and this stage changes neither.

**Out of scope**: the services the plugins import by module (§115);
the shims; any emission change.

**Acceptance**: code only, emission byte-identical; the four tests
above green; the proof plugin's builder reads the context in the dry
run; the five starters unchanged. One squash, branch kept, bracketed
by tags as §113. Records: the squash message; this section goes at
"merge 114".

---

## 115. The services behind the context

**Status: OPEN 2026-11-03. Waits for "do 115", after §114. Kept apart
from §116 (below) on the recommendation of 2026-11-03: this stage is
inside the workspace and its proof is byte-identical emission; §116
reaches outside it.**

After §114 a runtime still imports the engine's knowledge by module,
read from the sources on 2026-11-03: from `lineage` seventeen names
(`owner_of`, `belongs_to_another_configuration`, `config_tags`,
`pinned_instance_build`, `pinned_parent_build`, `record_build`,
`series_of`, `pending_instance_replacements`, `instance_follow_target`,
`ours_or_unlabelled`, `mod_records`, `lineage_tags`,
`configuration_tag`, `bake_disk_size`, `TAG_PREFIX`, `CONFIG_TAG`,
`FINGERPRINT_TAG_LENGTH`; seven plugins); from `launch_params` five
(`compute_launch_params`, `user_data_template`, `detachments`,
`ENROLLMENT_TOKEN_VARIABLE`, `MOUNT_MARK`; four plugins); from
`encryption` four (`emit`, `is_marker`, `decrypt_marker`,
`EncryptedStr`; four); from `bake_steps` two (`execute_command_line`,
`settle_commands`); from `capabilities` two (`image_chain`,
`group_builder_of`); from `materialize` one (`mirror_path`); from
`launch_enrollment` one (`register_enrollment_kind`); from `posix_ids`
one; and the power states (`RUNNING`, `STOPPED`, `STOPPING`,
`STARTING`, `SUSPENDED`, `ABSENT`, `UNKNOWN`, `is_off`, `describe`).
Each has one of three homes.

1. Vocabulary goes to the contract: the tag names and length, the
   enrollment variable, the mount mark, the storage states, the
   cardinalities, the gid policies, the power states (the enum and its
   two helpers), `EncryptedStr` (the type a model declares a secret
   field with). Constants and types only; the shim pattern at the old
   paths.
2. Run-bound services go behind the context, as members of
   `RunContextProtocol` typed by service protocols in `contract.context`:
   `lineage` (the fourteen functions, which read the run's
   configuration id and the lineage records), `launch` (the three
   launch-parameter functions), `secrets` (`emit`, `is_marker`,
   `decrypt_marker`), `files` (`mirror_path`), `commands`
   (`execute_command_line`, `settle_commands`), and
   `register_enrollment_kind`, `image_chain`, `group_builder_of`. The
   kit's `GlobalTypeContext` supplies them from the modules where they
   live today; the modules do not move. **YOUR DECISION:** the grouping
   and the names (the default above), or one flat protocol.
3. The measure, as a test: a plugin's imports from the kit are confined
   to `basic/*` (the base classes), `models/*` (the models it
   subclasses) and the two metadata abstractions; every other kit
   module is reached through the context or not at all. The test
   lists the exceptions it finds, so "do 115" ends when the list is
   empty.
4. The plugin author's page in OPERATIONS says the three homes and
   what a runtime may import.

**Out of scope**: moving the service modules themselves (they stay in
the kit; the engine still calls them directly); the shims; §116.

**Acceptance**: code only, emission byte-identical; the test of item 3
green with an empty exception list; the proof plugin unchanged (it
already imports nothing from the kit); one squash, branch kept,
bracketed by tags. Records: the squash message; this section goes at
"merge 115".

---

## 116. A runtime installed from outside

**Status: OPEN 2026-11-03. Waits for "do 116", after §115 and
preferably after §112 (the release walk; this stage adds a repository
to it). Kept apart from §115: it changes what a release ships, the
starters, the reference's install line and the release walk, and
makes a repository; §115 changes none of those.**

The end the four stages are for: the umbrella `cs-image-system`
installs without any runtime, a runtime installs beside it from an
index, and one runtime lives in a repository of its own as the proof
(DESIGN §3P: "a separate repository for it once stable, with an
external plugin as the proof"). Today [pyproject.toml](pyproject.toml)
pins all twenty-one packages into the umbrella with `==`, and that pin
list is the only place "built-in" means anything: the loader is
entry-point driven and names no plugin.

1. The contract's compatibility version (the other deferred item of
   DESIGN §3P). An external plugin cannot pin `==` to a workspace it is
   not in; it pins a range of the contract and of the kit. The contract
   and the kit each carry a version that moves only when their surface
   moves (the contract's `assert_conforms` set and the kit's base
   classes), stated in their READMEs; the umbrella keeps `==` for what
   it ships. **YOUR DECISION:** the kit's version moves with the
   workspace (the default; a runtime pins `>=` the release it was
   written against and `<` the next minor) or carries its own.
2. The umbrella's dependencies: the engine, the kit, the contract,
   `system`, hashicorp-utils, and every non-runtime plugin (the OS,
   the modifications, the identity plugins, the state backends) stay
   in it; the three runtime pairs (aws + tf-ebs-instance, gcloud +
   tf-gcp, docker + tf-docker) become extras `[aws]`, `[gcloud]`,
   `[docker]` and `[all]`. `validate` names a declared runtime `type:`
   with no plugin installed and says the extra; the bootstrap's
   section discovery and `init-config` read what is installed, as the
   loader does. **YOUR DECISION:** which plugins stay in the bare
   umbrella (the default above: everything that is not a runtime).
3. The starters: each tree's `just init` and `just take` install the
   umbrella with the extras its `cfg/` declares (the runtime `type:`
   values map to extras; `complete` declares all three), and CI's
   install line does the same; `init-config` writes the line. The five
   Justfiles stay byte-identical (the extras are read, not written in).
4. The proof: `gcloud-runtime-plugin` and `tf-gcp-plugin` move to a
   repository of their own (`cs-image-system-gcloud`, public, with its
   own Justfile on the contract, its own CI and its own release to
   PyPI under the range pins of item 1); the umbrella's `[gcloud]`
   extra names its PyPI project; the two packages leave this
   workspace. The reference installs `[aws,gcloud,docker]` and its
   emission is byte-identical, its dry run green, `perform` on `main`
   green with nothing baked. GCP is the operator's money: a move is
   not a change to the GCP code, so no GCE cycle runs for this stage;
   if the move touches the plugin's logic, that is a finding and the
   operator decides. **YOUR DECISION:** gcloud as the proof (the
   default: the least-coupled runtime, already kept out of CI), or
   docker (no cloud at all, but the newest code).
5. The release walk: the external repository releases on its own
   cadence and the umbrella's extra pins a range, so `just release`
   and `just take` learn nothing; `release-watch` (§112) learns the
   third repository's run. The §112 estimates stay.
6. The documents: DESIGN §3P (the layered picture: contract, kit,
   engine, plugins; the deferred list is empty), the README's package
   table, OPERATIONS (installing with extras; the plugin author's
   page: a runtime's repository from the proof as the template),
   DAILY_DRIVER, the five CI_SETUP copies, PARITY.
7. **YOUR DECISION, the last:** the §30 standing decision says the
   shims go together with the contract's own repository. With a
   runtime outside, the contract is pinned from outside and is stable
   by the measure of item 1; this is where that decision comes due.
   The default is a stage after this one (§117: the contract to its
   own repository, the shims removed, the weekly reminder retired),
   not this stage.

**Out of scope**: any plugin's logic; a GCE cycle; the shims and the
contract's repository (item 7's stage); trusted publishing (the
tokens stay until the names are stable, standing decision).

**Acceptance**: `uv tool install cs-image-system` installs no runtime
and `validate` on a tree declaring one says the extra; `uv tool
install 'cs-image-system[gcloud]'` installs the external project from
PyPI; the reference on `[aws,gcloud,docker]`: emission byte-identical,
dry run green, `perform` green with nothing baked; the external
repository's own CI green on its release tag; the §66 proof passes
whole on the release that carries this (a starter copy's `just init`
names the release and its extras). Records: the squash message here
and the external repository's first release; this section goes at
"merge 116".
