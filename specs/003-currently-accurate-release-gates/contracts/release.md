# Contract: the release, its finish, the starters and the watcher

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R9 to R15

What changes in the release walk's commands. Everything not named here
behaves as today.

## `just release <target> [test|pypi] [yes]` and `just release-take`

| Case | Exit | What is said | What changed |
| --- | --- | --- | --- |
| a word other than the target, the index, `yes` or `no` (for `release-take`: `main`, `yes`) | 2, first | `release: '<word>' is not an argument of release; a release has no optional checks: its gate runs every check its index requires` | nothing |
| the gate failed or a check did not run | the gate's | the gate's own lines (the full test run's verdict) and the return to the starting branch | nothing; the checkout is back where it started |
| after the gate, origin holds a commit a pushed branch lacks | 1 | the fetch probe's refusal, `BEHIND_ORIGIN`, then the return line | nothing |
| after the gate, `release-take` only: the reference's sessions | 2 | `release-take: a runtime session the take needs is absent or expired (just preflight there says which) -- nothing was changed` | nothing |
| the gate passed | 0 at the end | as today | the release commit's body is the record (below) |

The order after the probes: the move from develop, the sync, the
probes, the gate, the index again, **the fetch probe again**, **(take)
the reference's `just preflight`**, then the bump. A refusal at any of
them returns the checkout to its starting branch (`go_back`).

### The record

The body of the commit `release <version>`:

```text
gate (<index>): <gate>, no exclusions
  <check>: ran and passed
  ...
```

`<gate>` is `full-test` for PyPI and `test, test-docker-install` for
TestPyPI; one line per check, in the order run.

## `just release-finish [test|pypi]`

| Starting state | What it does |
| --- | --- |
| the bump uncommitted, every project holds the version | as today: the evidence (PyPI), the record row, the commit, the tag, the ending |
| HEAD is `release <version>`, tagged `v<version>`, the tree clean, every project holds the version | the ending alone: `git push origin <cut> v<version>`, develop checked out, fast-forwarded and pushed, the sync |
| the ending already complete (origin holds the commit and the tag, develop level) | refuses: `release-finish: <version> is released and pushed; there is nothing to finish` |

A failed step of the ending, in `release` or `release-finish`, says:

```text
<who>: <version> is on <index>, committed and tagged v<version> here, but `<step>` failed (above); finish it with: just release-finish <index>
```

## `just publish-starters [yes]`

| Repository | Line |
| --- | --- |
| already holds `v<version>` | `publish-starters: <repo> already holds v<version> -- done, left alone` |
| does not | built, gated and pushed as today |

Exit 0 when every repository holds the tag at the end. The repositories
are reached at `<starter_remote>/<owner>/<repo>.git`, where
`starter_remote` is `CSIS_STARTER_REMOTE` or `https://github.com`.

## `just release-watch <version>`

A run that does not exist, once another run of the same repository and
commit was found five minutes before:

```text
release-watch: <label>: NEVER STARTED -- no run of <workflow> on <branch> for <commit> five minutes after the others started; start it: GH_PAGER=cat gh workflow run <file> --ref <branch> -R <owner/repo>
```

A run started by that command (event `workflow_dispatch`, the same
commit and branch) is the expected run. The timeout, the other verdicts
and the exit codes are as today.
