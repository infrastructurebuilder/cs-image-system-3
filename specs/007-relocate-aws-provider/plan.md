# Implementation Plan: The AWS provider family in a repository of its own

**Branch**: `feature/007-relocate-aws-provider` (to be created from `develop`; spec 005 is complete, and spec 008 lands first, research R7) | **Date**: 2026-11-19, revised 2026-11-21 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/007-relocate-aws-provider/spec.md`

## Summary

The AWS family (`cs-image-system-aws-runtime-plugin`,
`cs-image-system-tf-ebs-instance-plugin`, `cs-image-system-tf-s3-state-plugin`)
leaves this workspace for `infrastructurebuilder/cs-image-system-aws`,
with its history, and stands alone as it moves, by spec 005's pattern:
the SDK and test kit from the index, its own fixture, golden, harness,
acceptance tests, CI and version line from 0.2.0. Here, the core's
behaviours that the shared suite proves through AWS move onto the
docker family (the operator's answer), and what docker cannot show is
carried as research R6 and R7 decide.

The work is spec 005's four phases (research R1). Phase 1 is the large
one: before anything leaves, the shared suite's vehicle changes from AWS
to docker, or to the test kit's double where docker cannot show a
behaviour (R6), for the 80 test files that name the AWS family's code
or the fixture's AWS entries today (889 tests; research R5). Phase 3
reuses the mechanism spec 005 built for a family released elsewhere
(`scripts/with-released-families` and the tests that hold it, research
R12): the AWS family joins the Google Cloud family there.

## Revision of 2026-11-21

Re-planned after spec 005 completed (merged, converged, released in
0.1.12, the Google Cloud family at 0.2.0 from its own repository) and
before any work on this specification. Each change was read in the code
on 2026-11-21 and is carried into the documents below.

- **The vehicle for the tests spec 005 re-hosted on AWS** (T039, T040,
  T046, T074 of spec 005: 13 files and two cases). They move a second
  time, onto docker by the operator's Q2 A where docker has the
  capability, and onto the test kit's double where it does not (R6 (a));
  each file's vehicle is listed in research R5. The counts are today's:
  46 test files import the AWS family's code (526 tests), 34 more name
  the fixture's AWS entries (363 tests). The 2026-11-19 figure of "about
  53 files" counted only the first kind.
- **Spec 008 lands before phase 1, not only before phase 3** (research
  R7, an operator's decision, default stated). Six of the shared
  fixture's eight images are owned by Okta groups, and the core refuses
  an Okta-owned image on a container runtime; their tests cannot move
  onto docker until spec 008 makes those groups POSIX.
- **Where the double's tests run** (research R6, chosen): in the core's
  own fixture and suite (`packages/system/tests`, run alone by `just
  test-core`), as a second double runtime type built on the kit's cloud
  base beside today's container double. The shared fixture cannot
  declare the double: `just fixture-live` loads it with the installed
  command, which registers no double.
- **The released-elsewhere mechanism** (research R12): phase 3 adds
  `aws` to `RELEASED_ELSEWHERE` in `scripts/with-released-families`, to
  the sync rule (`--no-extra aws`) in the `Justfile`'s `init` and
  `scripts/release.py`'s `SYNC`, and to the three tests that hold the
  rule. The private recipe `gcloud-with` is renamed `families-with`,
  since it layers in more than one family.
- **The starters' check** (research R9, corrected): `just
  test-cloud-starters` is a `full-test` leg and a step of CI's `live`
  job, not part of `just test`, and needs no cloud identity (its clouds
  are stubbed). `standard-aws` and `standard-aws-posix` join
  `standard-gce` and `complete` in `tests/cloud_starters/`.
- **A defect in the starter selection** (research R9, read): the
  helper `tests/starter_support.py` reads an executable's `type: tofu`
  as the AWS family's instance builder word, so `standard-docker` reads
  as needing the `aws` extra. Once the AWS family is absent, this
  repository would stop rendering its own docker starter. Phase 1 fixes
  the helper, since it blocks this specification.
- **CI identity** (research R10, corrected): once the fixture holds no
  AWS runtime, `AWS_ROLE_ARN` serves no step here. The plan drops the
  AWS identity steps from both workflows, as spec 005 dropped the
  Google Cloud one; removing the repository secret and the role's trust
  of this repository are the operator's.
- **Release traps** (research R13): the SDK READMEs of `base`,
  `hashicorp-utils` and `tofu-roots` name the AWS family; changing them
  under the published 0.2.1 needs `just sdk-bump kit last` and `just
  sdk-bump terraform last`. A take right after an upload can outrun
  PyPI. After any applying run, `just record` comes before the
  reference's push.
- **The destination, re-read** (research R4): still one commit
  (`88cdab3`); public; GitHub's default branch `main`; no Actions
  secret.
- **Versions, re-read** (research R3, R11): the AWS family is at the
  workspace's 0.1.12, twelve releases each on PyPI; its pins on `base`,
  `hashicorp-utils` and `tofu-roots` are exact at 0.2.1; the contract is
  already a range (`>=0.5,<0.6`).
- **The Budget** (below): measured from today's code, with the test
  count Principle VII asks for, which the first plan left out.
- **The statements this change makes false** (below): re-read; they now
  include the mechanism's files, the sync rule's quoted commands, the
  CI identity's rows in `docs/OPERATIONS.md`, and the Google Cloud
  family's READMEs, which link into this repository's AWS packages.
- **Complexity Tracking**: the order (spec 008 first) and the three
  releases are recorded as costs; the file count is today's.
- **The contract and the data model**: the stubs' home, the release
  script, the destination's state, the released-elsewhere table.
- **The definition of done** (constitution 1.2.0): the tasks end in
  convergence, the quickstart walk, the merge, the releases and the
  status lines (section "Definition of done" below).
- **The quickstart**: a step for the starters that need the cloud
  families; the reference step names the installed release, as spec
  005's did; the import search leaves out `tests/cloud_starters`; boxes
  renumbered and their versions bumped.
- **Spec statements the plan departs from** (the operator's to amend,
  listed in "Spec statements to amend" below).

## Technical Context

**Language/Version**: Python 3.13 (all repositories)

**Primary Dependencies**: as spec 005: uv workspaces, hatchling,
pytest, ruff, pyright, `git filter-repo`, bump-my-version; the SDK and
the test kit (`cs-image-system-system[testing]`) from the index; here,
`scripts/with-released-families` layers the families released elsewhere
in from PyPI for the commands that load a tree declaring them

**Storage**: N/A (fixtures, goldens, Terraform modules as package data)

**Testing**: pytest; here `just test` with its isolated runs (the
double's tests in `test-core`), and `just test-cloud-starters` as a
`full-test` leg and a CI `live` step; there `just test` under the strict
session

**Target Platform**: the operator's local machine; GitHub Actions

**Project Type**: a compiler-like CLI with a plugin SDK; this feature
moves the second provider family out

**Performance Goals**: N/A

**Constraints**: no AWS live cycle by default; the operator's AWS
session never lasts 60 minutes (a release needs a login midway); the
emission does not move except as read file by file; releases, the
destination repository's settings and secrets, and every IAM write (the
role's trust of a repository) are the operator's; spec 008 lands first
(research R7)

**Scale/Scope** (read 2026-11-21): three distributions, 21 source files,
3,632 source lines, 31 package tests in 651 lines; 80 top-level test
files name the AWS family's code or the fixture's AWS entries (889
tests), of them 46 import its code (526 tests) and 13 plus two cases
are spec 005's re-hosted ones; about 6 AWS-only files to move (research
R5); 58 shared golden files leave (`pckr-ebs-ans` 38, `some-other-builder`
5, `open-tofu` 6, `aws-ebs`, `aws-efs`, `aws-s3` 3 each) and the run
scripts and meta-state files change; 3 starters declare AWS
(`standard-aws`, `standard-aws-posix`, `complete`; `standard-docker`
and `standard-gce` only read as declaring it, by the selection defect
of research R9); the reference configuration keeps every root's state
in S3

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | A plugin author, operators, an adopting team (spec) | Pass |
| II. Acceptance is executable | Quickstart steps 1 to 6; both repositories' `just test`; `just test-cloud-starters` (a `full-test` leg and a CI `live` step, strict, so an absent family fails rather than skips); the reference's drift check | Pass |
| III. Nothing irreversible by default | No live cycle; releases stop for the operator | Pass |
| IV. The emission is the contract | The AWS family's golden read file by file against the shared golden before anything here moves; the shared golden's changes (the second docker runtime in phase 1, the 58 AWS files in phase 3) and the core golden's (the double's additions) read file by file | Pass |
| V. Public by construction | Both repositories public; `just public-safe` on each | Pass |
| VI. Layers and no interference | The AWS family's tests depend on no other provider family; the core's rules stay proven by the core's own tests, on the test kit's double in `test-core`, where no provider is installed (R6, decided (a)); the Okta plugin's instance proofs move with it (R7, decided (c), spec 008, which lands first) | Pass |
| VII. Budget, subtraction | Below: workspace packages, source lines, contract members and test count, each with its reason | Pass |
| VIII. One source per fact | Installing a family released elsewhere is stated once, in `docs/OPERATIONS.md` "Installing a release" (spec 005's T061), which gains the AWS family; its field tables move to its repository, as the Google Cloud family's did; the released-elsewhere extras are named once, in `scripts/with-released-families` | Pass |
| IX. Tests guard behaviour | Moved and re-vehicled tests keep their assertions; the double gets tests of behaviour, not of wording | Pass |
| X. What a change makes false | Listed below | Pass |

**Re-check after the revision of 2026-11-21**: still passes. The
starters' check and the CI identity rows were corrected (research R9,
R10); no principle's result changed.

### Budget (Principle VII)

Measured on `develop` on 2026-11-21 by spec 005's method (lines of
`*.py` under `packages/*/src` and `src`; tracked `*.py` under `tests`
and `packages/*/tests`, fixtures left out; a test is a `def test_`).
The source figure equals spec 005's after-figure (T065), so the method
reproduces. Phase 1 measures again on the branch, after spec 008 has
landed, and the expected column is restated from that figure.

| Measure | Today (2026-11-21) | Expected (this repository) | Reason for any growth |
| --- | --- | --- | --- |
| Workspace packages | 19 | 16 | none |
| Source lines | 54,249 | −3,100 to −3,500 | The AWS family's 3,632 leave, its stubs' new `aws_runtime/testing.py` with them; the test kit's second double runtime and its storage (R6 (a)) add about 150 to 500 |
| Test lines | 46,069 | −800 to −2,500 | The AWS family's own 651 and about 6 AWS-only files leave; most of the mixed files are re-vehicled rather than removed (spec 005's lesson: its fall was smaller than planned for this reason); the double's tests are new |
| Tests | 2,007 | −40 to −100 | The AWS family's 31 and the AWS-only cases leave; the double's cases and the mechanism's added cases are new |
| Contract protocol members | 0 changed | 0 | none |
| Golden files (shared) | 117 | the figure spec 008 leaves, less the 58 AWS files, plus what the second docker runtime adds | none expected beyond the second docker runtime's files, read file by file |

The AWS family's repository starts from its one commit and holds what
left here (3,632 source lines, the 651 lines of its own tests, the
AWS-only files), plus its pipeline tests, fixture and golden.

### Statements this change makes false (Principle X)

From the inventory of 2026-11-19 (research R3, R8 to R10), re-read on
2026-11-21:
`README.md`, `docs/PLUGINS.md`, `docs/DAILY_DRIVER.md` (and its quoted
sync command), `docs/OPERATIONS.md` (its "Installing a release" section
gains the AWS family; its quoted sync command; its rows for
`AWS_ROLE_ARN`, the federated-credentials step and the `[noaa]` shim),
`docs/CONFIGURATION.md` (its AWS field tables
move to the AWS family's repository), `docs/DESCRIPTION.md`,
`docs/DESIGN.md`, `GOLDEN.md` (this repository's providers),
`docs/CI_RUNNER.md` (the runner image keeps the AWS CLI, for
configurations), `docs/INCIDENTS.md` and
`docs/CHANGES.md` (links only, pointed at the AWS family's repository at
its `v0.2.0` tag), the READMEs of `tofu-roots`, `base`,
`hashicorp-utils` (these three are inside published SDK wheels:
research R13), `contract` (its namespace example stays true and is left
alone), `system`, `packer-plugin`, `docker-plugin`, `default-os-plugin`,
`local-state-plugin`, the fixture's README and `overlays/README.md`
(`aws-cycle-decommission.yaml` leaves),
`src/cs_image_system/extras.py` and its test (the
`aws` extra's words), the root `pyproject.toml`, `.vscode/settings.json`,
the `Justfile` (`init`'s sync rule and comment, `gcloud-with`,
`test-cloud-starters`, `full-test-legs`' messages, `fixture-live`'s
comment), `scripts/release.py` (`SYNC` and its messages),
`scripts/with-released-families` (its docstring names one family),
the workflows' `live` jobs (the AWS identity steps, the gate's list and
its SKIPPED line go: research R10), the starters' and `_skeleton`'s
CI_SETUP.md (where they say the AWS family comes from this repository), and
the reference configuration's CI_SETUP.md and README (the advice to
drive the tree with the development checkout's venv, already false since
spec 005's T067).

In the Google Cloud family's repository, whose READMEs are now its own:
the links into this repository's AWS packages
(`packages/gcloud-runtime-plugin/README.md`,
`packages/gcs-state-plugin/README.md`, `packages/tf-gcp-plugin/README.md`)
point at the AWS family's repository; they reach PyPI with that
family's next release, which this specification does not cut.

## Project Structure

### Documentation (this feature)

```text
specs/007-relocate-aws-provider/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/aws-family-repository.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
# this repository
packages/{aws-runtime-plugin,tf-ebs-instance-plugin,tf-s3-state-plugin}/   # phase 1: ranges, aws_runtime/testing.py; phase 3: removed
packages/system/src/cs_image_system/system/testing/                          # phase 1: the cloud-shaped double runtime and its storage (R6)
packages/system/tests/{fixture,golden}/, packages/system/tests/test_*.py     # phase 1: the double's declarations and tests (test-core)
tests/harness.py                    # phase 1: the AWS stubs out (into aws_runtime/testing.py), docker as the default vehicle
tests/starter_support.py            # phase 1: a word is read by its classification (R9)
tests/fixtures/config               # phase 1: a second docker runtime and a second local backend; phase 3: the AWS declarations leave
tests/test_*.py                     # phase 1: the 80 files re-vehicled or split (R5); phase 3: the AWS-only files leave
tests/cloud_starters/               # phase 3: standard-aws and standard-aws-posix join, on the AWS family's own stubs
scripts/with-released-families, scripts/release.py                           # phase 3: `aws` released elsewhere (R12)
tests/test_with_released_families.py, test_package_metadata.py, test_extras.py, test_release_whole.py, test_release_script.py   # phase 3 (R12)
pyproject.toml, .vscode/settings.json, Justfile, .github/workflows/*.yml, docs/**, README.md, packages/*/README.md

# the AWS family's repository (spec 005's layout)
packages/{aws-runtime-plugin,tf-ebs-instance-plugin,tf-s3-state-plugin}/
tests/{fixture,golden,pipeline,tooling,live}/
scripts/{full-test-legs,release}
pyproject.toml, Justfile, REUSE.toml, LICENSES/, docs/, .github/workflows/ci.yml
```

**Structure Decision**: the AWS family's repository copies the Google
Cloud family's (spec 005, research R5), its scripts and Justfile
included; this repository loses three more workspace members.

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| 80 test files change vehicle, 13 of them and two cases a second time (spec 005 moved those onto AWS) | AWS stays here throughout spec 005; it leaves now, and the core's proofs must stay here | Moving them straight to docker in spec 005 would have changed spec 005's scope; the operator chose to let spec 005 finish on AWS |
| A test-double runtime and storage in the test kit (R6, the operator's decision), a second runtime type beside today's container double | Ten core behaviours have no counterpart on docker (R6); the container double cannot take a cloud runtime's capabilities without changing the core golden it already emits | Without it, a core rule is proven only from the AWS family's repository, against released code |
| Spec 008 lands before this specification's phase 1 (R7) | Six of the shared fixture's eight images are Okta-owned, and the core refuses those on a container runtime | Re-vehicling only the POSIX images' tests first splits phase 1 in two and moves the same files twice |
| Three releases again (R1), each after the operator's word | The AWS family's SDK ranges and `aws_runtime.testing` must be on the index before its repository stands alone; the umbrella's `aws` extra must name a release that exists | As spec 005: a path source to a sibling checkout hides the coupling the move removes |

## Definition of done (constitution 1.2.0)

`/speckit-tasks` ends the task list with these, in order, each with a
record of what was done and its evidence:

1. `/speckit-converge` after the last implementation task, and every
   task it appends done.
2. The quickstart walked step by step on the final code, each result
   recorded, and any box it corrects bumped.
3. The squash-merge of `feature/007-relocate-aws-provider` into
   `develop`, the branch kept; the AWS family's own branch squashed
   into its `develop` the same way.
4. The releases of research R1, each the operator's: this repository's
   phase 1 release, the AWS family's 0.2.0 to PyPI, this repository's
   phase 3 release; every run each one starts passed (`just
   release-watch <version>`); the reference has taken the phase 3
   release (`UV_REFRESH=1 just take <version>`) with its drift check
   green.
5. `spec.md`'s status line and the row for 007 in `specs/README.md`
   say **complete**, with the date.

## Decisions in this plan

**Chosen** by this plan (the operator may overturn any): research R1
(the order), R6 placement (the double's tests in `test-core`, a second
double runtime type), R9 (the starters' selection fixed in phase 1; the
two AWS starters in `tests/cloud_starters`; the `complete` dry-run
defect of spec 005's T078 recorded, not fixed), R10 (the AWS identity
steps leave both workflows), R11 (the line from 0.2.0, PyPI only), R12
(the mechanism extended; `gcloud-with` renamed `families-with`), R13
(the SDK bumps; the contract left alone).

**YOUR DECISION** (the operator's, each with its default):

- **Spec 008 before phase 1** (research R7). Default: yes, spec 008
  lands wholly before this specification's branch starts.
- **The repository secret and the role's trust** (research R10).
  Default: after the phase 3 release reaches `main`, the operator
  removes `AWS_ROLE_ARN` from this repository and the role's trust of
  it, and adds both for the AWS family's repository before its `live`
  job is first dispatched.
- **The destination's default branch** (research R4). Default: set it
  to `develop`, as the Google Cloud family's is.
- **An AWS live cycle** (spec, edge case). Default: none.
- **The spec amendments** below. Default: amend FR-008 and the edge
  case as written there.

## Spec statements to amend

Three statements of [spec.md](spec.md) are no longer true or are
contradicted by a decision the operator made after the spec was written.
The plan follows the decision; amending the spec is the operator's, as
spec 005's SC-005 was (its T079).

- **FR-008** says a behaviour docker cannot show is carried to the AWS
  family's repository or stated as no longer proven here. The operator's
  R6 (a) proves it here, on the test kit's double. Proposed: "...MUST be
  named, and proven here on the test kit's double runtime or storage
  (research R6)".
- **Edge case, the live jobs**: it says the starters' check validates
  with an AWS identity. It needs none (spec 005's T077: its clouds are
  stubbed); only `fixture-live` takes the AWS identity, and after phase
  3 no step does. Proposed: "...once the AWS family's declarations
  leave, no step here takes the AWS identity, and it is removed".
- **Why, "No destination exists yet"**: the operator created it on
  2026-11-19 (research R4). Proposed: a dated note, nothing rewritten.

## Operator decisions of 2026-11-21

Asked one at a time after planning; each supersedes the default above where they differ.

- Spec 008 lands wholly before phase 1; then spec 003; then this specification.
- The AWS identity moves as spec 005's did: set for `cs-image-system-aws` before its first live dispatch; this repository's removed after phase 3's release reaches `main`.
- The new repository's default branch becomes `develop`.
- No live AWS cycle.
- The spec is amended as this plan wrote it (FR-008, the live-jobs edge case, the destination line).
