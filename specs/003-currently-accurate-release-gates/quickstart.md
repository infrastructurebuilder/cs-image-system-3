# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contracts**: [contracts/](contracts/)

Each step is a command that passes or fails. Steps 1 to 6 publish
nothing, push nothing and change no machine's power state: a
prerequisite is taken away from one command by its environment
(`DOCKER_HOST` pointed at no daemon, `CSIS_CONFIG_ROOT` at an empty
directory), never by stopping anything. Every box runs on your local
machine at this repository's root on
`feature/003-currently-accurate-release-gates`, unless it says
otherwise. Step 7 is the next real release.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The acceptance tests skip nothing | Story 2; FR-001; SC-002 |
| 2 | A full test run with a prerequisite missing fails and names what did not run | Story 2, scenarios 1 and 3; FR-002, FR-004; SC-002, SC-003 |
| 3 | The same run, asked to exclude by name, passes and says what it left out | Story 2, scenario 2; FR-003, FR-004; SC-003 |
| 4 | A release refuses an exclusion, and refuses without a prerequisite, publishing nothing | Story 1, scenarios 1 and 4; FR-006, FR-007; SC-001 |
| 5 | The release family's scenarios under its stubbed shell: a session lapsing during the gate, the remote moving during it, the finish after a refused push, the record, the watcher's missing run, the CI gates | Stories 1, 3, 4, 5; FR-007 to FR-011, FR-013 to FR-015; FR-005; SC-001, SC-004, SC-005 |
| 6 | Publishing the starters again after a partial publish finishes the rest | Story 5, scenario 1; FR-012; SC-006 |
| 7 | The next real release walks with no step done by hand | SC-008 |

## Step 1: the acceptance tests skip nothing

About 25 minutes.

```sh
# step 1 -- box 1 of 1 -- v1
just test 2>&1 | grep -E "passed|skipped|failed" | tail -3
```

Expect the main run's line to say `passed` with no `skipped` count, and
each isolated run `0 skipped`. Before this feature the main run said
`23 skipped`.

## Step 2: a missing prerequisite fails the run

About 2 minutes: no leg that needs docker or the reference starts.

```sh
# step 2 -- box 1 of 1 -- v1
empty=$(mktemp -d); DOCKER_HOST=unix:///nonexistent CSIS_CONFIG_ROOT="$empty" just full-test-legs; echo "exit $?"
```

Expect `DID NOT RUN` lines naming the `docker` legs and the
`reference` legs with their causes, the last leg line
`full-test: FAILED -- 2 run, 0 excluded on request, 10 failed`, and
`exit 1`. The two that ran are the network legs (`dev-pin-resolves`,
`test-cloud-starters`).

## Step 3: the same run, excluding by name

About 2 minutes.

```sh
# step 3 -- box 1 of 2 -- v1
empty=$(mktemp -d); DOCKER_HOST=unix:///nonexistent CSIS_CONFIG_ROOT="$empty" just full-test-legs without=docker,reference; echo "exit $?"
```

Expect `full-test: EXCLUDED on request (without=docker,reference): ...`
naming ten legs, then `full-test: passed WITH EXCLUSIONS -- 2 run, 10
excluded on request, 0 failed`, and `exit 0`.

```sh
# step 3 -- box 2 of 2 -- v1
just full-test-legs without=dokcer; echo "exit $?"
```

Expect the refusal of the misspelt name, no leg started, and `exit 2`.

## Step 4: a release refuses what it cannot check

Under a minute each. Run on `develop` with a clean tree: the first box
refuses before anything, the second is the dry form (it needs the index
token in the environment, as every release does), the third shows that
nothing changed.

```sh
# step 4 -- box 1 of 3 -- v1
just release patch test without=docker; echo "exit $?"
```

Expect `release: 'without=docker' is not an argument of release; a
release has no optional checks ...` and `exit 2`.

```sh
# step 4 -- box 2 of 3 -- v1
DOCKER_HOST=unix:///nonexistent just release patch test yes; echo "exit $?"
```

Expect the probe's refusal `docker is not answering (docker info) --
... the gate would fail at it ... nothing was changed` and a non-zero
exit.

```sh
# step 4 -- box 3 of 3 -- v1
git status --short | wc -l
```

Expect `0`.

## Step 5: the release family's scenarios

About 3 minutes. These are the rehearsals of research R18: the release,
its finish and the watcher run with every command stubbed, and each
case asserts what was and was not sent (no upload after a failed gate,
no upload after the remote moved, one finish after a refused push, the
missing run settled five minutes after the others, a dispatched run
accepted, the tag pushed by name, the take's `UV_REFRESH=1`); the CI
gates run with the secrets absent and fail.

```sh
# step 5 -- box 1 of 1 -- v1
just test-one tests/test_release_script.py tests/test_release_watch.py tests/test_release_probes.py tests/test_ci_workflow.py tests/test_justfile_contract.py -q 2>&1 | tail -1
```

Expect a line of passed tests with no `skipped` and no `failed`.

## Step 6: the starters, published again

About 5 minutes. Needs the network (the starters' modules come from the
index). Run on a checkout whose version is final (`develop` right
after a final release).

**YOUR DECISION**: which two repositories hold the tag already. Default:
the first two `scripts/starter-tree --list` prints.

```sh
# step 6 -- box 1 of 2 -- v1
v=$(uv run --no-sync bump-my-version show current_version); base=$(mktemp -d)
uv run --no-sync python scripts/starter-tree --list | while read -r name repo; do git init -q --bare "$base/$repo.git"; done
uv run --no-sync python scripts/starter-tree --list | head -2 | while read -r name repo; do d=$(mktemp -d); git -C "$d" init -q -b main && git -C "$d" commit -q --allow-empty -m seed && git -C "$d" tag "v$v" && git -C "$d" push -q "$base/$repo.git" main "v$v"; done
echo "$base"
```

Expect the scratch directory's path, which the next box uses.

```sh
# step 6 -- box 2 of 2 -- v1
CSIS_STARTER_REMOTE="file://<the path above>" just publish-starters yes; echo "exit $?"
```

Expect two lines `already holds v<version> -- done, left alone`, one
`dry -- ... would take v<version>` line for each other repository, and
`exit 0`.

## Step 7: the next real release

About 75 minutes for the release, then up to 60 for the watch. This is
the operator's release (the plan's decision D6).

**YOUR DECISION**: the release that carries this feature. Default: the
next final release to PyPI, with the take pushing main.

```sh
# step 7 -- box 1 of 2 -- v1
just release-take patch pypi main
```

Expect the release commit's body to list every check of the gate as
`ran and passed` (`git show -s v<version>`), and the take's closing line.

```sh
# step 7 -- box 2 of 2 -- v1
just release-watch <version>
```

Expect one verdict line per run and
`release-watch: every run the walk started passed, and what it published is there`.
Record any step done by hand that the walk did not plan; SC-008 holds
when there is none.
