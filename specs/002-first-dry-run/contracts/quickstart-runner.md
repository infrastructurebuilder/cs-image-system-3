# Contract: `scripts/quickstart` and its recipes

**Feature**: [spec.md](../spec.md) | **Decisions**:
[research.md](../research.md) R6 to R11

A script in `scripts/`, run by `uv run --no-sync python`, and the
recipes that wrap it. It replaces `scripts/isolated-run --install-check`
and `just test-docker-install` (R9).

## Commands

```text
scripts/quickstart run [--page PATH] [--passes N] [--limit SECONDS] [--keep DIR]
scripts/quickstart prerequisites [--write | --check] [--page PATH]
scripts/quickstart prepare --into DIR
```

| Command | Does | Exit |
| --- | --- | --- |
| `run` | Builds this workspace's wheels; makes a temporary working directory and tool directory; runs the page's commands (default `docs/QUICKSTART.md`) in one bash session with `UV_OVERRIDE` naming the built wheels; checks the installed version after the first command; `--passes 2` runs the page a second time in the same directory; `--keep DIR` copies the emitted `csis-quickstart/generated` there | 0 passed; 1 a command failed, the page has no box or more than ten commands, the version check failed, or the time limit was passed; 2 the run could not start (the wheels did not build, bash is absent) |
| `prerequisites` | Prints the page's prerequisites table from the docker starter's `cfg/executables.yml` and uv's floor; `--write` replaces the table between the page's markers; `--check` compares | 0 the same (or written); 1 different, naming the first differing row |
| `prepare` | Linux x86_64 only: downloads uv, the static docker CLI, OpenTofu and Packer at exactly the floors `prerequisites` prints, each checked against its vendor's published checksum, into `DIR/bin` | 0 every tool installed and answering its version; 1 otherwise, naming the tool |

## What `run` prints

```text
quickstart: built <n> wheels of <version> in <s>s (not counted)
quickstart: box 1 of 3: uv tool install --upgrade 'cs-image-system[docker]'
...
quickstart: installed cs-image-system <version>, the build under test
quickstart: box 1 of 3 took <s>s
...
quickstart: FAILED at box M of K: <the command> (exit N)            on a failure, then the verdict
quickstart: the page took <s>s (limit 900)
quickstart: pass 1 of 2 passed
quickstart: passed -- <c> commands in <K> boxes, each ran and succeeded, twice
```

The last line is the verdict, `passed -- ...` or `FAILED -- <why>`. A
command that did not run because an earlier one failed is reported as
not run; a verdict of `passed` needs every command to have run. In CI
(`GITHUB_STEP_SUMMARY` set) the time lines and the verdict are also
written to the job summary.

## The recipes

| Recipe | Runs | Where |
| --- | --- | --- |
| `just test-quickstart` | `scripts/quickstart run` | your local machine, `full-test-legs` (never SKIPPED), the release's gate for both indexes, the CI job with `--passes 2` |
| `just quickstart-prepare dir` | `scripts/quickstart prepare --into dir` | the CI job only |
| `just quickstart-table` | `scripts/quickstart prerequisites --write` | a maintainer, after the starter's floors change |

The CI job also runs `scripts/quickstart prerequisites --check` through
`just quickstart-table check`.

## What the tests hold

With a stubbed shell, as `tests/test_isolated_run.py` holds
`isolated-run`: the commands are read in page order with continuations
joined and comments skipped; one session carries an export into a later
box; a failing command is named with its box and exit code and later
commands are reported as not run; a page with no box fails; a page with
eleven commands fails; an install whose version is not the build's
fails; a run over the limit fails; `prerequisites` gives the floors of a
given `executables.yml`.
