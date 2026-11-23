# Implementation Plan: Releases go to TestPyPI until 1.0

**Branch**: `feature/013-testpypi-until-1-0` (to be created when implementation starts) | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/013-testpypi-until-1-0/spec.md`

**Users served**: operators; an adopting team; a plugin author.

## Summary

Every release of the three repositories goes to TestPyPI, and PyPI is
refused, until the operator lifts the decision at 1.0. An interim release
runs the lighter check and says when a full proof is probably needed; a
release run with `--full` is proven as a PyPI release was
([research.md](research.md) R1, R2). This repository moves to trusted
publishing: a pushed tag publishes every public project and then pushes
the starters; the release tags and never uploads (R7, R8).

Every consumer takes the system's names from TestPyPI and nothing else
from it: a released umbrella pins every one of the system's names
exactly, so the one install form (PyPI first per name, TestPyPI when
PyPI cannot meet an exact pin) takes ours from TestPyPI and every
third-party name from PyPI (R3); each repository's lock pins the
system's names it reaches to TestPyPI, transitive ones included (R4);
the overlays and the isolated runs read TestPyPI and install exact pins
(R5). The families test against the newest TestPyPI release, and their
publishing stops at TestPyPI (R6). One section of the operations guide
states the install form and TestPyPI's limits; every install line links
it (R10).

## Technical Context

**Language/Version**: Python 3.13; GitHub Actions; bash in the Justfiles

**Primary Dependencies**: uv 0.12 (`[tool.uv.sources]` with `index =`,
`--index-strategy unsafe-first-match`, `uv publish --trusted-publishing
always`); this repository's `scripts/release.py`, `scripts/isolated-run`,
`scripts/with-released-families`, `scripts/dev-pin-resolves`,
`scripts/release-watch`, `scripts/publish-dist`; the families'
`scripts/release`, `scripts/full-test-legs`, `.github/workflows/publish.yml`

**Storage**: none new; the tag message records a full proof (data-model)

**Testing**: pytest under the strict session; a new lock check per
repository; the release script's own tests

**Target Platform**: the three repositories, the reference configuration,
the five starter repositories, an operator's and a team's machine

**Constraints**: no third-party name ever from TestPyPI; nothing to PyPI;
an interim release stays cheap (the operator: there will be many)

**Scale/Scope**: three repositories; 18 projects here, 1 and 3 in the
families; about thirty install lines; the reference and five starters

## Constitution Check

| Principle | How the plan keeps it |
| --- | --- |
| I. Purpose first | operators (cheap releases, told when one needs more), an adopting team (an install that works), a plugin author (tested against the system it runs beside) |
| II. Acceptance is executable | the quickstart's four steps: the lock checks, the release's refusal and advisory, the first release installed clean, the reference's take |
| III. Nothing irreversible | a version is never re-cut; PyPI untouched; the take waits for the index |
| IV. The emission | unchanged; no golden moves |
| V. Public by construction | two long-lived tokens leave the repository's secrets (trusted publishing) |
| VI. Layers | unchanged |
| VII. Budget | below |
| VIII. One source | the install form and TestPyPI's limits stated once, in the operations guide |
| IX. Tests | the lock checks hold a safety invariant (no third-party name from TestPyPI); the release's tests hold its refusals |
| X. What it makes false | below |

No violation needs justifying.

## Budget

| Measure | Expected | Reason |
| --- | --- | --- |
| Source lines | about +150 here (the release's refusal, `--full`, the advisory, the take's wait; the scripts' TestPyPI reads), about −120 (the local upload, `release-finish`, the token proof) | the release no longer uploads |
| Workflows | +1 here (`publish.yml`); the publish job leaves `ci.yml`; −1 job in each family | trusted publishing |
| Tests | about +12 (lock checks in three repositories, the refusal, `--full`, the advisory) | |
| Documents | about thirty install lines changed; one new section | |

## What the change makes false

- Every install line naming PyPI (R10), and the code's install hint
  (`src/cs_image_system/extras.py`).
- `docs/OPERATIONS.md` on the release (the token secrets, "trusted
  publishing waits", the release's upload, `release-finish`, the starter
  push for a final PyPI release), `docs/DAILY_DRIVER.md`'s release walk,
  `docs/CI_RUNNER.md`, `docs/PLUGINS.md`.
- The skeleton's `Justfile` take recipe and `CI_SETUP.md`, and the five
  starters' workflows and READMEs (the reference takes them at its take).
- The families' README and RELEASING pages ("then, for a final version,
  PyPI").
- Spec 010's and 008's release tasks (they become TestPyPI releases).
- Memory and the records: the release recipe's "test vs pypi" split.

## Decisions (the operator's, all taken 2026-11-23 as their defaults)

- **D1. How does an install take the families from TestPyPI?** A range
  PyPI can meet takes PyPI's version in the safe install form (R3).
  Default: **a released umbrella pins each family extra exactly at the
  newest release TestPyPI holds inside its range, read when the system
  is released**; a family's later patch reaches installs with the
  system's next release (which will be frequent). The alternative is a
  constraints file the take and the install instructions fetch per
  release. **Taken.**
- **D2. How do the families test against the newest system?** Default:
  **a CI job that re-locks the system's names to TestPyPI's newest inside
  the ranges and runs the acceptance tests**, beside the committed lock's
  job. **Taken.**
- **D3. The Okta plugin's copy here (R9).** Default: **marked
  `Private :: Do Not Upload` now**, so only cs-image-system-okta publishes
  that project. **Taken.**

## Project Structure

```text
pyproject.toml, uv.lock                       # the families' names pinned to TestPyPI; the umbrella's exact pins
scripts/release.py                            # pypi refused; --full; the advisory; no upload; the take waits
scripts/isolated-run, scripts/with-released-families, scripts/dev-pin-resolves, scripts/release-watch
scripts/publish-dist                          # no token proof; used by the publish workflow
.github/workflows/publish.yml (new), ci.yml   # trusted publishing; the starters after the upload
Justfile                                      # release, release-take, publish-starters
docs/examples/_skeleton/{Justfile,CI_SETUP.md}, docs/examples/*/.github/workflows/*.yml, docs/examples/*/README.md
docs/OPERATIONS.md, DAILY_DRIVER.md, CI_RUNNER.md, PLUGINS.md, README.md; src/cs_image_system/extras.py
tests/test_index_pins.py (new) and the release, take, starter and docs tests that pin today's split
cs-image-system-okta, cs-image-system-google-cloud: pyproject.toml, uv.lock, scripts/{release,full-test-legs},
  .github/workflows/{publish,ci}.yml, README.md, docs/RELEASING.md, tests
```

## Order of work

1. This repository's locks and installs (R3 to R5, D1), the release's
   refusal, `--full` and advisory (R1, R2).
2. Trusted publishing here and the starters (R7, R8, D3), with the
   operator's setup of the 18 publishers.
3. The families (R6, D2).
4. The documents (R10), then the first TestPyPI-only release, the
   batched one, carrying specs 002, 003, 006 and 010 (quickstart steps 3
   and 4).
