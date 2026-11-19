# Implementation Plan: The Okta identity plugin in a repository of its own

**Branch**: `feature/008-relocate-okta-plugin` (to be created from `develop` once spec 005 is merged) | **Date**: 2026-11-19 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/008-relocate-okta-plugin/spec.md`

## Summary

`cs-image-system-okta-opa-plugin` leaves this workspace for
`infrastructurebuilder/cs-image-system-okta`, with its history, and
stands alone by spec 005's pattern. Its group, user and lookup roots,
commands and setup section are proven there on the SDK and the test kit
alone; its instance-side behaviour (enrollment, activation, the login
proof, its golden) on a small fixture of its own with the AWS family
from the index, as a replaceable test dependency of that suite alone
(the operator's decision and note). Here, the shared fixture's groups
become POSIX, the harness loses its Okta stubs, and the core's identity
seams stay proven through the POSIX identity plugin.

It follows spec 005 and runs before spec 007's phase 3 (research R2).

## Technical Context

**Language/Version**: Python 3.13

**Primary Dependencies**: as spec 005; for the instance suite there, the
AWS family from PyPI (`>=0.1.11,<0.3`)

**Storage**: N/A

**Testing**: pytest under the test kit's strict session there; `just
test` with its isolated runs here

**Target Platform**: the operator's local machine; GitHub Actions

**Project Type**: a plugin moving to its own repository

**Performance Goals**: N/A

**Constraints**: no identity root is ever applied; no OPA group or user
is ever destroyed; never echo an Okta credential; releases and the
destination's settings are the operator's

**Scale/Scope**: one distribution, 4,152 source lines, 71 own tests; 50
test files here name Okta (27 import the plugin); 14 identity golden
files leave and the bakes' and instance roots' Okta lines change; the
shared fixture's Okta groups and users become POSIX

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | How this plan meets it | Result |
| --- | --- | --- |
| I. Purpose first | A plugin author, operators | Pass |
| II. Acceptance is executable | Quickstart; both repositories' `just test`; the reference's drift check with no OPA change | Pass |
| III. Nothing irreversible by default | No identity root applied; the drift check proves no OPA change | Pass |
| IV. The emission is the contract | Every changed golden file read file by file; the plugin's own golden compared with the shared one before anything here moves | Pass |
| V. Public by construction | Both repositories public; no credential in any test | Pass |
| VI. Layers and no interference | The plugin's tests depend on another plugin (the AWS family) only in its instance suite, by the operator's decision, named and replaceable; the core's identity seams stay proven here | Pass, with the recorded cost |
| VII. Budget | Workspace packages −1; source lines about −4,150; tests here fall by the plugin's 71 and the Okta-only cases | Pass |
| VIII. One source per fact | Installing the plugin stated once | Pass |
| IX. Tests guard behaviour | Moved tests keep their assertions | Pass |
| X. What a change makes false | `README.md`, `docs/PLUGINS.md`, `docs/DAILY_DRIVER.md`, `docs/OPERATIONS.md`, `docs/CONFIGURATION.md` (its Okta field tables move), the fixture's README, the posix-identity plugin's README ("beside Okta"), the starters' and `_skeleton`'s CI_SETUP.md, the root manifest, `.vscode/settings.json`, the workflows' comments, the reference's CI_SETUP.md | Pass |

## Project Structure

### Documentation (this feature)

```text
specs/008-relocate-okta-plugin/
├── plan.md, research.md, data-model.md, quickstart.md
├── contracts/okta-repository.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code

```text
# this repository
packages/okta-opa-plugin/              # phase 1: ranges, okta_opa_plugin/testing.py; phase 3: removed
tests/harness.py                       # phase 1: the Okta stubs out
tests/fixtures/config/groups, cfg/group-builders.yml   # phase 3: POSIX
tests/test_*.py                        # phase 3: the Okta-only cases leave, the mixed ones lose their Okta part

# the Okta plugin's repository
packages/okta-opa-plugin/              # with history
packages/okta-opa-plugin/tests/      # its own suite, where it is today
tests/instance/{fixture,golden}/
pyproject.toml, Justfile, REUSE.toml, LICENSES/, scripts/, docs/, .github/workflows/ci.yml
```

## Complexity Tracking

| Cost | Why needed | Simpler alternative rejected because |
| --- | --- | --- |
| The plugin's instance suite depends on the AWS family from the index | The configured Okta is reached from AWS today (the operator's decision) | The test kit's double was the alternative; the operator chose AWS, noting it may change, so the dependency is confined to one suite |
