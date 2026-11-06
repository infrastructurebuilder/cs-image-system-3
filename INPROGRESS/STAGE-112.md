# 112. A release in two boxes

**Status: OPEN 2026-11-03, from the 0.1.7.dev1 walk. Waits for "do
112".** Re-scoped by §126 (2026-11-06, its item 6 under shape (b)):
this stage stays whole; the release walk keeps its twenty-two
projects (twenty published, two workspace-only), so its boxes are
the recipes' to shrink, not a package count's.

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
   [starters.py](../packages/system/src/cs_image_system/system/starters.py)):
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
