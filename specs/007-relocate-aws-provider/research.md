# Research: The AWS provider family in a repository of its own

**Feature**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

Each decision is marked **read** (seen in the code, the index or the
reference configuration on 2026-11-19), **re-read** (seen again on
2026-11-21, after spec 005 completed), **decided** (the operator's
answer in the spec's Clarifications or to a **YOUR DECISION**) or
**chosen** (this plan's, with the alternatives). The two decisions the
first plan left open (R6, R7) are decided. The revision of 2026-11-21
leaves five open, each with its default, listed in the plan's
"Decisions in this plan".

## R1. The order of work, reused from spec 005

**Decision** (**chosen**): spec 005's four phases, unchanged in shape.

0. **Spec 008 first** (R7, **YOUR DECISION**, default: wholly, before
   this specification's branch starts).
1. **Here, prepare, then release.** The AWS family's SDK pins become
   ranges, its stubs move out of `tests/harness.py` into its own package
   (`cs_image_system.aws_runtime.testing`), the test kit's double grows
   (R6), the starters' selection is fixed (R9), and the core's tests
   that run through AWS move onto their new vehicles (R5 to R7). This
   repository releases (its next 0.1 version), which also gives spec
   008's instance suite the AWS stubs it now copies.
2. **There, stand alone, then release.** History carried by `git
   filter-repo`; the AWS family's own fixture, golden, harness, CI and
   release in `infrastructurebuilder/cs-image-system-aws`; its first
   release, 0.2.0, above every version the index holds (0.1.12 today).
3. **Here, remove, then release.** The three packages and the shared
   suite's AWS parts leave; the `aws` and `all` extras name the AWS
   family by a range; the released-elsewhere mechanism takes it (R12).
4. **The reference** takes that release; its drift check exits 0.
5. **Done**: convergence, the quickstart walk, the merges, the status
   lines (the plan's "Definition of done").

**Rests on**: spec 005's records (its research R1 to R13, its tasks).

**Difference from spec 005**: phase 1 is much larger here, because the
core's tests move vehicle before anything leaves (R5).

## R2. Spec 005 first

**Decision** (**chosen**): this specification starts after spec 005 is
merged. Spec 005 re-hosted thirteen core test files on AWS; they move
again here (R5), and the shared suite this plan changes is the one spec
005 leaves (AWS and docker).

**Re-read**: spec 005 is complete (2026-11-21: merged, converged,
released in 0.1.12, the Google Cloud family at 0.2.0). Besides the
thirteen files (its T039: `test_convergent_bakes`, `test_bake_fingerprints`,
`test_bake_selection`, `test_decommission`, `test_detach`,
`test_ephemeral`, `test_retention`, `test_post_bake_tests`,
`test_runtime_facts`, `test_ci_perform`, `test_vendor_images`; its
T040: `test_nested_run_in_this_process`,
`test_two_runs_in_one_process_share_nothing`), two cases moved onto AWS:
`test_decommission`'s overlay case on
`overlays/aws-cycle-decommission.yaml` (T046) and the two core rules of
T074 (`test_instance_roots`, `test_pins_per_runtime`).

## R3. What the AWS family is

**Decision** (**read**; **re-read** 2026-11-21): three distributions,
today at the workspace's 0.1.12, twelve releases each on PyPI.

| Distribution | Import package | Entry points | Package data |
| --- | --- | --- | --- |
| `cs-image-system-aws-runtime-plugin` | `cs_image_system.aws_runtime` | runtime `aws_plugin`; bootstrap `aws`; modules | `tfmodules/` (5 modules, 19 files), `data/image-sources.yml` |
| `cs-image-system-tf-ebs-instance-plugin` | `cs_image_system.tf_ebs_instance_plugin` | instance `tf-ebs-instance-plugin` (words `tofu`, `tf-aws*`) | none |
| `cs-image-system-tf-s3-state-plugin` | `cs_image_system.tf_s3_state_plugin` | state `tf_s3_state_plugin` (word `s3`) | none |

Source: 21 files, 3,632 lines; their own tests: 31 in 651 lines. One
edge: `tf_storage_builder.py` imports `aws_runtime.aws_utils`. The
contract is already a range (`>=0.5,<0.6`); the pins on `base`,
`hashicorp-utils` and `tofu-roots` are exact at 0.2.1 (**re-read**; they
were 0.2.0 when this was first written, and moved at release 0.1.12);
phase 1 makes them `>=0.2,<0.3`, as the Google Cloud family declares.
`tf-ebs-instance-plugin`'s pin on `aws-runtime-plugin` stays exact, at
the AWS family's number.

**Noted** (**read**): the word `tofu` is the AWS family's instance
builder and version checker; the docker family registers its checker
under `tofu-docker`. A tree that names an executable of `type: tofu`
must still resolve once the AWS family is gone; phase 1 proves it on
docker's fixture.

**Re-read**: the same word misleads a test helper here (R9):
`tests/starter_support.py` maps every `type:` word to an extra without
its classification, so an executable's `type: tofu` reads as the AWS
family's instance builder, and `standard-docker` and `standard-gce` read
as needing the `aws` extra.

## R4. The destination

**Decision** (**decided**, Q1: A): `infrastructurebuilder/cs-image-system-aws`,
created by the operator. **Read**: it exists locally with `develop` and
`main` at one commit (`88cdab3`, LICENSE, README, `.gitignore`,
`REUSE.toml`); GitHub's default branch is `main`, while the Google Cloud
family's is `develop`. The plan works on `develop`, as spec 005 did; the
default branch is the operator's to set.

**Re-read** 2026-11-21: unchanged. One commit (`88cdab3`) on `develop`
and `main`, both pushed; the repository is public; GitHub's default
branch is still `main`; it holds no Actions secret. Its `live` job
(`validate --online` against the AWS family's fixture account) needs
its own `AWS_ROLE_ARN` and the read-only role's trust of this
repository's name, as the Google Cloud family's needed its federation's
admission (spec 005's T056): IAM writes and secrets are the operator's
(**YOUR DECISION**, default: set before the first dispatch of its `live`
job; the default branch set to `develop`).

## R5. The core's tests move onto the docker family

**Decision** (**decided**, Q2: A): the core's behaviours proven through
AWS move onto the docker family's runtime and roots.

**Rests on** (**read**, the inventory of 2026-11-19): 133 of 172
top-level test files use the shared harness, which imports the AWS
family; about 40 files and 450 tests prove the core through AWS, plus
the 13 files (101 tests) spec 005 just moved onto AWS; about 6 files and
48 tests are AWS-only and move to the AWS family's repository.

**Re-read** 2026-11-21 (177 tracked test files under `tests/`, fixtures
left out; a test is a `def test_`):

| Dependence on the AWS family | Files | Tests |
| --- | --- | --- |
| Import its code (`aws_runtime`, `tf_ebs_instance_plugin`, `tf_s3_state_plugin`), `tests/harness.py` left out | 46 | 526 |
| Name the fixture's AWS entries without importing it (`aws-east2-runtime`, `aws-east1`, `pckr-ebs-ans`, `some-other-builder`, `open-tofu`, `aws-ebs`, `aws-efs`, `aws-s3`, `s3-east2`, `test2`, `tf-aws*`) | 34 | 363 |
| Together: the files phase 1 reads one by one | 80 | 889 |
| Use the harness only, over the fixture whose defaults are AWS's | about 54 | about 290 |

The first plan's "about 53 files" counted only the first kind. The last
row's files change only where their output depends on the default
runtime; the golden comparison finds them. The clearly AWS-only files
include `test_aws_parity.py`, `test_bootstrap_aws.py` and
`test_preflight_refresh.py`; phase 1's first task writes the full table
of AWS-only cases, as spec 005's T073 scan did, and each goes to the AWS
family's repository.

**The second move of spec 005's re-hosted tests** (**chosen**, by Q2 A
and R6 (a)):

| Spec 005's task | Files or cases | New vehicle |
| --- | --- | --- |
| T039 | `test_convergent_bakes`, `test_bake_fingerprints`, `test_bake_selection`, `test_retention`, `test_ci_perform`, `test_vendor_images` | docker: `docker-fixture` and the second docker runtime, `pckr-docker`, the POSIX images (after spec 008) |
| T039 | `test_runtime_facts`, `test_post_bake_tests`, `test_decommission`, `test_detach` | docker, whose runtime has `inventory()` and a session (`exec`), so the stubbed AWS inventory spec 005 needed goes; `test_detach`'s unmount over the session |
| T039 | `test_ephemeral` (its SSM case) | docker for ephemerality; the double for a baked session agent (R6) |
| T040 | `test_nested_run_in_this_process`, `test_two_runs_in_one_process_share_nothing` | docker: `docker-fixture` and `docker-volume`; a `docker-cycle-decommission` overlay in place of `aws-cycle-decommission.yaml` |
| T046 | the overlay case of `test_decommission` | docker, on that overlay |
| T074 | `test_instance_roots`' plan-only ephemeral, `test_pins_per_runtime`'s second runtime | docker: `tofu-docker`'s roots; the second docker runtime |

Each file's vehicle is recorded as its task completes; where docker
lacks a capability a case asks for, the case goes to the double (R6),
never away.

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

**Re-read** 2026-11-21: the kit's double today
(`packages/system/src/cs_image_system/system/testing/double.py`, 143
lines, the type word `test-double`) is a container runtime on the kit's
`ContainerBuilderBase`, with no instance and no storage. The core's own
fixture (`packages/system/tests/fixture`) declares it as its one runtime
and no storage builder, and `just test-core` runs that suite with no
provider installed.

**How** (**chosen**):

- **A second double runtime type**, cloud-shaped, on the kit's
  `CloudBuilderBase`, beside the container double, which stays as it
  is: the container double's emission is the core golden, and a cloud
  runtime's capabilities (network facts, an SSH proxy, a baked session
  agent, relabelling in place) belong to the cloud base, not the
  container base.
  Alternative rejected: widening the container double, which moves the
  core golden for no behaviour of its own.
- **A double storage type** with the six storage rows of the table.
  How the double's instances are emitted (the rows that need a launched
  subject: single attach, relabel, zones) is settled by phase 1's first
  task: the neutral root of `tofu-roots` if it serves, otherwise a
  double instance builder in the kit. Neither is ever an installed
  entry point.
- **Where its tests run**: in the core's own suite
  (`packages/system/tests`, run alone by `just test-core`), over the
  core's fixture extended with the double's declarations; the core
  golden's additions are read file by file. Alternative rejected: the
  shared fixture, which `just fixture-live` loads with the installed
  command, where no double is registered, so its `validate` would fail.
  The core suite also proves each rule with no provider installed,
  which Principle VI asks of a core rule.

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

**Re-read** 2026-11-21: spec 008 is planned with its tasks written and
not started. Its FR-006 makes the shared fixture's groups and users
POSIX; its instance suite takes the AWS family from PyPI
(`>=0.1.11,<0.3`, its Q1 A) and carries a temporary copy of this
harness's AWS stubs until this specification's phase 1 publishes
`cs_image_system.aws_runtime.testing` (its T017); its T055 adds a note
here when it lands.

**The order, revised** (**YOUR DECISION**, default (a)): six of the
shared fixture's eight images (`imgfile-basic-cloudflow`,
`imgfile-basic-dask`, `imgfile-data-science`,
`imgfile-basic-cloudflow-two`, `imgfile-basic-dask-two`,
`imgfile-basic-cloudflow-notdocker`) are owned by Okta groups, and only
`imgfile-posix` and `imgfile-container` by the POSIX `pxgroup`. The
core refuses an Okta-owned image on a container runtime
(`check_container_runtimes`), so the tests that bake those images on
AWS today cannot move onto docker while the groups are Okta's.

- **(a)** Spec 008 lands wholly (its phase 3 and release) before this
  specification's branch starts; phase 1 then re-vehicles on a POSIX
  fixture. Recommended: one pass over each file.
- **(b)** Phase 1 starts now and moves only the tests of the two POSIX
  images; the rest wait for spec 008. Each waiting file is read twice.

**Landed** 2026-11-23 (spec 008's T055): the Okta plugin is out of this
repository ([specs/008-relocate-okta-plugin](../008-relocate-okta-plugin/spec.md),
its phases 1 to 5 committed on `feature/008-relocate-okta-plugin`, not yet
merged). The shared fixture's groups and users are POSIX: every image is
owned by a POSIX group (`basic` 3100, `pxgroup` 3101, `coops` 3102, `stofs`
3103, `tcmet` 3104, `secofs` 3105), so `check_container_runtimes` no longer
holds any of the six images to AWS, and the Okta plugin's instance-side
proofs ride on AWS in its own repository (`tests/instance/`, the AWS family
from the index). This specification's phase 3 may now remove the cloud
runtime those proofs rode on here; the order of (a) above holds once spec
008 is merged.

## R8. The reference configuration needs the AWS family whole

**Read**: every root of the reference keeps its state in S3 (its
default backend, `s3-east2`), the GCE and docker roots included; its
perform runtime is `aws-east2-runtime`. So the reference installs the
AWS family always, by `cs-image-system[aws,gcloud,docker,okta]`, as now.
Spec edge case widened: installing the Google Cloud family without the
AWS family's state backend on a tree that uses S3 must say which extra
it needs.

**Re-read** 2026-11-21: the reference's `.csis-version` is 0.1.12, its
`develop` level with its origin; `s3-east2` is still its default
backend. Every command of this repository that loads the reference
(`just cli`, `full-test`'s dry run and state query over a copy,
`just test-mods`, `just preflight`, the release's session probe) already
runs through `scripts/with-released-families` since spec 005's T056, so
once `aws` is in its `RELEASED_ELSEWHERE` they layer the AWS family in
from PyPI with no further change. The test of the widened edge case is
`tests/test_extras.py::test_validate_names_the_missing_extra_in_one_line`,
which spec 005 proved on a copy of the fixture given a `gcloud` runtime;
phase 3 adds the same case for an `s3` backend.

## R9. Starters

**Decision** (**chosen**, by spec 005's R11, option c): `standard-aws`,
`standard-aws-posix` and `complete` stay in the system's data; this
repository's tests render the starters whose words its plugins
register; the three that declare AWS are checked by `just
test-cloud-starters`, with both cloud families layered in from the
index. The `DEFAULT` starter (`docs/examples/DEFAULT`) stays
`standard-aws`; a system installed without the `aws` extra says which
extra it needs when asked for it.

**Re-read** 2026-11-21, and corrected: `just test-cloud-starters` runs
`tests/cloud_starters/` (outside the default collection) under the
strict session; it is a leg of `full-test-legs` and a step of CI's
`live` job in both workflows, and **not** part of `just test` (spec
005's T077, the operator's decision), so `just test` installs nothing
of a family released elsewhere. It needs the index and no cloud
identity: the starters' clouds are stubbed. Phase 3 adds to it a case
that renders, validates and dry-runs `standard-aws` and
`standard-aws-posix` on the AWS family's own stubs
(`cs_image_system.aws_runtime.testing`), as spec 005's T078 does for
`standard-gce`; `complete` keeps its two cases there.

**A defect that blocks this specification** (**read**, fixed in phase
1): `tests/starter_support.py`'s `extras_a_starter_needs` maps every
`type:` word to an extra without its classification, so the executable
`type: tofu` reads as the AWS family's instance builder.
`standard-docker` reads as needing `{aws, docker}` and `standard-gce`
as needing `aws`. With the AWS family absent, this repository would
stop rendering `standard-docker`, its own docker starter. The helper
takes each word with its classification, by the rule
`src/cs_image_system/extras.py` applies (`extra_for(classification,
word)`), and `tests/test_starters_by_declaration.py` gains the case.

**Recorded, not fixed** (**chosen**): spec 005's T078 found that
`complete`'s dry run fails on `aws-east1` (the chain
`imgfile-basic-cloudflow` names a parent with no build there). It is an
AWS chain in a fresh tree; this specification moves the AWS code without
changing what it does (FR-012), so the defect goes with it to the AWS
family's repository, named in its README, and waits until its code is
touched for another reason.

## R10. Live jobs and the runner image

~~**Chosen**: `fixture-live` keeps its AWS identity for the starters'
check (R9), as spec 005 kept the Google Cloud one.~~ Corrected
2026-11-21: the starters' check takes no identity (R9). The shared
fixture `fixture-live` validates loses its AWS declarations, so its
`validate --online` asks no cloud. The CI runner image keeps the AWS
CLI and the SSM plugin: configurations' CI runs in it.

**Re-read** 2026-11-21: both workflows' `live` jobs gate on
`AWS_ROLE_ARN` and the Okta triple, take the federated AWS credentials
(`aws-actions/configure-aws-credentials`), write the `[noaa]` profile
shim the fixture's runtimes name, then run `just fixture-live` and
`just test-cloud-starters`. Only `fixture-live`'s `validate --online`
reads AWS.

**Chosen**, by spec 005's precedent (its T056: the Google Cloud
identity served no step and was dropped): in phase 3 the AWS identity
steps leave `ci.yml` and `ci-from-scratch.yml` (the gate's
`HAVE_AWS_ROLE_ARN` and its name in the list and the SKIPPED line, the
federated-credentials step, the `[noaa]` shim, `AWS_REGION`), with the
rows of `docs/OPERATIONS.md` that describe them. Spec 008 removes the
Okta triple first (its T043); if it leaves the gate with no secret, the
`live` job runs on every push with no gate, which also meets the spec's
edge case ("neither fail nor silently succeed"). `tests/test_ci_workflow.py`
holds the job's commands. Removing the repository secret and the role's
trust of this repository are the operator's (**YOUR DECISION**,
default: after the phase 3 release reaches `main`, as spec 005's were).

## R11. Versions and installing

**Chosen**: the AWS family's own line starts at **0.2.0**, as the
Google Cloud family's did; the system's `aws` and `all` extras name it
by `>=0.2,<0.3` (FR-010). Its first release cuts the number the
manifests already carry, which spec 005's fixed release script now
handles.

**Re-read** 2026-11-21: the Google Cloud family's `scripts/release`
commits only when the bump or the lock changed something and tags in
every case (spec 005's T038); the AWS family's repository copies it.
The AWS family releases to **PyPI** only: this repository's release asks
PyPI alone whether a release inside each range exists
(`released_elsewhere_or_refuse`, R12), since TestPyPI holds no family
release and an install from TestPyPI takes what it lacks from PyPI.
The AWS family's pipeline suite takes the system's test kit and the core
plugins its fixture declares by the range of the system's line, in its
workspace's dev group, as the Google Cloud family's does.

## R12. The released-elsewhere mechanism takes the AWS family

**Read** 2026-11-21: spec 005 built one mechanism for a family released
from its own repository; phase 3 extends each part of it, never a
second copy.

| Part | Today | Phase 3 |
| --- | --- | --- |
| `scripts/with-released-families` | `RELEASED_ELSEWHERE = ("gcloud",)`; `--print`, `--check` (TestPyPI or PyPI) | `("gcloud", "aws")` (spec 008 adds `okta`); its docstring names the families |
| `Justfile` `init` | `uv sync --all-extras --no-extra gcloud --no-extra all` | `--no-extra aws` added, and its comment |
| `scripts/release.py` `SYNC` and its messages | the same rule | the same addition; `tests/test_release_script.py` |
| `Justfile` `gcloud-with` (private) | prints the `--with` options | renamed `families-with` (**chosen**: it layers in more than one family); `publish-starters` and `test-cloud-starters` call it |
| `tests/test_with_released_families.py` | asserts `("gcloud",)` | the new tuple |
| `tests/test_package_metadata.py` `RELEASED_ELSEWHERE` | the Google Cloud family's names, by `>=0.2,<0.3` | the AWS family's names too |
| `tests/test_extras.py` `ELSEWHERE` | `{"gcloud": "infrastructurebuilder/cs-image-system-google-cloud"}` | `"aws": "infrastructurebuilder/cs-image-system-aws"` added; the missing-extra case for an `s3` backend (R8) |
| `tests/test_release_whole.py` | the release builds and publishes none of the Google Cloud family | none of the AWS family either |
| the release's probe | `released_elsewhere_or_refuse` asks PyPI for each range | unchanged code; it now asks for the AWS family's range too, so the phase 3 release refuses until 0.2.0 is on PyPI |
| `publish-starters` | layers the families in from the index | unchanged code |
| `tests/cloud_starters/`, `just test-cloud-starters` | `complete`, `standard-gce` | `standard-aws`, `standard-aws-posix` added (R9) |

The sync rule's other trap (spec 005's T049): `uv sync --all-extras`
alone would install the AWS family from the index into this venv once
its extra names a range; every sync names the rule.

## R13. Release traps carried from spec 005

**Read** in spec 005's records (T063, T066, T067, T069):

- **SDK READMEs are inside their wheels.** The READMEs of `base`,
  `hashicorp-utils` and `tofu-roots` name the AWS family (links and
  neighbours). A change to them under the published 0.2.1 makes the
  own-versions probe refuse the release, as it did at 0.1.12; phase 3
  runs `just sdk-bump kit last` and `just sdk-bump terraform last`
  (0.2.1 to 0.2.2) when it changes them. The contract's README names
  `cs-image-system-aws-runtime-plugin` only as a namespace example,
  which stays true (**chosen**: left alone, so the contract, which has
  its own version, does not move).
- **A take right after an upload can outrun PyPI.** When `just take`
  stops because PyPI has not listed the release, `UV_REFRESH=1 just
  take <version>` in the reference minutes later finishes it.
- **Record after an apply.** After any run that applied in the
  reference, `just record` with the pinned release comes before the
  push; a scoped run's committed emission is not the whole tree's, and
  the reference's `develop` CI fails without it.
- **The AWS session never lasts 60 minutes**: a box that needs it is
  gated on 40, and a release re-logs in midway.
