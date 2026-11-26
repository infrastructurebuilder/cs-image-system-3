# Quickstart: Releases go to TestPyPI until 1.0

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

## Step 1: every lock takes the system's names from TestPyPI

About 1 minute.

```sh
# step 1 -- box 1 of 1 -- v1
just test-one tests/test_index_pins.py -q
```

Expect every `cs-image-system*` registry entry of `uv.lock` at
test.pypi.org, and the same test passing in both families' repositories.

## Step 2: a release refuses PyPI, advises, and tags without uploading

About 2 minutes.

On `develop` (a release is cut from `develop` or `main` alone, so a
feature branch is refused before the plan):

```sh
# step 2 -- box 1 of 1 -- v2
just release patch yes; just release patch pypi yes; echo "pypi exit $?"
```

Expect the dry form's plan with no upload, the advisory's line when the
changes since the last fully proven release touch the list, and `pypi`
refused (exit 2) naming the decision, on any branch.

## Step 3: the first TestPyPI-only release, installed clean

The operator's, once the publishers are set up. About an hour for the
release (`--full` is the full proof), then about 15 minutes for the
Publish run.

```sh
# step 3 -- box 1 of 3 -- v2 -- about an hour
just release patch --full
```

The release pushes its branch, its tag and `develop` itself, and the
tag's push starts the Publish run; no `git push` follows it. Expect its
last lines to name the version and the tag it pushed. Then, with that
version in place of `<version>`, wait for the tag's Publish run:

```sh
# step 3 -- box 2 of 3 -- v2 -- about 15 minutes
GH_PAGER=cat gh run watch --exit-status "$(GH_PAGER=cat gh run list --workflow Publish \
  --branch v<version> --limit 1 --json databaseId --jq '.[0].databaseId')"
```

Expect the run to pass (its `quickstart` job ran the quickstart page
against the tag's files before the `testpypi` job uploaded), and the
starters pushed for a final version alone (a `.dev` release pushes
none). Then the clean install:

```sh
# step 3 -- box 3 of 3 -- v2 -- about 1 minute
tools=$(mktemp -d)
UV_TOOL_DIR="$tools/tools" UV_TOOL_BIN_DIR="$tools/bin" uv tool install --python 3.13 \
  --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-first-match 'cs-image-system[all]==<version>'
"$tools/bin/cs-image-system" --version
```

The install goes into a temporary tool directory, so the
`cs-image-system` you run every day is not replaced by it (uv warns
that the directory is not on your `PATH`, which is intended). Expect
the last line to report `<version>`, and PyPI's newest version
unchanged.

## Step 4: the reference takes it

```sh
# step 4 -- box 1 of 1 -- v1
cd ../cs-image-system-testconfig && just take <version> && just config-drift
```

Expect the take to install from TestPyPI and the drift check green.
