# Data model: Release gates that cannot report a pass they did not earn

**Feature**: [spec.md](spec.md) | **Decisions**: [research.md](research.md)

No record or field of the system's configuration changes, and nothing
the system emits. What this feature defines are the release tooling's
own records: the legs of the full test run, an exclusion, a run's
summary, an expected CI run and a release's record.

## Leg (a check)

One row of the leg table in [scripts/release.py](../../scripts/release.py),
the one source; `just full-test-legs list` prints it (research R2, R3).

| Field | Meaning | Rule |
| --- | --- | --- |
| `name` | the leg's name, as the recipe it runs (`test-mods`, `dry-run-all`) | unique; an exclusion may name it |
| `needs` | the prerequisites: none, `docker`, `reference`, or both | a prerequisite is checked once per run, before the first leg that needs it |
| `command` | what the leg runs, through the script's `run` callable | its exit status is the leg's verdict |

The table, in run order (research R5; R7 keeps the Podman legs out):

| Leg | Needs |
| --- | --- |
| `dry-run-all` | `reference` |
| `state-query-strict` | `reference` |
| `test-mods` | `reference`, `docker` |
| `dev-pin-resolves` | none (the network) |
| `test-cloud-starters` | none (the network) |
| `test-docker-install` | `docker` |
| `test-docker-live` | `docker` |
| `test-posix-accounts` | `docker` |
| `test-bake-steps` | `docker` |
| `runner-image` | `docker` |
| `test-docker-bake` | `docker` |
| `test-docker-cycle` | `docker` |

## Prerequisite

| Name | Present when |
| --- | --- |
| `docker` | `docker info` exits 0, and `packer`, `ansible-playbook` and `tofu` are on PATH |
| `reference` | `<config_root>/cfg/_config.yml` exists, `just preflight` exits 0, and the identity credentials the reference's identity roots read are set and not empty (research R8) |

A prerequisite that is absent makes every leg that needs it, and was
not excluded, a leg that **did not run**: a failure, named with the
cause and with the word that would exclude it.

## Exclusion

| Field | Meaning | Rule |
| --- | --- | --- |
| names | the words after `without=`, split on commas | each a leg's or a prerequisite's name; any other name refuses the run (exit 2) before a leg starts |
| source | the command line of this one run | never the environment, a file or an absent tool (FR-003) |

A release accepts none: `release.py` refuses any word it does not know
(research R9).

## Run summary

| Field | Meaning |
| --- | --- |
| run | legs that ran (passed or failed) |
| excluded | legs left out on request, with the names that left them out |
| failed | legs that ran and failed, plus legs that did not run and were not excluded |
| result | `passed` (excluded = 0, failed = 0), `passed WITH EXCLUSIONS` (excluded > 0, failed = 0), `FAILED` (failed > 0) |

run + excluded + failed counts each leg once; a leg that did not run is
in failed, not in run. The line formats are
[contracts/full-test-verdict.md](contracts/full-test-verdict.md).

## Expected run (the watcher)

[scripts/release-watch](../../scripts/release-watch)'s `Expected`, with
one field added (research R12).

| Field | Meaning | Rule |
| --- | --- | --- |
| `label`, `cwd`, `commit`, `workflow`, `branch`, `kind`, `found` | as today | unchanged |
| `file` | the workflow's file (`ci.yml`, `ci-from-scratch.yml`) | the remedy names it |

A run is settled as never started either at the timeout, as today, or
five minutes after the first run of the same repository and commit was
found, whichever comes first. Its line carries the remedy:
`GH_PAGER=cat gh workflow run <file> --ref <branch> -R <owner/repo>`.

## Release record

The body of the release commit `release <version>` (research R9):

```text
release 0.1.13

gate (pypi): full-test, no exclusions
  test: ran and passed
  dry-run-all: ran and passed
  state-query-strict: ran and passed
  ...
  test-docker-cycle: ran and passed
```

For a TestPyPI release the gate is `test` and `test-docker-install`.
A release whose gate did not pass makes no commit, so a record never
says a check failed or did not run.

## States of a release that `release-finish` completes (research R14)

```text
uncommitted bump, upload partial   ->  just publish <index> until every project holds it, then release-finish
uncommitted bump, upload complete  ->  release-finish: evidence, record, commit, tag, ending
committed and tagged, ending refused or interrupted  ->  release-finish: the ending (each step safe to repeat)
ending complete                    ->  release-finish refuses: nothing to finish
```
