# Implementation Plan: The Google Cloud provider in a repository of its own

**Branch**: `feature/005-relocate-gcp-provider` | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-relocate-gcp-provider/spec.md`

## Summary

The Google Cloud family (`cs-image-system-gcloud-runtime-plugin`,
`cs-image-system-tf-gcp-plugin`, `cs-image-system-gcs-state-plugin`)
leaves this workspace for `infrastructurebuilder/cs-image-system-google-cloud`,
with its history, and is made to stand alone as it moves: its own tests,
fixture and golden there, built on the test kit and the SDK from the
index, its own version line from 0.2.0, its own acceptance tests and CI. Here, its
packages, its tests and its part of the shared suite leave; thirteen
test files that prove the core through GCE are re-hosted on AWS; the
umbrella's `gcloud` and `all` extras name the family by a range.

The work runs in four phases across two repositories and three
releases (research R1): prepare here and release; stand alone there
and release; remove here and release; the reference takes it. The SDK
the family must range on (contract 0.5.0, kit 0.2.0, Terraform 0.2.0)
is not yet on the index, which is why phase 1 ends in a release.

## Revision of 2026-11-19

Re-planned after phase 1 (merged and released as 0.1.11) and most of
phase 2. What the work found or the operator decided since the plan was
committed, each carried into the documents below:

- **The identity** (operator, at T021): the family's fixture gives its
  image a POSIX group, not the shared fixture's Okta group; the
  configured Okta is not available on Google Cloud (research R7).
- **The starters** (operator, at T031, option c): `standard-gce` and
  `complete` are tested here, where every provider is installed, by a
  check in this repository's CI `live` job, and not in the family's
  repository; that job keeps its Google Cloud identity (research R11).
- **The golden comparison** found a third cause of difference beside the
  backend and the identity: the other families' declarations absent from
  the tree (research R7, tasks T026).
- **The pipeline suite's dependencies** sit in the family workspace's
  dev group, not in a package's `test` extra; each package's extra holds
  only what its own tests need (data model).
- **The family's CI** runs on every push, as FR-003 says, not only on
  pushes to `develop` (contract; a follow-up to THERE's workflow).
- **A defect found, not this feature's**: a runtime written by its
  qualified word fails validation; it is specification 006.

## Technical Context

**Language/Version**: Python 3.13 (both repositories)

**Primary Dependencies**: uv workspaces; hatchling; pytest; ruff;
pyright; `git filter-repo` (history, phase 2); bump-my-version; the
SDK (`cs-image-system-contract`, `-base`, `-hashicorp-utils`,
`-tofu-roots`) and the test kit (`cs-image-system-system[testing]`)
from the index

**Storage**: N/A (files: fixtures, goldens, Terraform modules as
package data)

**Testing**: pytest under the test kit; here, `just test` with its
isolated runs; there, `just test` under the strict session (R6)

**Target Platform**: the operator's local machine and GitHub Actions
(ubuntu runners; this repository's `csis-ci` image)

**Project Type**: a compiler-like CLI with a plugin SDK; this feature
moves one plugin family between repositories

**Performance Goals**: N/A

**Constraints**: no Google Cloud spending by default (Constitution;
R12); the emission does not move except as R7 and R10 state, and every
golden change is read file by file; releases are the operator's (R2);
a version the index ever held is never cut again

**Scale/Scope**: three distributions, 3,030 source lines; 26 package
tests and about 160 top-level tests to move or re-host; 81 of 172
top-level test files touched; 31 golden files leave and 6 change; three
repositories (this one, the family's, the reference)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | Serves a plugin author (primary), operators and an adopting team, named in the spec | Pass |
| II. Acceptance is executable | Quickstart steps 1 to 5; the family's `just test` and CI; this repository's `just test`; the reference's drift check. The strict session makes a skip a failure there as here | Pass |
| III. Nothing irreversible by default | No apply; no live cycle unless the operator decides one (R12); releases stop for the operator (R2) | Pass |
| IV. The emission is the contract | The family's golden is compared file by file with the shared golden before anything here moves (R7, done at T026); the shared golden's 37 changed files read file by file (R10). One recorded departure, with three causes: the GCE roots' state backend, the POSIX identity, the other families' declarations absent (Complexity Tracking) | Pass, with the recorded departure |
| V. Public by construction | Both repositories are public; the moved files are already public; `just public-safe` runs on each | Pass |
| VI. Layers and no interference | The family imports only the contract and the SDK's declared surfaces (its self-check); nothing here imports it; its tests depend on no other provider family (R7 rejects the S3 coupling) | Pass |
| VII. Budget, subtraction | Below: this workspace falls by three packages and their code; growth is in the family's repository and is the code that left here | Pass |
| VIII. One source per fact | The strict verdict lives in the test kit, read by `isolated-run` (R6); installing the family is stated once (operations guide) | Pass |
| IX. Tests guard behaviour | The moved and re-hosted tests keep what they assert; no test of wording is added | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after design**: still passes. Two costs are recorded under
Complexity Tracking.

### Budget (Principle VII)

Measured on this branch on 2026-11-19 (the method of spec 004's T002:
lines of `*.py` under `packages/*/src` and `src`; tracked `*.py` under
`tests` and `packages/*/tests`, fixtures left out).

| Measure | Today | Expected (this repository) | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 22 | 19 | — |
| Source lines | 57,214 | −2,950 to −3,050 | The family's 3,030 leave; the test kit's strict session adds about 40 |
| Test lines | 48,141 | −3,500 to −5,500 | The family's own tests (472), the four GCP-only files (1,652) and the GCP parts of the mixed files leave; the 13 re-hosted files keep their size |
| Tests | 2,093 | −100 to −160 | 26 package tests, 59 GCP-only tests and the GCP-only cases of the mixed files leave; the strict session gains a few tests |
| Contract protocol members | — | 0 | — |
| Golden files (shared) | 148 | 117 | — |

The family's repository starts from nothing and holds what left here
(about 3,030 source lines and 2,000 to 3,500 test lines), plus its new
pipeline tests, fixture and golden.

### Statements this change makes false (Principle X)

Corrected in the same work. From the inventory of 2026-11-19.

- **This repository's documents**: `README.md` (lines 7, 63, 88-89,
  107-108, 111-112, 138); `docs/PLUGINS.md` (11, 57, 66, 70, 86-89,
  121, 128, 169: the plugin table and namespaces say where the family
  lives); `docs/DAILY_DRIVER.md` (97, 112, the GCP prerequisites,
  467-497, 1179, 1313-1319, 1384-1401); `docs/OPERATIONS.md` (2495,
  2512, and every link into the family's files); `docs/CONFIGURATION.md`
  (the `gcloud` runtime §4.4 and the `gcs` backend: their field tables
  move to the family's documents as their one source, and these
  sections link there; links at 362, 857, 1257, 1311, 1558);
  `docs/DESCRIPTION.md` (the in-repository plugin list); `docs/DESIGN.md`
  (links only); `GOLDEN.md` (the shared golden's providers);
  `docs/CI_RUNNER.md` (the runner image still carries `gcloud`, for
  configurations).
- **History documents** (`docs/CHANGES.md`, `docs/INCIDENTS.md`): what
  they say stays; their links into the family's files point at its
  repository.
- **Other packages' READMEs** that name the family as a neighbour:
  `packages/base`, `tofu-roots`, `tf-s3-state-plugin`,
  `tf-ebs-instance-plugin`, `hashicorp-utils`, `aws-runtime-plugin`,
  `default-os-plugin`, `packer-plugin`, `system`.
- **The family's own READMEs**: 145 relative links into this
  repository (`../../tests`, `../../docs`, `../<package>`) become links
  to the family's own files or to this repository by URL.
- **Starters**: `docs/examples/_skeleton/CI_SETUP.md` §3.4 and the
  `extras` recipe stay true (the extra is kept); `standard-gce` and
  `complete` are unchanged (R11). The starters' `PERFORM_RUNTIME:
  aws-REPLACE-ME` in `standard-gce` is a defect seen in passing, not
  this feature's (Constitution: it waits until its code is touched).
- **Workflows**: `.github/workflows/ci.yml` and `ci-from-scratch.yml`:
  `fixture-live` no longer asks Google Cloud (the frozen fixture loses
  its GCP declarations), while the `live` jobs keep their Google Cloud
  identity for the starters' check (`just test-cloud-starters`, R11);
  `publish-starters` installs the family from the index (R11).
- **The reference configuration** (`cs-image-system-testconfig`): its
  `CI_SETUP.md` (lines 29-30, 49-62, 226-234) and `README.md` (38-40)
  where they say the family comes from this repository; its pin and
  `just extras` stay.
- **The family's repository**: its `README.md` ("not yet implemented")
  and its draft `pyproject.toml` (R4).
- **Specifications**: spec 001's statements that the move is a later
  specification (`spec.md` FR-024 and the Google Cloud line at
  461-465) get a note pointing here; `specs/README.md` row 005.

## Project Structure

### Documentation (this feature)

```text
specs/005-relocate-gcp-provider/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── family-repository.md
│   └── test-kit-strict.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
# this repository
packages/gcloud-runtime-plugin/        # phase 1: ranges, testing.py (stubs); phase 3: removed
packages/tf-gcp-plugin/                # phase 1: ranges, test off the harness; phase 3: removed
packages/gcs-state-plugin/             # phase 1: ranges, test off the AWS plugin; phase 3: removed
packages/system/src/cs_image_system/system/testing/strict.py   # phase 1: new (R6)
scripts/isolated-run                   # phase 1: reads the verdict from strict.py
tests/harness.py                       # phase 1: GCP stubs out (R6)
tests/test_*.py                        # phase 3: R9's table
tests/fixtures/config, tests/fixtures/golden   # phase 3: R10
pyproject.toml                         # phase 3: extras by range; sources, testpaths, pythonpath, extraPaths
.vscode/settings.json                  # phase 3: extraPaths (held equal by test_editor_paths)
.github/workflows/ci.yml, ci-from-scratch.yml  # phase 3: GCP identity steps out
docs/**, README.md, packages/*/README.md        # phase 3: Principle X list

# the family's repository (R5)
packages/{gcloud-runtime-plugin,tf-gcp-plugin,gcs-state-plugin}/
tests/{fixture,golden,pipeline,tooling,live}/
scripts/{full-test-legs,release}
pyproject.toml, Justfile, REUSE.toml, LICENSES/, docs/, .github/workflows/ci.yml
```

**Structure Decision**: the family's repository is a uv workspace of
the three packages with one shared suite at its root (R5). This
repository loses three workspace members and keeps its layout.

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| The family's golden is not byte-identical to the shared golden's GCE files: its roots keep their state in the family's own `gcs` backend, not the AWS family's S3; its image's group is POSIX, not Okta; and the other families' declarations are absent (R7; the backend and the identity are the operator's decisions of 2026-11-19) | Byte-identity needs the AWS state plugin and the Okta plugin as test dependencies of the Google Cloud family, and AWS storage types declared on a tree with no AWS plugin, which validation refuses | Each couples one family's tests to another's release (Constitution VI), and the configured Okta is not available on Google Cloud. Every difference was read file by file and follows from one of the three causes (T026) |
| A check of two starters in this repository's `live` job, under cloud sessions (R11) | `standard-gce` declares the Okta plugin and `complete` every provider, so neither renders where only the family is installed | Changing the starters changes what adopting teams get; testing them nowhere leaves them unproven (the operator's decision, option c) |
| Three releases, two of them this repository's, for one move (R1) | The SDK the family ranges on is not published; the umbrella's `gcloud` extra must name a family release that exists | A path source to a sibling checkout hides the coupling the move removes; removing first leaves `develop` without Google Cloud |
