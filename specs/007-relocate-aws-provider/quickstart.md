# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/aws-family-repository.md](contracts/aws-family-repository.md)

Each step is a command that passes or fails. Nothing here applies
anything or stands up anything in a cloud. Steps 1 and 2 run in a fresh
clone of the AWS family's repository; steps 3 and 4 at this
repository's root on `feature/007-relocate-aws-provider`; step 5 at the
reference configuration's root.

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The AWS family passes its acceptance tests from a fresh clone | Story 1; FR-001 to FR-004; SC-001 |
| 2 | It passes at the low end of its SDK ranges | Story 1; FR-002 |
| 3 | This repository passes without it, nothing imports it, and every core behaviour it proved has a test here | Story 2; FR-006 to FR-008; SC-002, SC-005 |
| 4 | A release here builds nothing of it | Story 4 |
| 5 | The reference's emission did not move | Story 3; FR-012; SC-003 |

## Step 1: the AWS family alone

About 10 minutes.

```sh
# step 1 -- box 1 of 1 -- v1
rm -rf /tmp/aws-family && git clone -b develop https://github.com/infrastructurebuilder/cs-image-system-aws /tmp/aws-family
cd /tmp/aws-family && just init && just test
```

Expect lint clean, the type check at zero errors, every test passing
under the strict session.

## Step 2: the low end

A few minutes.

```sh
# step 2 -- box 1 of 1 -- v1
cd /tmp/aws-family && just full-test
```

Expect `full-test: passed` last.

## Step 3: this repository without the AWS family

About 30 minutes.

```sh
# step 3 -- box 1 of 2 -- v1
grep -rln "aws_runtime\|tf_ebs_instance_plugin\|tf_s3_state_plugin" --include='*.py' packages src tests scripts; echo "searched"
```

Expect the single line `searched`.

```sh
# step 3 -- box 2 of 2 -- v1
just test
```

Expect all the acceptance tests to pass, the isolated runs each with
`0 skipped`.

## Step 4: a release here leaves the AWS family alone

Under a minute.

```sh
# step 4 -- box 1 of 1 -- v1
just build && ls dist | grep -c "aws_runtime\|tf_ebs\|tf_s3"
```

Expect `0`.

## Step 5: the reference

About 5 minutes; needs the AWS session (gate on 40 minutes).

```sh
# step 5 -- box 1 of 1 -- v1
cd ../cs-image-system-testconfig && just config-drift
```

Expect exit 0, with no change that is the tree's own.
