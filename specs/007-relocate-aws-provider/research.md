# Research: The AWS provider family in a repository of its own

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision is marked **read** (seen in the code, the index or the
reference configuration on 2026-11-19), **decided** (the operator's
answer in the spec's Clarifications) or **chosen** (this plan's, with
the alternatives). Two decisions are **YOUR DECISION**: the plan cannot
settle them without the operator (R6, R7).

## R1. The order of work, reused from spec 005

**Decision** (**chosen**): spec 005's four phases, unchanged in shape.

1. **Here, prepare, then release.** The AWS family's SDK pins become
   ranges, its stubs move out of `tests/harness.py` into its own package
   (`cs_image_system.aws_runtime.testing`), and the core's tests that run
   through AWS move onto their new vehicles (R5 to R7). This repository
   releases.
2. **There, stand alone, then release.** History carried by `git
   filter-repo`; the AWS family's own fixture, golden, harness, CI and
   release in `infrastructurebuilder/cs-image-system-aws`; its first
   release above 0.1.11.
3. **Here, remove, then release.** The three packages and the shared
   suite's AWS parts leave; the `aws` and `all` extras name the AWS
   family by a range.
4. **The reference** takes that release; its drift check exits 0.

**Rests on**: spec 005's records (its research R1 to R13, its tasks).

**Difference from spec 005**: phase 1 is much larger here, because the
core's tests move vehicle before anything leaves (R5).

## R2. Spec 005 first

**Decision** (**chosen**): this specification starts after spec 005 is
merged. Spec 005 re-hosted thirteen core test files on AWS; they move
again here (R5), and the shared suite this plan changes is the one spec
005 leaves (AWS and docker).

## R3. What the AWS family is

**Decision** (**read**): three distributions, today at the workspace's
0.1.11, eleven releases each on PyPI.

| Distribution | Import package | Entry points | Package data |
| --- | --- | --- | --- |
| `cs-image-system-aws-runtime-plugin` | `cs_image_system.aws_runtime` | runtime `aws_plugin`; bootstrap `aws`; modules | `tfmodules/` (5 modules, 19 files), `data/image-sources.yml` |
| `cs-image-system-tf-ebs-instance-plugin` | `cs_image_system.tf_ebs_instance_plugin` | instance `tf-ebs-instance-plugin` (words `tofu`, `tf-aws*`) | none |
| `cs-image-system-tf-s3-state-plugin` | `cs_image_system.tf_s3_state_plugin` | state `tf_s3_state_plugin` (word `s3`) | none |

Source: 21 files, 3,632 lines; their own tests: 31 in 651 lines. One
edge: `tf_storage_builder.py` imports `aws_runtime.aws_utils`. Every SDK
pin is exact (`base==0.2.0` and the Terraform libraries'); phase 1 makes
them ranges, as spec 005 did for the Google Cloud family.

**Noted** (**read**): the word `tofu` is the AWS family's instance
builder and version checker; the docker family registers its checker
under `tofu-docker`. A tree that names an executable of `type: tofu`
must still resolve once the AWS family is gone; phase 1 proves it on
docker's fixture.

## R4. The destination

**Decision** (**decided**, Q1: A): `infrastructurebuilder/cs-image-system-aws`,
created by the operator. **Read**: it exists locally with `develop` and
`main` at one commit (`88cdab3`, LICENSE, README, `.gitignore`,
`REUSE.toml`); GitHub's default branch is `main`, while the Google Cloud
family's is `develop`. The plan works on `develop`, as spec 005 did; the
default branch is the operator's to set.

## R5. The core's tests move onto the docker family

**Decision** (**decided**, Q2: A): the core's behaviours proven through
AWS move onto the docker family's runtime and roots.

**Rests on** (**read**, the inventory of 2026-11-19): 133 of 172
top-level test files use the shared harness, which imports the AWS
family; about 40 files and 450 tests prove the core through AWS, plus
the 13 files (101 tests) spec 005 just moved onto AWS; about 6 files and
48 tests are AWS-only and move to the AWS family's repository.

**How**: the docker family's runtime already answers most of what those
tests ask of a runtime -- vendor images (by digest), image listing and
disposal, retagging, instance verification, sessions, boot image, power
state and its control, identity, inventory, release commands, image
names, bake users -- and docker's stub covers the four calls a stubbed
run needs. Where a test needs a second runtime of the same type (retention,
pins per runtime, scoping, bake selection), the shared fixture declares
a second docker runtime. Where a test needs a second state backend, a
second `local` backend (the core's).

## R6. The capabilities docker does not have

**Read**: the core proves these through AWS today, and the docker family
has no counterpart:

| Area | Core behaviour proven through AWS | Why docker cannot show it |
| --- | --- | --- |
| Storage | archive and restore of a storage (`supports_archive`, transitions) | docker volumes do not archive |
| Storage | the single-attach cardinality rule and its refusal | docker volumes are multi-attach only |
| Storage | non-POSIX stores (a bucket's wipe before destroy, its lookup) | docker volumes are POSIX only |
| Storage | data lifecycle rules | docker volumes have none |
| Storage | zonal storage and availability-zone checks | docker volumes are not zonal |
| Storage | relabelling a storage in place | docker refuses |
| Runtime | network facts (discovery, `validate --online`, recorded facts) | docker has no network discovery |
| Runtime | an SSH proxy command and a session agent baked into the image | docker sessions are `exec` |
| Runtime | relabelling an instance in place (`lineage relabel`) | docker refuses |
| Runtime | base-image prerequisites a storage type declares | docker volumes declare none |

**Options**:
- **(a)** A **test-double runtime and storage** in the test kit
  (`cs_image_system.system.testing`, which already has a double runtime
  type), each implementing exactly these capabilities, so the core's
  rules stay proven here without a provider. The test kit grows; it is
  released with the system.
- **(b)** **Carry those tests to the AWS family's repository**, where
  AWS implements them. The core's rules are then proven only from
  another repository, against released code.
- **(c)** **Both**: the double for the rules (cardinality, archive
  transitions, network facts as recorded), the AWS repository for the
  AWS-shaped proofs (S3 wipes, EBS zones).

**Decided** by the operator, 2026-11-19: **(a)**, a test-double runtime
and storage in the test kit. Every core rule in the table stays proven
by this repository's own acceptance tests, on the double; the AWS
family's repository proves AWS's own implementation of each, through
its own tests (what it carries from here and its golden).

## R7. Okta identity on instances

**Read**: the core's validation refuses an Okta-owned image on a
container runtime (`engine/commands/validate.py`, `check_container_runtimes`;
the Okta group builder's `container_runtime_objection`). Today the
shared fixture's images are owned by Okta groups (`coops`, `tcmet`,
`stofs`, `secofs`) except `imgfile-posix`, and they bake on AWS. Once
AWS leaves, no runtime here can carry an Okta-owned image, so the Okta
plugin's instance-side behaviour (enrollment at launch, the login proof,
the group's activation in the bake, the enrollment in the golden) loses
its vehicle here.

**Options**:
- **(a)** The test-double runtime (R6) accepts an Okta group; the Okta
  plugin's instance behaviour stays proven here, on the double.
- **(b)** Those proofs move to the AWS family's repository, with the
  Okta plugin as its test dependency from the index.
- **(c)** The Okta plugin moves out too, as a family of its own, with a
  cloud runtime as its test dependency; a later specification.

**Decided** by the operator, 2026-11-19: **(c)**, the Okta plugin moves
out too, as a family of its own: specification 008
(`specs/008-relocate-okta-plugin`), into
`infrastructurebuilder/cs-image-system-okta`. Its instance-side proofs
move with it. The double of R6 does not take Okta groups.

**Sequencing**: the Okta plugin's instance proofs ride on AWS here
today. Spec 008 moves the Okta plugin before this specification's phase
3 removes AWS from the shared suite, or this specification's phase 3
waits for it.

## R8. The reference configuration needs the AWS family whole

**Read**: every root of the reference keeps its state in S3 (its
default backend, `s3-east2`), the GCE and docker roots included; its
perform runtime is `aws-east2-runtime`. So the reference installs the
AWS family always, by `cs-image-system[aws,gcloud,docker,okta]`, as now.
Spec edge case widened: installing the Google Cloud family without the
AWS family's state backend on a tree that uses S3 must say which extra
it needs.

## R9. Starters

**Decision** (**chosen**, by spec 005's R11, option c): `standard-aws`,
`standard-aws-posix` and `complete` stay in the system's data; this
repository's tests render the starters whose words its plugins
register; the three that declare AWS are checked in this repository's
CI `live` job, with both cloud families installed from the index. The
`DEFAULT` starter stays `standard-aws`; a system installed without the
`aws` extra says which extra it needs when asked for it.

## R10. Live jobs and the runner image

**Chosen**: `fixture-live` keeps its AWS identity for the starters'
check (R9), as spec 005 kept the Google Cloud one; the shared fixture
it validates loses its AWS declarations, so its `validate --online`
asks no cloud. The CI runner image keeps the AWS CLI and the SSM
plugin: configurations' CI runs in it.

## R11. Versions and installing

**Chosen**: the AWS family's own line starts at **0.2.0**, as the
Google Cloud family's did; the system's `aws` and `all` extras name it
by `>=0.2,<0.3` (FR-010). Its first release cuts the number the
manifests already carry, which spec 005's fixed release script now
handles.
