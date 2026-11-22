# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contracts**: [contracts/](contracts/)

This is the walk that proves the feature, not the page it builds (that
page is `docs/QUICKSTART.md`). Each step is a command that passes or
fails. Every box runs at this repository's root on your local machine,
on `feature/first-dry-run`, with the workspace synced (`just init`).
Nothing is applied anywhere except in step 8, and only if you decide so.
Boxes that need a scratch directory make their own with `mktemp`.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The acceptance tests pass | Constitution |
| 2 | The page's own commands reach a dry run on your local machine, twice, in time | Story 1; FR-001 to FR-007, FR-010, FR-012; SC-001, SC-003, SC-004 |
| 3 | The prerequisites table is the code's | FR-002; Principle VIII |
| 4 | CI ran the page on a clean machine and recorded the time | Story 2; FR-010 to FR-012 |
| 5 | A broken command fails the run and is named | Story 2 scenario 2; SC-005 |
| 6 | Each first-run failure is one line with its remedy | Story 3; FR-013; SC-006 |
| 7 | The front page leads to the page second, and no other document repeats it | Story 4; FR-014, FR-015; SC-007 |
| 8 | Each route onward begins with a command that works | Story 4 scenario 2; FR-008 |
| 9 | A release cannot be cut without the page having run | FR-011; SC-008 |
| 10 | Someone outside the project completes the page | SC-002 |

## Step 1: the acceptance tests

About 20 minutes.

```sh
# step 1 -- box 1 of 1 -- v1
# about 20 minutes
just test
```

Expect lint clean, the type check at zero errors, and every test passing,
the isolated runs each with `0 skipped`.

## Step 2: the page on your local machine

About 5 minutes. Needs the network and a daemon that answers. Your own
installed `cs-image-system` is not touched: the recipe uses a temporary
tool directory.

```sh
# step 2 -- box 1 of 1 -- v1
# about 5 minutes: the wheels, two passes of the page
just test-quickstart --passes 2
```

Expect, last, `quickstart: passed -- 7 commands in 3 boxes, each ran and
succeeded, twice`, after a line `quickstart: the page took <s>s (limit
900)` with a number under 900.

## Step 3: the table is the code's

Under a minute.

```sh
# step 3 -- box 1 of 1 -- v1
just quickstart-table check
```

Expect exit 0 and the line `quickstart: the prerequisites table matches
cfg/executables.yml and uv's floor`.

## Step 4: CI ran it on a clean machine

A few minutes after the branch is pushed (pushing is yours).

```sh
# step 4 -- box 1 of 1 -- v1
id=$(GH_PAGER=cat gh run list --branch feature/first-dry-run --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')
GH_PAGER=cat gh run view "$id" --log | grep -E "quickstart: (the page took|passed|FAILED)"
```

Expect two `the page took <s>s (limit 900)` lines and one `passed --`
line, and no `FAILED`.

## Step 5: a broken command fails and is named

About 3 minutes.

```sh
# step 5 -- box 1 of 1 -- v1
broken=$(mktemp -d)/QUICKSTART.md && sed 's/run --all/run --al/' docs/QUICKSTART.md > "$broken"
just test-quickstart --page "$broken" 2>&1 | grep -E "quickstart: (FAILED at|FAILED --)"
```

Expect `quickstart: FAILED at box 3 of 3: cs-image-system --root-dir
csis-quickstart run --al (exit 2)` and a `FAILED --` verdict. The CI
half of SC-005 is step 4 run on a scratch branch holding the same
change: its `quickstart` job fails, naming the same command.

## Step 6: the first-run failures

About 4 minutes. The boxes share a scratch directory made in box 1, and
run the workspace's command (`.venv/bin/cs-image-system`), not your
installed one.

```sh
# step 6 -- box 1 of 6 -- v1
qs=$(mktemp -d); CS="$PWD/.venv/bin/cs-image-system"
"$CS" init-config "$qs/t" --from standard-docker >/dev/null
mkdir "$qs/bin" && for t in docker tofu bash ansible-playbook; do ln -s "$(command -v $t)" "$qs/bin/$t"; done
PATH="$qs/bin:/usr/bin:/bin" "$CS" --root-dir "$qs/t" validate 2>&1 | grep "packer:"
```

Expect one line: `packer: binary 'packer' not found (declared in
cfg/executables.yml; an absolute path, or a name on PATH) -- install it
(where each tool comes from: the daily driver, section 1.2)`.

```sh
# step 6 -- box 2 of 6 -- v1
printf '#!/bin/sh\necho "0,,version,1.13.0"\necho "Packer v1.13.0"\n' > "$qs/bin/packer" && chmod +x "$qs/bin/packer"
PATH="$qs/bin:/usr/bin:/bin" "$CS" --root-dir "$qs/t" validate 2>&1 | grep "does not meet"
```

Expect `packer 1.13.0 does not meet its requirement >=1.14
(cfg/executables.yml)`.

```sh
# step 6 -- box 3 of 6 -- v1
# about a minute: the dry run gets as far as the pull
DOCKER_HOST=unix:///nonexistent.sock "$CS" --root-dir "$qs/t" run --all 2>&1 | grep -m1 "cannot be reached"
```

Expect one line naming `docker runtime docker-main` and `cannot be
reached`, followed on the same line by the remedy, which begins "the
runtime's daemon must answer".

```sh
# step 6 -- box 4 of 6 -- v1
# about a minute: a bare install from the index into a scratch tool directory
UV_TOOL_DIR="$qs/tools" UV_TOOL_BIN_DIR="$qs/tbin" uv tool install --quiet cs-image-system
"$qs/tbin/cs-image-system" --root-dir "$qs/t" validate 2>&1 | grep "install the extra"
```

Expect a line ending `install the extra: uv tool install
'cs-image-system[docker]'`.

```sh
# step 6 -- box 5 of 6 -- v1
UV_TOOL_DIR="$qs/tools2" UV_TOOL_BIN_DIR="$qs/tbin2" uv tool install --quiet 'cs-image-system[docker]==0.1.11'
UV_TOOL_DIR="$qs/tools2" UV_TOOL_BIN_DIR="$qs/tbin2" uv tool install --quiet --upgrade 'cs-image-system[docker]'
"$qs/tbin2/cs-image-system" --version
```

Expect the newest release on PyPI, not `0.1.11`.

```sh
# step 6 -- box 6 of 6 -- v1
echo 0.1.0 > "$qs/t/.csis-version"
"$CS" init-config "$qs/t" --from standard-docker 2>&1 | tail -1
```

Expect `init-config: <the directory> already holds a configuration this
release did not write; to start over remove it, or keep it and refresh
the release's files with --force`.

## Step 7: the way in

Under a minute.

```sh
# step 7 -- box 1 of 2 -- v1
sed -n '/^## Where to start/,/^## The Justfile/p' README.md | grep -m2 '^- ' | cut -c1-40
```

Expect two lines, the first naming `docs/DESCRIPTION.md`, the second
`docs/QUICKSTART.md`.

```sh
# step 7 -- box 2 of 2 -- v1
git grep -l -e "init-config csis-quickstart" -e "root-dir csis-quickstart validate" -- . ':!specs'
```

Expect the single line `docs/QUICKSTART.md`.

## Step 8: the routes onward

Each route's page begins with a command that works. Boxes 1 and 2 use a
scratch tool directory and take a minute or two each.

```sh
# step 8 -- box 1 of 3 -- v1
r=$(mktemp -d); UV_TOOL_DIR="$r/tools" UV_TOOL_BIN_DIR="$r/bin" uv tool install --quiet --upgrade 'cs-image-system[aws,okta]'
"$r/bin/cs-image-system" init-config "$r/aws" --from standard-aws | tail -1
```

Expect `init-config: next: git init, just init, then replace every
REPLACE-ME ...` (the cloud starters' route, its README's first box).

```sh
# step 8 -- box 2 of 3 -- v1
mkdir "$r/own" && git -C "$r/own" init -q -b develop && "$r/bin/cs-image-system" init-config "$r/own" | tail -1
```

Expect the same `init-config: next:` line (a team's own repository, the
daily driver's section 1.9).

**YOUR DECISION**: run the first real local run (default: **yes**, on
your local machine; about 10 minutes; it bakes two images and stands one
container and one volume on your daemon, then takes them down). It is
the docker starter's README, "A first real run", walked in a copy of the
quickstart's tree; the box below is its first command, and the section's
own last box is the teardown, which you run next.

```sh
# step 8 -- box 3 of 3 -- v1
# about 10 minutes: two bakes and a container
CS="$PWD/.venv/bin/cs-image-system"; t=$(mktemp -d)/csis-quickstart && "$CS" init-config "$t" --from standard-docker >/dev/null
(cd "$t" && "$CS" --overlay overlays/launch.yaml --no-dry-run run --all 2>&1 | tail -1)
```

Expect `Run <id> completed: ...`. Then run the section's teardown box
and check its last line as the README says.

## Step 9: a release runs the page first

About a minute. The release script's tests hold the commands each gate
runs, with a stubbed shell; nothing is released.

```sh
# step 9 -- box 1 of 1 -- v1
just test-one tests/test_release_script.py tests/test_ci_workflow.py -q
```

Expect every test passing: among them, the TestPyPI gate runs `just
test-quickstart` exactly once, and CI's `publish` job needs the
`quickstart` job. After the next real release, step 4 run against its
tag shows the tag's `quickstart` job passed before `publish` ran
(SC-008).

## Step 10: someone outside the project

Not a box: a record. **YOUR DECISION** (research D2): who walks the
released page and on what machine (default: a member of an adopting
team, on their own macOS machine, after the next release). They follow
`docs/QUICKSTART.md` as published, unaided; the record, under the
spec's tasks, gives the date, the machine, the minutes taken (15 or
fewer passes SC-002) and every place they hesitated.
