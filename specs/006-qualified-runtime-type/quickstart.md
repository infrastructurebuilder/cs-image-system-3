# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/image-source-keys.md](contracts/image-source-keys.md)

Each step is a command that passes or fails. Nothing here applies
anything, and nothing reaches a cloud until step 8. Every box runs on
your local machine in a shell at this repository's root, on the
feature branch `feature/006-qualified-runtime-type` (or `develop` once
it is merged), unless the box says otherwise.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | Either form reads the same block; two runtimes of one bare word each read their own plugin's; a tree's bare and qualified keys; an unknown key is named | Stories 1 to 3; FR-001 to FR-004 |
| 2 | Two plugins registering one bare runtime word, through a whole load: each qualified runtime's query is its own plugin's; the bare word is refused naming both | Story 3; FR-003; SC-003 |
| 3 | With no provider installed, the core fixture written `testing/test-double` emits the core golden | Stories 1 and 2; FR-002, FR-005 |
| 4 | Every installed runtime type written qualified validates and emits the bare emission, file for file | Story 1; FR-001, FR-005; SC-001, SC-002 |
| 5 | The bootstrap interview finds a runtime written qualified | Story 1 ("every command") |
| 6 | No golden moved | FR-007; SC-004 |
| 7 | The acceptance tests pass | Principle II |
| 8 | The release, and the Google Cloud family's whole run | FR-008 |

## Step 1: the catalog's rule

About a minute.

```sh
# step 1 -- box 1 of 1 -- v1
just test-one tests/test_image_sources.py -q
```

Expect every test to pass, among them the new catalog cases beside
`test_where_two_plugins_share_a_runtime_word_the_qualified_word_reads_its_own_part`.

## Step 2: two plugins, one bare runtime word

Under a minute.

```sh
# step 2 -- box 1 of 1 -- v1
just test-one packages/system/tests/test_qualified_runtime_words.py -q
```

Expect every test to pass.

## Step 3: the core fixture, qualified, with no provider

Under a minute.

```sh
# step 3 -- box 1 of 1 -- v1
just test-one packages/system/tests/test_core_golden.py -q
```

Expect every test to pass, the new qualified case among them.

## Step 4: the shared fixture with every runtime qualified

About a minute: two whole dry runs of the shared fixture.

```sh
# step 4 -- box 1 of 1 -- v1
just test-one tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py -q
```

Expect both tests to pass: the rewrite reaches `runtime_builders.type`,
and the two emissions are identical.

## Step 5: the bootstrap interview

Under 30 seconds.

```sh
# step 5 -- box 1 of 1 -- v1
just test-one tests/test_bootstrap.py -q
```

Expect every test to pass.

## Step 6: no golden moved

Under 10 seconds. Run it on the feature branch, before the merge.

```sh
# step 6 -- box 1 of 1 -- v1
git diff --name-only develop -- tests/fixtures/golden packages/system/tests/golden | wc -l
```

Expect `0`.

## Step 7: the acceptance tests

About 30 minutes.

```sh
# step 7 -- box 1 of 1 -- v1
just test
```

Expect lint clean, the type check at zero errors, every test passing,
the isolated runs each with `0 skipped`, and `git status --short
tests/fixtures` printing nothing afterwards.

## Step 8: the release, and the Google Cloud family's whole run

**YOUR DECISION** (D2 in [plan.md](plan.md#decisions-in-this-plan)):
which release carries the fix. **Default: 0.1.13**, cut by the
operator on `main` after the merge, as every release is
(`just release patch pypi`). This step reads that release; skip it if
the fix rides a later release, and walk it then.

About 10 minutes once the release has started: its runs are watched to
the end.

```sh
# step 8 -- box 1 of 3 -- v1
GH_PAGER=cat just release-watch 0.1.13
```

Expect every run the release started to have passed.

In the Google Cloud family's repository, on its branch that takes the
release (its lock moved to 0.1.13 and kit 0.2.2) and carries the whole
run of research R11. About 2 minutes.

```sh
# step 8 -- box 2 of 3 -- v1
cd ../cs-image-system-google-cloud && just pytest tests/pipeline/test_qualified_words.py -q
```

Expect every test to pass, the whole qualified run among them.

The reference configuration takes the release (`UV_REFRESH=1 just take
0.1.13` there first). About 5 minutes; it needs the reference's AWS
session, as its drift check always does. Name the installed release as
the command: a development checkout's venv does not hold the Google
Cloud family the reference declares.

```sh
# step 8 -- box 3 of 3 -- v1
cd ../cs-image-system-testconfig && CSIS="$HOME/.local/bin/cs-image-system" just config-drift
```

Expect exit 0, with no change that is the tree's own.
