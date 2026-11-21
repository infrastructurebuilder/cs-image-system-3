# Quickstart: proving the feature

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each step passes or fails; nothing is applied, and no OPA group or user
changes.

| Step | Proves | Spec |
| --- | --- | --- |
| 1 | The Okta plugin passes its acceptance tests from a fresh clone | Story 1; FR-001 to FR-004; SC-001 |
| 2 | This repository passes without it, and nothing imports it | Story 2; FR-005, FR-006; SC-002 |
| 3 | The reference's emission did not move, and no OPA group or user changes | Story 3; FR-007, FR-008; SC-003 |

## Step 1: the Okta plugin alone

About 10 minutes.

```sh
# step 1 -- box 1 of 1 -- v1
rm -rf /tmp/okta-plugin && git clone -b develop https://github.com/infrastructurebuilder/cs-image-system-okta /tmp/okta-plugin
cd /tmp/okta-plugin && just init && just test
```

Expect every test passing under the strict session.

## Step 2: this repository without it

About 30 minutes.

```sh
# step 2 -- box 1 of 2 -- v1
grep -rln "okta_opa_plugin" --include='*.py' packages src tests scripts; echo "searched"
```

Expect the single line `searched`.

```sh
# step 2 -- box 2 of 2 -- v1
just test
```

Expect all the acceptance tests to pass, the isolated runs each with
`0 skipped`.

## Step 3: the reference

About 5 minutes; needs the AWS session (gate on 40 minutes) and the
reference's Okta credentials in its `.envrc`.

```sh
# step 3 -- box 1 of 1 -- v1
cd ../cs-image-system-testconfig && just config-drift
```

Expect exit 0, with no change that is the tree's own, and no identity
root planning a change.
