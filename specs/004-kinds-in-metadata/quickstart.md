# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contract**: [contracts/plugin-metadata.md](contracts/plugin-metadata.md)

Each step is a command that passes or fails. Nothing here applies
anything. Every box runs on your local machine, in a shell at the
repository root, on the branch `feature/004-kinds-in-metadata`.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | Declared kinds load, collide and are skipped the same way in every order | Stories 1 to 3; FR-004 to FR-008, FR-010; SC-001 to SC-003 |
| 2 | No plugin can call the registration any more | FR-002 |
| 3 | The inference code is gone | Story 4; FR-009; SC-005 |
| 4 | Nothing moved, and the whole bar holds | FR-003, FR-011; SC-004 |

## Step 1: declared kinds, in every order

Under a minute.

```sh
# step 1 -- box 1 of 1 -- v1
just test-one packages/engine/tests/test_unusable_plugins.py tests/test_posix_identity.py -q
```

Expect every test to pass, among them one per case recorded in spec
001 (research R13, tasks T140 to T143), each run over every order of
discovery.

## Step 2: the registration is out of reach

Under 10 seconds.

```sh
# step 2 -- box 1 of 1 -- v1
grep -rn "register_enrollment_kind\|register_field_kind" --include='*.py' packages/*/src src; echo "searched"
```

Expect the single line `searched`.

## Step 3: the inference is gone

Under 10 seconds.

```sh
# step 3 -- box 1 of 1 -- v1
grep -n "_shared_kinds\|_restore\|kind_owner\|kind_claimant\|collided_kinds" packages/engine/src/cs_image_system/engine/loader.py; echo "searched"
```

Expect the single line `searched`.

## Step 4: the bar

About 30 minutes.

```sh
# step 4 -- box 1 of 1 -- v1
just test
```

Expect lint clean, the type check at zero errors, every test passing,
the three isolated runs with `0 skipped`, and
`git status --short tests/fixtures` printing nothing afterwards.
