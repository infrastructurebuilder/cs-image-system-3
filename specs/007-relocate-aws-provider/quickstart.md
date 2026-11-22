# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/aws-family-repository.md](contracts/aws-family-repository.md)

Each step is a command that passes or fails. Nothing here applies
anything or stands up anything in a cloud. Every box runs on your local
machine. Steps 1 and 2 run in a fresh clone of the AWS family's
repository; steps 3 to 5 at this repository's root on
`feature/007-relocate-aws-provider`; step 6 at the reference
configuration's root.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The AWS family passes its acceptance tests from a fresh clone, nothing skipped | Story 1; FR-001 to FR-004; SC-001 |
| 2 | It passes at the low end of its SDK ranges | Story 1; FR-002 |
| 3 | This repository passes without it, nothing here imports it, none of it is installed, and every core behaviour it proved has a test here | Story 2; FR-006 to FR-008; SC-002, SC-005 |
| 4 | The starters that declare AWS render, validate and dry-run with the AWS family from its release | Story 3; Story 1, scenario 2 |
| 5 | A release here builds nothing of it | Story 4 |
| 6 | The reference's emission did not move | Story 3; FR-012; SC-003 |

## Step 1: the AWS family alone

About 10 minutes. Needs no AWS session.

```sh
# step 1 -- box 1 of 1 -- v1
rm -rf /tmp/aws-family && git clone -b develop https://github.com/infrastructurebuilder/cs-image-system-aws /tmp/aws-family
cd /tmp/aws-family && just init && just test
```

Expect lint clean, the type check at zero errors, every test passing
under the strict session (no `strict:` line).

## Step 2: the low end

A few minutes. The starters that declare AWS are not rendered there:
they declare other providers too, so this repository tests them with
the cloud families layered in from the index (step 4; research R9).

```sh
# step 2 -- box 1 of 1 -- v1
cd /tmp/aws-family && just full-test
```

Expect every leg reported as passed, and `full-test: passed` last.

## Step 3: this repository without the AWS family

About 30 minutes in all.

```sh
# step 3 -- box 1 of 3 -- v2
grep -rln "aws_runtime\|tf_ebs_instance_plugin\|tf_s3_state_plugin" --include='*.py' packages src tests scripts | grep -v '^tests/cloud_starters/'; echo "searched"
```

Expect the single line `searched`. `tests/cloud_starters` is left out
on purpose: it imports the cloud families' own test stubs, and runs only
with them layered in from the index (step 4).

```sh
# step 3 -- box 2 of 3 -- v1
uv pip list 2>/dev/null | grep -c "aws-runtime-plugin\|tf-ebs-instance-plugin\|tf-s3-state-plugin"
```

Expect `0`: the venv `just init` made holds none of the three.

About 25 minutes.

```sh
# step 3 -- box 3 of 3 -- v2
just test
```

Expect all the acceptance tests to pass, the isolated runs each with
`0 skipped`, `test-core` among them (the double's cases, research R6).

## Step 4: the starters that declare AWS

About 3 minutes. Needs the index, no cloud session: the starters'
clouds are stubbed.

```sh
# step 4 -- box 1 of 1 -- v1
just test-cloud-starters
```

Expect every case to pass under the strict session, `standard-aws` and
`standard-aws-posix` among them; an absent family fails, it never
skips.

## Step 5: a release here leaves the AWS family alone

Under a minute. Nothing is published.

```sh
# step 5 -- box 1 of 1 -- v2
just build && ls dist | grep -c "aws_runtime\|tf_ebs\|tf_s3"
```

Expect `0`.

## Step 6: the reference

About 5 minutes. Needs the reference configuration's AWS session, as
its drift check always does (gate on 40 minutes).

**YOUR DECISION**: this reads the reference with the AWS family
installed from its release, by the reference's own pin. Take the release
with `just take <version>` first (default: the phase 3 release). If the
take stops because PyPI has not listed the release yet, run
`UV_REFRESH=1 just take <version>` a few minutes later. Name the
installed release as the command: a development checkout's venv does
not hold the families the reference declares.

```sh
# step 6 -- box 1 of 1 -- v2
cd ../cs-image-system-testconfig && CSIS="$HOME/.local/bin/cs-image-system" just config-drift
```

Expect exit 0, with no change that is the tree's own. After any run
that applied (a cycle), `just record` comes first: a scoped run's
committed emission is not the whole tree's.
