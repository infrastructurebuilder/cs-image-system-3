# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/recorded-builder-words.md](contracts/recorded-builder-words.md)

Each step is a command that passes or fails. Nothing here applies
anything, and nothing reaches a cloud until step 8. Every box runs on
your local machine in a shell at this repository's root, on the
feature branch `feature/009-qualified-builder-words` (or `develop` once
it is merged), unless the box says otherwise. Spec 006 is merged first
(plan, "Depends on spec 006"); step 4's whole tree writes runtimes
qualified only then.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | Every builder kind's qualified word is read as its registered word at the load; two plugins of one bare word each emit their own backend, labelled `local`, and record their own word; the bare word is refused naming both, in both discovery orders; OpenTofu initialises the emitted root | Stories 1 and 3; FR-001, FR-006 to FR-008; SC-002, SC-005 |
| 2 | The backend label is the kind's word; the bootstrap interview finds a state backend written qualified | Story 1; FR-001 |
| 3 | With no provider installed, the core fixture with its builder words qualified emits the core golden | Story 2; FR-002, FR-004, FR-005 |
| 4 | The shared fixture with every builder word qualified emits all of its files identical to the bare form's | Stories 1 and 2; SC-001, SC-003 |
| 5 | No golden moved | FR-004, FR-005; Constitution IV |
| 6 | The declared surfaces did not move, and the Terraform line took its PATCH | FR-006; SC-004 |
| 7 | The acceptance tests pass | Principle II |
| 8 | The release, and the Google Cloud family's whole qualified run | SC-004; the spec's Assumptions |

## Step 1: the rule at the load, and two plugins of one bare word

About 2 minutes: four whole dry runs of the shared fixture, and one
`tofu init` of a local backend (no network).

```sh
# step 1 -- box 1 of 1 -- v1
just test-one tests/test_qualified_builder_words.py -q
```

Expect every test to pass, none skipped. A skip means `tofu` is not on
the path: install OpenTofu on your local machine and repeat; a skipped
check is a failed check (Principle II).

## Step 2: the backend label and the bootstrap interview

Under 30 seconds.

```sh
# step 2 -- box 1 of 1 -- v1
just test-one tests/test_terraform_collector.py tests/test_bootstrap.py -q
```

Expect every test to pass, the new label case and the qualified
state-backend case among them.

## Step 3: the core fixture, qualified, with no provider

Under a minute.

```sh
# step 3 -- box 1 of 1 -- v1
just test-one packages/system/tests/test_core_golden.py -q
```

Expect every test to pass, the new qualified-builder-words case among
them.

## Step 4: the shared fixture with every builder word qualified

About a minute: two whole dry runs of the shared fixture.

```sh
# step 4 -- box 1 of 1 -- v1
just test-one tests/test_a_qualified_tree_emits_what_the_bare_tree_emits.py -q
```

Expect both tests to pass: the rewrite reaches every builder
collection's `type` (runtimes included once spec 006 is merged), and the
two emissions are identical.

## Step 5: no golden moved

Under 10 seconds. Run it on the feature branch, before the merge.

```sh
# step 5 -- box 1 of 1 -- v1
git diff --name-only develop -- tests/fixtures/golden packages/system/tests/golden | wc -l
```

Expect `0`.

## Step 6: the surfaces and the version line

Under 30 seconds.

```sh
# step 6 -- box 1 of 2 -- v1
just surface-check
```

Expect exit 0: no declared member of the kit or the Terraform
libraries was removed or altered.

Under 10 seconds.

```sh
# step 6 -- box 2 of 2 -- v1
grep -h '^version' packages/hashicorp-utils/pyproject.toml packages/tofu-roots/pyproject.toml packages/base/pyproject.toml
```

Expect `0.2.2` for the two Terraform libraries (one more than at the
start, by `just sdk-bump terraform last`) and the kit's version as it
was before this work.

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
which release carries the fix. **Default: the one final release the
operator decided for specs 002, 003 and 006**, cut by the operator on
`main` after the merge, as every release is. This step reads that
release, written here as `<version>`; skip it until the release is cut,
and walk it then.

About 10 minutes once the release has started: its runs are watched to
the end.

```sh
# step 8 -- box 1 of 3 -- v1
GH_PAGER=cat just release-watch <version>
```

Expect every run the release started to have passed.

In the Google Cloud family's repository, on its branch that takes the
release and writes all four of its words qualified in the whole run
(research R15). About 2 minutes.

```sh
# step 8 -- box 2 of 3 -- v1
cd ../cs-image-system-google-cloud && just pytest tests/pipeline/test_qualified_words.py -q
```

Expect every test to pass, the whole qualified run among them.

The reference configuration takes the release (`UV_REFRESH=1 just take
<version>` there first). About 5 minutes; it needs the reference's AWS
session, as its drift check always does. Name the installed release as
the command: a development checkout's venv does not hold the Google
Cloud family the reference declares.

```sh
# step 8 -- box 3 of 3 -- v1
cd ../cs-image-system-testconfig && CSIS="$HOME/.local/bin/cs-image-system" just config-drift
```

Expect exit 0, with no change that is the tree's own.
