# Contract: a CI job's gate on its secrets

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R16, R17

The gate step of the `live` job in
[ci.yml](../../../.github/workflows/ci.yml) and
[ci-from-scratch.yml](../../../.github/workflows/ci-from-scratch.yml),
and of the `publish` job in `ci.yml`. The starters' workflows are not
changed (research R17).

## The rule

| Event | Secrets | The job |
| --- | --- | --- |
| `pull_request` | any | not started (`if: github.event_name != 'pull_request'`): GitHub shows it **skipped**, which is neither success nor failure and blocks nothing |
| any other | every one the job needs is set and not empty | runs its steps |
| any other | one or more missing or empty | **fails** at the gate, one line naming each: `<job>: FAILED -- these secrets are missing or EMPTY: <names> (no step ran)` |

The `publish` job needs `TEST_PYPI_TOKEN` for every tag, and also
`PYPI_TOKEN` and `STARTER_PUSH_TOKEN` for a final one.

## What the job's steps add

`just fixture-live` fails without docker, as the full test run's legs
do: a `live` job that could not run its modification tests is red.

## What never happens

- A gate step that exits 0 without setting `ready=true`.
- The words `SKIPPED` in a job's summary for a job that ran its gate.
