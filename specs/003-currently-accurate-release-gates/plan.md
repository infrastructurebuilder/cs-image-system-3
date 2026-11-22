# Implementation Plan: Release gates that cannot report a pass they did not earn

**Branch**: `feature/003-currently-accurate-release-gates` (to be created from `develop` when the work starts) | **Date**: 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-currently-accurate-release-gates/spec.md`

## Summary

Eleven places let a check that did not run read as a pass (research
R1): the full test run's `SKIPPED` legs (no daemon, no reference
configuration, an expired session, no Podman), the 23 tests `just test`
skips on every run, the tools a leg's tests skip without, the Okta
roots a dry run leaves unplanned without credentials, `fixture-live`
without docker, and the CI jobs that end green with no secret. Each
becomes a failure unless the caller excluded it by name, and a release
accepts no exclusion.

The approach subtracts more than it adds. The full test run's legs move
from bash in the [Justfile](../../Justfile) into
[scripts/release.py](../../scripts/release.py) as one table, with an
explicit `without=` exclusion, a three-count summary and the session
legs first (R2 to R5). The container tests leave the default collection
and run only in their legs, under the strict session, which the
workspace's pytest settings also take (R6). The release refuses any
word it does not know, records the checks that ran in its commit, and
after the gate fetches the remote again and, for a take, asks the
reference's sessions again (R9, R10). The watcher settles a missing run
five minutes after its siblings started and prints the command that
starts it (R12). `publish-starters` leaves alone a repository that
already holds the tag (R13), and `release-finish` also finishes a
release whose push was refused (R14). The CI gates lose their "none
configured" branch (R16). The two fixes made after 0.1.10 stay, held by
the tests that hold them today (R15).

## Technical Context

**Language/Version**: Python 3.13; bash in the Justfile's recipes;
GitHub Actions YAML

**Primary Dependencies**: `just`; uv; pytest and the test kit's strict
session ([strict.py](../../packages/system/src/cs_image_system/system/testing/strict.py));
`gh` (the watcher); git; bump-my-version (unchanged)

**Storage**: N/A (the release record is the release commit's body)

**Testing**: pytest; the release family's and the watcher's stubbed
shells (`Family(run=...)`, `Watch(run=..., clock=..., sleep=...)`);
the CI gate steps executed from the workflow files with their
environment, as `tests/test_docs_examples.py` already does for the
starters' gates

**Target Platform**: your local machine (the release is run there) and
GitHub Actions (the runner image; `ubuntu-24.04` for CI from scratch)

**Project Type**: the release tooling of a compiler-like CLI: scripts,
Justfile recipes and CI workflows

**Performance Goals**: a missing CI run reported within 5 minutes of
its siblings starting (SC-004); a full test run with a missing
prerequisite fails before it starts any leg that needs it

**Constraints**: nothing is published, pushed or powered on or off by
a rehearsal (R18); releases are the operator's; the emission does not
move; no new release script (FR-016); the release tooling and its tests
no larger after the feature (SC-007)

**Scale/Scope**: 12 legs; 23 skipped tests and 19 tool-guard skips in
the default run; 3 CI gate steps in two workflows; 4 commands of the
release walk changed (`release`, `release-finish`, `publish-starters`,
`release-watch`)

**Unknowns at the start**, each resolved in [research.md](research.md):

- What `just test`'s 23 skips are (R1, R6): resolved.
- Whether the Podman legs are required by a final release: NEEDS
  CLARIFICATION, resolved as a recommended default pending the operator
  (R7, D1).
- Whether the dry run leg plans the identity roots without credentials:
  it does not (R1 item 7); what to require is pending the operator (R8,
  D2).
- Whether a rehearsal mode exists: it does not as a mode; R18 composes
  one from the stubbed shell, the dry form and scratch remotes.
- Whether the watcher accepts a run started by hand: it does (R12),
  untested.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves operators (the release) and, through them, an adopting team and a plugin author, who install what a release publishes; named in the spec | Pass |
| II. Acceptance is executable | Quickstart steps 1 to 7; every scenario is a command or a test under the stubbed shell. This feature is Principle II's second sentence made true of `full-test`, the release gate and CI | Pass |
| III. Nothing irreversible by default | The release refuses more and earlier: after the gate it checks the remote and the take's sessions before the bump, and a refusal returns the checkout (R10); rehearsals publish and push nothing (R18) | Pass |
| IV. The emission is the contract | No emission changes; no golden moves | Pass |
| V. Public by construction | Nothing new is written to a public tree; scratch remotes are local; no secret is named in a log, only its name | Pass |
| VI. Layers and no interference | No package's code changes. R8 names the Okta plugin's variables in the release tooling's leg runner, which is about the reference configuration, not the core (Complexity Tracking) | Pass |
| VII. Budget, subtraction | Below. Source and package counts unchanged; the release tooling shrinks; test growth is the new behaviours' cases, offset in the release tooling's tests by removing tests of wording | Pass, with the test growth reasoned |
| VIII. One source per fact | The leg table is one source, printed by `just full-test-legs list`; the documents link to it and stop listing legs by hand | Pass |
| IX. Tests guard behaviour | The new tests assert exit codes, the commands sent or not sent, and the parsed counts; the tests that read the Justfile's or a workflow's text for `SKIPPED` are removed or turned into tests that run the gate | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after design**: still passes. Two costs are recorded under
Complexity Tracking.

### Budget (Principle VII)

Measured on `develop` at `35446e3f` on 2026-11-21 (research R20: lines
of `*.py` under `packages/*/src` and `src`; tracked `*.py` under `tests`
and `packages/*/tests`, fixtures left out; tests are `def test_`
functions).

| Measure | Today | Expected | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 19 | none |
| Source lines | 54,249 | 0 | none (the work is in `scripts/`, the Justfile and the workflows) |
| Test lines | 46,069 | −50 to +200 | The new cases: the leg runner's verdicts and exclusions, the re-checks after the gate, the record, the finish's second state, the watcher's settling and dispatched run, the starters' resumption, the CI gates run. Offset by 19 tool-guard skips, the container files' gating and the tests of wording |
| Tests | 2,007 | +8 to +20 | The same cases |
| Contract protocol members | none | 0 | none |
| Release tooling (11 scripts 3,263, Justfile 773, two workflows 535) | 4,571 | −80 to 0 | none (SC-007: no larger). The leg runner (about +90 in `release.py`) replaces 57 lines of bash; the gates lose a branch each; the finish and the watcher grow by about 50 together; the release's docstrings are trimmed where they repeat the Justfile |
| Release tooling's tests (16 files, R20) | 4,078 lines, 183 tests | at most 4,078 lines; +5 to +15 tests | SC-007 holds the lines; the count grows by the new cases, offset by removing the text assertions of `test_justfile_contract.py`, `test_ci_workflow.py`, `test_ci_runner.py` and `test_podman_machine_host.py` |

### Statements this change makes false (Principle X)

Corrected in the same work (FR-017).

- **The Justfile's comments**: `full-test` ([Justfile:66-75](../../Justfile#L66):
  "reports SKIPPED loudly ... does not fail the run", the identity
  credentials "not gated"); `full-test-legs` (191-193); the release's
  gate and probes (93-96, 147-158: "the live legs would be SKIPPED");
  `test-posix-accounts`, `test-bake-steps`, `test-docker-bake`,
  `test-docker-cycle` ("under `just test` the same file is skipped");
  `test-podman-cycle` and `test-podman-desktop-cycle` ("SKIPPED with
  exit 0"); `fixture-live` ("SKIPPED test-mods"); `publish-starters`
  ("never twice", "one that holds the version refuses them all");
  `release-finish` (its one starting state); `release-watch` ("sixty
  minutes at most" for a run that never started).
- **The scripts' docstrings**: [scripts/release.py](../../scripts/release.py)
  (the ending's failure "by hand", the probes' reason, `release-finish`'s
  one state); [scripts/release-watch](../../scripts/release-watch) (a
  missing run waited on to the timeout); [scripts/podman-machine-host](../../scripts/podman-machine-host)
  ("a recipe can skip, loudly").
- **The workflows' comments**: [ci.yml:18-22](../../.github/workflows/ci.yml#L18)
  ("every such leg reports SKIPPED and the job passes"), the gate
  steps' comments in both workflows.
- **[README.md](../../README.md)**: the `full-test` and `release` rows
  of the lifecycle table (lines 42-43).
- **[docs/OPERATIONS.md](../../docs/OPERATIONS.md)**: "`just full-test`"
  (1763-1791: the leg list, replaced by a link to `just full-test-legs
  list`, and "A leg whose prerequisite is absent reports `SKIPPED`");
  `fixture-live` (1882: "skipped loudly without docker"); the release
  walk's finish and the starters' publication (the section around
  2442-2458).
- **[docs/DAILY_DRIVER.md](../../docs/DAILY_DRIVER.md)**: the
  troubleshooting rows at 1227 (`full-test: passed` above `SKIPPED`)
  and 1259 (a missing tag run found after the timeout); the release
  walk's steps that name the watch's wait and the hand-typed ending.
- **[docs/CI_RUNNER.md](../../docs/CI_RUNNER.md)**: what this
  repository's jobs do with no secret, where it speaks of them.
- **History documents** (`docs/CHANGES.md`, `docs/INCIDENTS.md`): what
  they say stays; each incident this feature cures gains a line saying
  so, as spec 005 did.
- **Specifications**: spec 001's research R17 boundary gets a note that
  this feature took the legs; `specs/README.md` row 003.
- **Not changed, by D3**: the starters' workflows, `_skeleton/Justfile`
  and `_skeleton/CI_SETUP.md` 3.7 to 3.9, and `docs/DAILY_DRIVER.md`
  424-430 and 688-692, which describe them.

### Decisions for the operator

None of these is recorded in the spec's Clarifications; each has a
recommended default the plan is written to.

| # | Decision | Recommended default | Why |
| --- | --- | --- | --- |
| D1 | The Podman legs: required by every final release, or a recipe of their own outside `full-test` | Their own recipe, `just test-podman`, no gate requires it (R7) | No release has required them (they passed when absent); the spec keeps what each release requires; the Podman machine's power state is yours |
| D2 | The identity roots in the dry run leg | The `reference` prerequisite requires the Okta variables set and not empty (R8) | Otherwise the leg passes having planned less than the tree; the cure in the plugin itself belongs to spec 008's repository |
| D3 | Whether the starters' gates (their CI and `_skeleton/Justfile`) change too | Not in this feature (R17) | It changes what an adopting team sees on its first push, which spec 002 owns; this feature's gates do not depend on them |
| D4 | The exit status of a pass with exclusions | 0, with the last line saying `passed WITH EXCLUSIONS` (R4) | The developer asked for it by name; a non-zero exit reads as a failure in `just`; the release cannot reach it |
| D5 | The order against specs 007 and 008 | This feature first, before 007's phase 1 release (R19) | Their four phase releases then pass the honest gate; all three edit `ci.yml`'s `live` job and the Justfile |
| D6 | The release that carries this feature | The next final release, 0.1.13 to PyPI, by `just release-take 0.1.13 pypi main` (R21) | It is the only release whose gate is `full-test` and whose tag run publishes the starters, which SC-008 measures |

## Project Structure

### Documentation (this feature)

```text
specs/003-currently-accurate-release-gates/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── full-test-verdict.md
│   ├── release.md
│   └── ci-gate.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
scripts/release.py                 # the leg table and runner (full-test-legs, list, without=); the words refused;
                                   # the gate's record; the fetch and the take's preflight after the gate;
                                   # release-finish's second state; ENDING_FAILED names the finish; R1 item 11
scripts/release-watch              # Expected.file; a missing run settled five minutes after its siblings, with its remedy
scripts/podman-machine-host        # docstring only (D1)
Justfile                           # full-test and full-test-legs take words and wrap release.py; test-podman (D1);
                                   # the container legs run tests/containers under the strict session, their env
                                   # gates gone; fixture-live fails without docker; publish-starters resumes and
                                   # reads starter_remote; the comments of Principle X
pyproject.toml                     # pytest addopts take the strict session; norecursedirs gains containers
tests/containers/                  # the five container files, moved from tests/, their skips gone (R6)
tests/test_*.py                    # the 19 tool-guard skips removed; the new cases; the tests of wording removed
.github/workflows/ci.yml           # the live and publish gates: any missing secret fails
.github/workflows/ci-from-scratch.yml   # the live gate: the same
docs/OPERATIONS.md, docs/DAILY_DRIVER.md, docs/CI_RUNNER.md, README.md   # Principle X
```

**Structure Decision**: no package changes. The release family keeps
its one script ([scripts/release.py](../../scripts/release.py)), which
gains the leg runner; the Justfile keeps its recipes as wrappers.

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| The leg runner names the Okta plugin's credential variables (D2, R8) | The dry run leg otherwise passes having skipped the identity roots' plan, which FR-001 forbids | A contract hook for identity sessions adds a protocol member; changing the plugin's skip is a change spec 008 is about to carry to another repository; accepting the skip is the fault itself |
| Test lines may grow by up to 200 across the suite | Five new behaviours (the re-checks, the record, the finish's second state, the watcher's settling, the starters' resumption) and the leg runner's verdicts need cases under the stubbed shell | Leaving them untested would make the gate honest by assertion only; the release tooling's own tests are held at no growth by removing tests of wording |

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- D1: the Podman legs move to `just test-podman`, outside every gate.
- D2: the `reference` prerequisite requires the `OKTA_API_*` variables set and not empty.
- D3: the starters' own gates stay out of this feature.
- D4: a pass with exclusions exits 0, saying `passed WITH EXCLUSIONS`.
- D5: the order is 008, then this feature, then 007 (so 007's phase releases pass the new gate; 008's come first).
- D6: one final release carries specs 002, 003 and 006 together, taken on the reference's `main` too (SC-008's proof).
