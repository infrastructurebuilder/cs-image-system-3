# Implementation Plan: The AWS provider family in a repository of its own

**Branch**: `feature/007-relocate-aws-provider` (to be created from `develop` once spec 005 is merged) | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

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
to docker for about 50 test files.

## Technical Context

**Language/Version**: Python 3.13 (all repositories)

**Primary Dependencies**: as spec 005: uv workspaces, hatchling,
pytest, ruff, pyright, `git filter-repo`, bump-my-version; the SDK and
the test kit (`cs-image-system-system[testing]`) from the index

**Storage**: N/A (fixtures, goldens, Terraform modules as package data)

**Testing**: pytest; here `just test` with its isolated runs; there
`just test` under the strict session

**Target Platform**: the operator's local machine; GitHub Actions

**Project Type**: a compiler-like CLI with a plugin SDK; this feature
moves the second provider family out

**Performance Goals**: N/A

**Constraints**: no AWS live cycle by default; the operator's AWS
session never lasts 60 minutes (a release needs a login midway); the
emission does not move except as read file by file; releases and the
destination repository's settings are the operator's

**Scale/Scope**: three distributions, 3,632 source lines, 31 package
tests; about 53 core test files to re-vehicle (551 tests), 6 AWS-only
files (48 tests) to move; 58 golden files leave and about 8 shared ones
change; 3 starters declare AWS; the reference configuration keeps every
root's state in S3

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | A plugin author, operators, an adopting team (spec) | Pass |
| II. Acceptance is executable | Quickstart steps; both repositories' `just test`; the reference's drift check; the starters' check in CI's `live` job | Pass |
| III. Nothing irreversible by default | No live cycle; releases stop for the operator | Pass |
| IV. The emission is the contract | The AWS family's golden read file by file against the shared golden before anything here moves; the shared golden's changes read file by file | Pass |
| V. Public by construction | Both repositories public; `just public-safe` on each | Pass |
| VI. Layers and no interference | The AWS family's tests depend on no other provider family; the core's rules stay proven by the core's own tests, on the test kit's double (R6, decided (a)); the Okta plugin's instance proofs move with it (R7, decided (c), spec 008) | Pass |
| VII. Budget, subtraction | Below | Pass |
| VIII. One source per fact | Installing the AWS family stated once; its field tables move to its repository, as spec 005's did | Pass |
| IX. Tests guard behaviour | Moved and re-vehicled tests keep their assertions | Pass |
| X. What a change makes false | Listed below | Pass |

### Budget (Principle VII)

Measured when phase 1 starts (spec 005's method). Expected, this
repository: workspace packages 19 to 16; source lines about −3,600 (the
family) plus what R6 (a) adds to the test kit (a double runtime
and storage, a few hundred lines); test lines roughly level (about 50
files change vehicle; the AWS-only files and the package tests leave);
contract members 0; shared golden files 117 to about 59.

### Statements this change makes false (Principle X)

From the inventory of 2026-11-19 (research R3, R8 to R10):
`README.md`, `docs/PLUGINS.md`, `docs/DAILY_DRIVER.md`,
`docs/OPERATIONS.md`, `docs/CONFIGURATION.md` (its AWS field tables
move to the AWS family's repository), `docs/INCIDENTS.md` and
`docs/CHANGES.md` (links only), the READMEs of `tofu-roots`, `base`,
`hashicorp-utils`, `packer-plugin`, `docker-plugin`, `default-os-plugin`
and the Google Cloud family's (which name S3 for the GCE roots), the
fixture's README, `src/cs_image_system/extras.py` and its test (the
`aws` extra's words), the root `pyproject.toml`, `.vscode/settings.json`,
the workflows' `live` jobs (comments; the AWS identity stays for the
starters' check), the starters' and `_skeleton`'s CI_SETUP.md (where they
say the family comes from this repository), and the reference
configuration's CI_SETUP.md and README.

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
packages/system/src/cs_image_system/system/testing/                          # phase 1: the double runtime and storage (R6)
tests/harness.py                    # phase 1: the AWS stubs out (into aws_runtime/testing.py), docker as the default vehicle
tests/fixtures/config               # phase 1: a second docker runtime and a second local backend; phase 3: the AWS declarations leave
tests/test_*.py                     # phase 1: about 53 files re-vehicled; phase 3: the AWS-only files leave
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
| About 50 test files change vehicle a second time (spec 005 moved 13 of them onto AWS) | AWS stays here throughout spec 005; it leaves now, and the core's proofs must stay here | Moving them straight to docker in spec 005 would have changed spec 005's scope; the operator chose to let spec 005 finish on AWS |
| A test-double runtime and storage in the test kit (R6, the operator's decision) | Ten core behaviours have no counterpart on docker (R6) | Without it, a core rule is proven only from the AWS family's repository, against released code |
