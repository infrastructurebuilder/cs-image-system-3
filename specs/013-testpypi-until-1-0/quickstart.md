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

The operator's, once the publishers are set up (about 10 minutes).

```sh
# step 3 -- box 1 of 1 -- v1
just release patch --full && git push origin HEAD v<version>
uv tool install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-first-match 'cs-image-system[all]==<version>' && cs-image-system --version
```

Expect the publish workflow's run to pass, the starters pushed, PyPI's
newest version unchanged, and the clean install to report `<version>`.

## Step 4: the reference takes it

```sh
# step 4 -- box 1 of 1 -- v1
cd ../cs-image-system-testconfig && just take <version> && just config-drift
```

Expect the take to install from TestPyPI and the drift check green.
