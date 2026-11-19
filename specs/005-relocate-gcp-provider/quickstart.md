# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) |
**Contracts**: [contracts/](contracts/)

Each step is a command that passes or fails. Nothing here applies
anything or stands up anything in a cloud. Every box runs on your local
machine. Steps 1 and 2 run in a fresh clone of the family's repository;
steps 3 and 4 at this repository's root on
`feature/005-relocate-gcp-provider`; step 5 at the reference
configuration's root.

## What each step proves

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The family passes its bar from a fresh clone, nothing skipped | Story 1; FR-001 to FR-004; SC-001 |
| 2 | It passes at the low end of its SDK ranges, and its starters render | Story 1, scenario 2; Story 3, scenario 4; FR-002 |
| 3 | This repository passes without the family, and nothing here imports it | Story 2; FR-006, FR-007; SC-002 |
| 4 | A release here builds nothing of the family | Story 4; FR-011 |
| 5 | The reference configuration's emission did not move | Story 3; FR-012; SC-003 |

## Step 1: the family alone

About 10 minutes. Needs no Google Cloud session.

```sh
# step 1 -- box 1 of 1 -- v1
rm -rf /tmp/gcp-family && git clone https://github.com/infrastructurebuilder/cs-image-system-google-cloud /tmp/gcp-family
cd /tmp/gcp-family && just init && just test
```

Expect lint clean, the type check at zero errors, and the tests passing
under the strict session (no `strict:` line).

## Step 2: the low end and the starters

About 20 minutes. Needs a container daemon, `packer`, `tofu` and
`ansible-playbook`, as `just test-docker-install` does.

```sh
# step 2 -- box 1 of 1 -- v1
cd /tmp/gcp-family && just full-test
```

Expect every leg reported as ran and succeeded.

## Step 3: this repository without the family

About 30 minutes.

```sh
# step 3 -- box 1 of 2 -- v1
grep -rln "gcloud_runtime\|tf_gcp_plugin\|gcs_state_plugin" --include='*.py' packages src tests scripts; echo "searched"
```

Expect the single line `searched`.

```sh
# step 3 -- box 2 of 2 -- v1
just test
```

Expect the whole bar to pass, the isolated runs each with `0 skipped`.

## Step 4: a release here leaves the family alone

Under a minute. Nothing is published.

```sh
# step 4 -- box 1 of 1 -- v1
just build && ls dist | grep -c "gcloud\|tf_gcp\|gcs_state"
```

Expect `0`.

## Step 5: the reference

About 5 minutes. Needs the reference configuration's AWS session, as
its drift check always does.

**YOUR DECISION**: this reads the reference with the family installed
from its release, by the reference's own pin. Take the release with
`just take` first (default: the phase 3 release).

```sh
# step 5 -- box 1 of 1 -- v1
cd ../cs-image-system-testconfig && just config-drift
```

Expect exit 0, with no change that is the tree's own.
