# 112. A release in two boxes

**Status: OPEN 2026-11-03; RE-PLANNED 2026-11-13 against develop at
`a2c81f1`, after the 0.1.7 and 0.1.8 walks. IN PROGRESS since "do
112", 2026-11-13. The operator took every default: the recipe pushes
(item 1); `take` always uses the release it installs (3), refreshes
what is safe (4), records (5), refuses a missing session naming the
login (6) and makes the before-tag (7); `take` pushes `main` only when
told `main` (8); `release-take` is a separate recipe (9); the bar,
then the full-test legs. Asked while it was built: the release
fetches origin and refuses up front when origin holds commits the
local branches lack; a release started from `main` ends on `develop`,
as one from `develop` does.**
Re-scoped by §126 (2026-11-06, its item 6 under shape (b)): this
stage stays whole; the release walk keeps its packages, so its boxes
are the recipes' to shrink, not a package count's.

The principle (the operator, 2026-10-31, restated 2026-11-03): a
release walk is as few boxes as the recipes allow, and a recipe that
cannot proceed says exactly what to do next and leaves nothing
half-done. The 0.1.8 walk on 2026-11-12 was sixteen boxes and two
logins. Fourteen of the sixteen were mechanical: each did a thing a
recipe had already decided, or that a later check demanded, and was a
box only because the recipe stopped where it could have acted. The
walk, with what each box was:

| # | Where | Box | Source |
| --- | --- | --- | --- |
| 1 | reference | tag `v0.1.8-before`, push it | the before-tag rule |
| 2 | system | checkout `main`, ff, `just init` | branch dance, stale venv |
| 3 | system | `just release 0.1.8 pypi yes` | the dry form, a habit |
| 4 | system | `just release 0.1.8 pypi` | the release |
| 5 | system | `aws sso login` halfway | a login lasts an hour |
| 6 | system | tag, status, log | a check |
| 7 | system | push `main` with the tag | branch dance |
| 8 | system | `develop`: ff, push, `just init` | branch dance |
| 9 | reference | `uv tool install` the release | skipped under `CSIS` |
| 10 | reference | `init-config . --force`, the pin | the refresh |
| 11 | reference | `just take 0.1.8 patched` | the take |
| 12 | reference | `just record`, pinned CLI | the pin's emission |
| 13 | reference | push `develop` | the record |
| 14 | reference | status | a check |
| 15 | reference | push `develop:main` | the one cloud act |
| 16 | reference | fetch, ff `develop`, push | CI's records on `main` |

After this stage the walk is `just release <part> <index>`, the login
halfway, and `just take <version>` in the reference; the reference's
`main` push stays a decision. Every item below names the gate that
makes the fewer boxes as safe as the many.

What changed under the plan since it was written, and is folded in
below: the release family's logic is `scripts/release.py`, tested
with a stubbed shell (§130), so items 1 and 2 are changes there and
not recipe text; the five starters share one skeleton
(`docs/examples/_skeleton/Justfile` and `CI_SETUP.md`), so there is
one `take` to change, not five; `validate` reaches no cloud (§127),
so the old reason for item 7 is gone and a new one took its place; a
committing run is held to the tree's pin (§132), so a record after a
take must be made by the pinned release; and the release refuses a
changed package that keeps its own version before its gate
(`scripts/own-versions-current`).

1. `release` does the branch moves itself (boxes 2, 7 and 8). Today
   `Family.branch_guard` refuses unless the checkout is on `main` with
   `develop` an ancestor. The guard stays a guard and acts: from
   `develop` with a clean tree, `release` checks out `main`,
   fast-forwards it to `develop` (refusing if it cannot), cuts the
   release as now, pushes `main` with `--follow-tags`, checks out
   `develop`, fast-forwards it to `main` and pushes it. From `main` it
   runs as today. From any other branch (a maintenance branch
   excepted) it refuses, as today. A refusal or a failure BEFORE the
   bump returns the checkout to the branch it started on and says so;
   a failed upload leaves the uncommitted bump on `main`, where
   `release-finish` or the discard needs it, and says that. The dry
   form prints the branch moves and the pushes it would make.
   `release-finish` gets the same ending. **YOUR DECISION:** the push
   is part of the recipe (the default), or stays the operator's and
   the recipe ends where it does now. The case for the default: the
   irreversible act is the upload, which the recipe already does; a
   version on the index whose commit and tag are unpushed is the wrong
   state, and the push is the only sane continuation.
2. `release` resyncs the venv (boxes 2 and 8). A branch switch
   rewrites the files the two branches differ in, and `uv lock` moves
   the lock, so the venv falls behind the checkout twice: after the
   move to `main` (the venv probe refused the first 0.1.7 attempt
   there) and after the release. `release` runs `uv sync --all-extras`
   after its move to `main`, before the probes, and again as its last
   act on `develop`; the closing line says so. The refusal that names
   the checkout stays, for a `CSIS` that points somewhere else.
3. `take` uses the pinned release (box 9). Today `take` installs the
   release only when `CSIS` is unset; a tree whose `.envrc` points
   `CSIS` at a development checkout (the reference's does) is checked
   by version alone and keeps whatever tool was installed before.
   Since §132 a committing run refuses anything but the pinned release
   installed from an index, and CI installs exactly that. So `take`
   always installs the release as the tool, with the tree's extras
   (`uv tool install --force`), and runs every step of its own with
   that binary, found through `uv tool dir --bin`; `CSIS` stays what
   the tree's other recipes use. **YOUR DECISION:** `take` always uses
   the release it installs (the default), or keeps honouring `CSIS`
   and refuses when what `CSIS` names is not that release from an
   index.
4. `take` refreshes what it already knows is safe (boxes 10 and 11).
   `init-config --changes-since` sorts a changed release-owned file
   into three classes (`ChangesReport` in
   [starters.py](../packages/system/src/cs_image_system/system/starters.py)):
   `refresh`, changed by the release while the tree's copy is still
   the previous release's own text; `edited`, changed by the release
   AND edited in the tree; `added`, new in the release. Today `take`
   stops on any of the three, and every take since 0.1.7.dev1 has been
   a stop on files nobody had edited. The change:
   - a module is judged by its stamp, not by text. Today a previous
     release of the current layout carries no module, so every changed
     module file is listed `edited` (the 0.1.7 take listed twelve
     untouched ones). The stamps already tell an unmodified copy from
     an edited one (`materialise_modules`: refreshed, adopted and kept
     are safe; refused is edited), and `--changes-since` reports a
     module by that judgement;
   - `--changes-since` gains a porcelain form the recipe can read (one
     line per file or module, `<class> <path>`, and an exit code that
     says whether anything is `edited`);
   - when nothing is `edited`, `take` runs `init-config . --force`
     itself, prints the list with each entry's class, and goes on to
     `init`, `validate` and the commit, whose message carries the list
     ("Take 0.1.8; refreshed: Justfile, .gitignore"); when anything is
     `edited` it stops as today, naming those alone, and `patched` is
     the way past;
   - the pin `--force` writes is the one `take` would write; the
     restore on a later failure reads the prior pin from `HEAD`, not
     from the tree, since `--force` has moved it.

   **YOUR DECISION:** this reverses "refreshing release-owned files:
   by hand, decided" of §110's scope. The case: the by-hand read
   compares two texts a person can see; the tool's rule compares
   against the previous release's exact text and the module's stamp,
   which the eye cannot, and stops on exactly the case where a
   person's judgement is needed.
5. `take` records (boxes 12 to 14). A release that moves the emission
   leaves the tree's committed emission behind its new pin, and the
   take's own push then fails CI's drift check until a record follows
   (the 0.1.7 take's first run did). After `init`, `validate` and the
   "Take" commit, `take` makes the record itself (a dry
   `run --all --commit` by the pinned release of item 3) and pushes
   `develop` once, with both commits. **YOUR DECISION:** the record is
   part of `take` (the default), or stays a box of its own.
6. `take` probes before it writes. With item 5 the take needs the
   tree's runtime sessions (a record reads them; `validate` alone no
   longer does), and a lapsed token found after the pin was written
   is the half-done state the principle forbids. `take` asks
   `preflight` first, as the system's release probes do, and refuses
   with the login command before anything changes. **YOUR DECISION:**
   refuse and name the command (the default), or run `aws sso login`
   itself; the browser's click stays the operator's either way.
7. `take` makes the before-tag (box 1). The operator's rule of
   2026-10-29: around a final release the configuration repository
   gets `v<version>-before` and nothing else. For a final version
   `take` tags `HEAD` so and pushes the tag as its first act after the
   guard; a development version gets none. **YOUR DECISION:** `take`
   makes the tag (the default), or it stays by hand.
8. `take` offers the `main` push as an argument (boxes 15 and 16):
   `just take <version> main` (or `patched main`) ends with `git push
   origin develop:main`, after the take's own push of `develop`, and
   says that `main` performs; item 5's record is the one CI's guard
   needs to find before `main` moves. Fast-forwarding `develop` to the
   records CI then commits on `main` is `release-watch`'s closing
   line (item 10), since it can only follow the run. **YOUR
   DECISION:** the default stays no push of `main` (standing: a push
   to `main` is the operator's; it bakes and applies under the write
   role), and the argument is the operator saying so in the same
   breath.
9. `release-take`: one recipe for both repositories, `just
   release-take <part> <index>`: item 1's release here, then `just
   take <version>` in the live configuration (`config_root`, where
   `release` already commits the modification-test evidence), with
   item 8's `main` passed through when given. **YOUR DECISION:** a
   separate recipe (the default: `release` alone serves a tree that
   takes at its own pace), or `release` itself chaining into
   `config_root`.
10. `release-watch <version>`: waits on the runs the walk starts (the
    tag's, `main`'s, `develop`'s and "CI from scratch" here; the
    reference's `develop` and, when pushed, `main`), found by commit,
    and prints one verdict line each, so the walk's end is a recipe's
    closing line and not a person polling. A green job is not proof
    that its steps ran: for the tag's run it reads that the index and
    the template repositories hold the version, and for the
    reference's `main` that the guard passed and what was baked.
    Separate from `release`: the runs take twenty to thirty minutes.
11. The documents say the new walk: the release walk in OPERATIONS
    ("`just build`, `just release`, `just publish`"), the release and
    take paragraphs of DAILY_DRIVER, the skeleton's `CI_SETUP.md`, and
    the Releases standing decision in [TODO.md](TODO.md) (the
    fast-forwards are the recipe's, the push of `main` with the tag is
    the recipe's when so decided). The skeleton's new and changed
    recipes carry a `[doc]` line, and their comments name behaviour
    (the narration rule reads the starter trees). The time estimates
    stay (a release about an hour).

**The first take after this stage is still by hand.** A tree runs the
`take` of the release it is ON, and gets the new recipe by refreshing
its Justfile at that take. So the release that carries this stage is
taken the old way, and the one after it is the first two-box walk.

**Out of scope**: the login itself (a browser); any change to CI; the
reference's `main` push by default; the release gate's legs; a
release from a maintenance branch (unchanged).

**Acceptance**: `tests/test_release_script.py` (the stubbed shell)
holds the branch moves in order, the resync after each, the return to
the starting branch on a refusal before the bump, and the dry form
naming every move and push while changing nothing;
`tests/test_take_recipe.py` (the take harness) holds that a release
whose changed files and modules are all safe is taken in one box with
the entries named in the commit, the record committed after it and one
push; that an `edited` file or module stops the take naming it alone
and commits nothing; that a failure after `--force` leaves the pin at
`HEAD`'s; that a final version is tagged before anything and a
development version is not; and that a missing session refuses before
anything changes; `tests/test_changes_since.py` has a test per class
in the porcelain form, a module judged by its stamp among them; the
recipes' presence is read from `just --summary` and their plans from
`just --dry-run`, never from the Justfile's text; the docs tests are
green; the bar and `just full-test-legs` are green. The live proof is
the second release after this stage, walked in two boxes and a login:
`just release <part> <index>`, `just take <version>` in the reference.
Records: the squash message; this section goes at "merge 112".
