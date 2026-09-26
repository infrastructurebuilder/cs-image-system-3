# The daily driver

*How a team actually uses cs-image-system: what must exist before the
first command, the first run, making groups, storages, images and
instances, changing them, what each declaration promises and what proves
it, and what to do when a run fails. Written in the order you meet things,
for the person who USES a release of the system in their own configuration
repository. Where the reference manuals already say it, this page links
rather than repeats: [docs/CONFIGURATION.md](docs/CONFIGURATION.md) is
every file and field, [docs/OPERATIONS.md](docs/OPERATIONS.md) is every
run, rule and procedure, [docs/PLUGINS.md](docs/PLUGINS.md) is every
package, and each package's README ends with the same four sections in the
same place: prerequisites, configuration, what it tests, when it fails. The
standard this page is held to: no one should be surprised by the system's
behaviour after reading it. Where it could say a little less, it says a
little more; skip what you already know.*

## 0. What you are driving

Two things, and it matters which is which.

**The system** is `cs-image-system`, a released Python package: a command
and its plugins. You install it; you never clone this repository to use it
(this repository is where the system is developed; section 9 is for that).
The command turns one YAML tree into infrastructure-as-code and applies it
through gates.

**Your configuration repository** is a git repository you own, and it is
where everything you do happens. It holds:

### What You Provide

- the declarations: **groups** (who may log in where), **storages**
  (volumes, filesystems, buckets), **base images** and **instance images**
  (what is baked), and **instances** (what runs), under `cfg/`, `groups/`,
  `storages/`, `images/`, `instances/`
- the provisioning content the images are baked with (playbooks, scripts)

### What the System Provides

- the emission the system writes, under `generated/`: Packer and OpenTofu
  for six lifecycles in a fixed order (identity, storage, base-image,
  instance-image, release, retention), and the runner script of each;
- the system's memory of what exists, under `meta-state/`, written by
  runs and committed
- its own `Justfile`, the single entry point for everything below; its
  own CI under `.github/workflows/`; the public-safe hook under
  `.githooks/`; the terraform modules the emitted roots call, under
  `tfmodules/`; and three helper scripts under `scripts/`.

You do not write these from nothing: a **starter tree** is a
whole repository of exactly this shape, and section 1.9 starts from one.
Three commitments show up everywhere and explain most of what follows:

- **Humans own identity; code owns access.** People and OPA groups are never
  destroyed by the system. Who may log in where is YAML, and a change to
  the YAML is the explicit decision.
- **Nothing irreversible happens by default.** A run is a dry run unless you
  say so; an apply happens only when a flag says so and is re-checked at
  execution; a plan that destroys anything no operation sanctioned is
  refused by the gate before it applies.
- **The records are the truth, and reality is checked against them.** Every
  run starts with a state query; a difference the records do not know
  about is drift, and the cycles refuse to start on drift.

The configuration repository is public by design in the reference
deployment, so nothing secret is ever committed to it: values that must
stay private are committed encrypted, and a hook refuses anything that
looks like a secret.

## 1. Before the first command

Everything in this section exists outside the system. The system finds it
through a configuration field or an environment variable, never creates it,
and refuses to run without it. Do these once per environment; the
per-package detail is each README's "Prerequisites and integration" section
(section 7 links them).

### 1.1 The release, and how it reaches you

The command comes from the index, in one of two ways. Either is fine; the
starter tree's `Justfile` works with both.

```sh
uv tool install cs-image-system        # the command on PATH; the default the Justfile assumes
cs-image-system --help
```

or, for a team that pins its dependencies in the repository, a
`pyproject.toml` in the configuration repository that depends on
`cs-image-system`, run through `uv run`:

```sh
uv init --bare && uv add cs-image-system
export CSIS="uv run cs-image-system"     # the Justfile reads CSIS; every recipe then goes through uv
```

CI installs the release the same way, pinned by the content of
`.csis-version` when that file exists (section 1.8). Upgrading the system
is upgrading the package; the configuration repository does not change.
The versions on the index, and what each carries, are the system
repository's releases ([OPERATIONS.md](docs/OPERATIONS.md), "Installing a
release").

### 1.2 Tools and their floors

The configuration pins the tools it expects in `cfg/executables.yml`
([CONFIGURATION.md](docs/CONFIGURATION.md), section 3), and `validate` and
every run check that each exists at its path and meets its floor. The
floors the reference deployment runs today:

| Tool | Floor | Used by |
| --- | --- | --- |
| `just` | 1.56+ | the recipes |
| `git` | |  the commits |
| `uv` | | installing the release (either way above) |
| `tofu` (OpenTofu) | `>1,<2` | every terraform root, may also swap out for `terraform` executable |
| `packer` | `>=1.14` | every bake |
| `aws` (AWS CLI v2) | `>=2.32` | sessions, the state bucket, archives |
| `gcloud` | `>=500` (the SDK version, not a component's date) | GCE, IAP sessions, ADC |
| `ansible-playbook` (ansible-core) | `>=2.16` | ansible modifications and the launch playbook |
| `bash` | `>=5` | never macOS's 3.2 |
| `docker` | `>=24` | the modification tests |
| `yq`, `jq` | `>=4.5`, `>=1.7` | recipes |
| `sft` (the Okta Privileged Access client) | 1.114 in use | logging into machines; `just sft-install` on an apt system |
| the Session Manager plugin | | SSM sessions to AWS instances (verify, aliases, unmount) |

A version below the floor fails validation by name; a tool that is absent
is a validation failure too. Version checks are real: a CI failure naming a
tool's version means the floor moved, not that the tool broke.

### 1.3 AWS, if you use the AWS runtime

| What | Why the system needs it | Where it is named |
| --- | --- | --- |
| An account and a way to log in: an SSO portal and a profile (an `sso-session` profile lets the CLI token renew itself while the portal session lives) | every `aws` runtime, and every root whose state backend is `s3`. The system defers to what the tree declares: a GCE-only repository keeps its state in `gcs` (as the GCE starter does) and needs no AWS account at all; the reference deployment keeps its GCE roots' state in S3 beside its AWS roots by its own decision | `credentials.profile_name` on the runtime; `AWS_PROFILE` and `AWS_REGION` in your shell |
| An S3 bucket for terraform state, encrypted, with lock files | every root's state | `cfg/state-backends.yml` |
| A VPC with private subnets and no internet gateway; a default subnet per runtime | instances launch there with no public IP | `networking:` on the runtime |
| The security group SSH ingress comes from (the OPA gateway's) and any group every instance must wear (the gateway relay requires its group on the target) | access to the machines | `ssh_ingress_security_group_ids`, `addl_security_groups` |
| An instance profile with SSM | bakes and sessions over Session Manager, since nothing has a public IP | operator wiring; the emitted packer sources use `ssh_interface = session_manager` |
| For CI: two OIDC roles, one read-only (the `live` job) and one write role that trusts `main` alone (the `perform` job) | CI never holds a static key | repository secrets `AWS_ROLE_ARN`, `AWS_APPLY_ROLE_ARN` |

The network rules are absolute and are yours to keep, not the system's to
enforce: never modify existing security groups, subnets or routes; never
open ingress to the shared address space; new security groups are fine.
The system generates no IAM. Read [OPERATIONS.md](docs/OPERATIONS.md),
"Network" and "Instance access and sizing".

### 1.4 GCP, if you use the GCE runtime

Nothing in the system needs AWS for a GCE runtime: the runtime, its
storages and its state backend are the declarations, and the GCE starter
declares a `gcs` backend. What GCE needs is below.

A project, a network and subnet, Application Default Credentials that
impersonate the runner service account
(`gcloud auth application-default login --impersonate-service-account=<runner>@<project>.iam.gserviceaccount.com`,
which needs the Token Creator role on it), the IAP tunnel role on your own
Google identity for sessions, and an SSH key your agent holds without a
passphrase (a session hook cannot prompt). Every GCE cycle ends with
`just cloud-empty <runtime>`, so nothing billable is left standing beyond
the declared storages. Read [OPERATIONS.md](docs/OPERATIONS.md), "GCE cost
discipline".

### 1.5 Okta and Okta Privileged Access

| What | Why | Where it is named |
| --- | --- | --- |
| An Okta API services app with key-based auth and the read scopes, DPoP off, the `*.manage` scopes ungranted | user lookups by the `okta/okta` provider | `OKTA_API_CLIENT_ID`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID`, `OKTA_API_SCOPES` |
| An OPA team, and a service user's API key pair | groups, policies, memberships, enrollment tokens, the gid shim, the server registry, the state query | `team:` on the group builder; `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` (the team name with non-alphanumerics as `_`); needed at load, not only at apply |
| A resource group the system's projects live under, and a gateway | the login projects, the relay | `OKTA_RESOURCE_GROUP`; `okta_gateway_selector` |
| For CI: a workload connection and a workload role, made by hand once | CI logs in as a workload, never with a key | `workload_connection`, `workload_role` on the group builder; [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md) is the checklist, step by step |
| For people: the `sft` client, enrolled in the team (`sft enroll`), with a live session (`sft login`) | `sft ssh <machine>` | your machine |

Enrollment tokens are the system's: one per project, created and rotated
through terraform, never typed. Users are looked up, not created: a person
makes them in the Okta admin console and declares them in `groups/`.

### 1.6 The age identities

Any value in the tree may be committed encrypted (`ENC[age:...]`), and the
reference deployment keeps its rosters and its e-mail domain that way. Each
holder keeps an age identity under `~/.config/cs-image-system/age/`, never
committed; every identity's public key is a recipient in
`cfg/_config.yml`'s `encryption.recipients`; CI's identity is a repository
secret. Whatever loads the configuration needs `CSIS_CONFIG_IDENTITY` in
its environment, and a load that meets a marker no identity can open
refuses with the field's path. A removed recipient is followed by `just
cli reencrypt`. The starter trees carry a TEST identity so they load as
they stand; replacing it is the first thing a team does (section 1.9).
Read [CONFIGURATION.md](docs/CONFIGURATION.md), section 13, and
[OPERATIONS.md](docs/OPERATIONS.md), "Encrypted values".

### 1.7 The shell

The configuration repository has a gitignored `.envrc` you write by hand:
the Okta and `TF_VAR_<team>_*` names, `CSIS_CONFIG_IDENTITY`, and `CSIS`
if you run the release through `uv`. The recipes assume no direnv, so
every session starts:

```sh
cd <your configuration repository>
source .envrc
export AWS_PROFILE=<profile> AWS_REGION=<region>
aws sso login --profile <profile>     # when preflight says the session is absent or expired
just preflight                        # every session the runtimes need, without loading anything
```

`just validate` is the first thing to run after any edit. An `sso-session`
profile reports "refreshes itself (no fixed expiry readable)": that is
normal, and it means the portal session's end, not the token's, is what
ends a long run. The variable table is
[CONFIGURATION.md](docs/CONFIGURATION.md), section 14; the credentials
contract is [OPERATIONS.md](docs/OPERATIONS.md), "Credentials contract".

### 1.8 CI

The configuration repository's own workflow, `.github/workflows/ci.yml`
from the starter tree, has three jobs, and each installs the release the
way section 1.1 does (pinned by `.csis-version` when present):

- **`verify`** needs no secret: the tree must be public-safe and the
  `Justfile` must parse. Every push and pull request.
- **`live`** is read-only against the clouds and OPA: `just validate`, a
  dry run, the strict state query, then the private mirror removed.
  Pushes and the nightly schedule, never pull requests (forks carry no
  secrets).
- **`perform`** runs on `main` alone, under the write role: the performing
  run of the runtime the workflow names (`just cloud-perform`), the login
  proof as a workload, and the records committed and pushed back.

Each job is gated on the repository secrets it needs, named in the
workflow: none configured is SKIPPED and said so in the job summary, some
configured and some missing is a failure that names them. A green job is
not proof its steps ran, so read the summary. Every `REPLACE-ME` in the
workflow is a team value: the runtime it performs on, the region, the
`TF_VAR_<team>` names.

### 1.9 The configuration repository, from scratch

Start from a starter tree; do not write from nothing. The release
carries three and writes one out:

```sh
cs-image-system init-config my-config                          # standard-aws, the default
cs-image-system init-config my-config --from standard-gce
cs-image-system init-config my-config --from complete
```

[docs/examples/standard-aws/](docs/examples/standard-aws/README.md) is the
smallest repository that works on the AWS plugin set, one of everything,
every value you must replace an obvious `REPLACE-ME` and every line that
is a decision commented; [docs/examples/standard-gce/](docs/examples/standard-gce/README.md)
is the same for GCE; [docs/examples/complete/](docs/examples/complete/README.md)
has every plugin, every field and every variation, and is where to look
when the reference manual's table needs a living example. Those three
directories are the source the release is built from: all three load and
validate in the system's tests, the built wheel is held to them byte for
byte, and their `Justfile`, workflow, hook and modules are the release's,
so a tree written by `init-config` cannot drift from the system that wrote
it. `.csis-version` in the written tree names that release.

Run `init-config` again, in the repository, after upgrading the release:
into a tree that already holds a configuration it writes only the parts
the release owns (the `Justfile`, the workflow, the hook, `.gitignore`,
`tfmodules/`, `.csis-version`) and never a line of the YAML; a
release-owned file you changed is refused by name until you pass
`--force`.

Then, in the written tree:

1. `git init`, `just init` (the hook, the plugin cache, a check that the
   command runs), and a first commit of the tree as it stands.
2. **The identity.** Generate your own age key pair, put its public key in
   `cfg/_config.yml` `encryption.recipients` in place of the test
   recipient, run `just cli reencrypt` with `CSIS_CONFIG_IDENTITY` pointing
   at the test identity, then delete `.age-identity` and its allowance in
   `public_safe.allow`. From here the tree opens only to your keys.
3. **`cfg/`**, file by file ([CONFIGURATION.md](docs/CONFIGURATION.md),
   section 1, is the load order): `_config.yml` (every `apply_*` flag
   `false` to begin with, `public_safe.allow`, `admin_public_keys`,
   `preflight.expected_run_minutes`, `require_released_builds`,
   `require_image_tests`); `executables.yml` (the tools and floors above);
   `runtime-builders.yml` (one entry per cloud context: profile, region,
   VPC, subnets, security groups; ids are configuration, never code);
   `state-backends.yml` (the bucket and prefix; every root resolves its
   backend own, then its runtime's, then the default, and `validate`
   refuses two roots that would share a location); the builder files,
   each entry marked `is_default` where a collection may omit `type`.
4. **The collections**: `groups/` (users, then groups), `storages/`,
   `images/`, `instances/`. `meta-state/` is the system's and is written
   by runs; the one file a person touches there is `aliases.txt`, and
   only by appending names to it.
5. **The workflow**: replace every `REPLACE-ME` in
   `.github/workflows/ci.yml`, set the repository secrets it names, and
   push. The `verify` job is green on a tree that is public-safe; the
   others report SKIPPED until their secrets exist.

## 2. The first run

```sh
just validate                 # every rule; exit 1 on any failure, nothing generated
just dry                      # a DRY run of every lifecycle: generates, plans nothing against remote state
```

Read what it wrote. `generated/<lifecycle>/run-<lifecycle>.sh` is exactly
what a real run would execute, in order, reviewable line by line;
`generated/run-summary.json` says what was requested, what would apply,
and why each image would or would not bake (`bake_plan`);
`generated/state-report.json` is the state query that ran first. A dry run
never touches remote state and never burns anything: no alias is drawn,
no pin moves, no launch is recorded. Commit `generated/` and `meta-state/`
with the tree: the emission is part of the repository, reviewable in every
pull request.

A real run is `just run <lifecycles>`: it does exactly what the dry run's
scripts showed, gated. Each terraform root plans to a file, the gate
refuses any destroy no operation sanctioned, `apply-check` re-reads the
flag at execution, and only then applies; the run commits its records and
emission, and you push. The terraform commands run in a private mirror of
the emission, `_private/<lifecycle>/<root>/`, where the ciphertext is
opened; the mirror is never committed. Read
[OPERATIONS.md](docs/OPERATIONS.md), "What a run is" and "The apply gate".

## 3. Making things

Each thing is a declaration, a run of its lifecycle with the apply
allowed, and a record afterwards. The rhythm is always the same: declare,
`just validate`, `just dry`, read the script, `just run`, push, `just
state-query --strict`.

### 3.1 A group and its access

Declare users and the group in `groups/` ([CONFIGURATION.md](docs/CONFIGURATION.md),
section 11): `members` may log in, `admins` may log in with sudo, and the
root group's admins are merged into every group's. Run the identity
lifecycle with `apply_identity: true` (a convergent flag, safe to leave
on: it applies only what the YAML says, and the gate refuses destroys):

```sh
just run identity
```

What appears in OPA per group: `<g>_user` and `<g>_admin`, a resource
group delegated to the admins, a login project, two security policies
scoped to servers labelled `sftd.tx.group=<g>`, the project's enrollment
token, and, with the workload objects named, a CI login policy that copies
the user policy with the workload role as its only principal. The record
is `meta-state/identity.yaml`, and the state query then reports members,
admins, the gid, the token's liveness and the CI policy per group. A
membership removed from the YAML is removed from OPA by the next real
identity run: the plan shows the destroy and the gate sees it. A
membership removed in OPA first is pruned from terraform state by the
runner itself, after a backup, so the plan does not trip on it (section
4, "Who may log in").

### 3.2 A storage

Declare it in `storages/` with its type (EBS, EFS, S3 on AWS; a persistent
disk, GCS or Filestore on GCE), size or tier, the groups allowed, the
share mode, and optionally a data `lifecycle` and builder `variables`.
**A storage exists exactly as long as it is declared.** Run:

```sh
just run storage                # apply_storage: true in cfg/_config.yml
```

An EBS volume is bound to one availability zone and, with
`attachment_cardinality: single`, to one instance at a time; the runtime's
default subnet decides where instances land, and validation refuses a
combination that cannot attach. The records are `meta-state/storage.yaml`
(what was declared) and `meta-state/storage-state.yaml` (every transition,
with tombstones). Read [OPERATIONS.md](docs/OPERATIONS.md), "Storages",
for archive, restore, detach and the tombstone rules.

### 3.3 A base image

An OS builder in `cfg/os-builders.yml` names the vendor image by owner and
filters, its family, whether to update it, the admin user's public keys,
and the identity and storage types it must be prepared for (the OPA agent
and the EFS and S3 tooling ride on those declarations). It bakes when it
has no build, when its inputs' fingerprint changes, when its update
refresh is due, or when forced:

```sh
just cloud-bake <runtime>       # the bakes that are due on that runtime; preflight first
```

The build lands in `meta-state/lineage.yaml` with its fingerprint and
tags, and the cloud image carries the same tags, so the state query can
tell a recorded image from a foreign one. Read
[OPERATIONS.md](docs/OPERATIONS.md), "When an image bakes".

### 3.4 An instance image

Declare it in `images/`: `source_image` (a base image, or another instance
image), `group` (its owner: that group's members get access),
`parent_policy` (`pinned`, or `follow` to re-bake when the parent moves),
`modifications` (ansible playbooks, or bash `script`, `scripts` and
`ensure`), `tests` (in-bake: `packages`, `commands`, `users`),
`tests.post_bake` (the same proof again on a launched machine, plus
`mounts`), and `release: {model: <name>}`. Prove the modifications
offline first, then bake:

```sh
just test-mods --strict         # every modification twice in a container: apply, then idempotence
just cloud-perform <runtime>    # the due bakes, the declared releases and retention, on that runtime
```

The in-bake tests fail the bake; a build is recorded only on success. The
release lifecycle records the build as the model's current release only
once its post-bake tests have passed on a launched machine, which for a
brand-new image means launching an instance of it first. Read
[OPERATIONS.md](docs/OPERATIONS.md), "Post-bake tests and releases".

### 3.5 An instance

Declare it in `instances/`: `image`, `machine_type`, `storages` with mount
points, tags, and either nothing (a durable machine that stands) or
`ephemeral: true` (launched, verified and torn down in one run, with
`on_failure` and `teardown_after` policies). Launch it:

```sh
just cloud-launch <runtime>     # instance-image alone, no re-bake, the runtime's roots allowed to apply
```

What a launch does: the machine boots as `<name>-001` (the first
generation of that name; a replacement later is `-002`), sets its
hostname, enrolls in OPA with the project's token, mounts its storages,
records its launch parameters (immutable from now on) in
`meta-state/launch-params.yaml`, opens generation 1 in
`meta-state/instance-state.yaml`, and gets its names: the bare declared
name and the provider's `ip-...` label as aliases, and a memorable name
from `meta-state/aliases.txt` if the pool has one (the pool's line is
commented out with what took it and when). Then:

```sh
just cloud-verify <runtime> <name>       # startup scripts, booted image, mounts, the post-bake tests; recorded
just ci-login-proof <name>               # sft ssh by name through the policy; recorded
```

A durable instance's FIRST launch of a brand-new image is the one case
where `require_released_builds: true` and `release` pull against each
other, since the proof can only run on the machine itself: the release
grace admits the series head while its own proof is under way, so the
sequence is launch, verify, then `just run release`, with the flag left
on. Read [OPERATIONS.md](docs/OPERATIONS.md), "A model image, end to end:
the second release".

## 4. Changing things

Every change is a change to the YAML, then a run. The procedures are in
[OPERATIONS.md](docs/OPERATIONS.md), "Procedures" and the sections named
below; this is the order a person meets them.

| Change | Do | Then |
| --- | --- | --- |
| A modification, a test or a package on an image | edit `images/`, `just test-mods --strict`, commit | the bake is due: `just cloud-perform <runtime>` bakes the new build. A durable instance then takes it in ONE command, `just cloud-upgrade <runtime> <instance>`: pin, gated replace, proof on the new machine, release, names, with `require_released_builds` left true throughout. "A model image, end to end: the second release" |
| The base an image is built from | `parent_policy: follow` re-bakes on its own when the base moves; `pinned` waits for `just cli upgrade image <image>` | then as above |
| The build an instance runs | `just cli upgrade instance <name> [--to <build>]`, or the `cloud-upgrade` recipe above | `just cloud-launch <runtime>`: the plan carries one `-replace`, the gate whitelists it and the volume attachments; the new machine is the next generation with the next number, the old registration is retired, the names come back once it enrolls |
| A storage's size or type on EBS | declare what exists, or intend a replacement | `volume_type` and `size` force replacement |
| Detach a storage from a launched instance | remove it from the instance's `storages` | the run unmounts on the machine first and refuses the plan without the receipt; adding it back is a replacement |
| Archive, restore, destroy a storage | `state: archived` (EBS and pd only), `active` again, `destroyed`, or delete the entry | each goes through the gate; tombstones stay in `storage-state.yaml` |
| Who may log in | edit `members` or `admins` | `just run identity`. A removal OPA still holds is a destroy the plan shows. A membership already gone from OPA (removed in the console, or a roster conformed to OPA by hand) is pruned from terraform state by the runner's `prune-attachments` step, after a backup to `_private/state-backups/`, so the provider's refresh error never blocks the plan |
| Stop managing a group | `unmanaged: true` | released from state, never destroyed; deleting the entry is a validation failure |
| Decommission an instance | delete the entry, or `just cli --undeclare instance:<name> run instance-image --only none --apply-runtime <runtime> --commit` for one run | the gate whitelists exactly its destroy; the launch record, pin and OPA registration are forgotten; the pool name it took stays spent |
| Rotate the admin key | add the new key, bake, upgrade every instance, remove the old key, repeat | "Rotate the admin key" |
| Move a root's state | change `state_configuration`, `just cli --no-dry-run run <lifecycle> --migrate-state <root>` | backs up, copies, accepts only a clean plan at the new location, records the move |
| Adopt something made by hand | `just cli state import`; for memberships, `tofu import` then a no-op apply | "Adopt out-of-band group membership" |
| Upgrade the system | `uv tool upgrade cs-image-system` (or bump the pin and `uv lock`); `.csis-version` for CI | `just validate`, `just dry`, and read the diff of `generated/`: an emission change is what a system upgrade looks like |

Two habits keep changes safe. Dry-run first and read the script: a dry
run shows the plan the real run will gate. And never edit a launched
instance's declaration expecting an in-place change: launch parameters are
immutable, and the system will tell you so and name the way, a replacement
or a detach.

## 5. What specifies, and what tests it

Every declaration that states an intent has a mechanism that proves it and
a place the verdict lands. Nothing is taken on faith.

| The declaration | Where | Proved by | The verdict lands in |
| --- | --- | --- | --- |
| `tests: packages / commands / users` on an image | `images/` | the in-bake tests compiled into the bake; a failure fails the bake | `meta-state/lineage.yaml` (a build is recorded only on success) |
| `tests.post_bake` (the same, plus `mounts`) | `images/` | `just cloud-verify` on the launched machine; `release` requires a passing record | `meta-state/image-tests.yaml`, `meta-state/verifications.yaml` |
| `modifications` (`playbooks`, `script`, `scripts`, `ensure`) | `images/` | `just test-mods --strict`: twice in a container, apply then idempotence; then the bake | `meta-state/mod-tests.yaml`; `/opt/csis/mods` on the image |
| `release: {model}` | `images/` | the release lifecycle, gated on the post-bake record | `meta-state/releases.yaml` |
| `require_released_builds`, `require_image_tests` | `cfg/_config.yml` | `validate` refuses an unreleased pin, except the series head under its own proof (the release grace, which says why it allowed or refused); `release` refuses without the record | a validation error naming what is missing; a refused release |
| `parent_policy`, `image_policy` | `images/`, `instances/` | the bake plan; the state query's `stale` | `run-summary.json` `bake_plan`; `state-report.json` |
| `ephemeral`, `on_failure`, `teardown_after` | `instances/` | launch, `verify instance`, teardown in one run | `meta-state/verifications.yaml`; the launch record forgotten |
| `storages[]` and `mount_point` | `instances/` | verify's "data disks mounted"; an unmount receipt before a detach | `meta-state/verifications.yaml`; `unmount-receipts/` in the workspace |
| a storage's `state` and `lifecycle` | `storages/` | the storage lifecycle; the state query's `missing` and `stale` | `meta-state/storage-state.yaml`, `storage.yaml` |
| `apply_*` | `cfg/_config.yml` | `apply-check` at execution; the gate before it | `run-summary.json` `apply` |
| `members`, `admins` | `groups/` | the identity apply; the runner's prune step against OPA; the state query's membership diff; the login proof | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| `workload_connection`, `workload_role` | `cfg/group-builders.yml` | the CI policy reconcile after the identity apply; the state query's `workload` record; the `perform` job's login | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| the canonical hostname, the aliases, the pool | the system's | `validate` (label rules, claimed names, the pool's free lines); the state query's notes; `sft resolve` | `launch-params.yaml`, `instance-state.yaml`, `aliases.txt` |
| the committed emission | `generated/` | `just config-drift`: a dry run against what is committed | exit 1 with the diff |
| the records against reality | `meta-state/` | `just state-query --strict`, both clouds and the OPA API; the `live` job nightly | `generated/state-report.json` |
| that nothing published is secret | everything committed | `just public-safe`, the pre-commit hook, the commit gate, the plaintext scan of the run's own decrypted values; the `verify` job | a refusal naming the file and line |
| the tools and their floors | `cfg/executables.yml` | `validate` and every run | a validation error by name |

Read [OPERATIONS.md](docs/OPERATIONS.md), "The state query", for the drift
classes and which are hard: `missing` when the record claims liveness;
`stale`, `changed` and `foreign` never; `unavailable:` is a provider that
could not answer and is never a claim, though the strict query refuses on
it because it cannot vouch.

## 6. When it fails

Where to look, always: the run's terminal output (keep it), then
`generated/run-summary.json` (`error`, `validation_errors`, `apply`),
`generated/state-report.json`, `meta-state/runs.yaml`, and the runner
script under `generated/<lifecycle>/`. `just cli --verbose ...` prints the
debug lines, including the HTTP status of an OPA call that failed. A
terraform command a run ran can be re-run by hand in the private mirror,
`_private/<lifecycle>/<root>/`, never in `generated/`, which carries
ciphertext. State backups the runner took before a `state rm` are under
`_private/state-backups/`. The exit codes are
[OPERATIONS.md](docs/OPERATIONS.md), "Run outputs and exit codes". In CI,
the job summary says whether a job ran at all.

The failures below all happened in the reference deployment, and each row
names what was done. New ones get a row here and, if they need work, an
item in the open hygiene bundle in [TODO.md](TODO.md).

| Symptom | Meaning | Do |
| --- | --- | --- |
| `init: 'cs-image-system' is not runnable` | the release is not installed, or `CSIS` names a command that does not run | `uv tool install cs-image-system`, or `export CSIS="uv run cs-image-system"` beside a pyproject that depends on it |
| `preflight: a session has EXPIRED`; `Token has expired and refresh failed`; `Error reading config file : AWS Error ...` | the AWS portal session behind the profile ended (8h from a browser sign-in; less if the CLI token was minted mid-session); an `sso-session` profile has no fixed expiry the system can read, so a lapse mid-run is environmental, not a defect | `aws sso login --profile <profile>`, then re-run |
| `runtime <gce> could not answer` under `unavailable:` | no Application Default Credentials, or they expired, or Google was unreachable | `gcloud auth application-default login --impersonate-service-account=...`; an `unavailable` line is not drift, but the strict query refuses on it |
| `state query storages/<pd> unavailable: ... oauth2.googleapis.com ... Read timed out` (2026-09-23) | the network to Google, not the system; `cloud-preflight` then exits 1 and the recipe stops before its first step | check `gcloud auth application-default print-access-token`; run the recipe again |
| `Validation failed with N error(s)` | a rule failed before anything was generated; each line names the file and the rule | fix the declaration; `just validate` alone re-checks in seconds |
| `unavailable: groups/<g>: HTTP 401 ...` for every group at once | the OPA API could not be asked: a lapsed key pair, or `.envrc` not sourced (before 2026-09-23 this read as five `missing` groups) | `source .envrc`; a real absence is one `missing [HARD]` group, from an answered 404 |
| `OPA credentials for team '<t>' not found in the environment` at load | the `TF_VAR_<team>_key` / `_secret` pair is needed by `validate` and dry runs too, not only at apply | export them (`.envrc`); in CI, the secrets the workflow names |
| `no users found using search criteria: profile.login eq "x@ENC[age:..."` | a plan ran on the committed emission, where the e-mail domain is ciphertext | the system plans in the mirror since 2026-09-22; by hand, run terraform under `_private/`, never `generated/` |
| `user "x" is not present within group "g"` at plan | a membership the YAML dropped and OPA already lacks is still in terraform state; the provider errors on refresh instead of dropping it | since 2026-09-23 the identity runner's `prune-attachments` step removes it after a backup, and the group root's generation-time plan does not refresh; if it still appears, the runner did not reach that step: read the run's output above the plan |
| `state backup for workspace '...' REFUSED: ... is not an initialised terraform root` | the backup step was started somewhere other than the root the runner initialised; nothing left state | the runner stops; report it, since the step is the system's and ran where the system put it (2026-09-23 10:15, fixed the same day) |
| `DESTROY NOT WHITELISTED: <address>` (gate, exit 3) | the plan destroys something no operation sanctioned | read the plan; if a decommission, detach or replacement was intended, declare it so; never widen the whitelist by hand. A replacement whitelists the instance AND its volume attachments (2026-09-22) |
| `launch parameters are immutable after launch` | a launched instance's declaration changed in place | revert, or make it a replacement (`upgrade instance`), or a detach (remove the mount) |
| `instance 'x' is pinned to build ... which is not a released build (...; no grace: <reason>)` | `require_released_builds` and an unreleased pin the grace does not cover; the reason says which condition failed (not the series head, no in-bake record, a failed post-bake, or the instance neither stands on it nor is being replaced onto it) | act on the reason: move the pin, fix the build, or verify; never switch the flag off |
| `upgrade: instance 'x' is already pinned to <build>` (exit 1) | the pin is already at the target, usually because `cloud-upgrade` already ran to completion | nothing to do; the recipe stops here by design |
| `release: ... no passing post-bake record` | the build has never been verified on a launched machine | verify first (an ephemeral cycle, or the standing machine after the replace) |
| `changed instance x: booted image ... != pinned build ...` | the pin moved without a replacement, or a replacement is pending (then a `note`, not drift) | `upgrade instance` then `cloud-launch`; or move the pin back |
| `CI login policy '<g>_v1_security_policy_ci' is absent` | the identity apply has not run since the workload objects were named | `just run identity` with `apply_identity` on; never hard drift |
| `workload role '...' is not known to OPA` | the operator's object is missing | [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md), section 2 |
| `sft resolve ...: exit 126` with nothing on stderr | the `sft` client's session lapsed and `--quiet` forbade the browser (2026-09-23, after a replace: the registration half of the proof had passed) | `sft login`, then the proof again; as the workload, the token was missing or refused |
| `'<name>' has 2 registrations: ...` in a login proof | two servers answer to one canonical hostname | retire the stale one (a replacement now does this itself); `sft ssh` would reach either |
| `Instance x: alias 'y' SKIPPED -- already claimed by <id>` | a stale record holds the name | retire that record; the alias comes back on the next applies-on run |
| `verify ...: SKIPPED -- the machine is STOPPED`; `login proof ...: SKIPPED` | someone switched the machine off; a note, not drift; nothing is started for a proof | start it if you want the proof, then re-run |
| `Instance x: not enrolled within 300s of its launch; no alias this run` | the machine booted this run and sftd had not enrolled in time | the next applies-on run gives the names back |
| `--locked: another tofu-using command holds ...` (exit 75) | one tofu process at a time; another recipe is running | wait; remove the lock directory only if the process is gone |
| `full-test: passed` above `SKIPPED the credential-gated legs` | the legs did not run: a session was absent | not a pass; source the shell, log in, run again |
| `Meta-state commit: never staging generated/.../instances.auto.tfvars` | the instance root's variable file is where it belongs and is never committed by design; before 2026-09-23 the release and retention runs left stray copies too | nothing; a stray copy under `generated/release/` or `generated/retention/` from an older run is deleted by hand once |
| `mod tests: N failed` or `not idempotent` | a modification fails, or changes something on its second run | make it idempotent: `ensure`, `unless`, `changed_when: false`; read `meta-state/mod-tests.yaml` |
| `rpm -q vim` fails on AlmaLinux 10; `dnf install amazon-efs-utils` finds nothing | the package is `vim-enhanced`; efs-utils is not in AlmaLinux's repositories | name the real package; build efs-utils from source as the reference image does |
| `public-safe: ... <file>:<line>` from the hook | a committed line looks like a secret, a key, a plan or a state file | never bypass the hook; encrypt the value, or allow it BY DECISION in `cfg/_config.yml` `public_safe.allow` |
| the `live` or `perform` job green with `SKIPPED` in its summary | no secret was configured, so nothing ran | not a pass: set the secrets the workflow names |

## 7. Every plugin, in one paragraph each

Each README ends, after its own content, with the same four sections:
**Prerequisites and integration**, **Configuration reference** (every field
and every variation), **What it tests and verifies**, **When it fails**. The
four links after each paragraph go straight to them. The three core
packages come first; a plugin is selected by the `type:` a builder entry
declares.

- [base](packages/base/README.md): the core. Models, the plugin registry,
  lifecycles and phases, the run context, meta-state, encryption, the
  public-safe gate, lineage, releases, retention, launch parameters,
  generations, aliases, the state query. Every rule in the manual's
  section 5 is enforced here.
  [prerequisites](packages/base/README.md#prerequisites-and-integration) ·
  [configuration](packages/base/README.md#configuration-reference) ·
  [tests](packages/base/README.md#what-it-tests-and-verifies) ·
  [failures](packages/base/README.md#when-it-fails)
- [system](packages/system/README.md): the `cs-image-system` command and
  every subcommand; the global options that decide dry or real, overlays,
  undeclares; the commands runner scripts call back into.
  [prerequisites](packages/system/README.md#prerequisites-and-integration) ·
  [configuration](packages/system/README.md#configuration-reference) ·
  [tests](packages/system/README.md#what-it-tests-and-verifies) ·
  [failures](packages/system/README.md#when-it-fails)
- [hashicorp-utils](packages/hashicorp-utils/README.md): the terraform/tofu
  library: providers and backends by reference, the init, the gated plan
  then gate then apply sequence, the private mirror for plans and applies.
  [prerequisites](packages/hashicorp-utils/README.md#prerequisites-and-integration) ·
  [configuration](packages/hashicorp-utils/README.md#configuration-reference) ·
  [tests](packages/hashicorp-utils/README.md#what-it-tests-and-verifies) ·
  [failures](packages/hashicorp-utils/README.md#when-it-fails)
- [aws-runtime-plugin](packages/aws-runtime-plugin/README.md): the AWS
  cloud context: credentials, network discovery, the image query, power
  state and identity hooks, SSM sessions, retention.
  [prerequisites](packages/aws-runtime-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/aws-runtime-plugin/README.md#configuration-reference) ·
  [tests](packages/aws-runtime-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/aws-runtime-plugin/README.md#when-it-fails)
- [gcloud-runtime-plugin](packages/gcloud-runtime-plugin/README.md): the
  GCE context: ADC and impersonation, IAP sessions, labels, the cost
  posture.
  [prerequisites](packages/gcloud-runtime-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/gcloud-runtime-plugin/README.md#configuration-reference) ·
  [tests](packages/gcloud-runtime-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/gcloud-runtime-plugin/README.md#when-it-fails)
- [default-os-plugin](packages/default-os-plugin/README.md): the OS
  families: vendor image lookup, updates, the admin user and its keys, the
  prerequisites a base image bakes for its identity and storage types.
  [prerequisites](packages/default-os-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/default-os-plugin/README.md#configuration-reference) ·
  [tests](packages/default-os-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/default-os-plugin/README.md#when-it-fails)
- [packer-plugin](packages/packer-plugin/README.md): bakes: sources, build
  blocks in dependency order, the in-bake tests, the manifest that becomes
  an image id, lineage.
  [prerequisites](packages/packer-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/packer-plugin/README.md#configuration-reference) ·
  [tests](packages/packer-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/packer-plugin/README.md#when-it-fails)
- [ansible-plugin](packages/ansible-plugin/README.md): ansible
  modifications: playbooks staged into the on-image bundle, run in the
  bake and twice in the modification tests.
  [prerequisites](packages/ansible-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/ansible-plugin/README.md#configuration-reference) ·
  [tests](packages/ansible-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/ansible-plugin/README.md#when-it-fails)
- [bash-mod-plugin](packages/bash-mod-plugin/README.md): bash
  modifications: `script`, `scripts` and the declarative `ensure` steps,
  and what idempotence means for each.
  [prerequisites](packages/bash-mod-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/bash-mod-plugin/README.md#configuration-reference) ·
  [tests](packages/bash-mod-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/bash-mod-plugin/README.md#when-it-fails)
- [okta-opa-plugin](packages/okta-opa-plugin/README.md): groups and users:
  OPA groups, resource groups, projects, policies, enrollment tokens, the
  gid shim, the server registry and retirements, the CI login policy, the
  prune step for memberships OPA no longer holds.
  [prerequisites](packages/okta-opa-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/okta-opa-plugin/README.md#configuration-reference) ·
  [tests](packages/okta-opa-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/okta-opa-plugin/README.md#when-it-fails)
- [tf-ebs-instance-plugin](packages/tf-ebs-instance-plugin/README.md):
  terraform/tofu-backed instances and storages on AWS: the instance root, EBS, EFS and S3,
  attachments, detaches, archives, the gate's whitelist, the release
  grace's evidence.
  [prerequisites](packages/tf-ebs-instance-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/tf-ebs-instance-plugin/README.md#configuration-reference) ·
  [tests](packages/tf-ebs-instance-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/tf-ebs-instance-plugin/README.md#when-it-fails)
- [tf-gcp-plugin](packages/tf-gcp-plugin/README.md): the GCE instance and
  storage pieces.
  [prerequisites](packages/tf-gcp-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/tf-gcp-plugin/README.md#configuration-reference) ·
  [tests](packages/tf-gcp-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/tf-gcp-plugin/README.md#when-it-fails)
- [tf-s3-state-plugin](packages/tf-s3-state-plugin/README.md),
  [local-state-plugin](packages/local-state-plugin/README.md),
  [gcs-state-plugin](packages/gcs-state-plugin/README.md): where a root's
  state lives, and how it moves.
  [s3: prerequisites](packages/tf-s3-state-plugin/README.md#prerequisites-and-integration) ·
  [s3: configuration](packages/tf-s3-state-plugin/README.md#configuration-reference) ·
  [s3: tests](packages/tf-s3-state-plugin/README.md#what-it-tests-and-verifies) ·
  [s3: failures](packages/tf-s3-state-plugin/README.md#when-it-fails) ·
  [local: configuration](packages/local-state-plugin/README.md#configuration-reference) ·
  [local: failures](packages/local-state-plugin/README.md#when-it-fails) ·
  [gcs: configuration](packages/gcs-state-plugin/README.md#configuration-reference) ·
  [gcs: failures](packages/gcs-state-plugin/README.md#when-it-fails)
- [dummy-plugin](packages/dummy-plugin/README.md): the extension template
  and the tests' double.
  [prerequisites](packages/dummy-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/dummy-plugin/README.md#configuration-reference) ·
  [tests](packages/dummy-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/dummy-plugin/README.md#when-it-fails)

## 8. The daily habits

1. Start the shell in the configuration repository: `source .envrc` \[or install `direnv` 
   so that the system does it for you\], the profile, `just preflight`.
2. `just validate` after every edit; `just dry` before every real run;
   read the script it wrote.
3. `just cloud-preflight` before any cycle: reality must match the
   records. A provider that cannot answer stops the cycle before it
   starts; that is the point.
4. Real runs commit their records; you push. `main` performs; everything
   else is read-only in CI.
6. `just test` before every commit (the sessions present), `just
   full-test` before a performing run you make by hand.
7. GCP costs are yours: a cycle there ends with `just cloud-empty`, and
   any billable resource left standing is named with its cost.
8. When something fails, the row in section 6 first, then the hygiene
   bundle in [TODO.md](TODO.md); a new failure gets a row.
9. Upgrade the system deliberately: a new release, then `just validate`,
   `just dry`, and the diff of `generated/` read before anything runs.

## 9. If you develop the system itself

Development generally requires a tool that can run `docker` commands, like
docker desktop or OrbStack (maybe PodMan).

Everything above is for a release. Developing the system is this
repository: `just init`, then `just test` is the bar (lint, types, the
fast suite over the frozen fixture and its golden emission), `just full-test` 
adds the docker-backed modification tests and, when the
sessions are present, a dry run and a strict state query over a private
copy of the reference configuration, which is checked out BESIDE this
repository as `cs-image-system-testconfig` for that purpose alone; 
`just release <part|version> [test|pypi]` cuts a release to the index. The
recipes here drive that reference configuration through `just cli ...`
for the system's own live proofs; a team's repository is driven by its own
`Justfile` and never needs this one. Read [OPERATIONS.md](docs/OPERATIONS.md),
sections 2 and 3, [GOLDEN.md](GOLDEN.md), and [PARITY.md](PARITY.md).
