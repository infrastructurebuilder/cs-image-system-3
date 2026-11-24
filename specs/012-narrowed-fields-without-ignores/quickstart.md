# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/narrowed-field-form.md](contracts/narrowed-field-form.md)

Each step is a command that passes or fails. Nothing here applies
anything or reaches a cloud. Every box runs on your local machine, in
a shell at this repository's root, on the feature branch
`feature/012-narrowed-fields-without-ignores` (or `develop` once it is
merged), unless the box says otherwise.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | One variable-override exception is left in this repository: the description's | FR-003 as deferred; SC-001 as deferred |
| 2 | The type check reports zero errors | FR-001, FR-003 |
| 3 | Narrowed fields refuse unknown keys at the same location, and unparametrized subclasses keep the general class and its default | Stories 1 and 2; FR-002, FR-004; SC-002 |
| 4 | Neither golden moved | FR-005; SC-003; Constitution IV |
| 5 | The declared surfaces only gained entries (the two type parameters) | FR-007 |
| 6 | The Google Cloud family's three fields pass in the new form against this kit, with that repository unchanged | Story 4; FR-008 |
| 7 | The acceptance tests pass | Principle II |
| 8 | The released Google Cloud family, unchanged, loads beside the new kit in the reference configuration's dry run | Story 2; SC-004 |

## Step 1: the exceptions are gone

Under 30 seconds.

```sh
# step 1 -- box 1 of 1 -- v1
GIT_PAGER=cat git grep -n "reportIncompatibleVariableOverride" -- '*.py'
```

Expect exactly one line:
`packages/base/src/cs_image_system/base/models/os_builder_runtime_config.py`,
the `description` field (deferred, [research.md](research.md) R5).
Any other line fails this step.

## Step 2: the type check

About 30 seconds.

```sh
# step 2 -- box 1 of 1 -- v1
just typecheck
```

Expect `0 errors`. Warnings also fail: the bar is zero.

## Step 3: refusal and defaults

Under a minute. The new test files are named by `tasks.md`. This box
lists the existing ones that must still pass alongside them.

```sh
# step 3 -- box 1 of 1 -- v1
just test-one tests/test_credentials.py packages/base/tests packages/tofu-roots/tests packages/tf-ebs-instance-plugin/tests packages/aws-runtime-plugin/tests packages/docker-plugin/tests/unit -q
```

Expect every test to pass, none skipped. The new cases cover these
paths:

- an unknown key under each narrowed field (AWS `credentials`; EBS,
  EFS, S3 and docker volume `variables`) is refused at
  `('<field>', '<key>')`;
- an absent field gives the narrowed default;
- the docker runtime and the test double keep `CredentialsBase`;
- a second level of narrowing (the AWS intermediate) holds.

## Step 4: neither golden moved

Under a minute.

```sh
# step 4 -- box 1 of 1 -- v1
just test-one tests/test_golden.py packages/system/tests/test_core_golden.py -q
```

Expect both to pass. A moved golden is read file by file, never
accepted wholesale (Constitution IV). No file should move.

## Step 5: the surfaces only gained entries

Under 30 seconds.

```sh
# step 5 -- box 1 of 1 -- v1
just surface-check
```

Expect it to be silent and exit 0. The recorded entries for
`credentials` and `variables` read as before (`CredentialsBase`,
`...ModuleVariables`). The new `CredentialsT` and `VariablesT` entries
are recorded as `typevar ...`. A "changed; the middle number must
rise" line fails this step.

## Step 6: the Google Cloud family's fields, in a scratch copy

Under a minute. This reads the sibling clone
`../cs-image-system-google-cloud` and changes nothing there.

```sh
# step 6 -- box 1 of 2 -- v1
scratch="$(mktemp -d)"; cp ../cs-image-system-google-cloud/packages/tf-gcp-plugin/src/cs_image_system/tf_gcp_plugin/tf_gcp_models.py "$scratch/gcp_models.py"
sed -i '' -e 's/(TofuStorageBuilderModelBase):/(TofuStorageBuilderModelBase[VariablesT]):/' -e 's/TofuStorageBuilderModelBase$/TofuStorageBuilderModelBase, VariablesT/' -e 's/(TofuGcpStorageBuilderModel):/(TofuGcpStorageBuilderModel[GcpVariables]):/' -e 's/  # pyright: ignore\[reportIncompatibleVariableOverride\]//' "$scratch/gcp_models.py"
grep -c "reportIncompatibleVariableOverride" "$scratch/gcp_models.py"
```

Expect `0`.

```sh
# step 6 -- box 2 of 2 -- v1
just typecheck-path "$scratch/gcp_models.py"
```

Expect `0 errors`. Then confirm the sibling repository is untouched:
`GIT_PAGER=cat git -C ../cs-image-system-google-cloud status --short`
prints nothing that this step made.

## Step 7: the acceptance tests

About 10 minutes.

```sh
# step 7 -- box 1 of 1 -- v1
just test
```

Expect lint, the type check (0 errors), the tests, the core run, the
Terraform libraries alone and the docker family alone all to pass,
with none skipped. The docker family's low end now resolves the
version that carries this change, from this repository's build if it
is not yet published. The run names it as a development install
([research.md](research.md) R7).

## Step 8: the released family beside the new kit

About 30 minutes. It needs this repository's `.envrc` loaded and
`AWS_PROFILE=noaa` with a live session. A dry run applies nothing.

```sh
# step 8 -- box 1 of 1 -- v1
just full-test
```

Expect it to pass. Its reference-configuration legs load the released
Google Cloud family (unparametrized, its exceptions in place) beside
this workspace's kit and Terraform library, through
`scripts/with-released-families`. That is SC-004's evidence: zero
plugins written against the published kit needed a change. An expired
session or an unreachable index is environmental. Report it as that,
not as a code failure.
