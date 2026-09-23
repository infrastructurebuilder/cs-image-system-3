# The daily driver

*How a person actually uses cs-image-system: what must exist before the
first command, the first run, making groups, storages, images and
instances, changing them, what each declaration promises and what proves
it, and what to do when a run fails. Written in the order you meet things.
Where the reference manuals already say it, this page links rather than
repeats: [docs/CONFIGURATION.md](docs/CONFIGURATION.md) is every file and
field, [docs/OPERATIONS.md](docs/OPERATIONS.md) is every run, rule and
procedure, [docs/PLUGINS.md](docs/PLUGINS.md) is every package, and each
package's README ends with the same four sections in the same place:
prerequisites, configuration, what it tests, when it fails. The standard
this page is held to: no one should be surprised by the system's behaviour
after reading it. Where it could say a little less, it says a little more;
skip what you already know.*

## 0. What you are driving

cs-image-system turns one YAML tree into infrastructure-as-code and applies
it through gates. You describe **groups** (who may log in where), **storages**
(volumes, filesystems, buckets), **base images** and **instance images**
(what is baked), and **instances** (what runs). The system emits Packer and
OpenTofu under `generated/` in the configuration repository, runs it in six
lifecycles in a fixed order (identity, storage, base-image, instance-image,
release, retention), and keeps its memory in `meta-state/` beside it. Three
commitments show up everywhere and explain most of what follows:

- **Humans own identity; code owns access.** People and OPA groups are never
  destroyed by the system. Who may log in where is YAML, and a change to
  the YAML is the explicit decision.
- **Nothing irreversible happens by default.** A run is a dry run unless you
  say `--no-dry-run`; an apply happens only when a flag says so and is
  re-checked at execution; a plan that destroys anything no operation
  sanctioned is refused by the gate before it applies.
- **The records are the truth, and reality is checked against them.** Every
  run starts with a state query; a difference the records do not know
  about is drift, and the operator's cycles refuse to start on drift.

Two repositories: this one (the system) and the **configuration repository**
beside it, `cs-image-system-testconfig`, which holds the YAML, the emission
and the records. Every `just` recipe drives the configuration through
`CSIS_CONFIG_ROOT` (default: the sibling checkout). Both are public; nothing
secret is ever committed to either, and a hook refuses anything that looks
like it. Two example configuration repositories live in this one, under
[docs/examples/](docs/examples/): the smallest tree that works, per cloud,
and the complete one; section 1.9 starts from them.

## 1. Before the first command

Everything in this section exists outside the system. The system finds it
through a configuration field or an environment variable, never creates it,
and refuses to run without it. Do these once per environment; the
per-package detail is each README's "Prerequisites and integration" section
(section 7 links them).

### 1.1 The two checkouts

```text
<some dir>/
  cs-image-system-3/             this repository
  cs-image-system-testconfig/    the configuration repository, on its `develop` branch
```

The Justfile's default root is the sibling; `CSIS_CONFIG_ROOT` overrides.
The configuration's `module_source_base: ../cs-image-system-3/tfmodules`
reaches the terraform modules by that relative path, so keep the shape.
Then, in this repository:

```sh
just init          # uv sync --all-extras and the pre-commit hook; idempotent
just hooks-live    # the same public-safe hook in the configuration checkout
```

`just init` needs `uv` and Python 3.13; every recipe runs Python as
`uv run`. See [OPERATIONS.md](docs/OPERATIONS.md), "Setting up".

### 1.2 Tools and their floors

The configuration pins the tools it expects in `cfg/executables.yml`
([CONFIGURATION.md](docs/CONFIGURATION.md), section 3), and `validate` and
every run check that each exists at its path and meets its floor. The live
tree's floors today:

| Tool | Floor | Used by |
| --- | --- | --- |
| `just`, `uv`, Python 3.13, `git` | | the recipes, the workspace, the commits |
| `tofu` (OpenTofu) | `>1,<2` | every terraform root |
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

### 1.3 AWS

| What | Why the system needs it | Where it is named |
| --- | --- | --- |
| An account and a way to log in: the SSO portal and a profile (`noaa` in the live tree, an `sso-session` profile since 2026-09-21 so the CLI token renews itself while the portal session lives) | every AWS runtime, every S3 state read, the GCE roots too (their state is in S3 by decision) | `credentials.profile_name` on the runtime; `AWS_PROFILE` and `AWS_REGION` in your shell |
| An S3 bucket for terraform state, encrypted, with lock files | every root's state | `cfg/state-backends.yml` |
| A VPC with private subnets and no internet gateway; a default subnet per runtime | instances launch there with no public IP | `networking:` on the runtime |
| The security group SSH ingress comes from (the OPA gateway's) and any group every instance must wear (the gateway relay requires `OKTA-GATEWAY` on the target) | access to the machines | `ssh_ingress_security_group_ids`, `addl_security_groups` |
| An instance profile with SSM (`AmazonSSMRoleForInstancesQuickSetup` in the live account) | bakes and sessions over Session Manager, since nothing has a public IP | operator wiring; the emitted packer sources use `ssh_interface = session_manager` |
| For CI: two OIDC roles, one read-only (the `live` job and every recording step) and one write role that trusts `main` alone (the performing step) | CI never holds a static key | repository secrets `AWS_ROLE_ARN`, `AWS_APPLY_ROLE_ARN` |

The network rules are absolute and are yours to keep, not the system's to
enforce: never modify existing security groups, subnets or routes; never
open ingress to the shared address space; new security groups are fine.
The system generates no IAM. Read [OPERATIONS.md](docs/OPERATIONS.md),
"Network" and "Instance access and sizing".

### 1.4 GCP, if you use the GCE runtime

A project, a network and subnet, Application Default Credentials that
impersonate the runner service account
(`gcloud auth application-default login --impersonate-service-account=csis-runner@<project>.iam.gserviceaccount.com`,
which needs the Token Creator role on it), the IAP tunnel role on your own
Google identity for sessions, and an SSH key your agent holds without a
passphrase (a session hook cannot prompt). GCP is the operator's own
money: nothing is left standing there beyond the declared storages and the
one released image, by decision, and every cycle ends with `just gce-empty`.
Read [OPERATIONS.md](docs/OPERATIONS.md), "GCE cost discipline" and
[BILLING_REMINDERS.md](BILLING_REMINDERS.md).

### 1.5 Okta and Okta Privileged Access

| What | Why | Where it is named |
| --- | --- | --- |
| An Okta API services app with key-based auth and the read scopes, DPoP off, the `*.manage` scopes ungranted | user lookups by the `okta/okta` provider | `OKTA_API_CLIENT_ID`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID`, `OKTA_API_SCOPES` |
| An OPA team, and a service user's API key pair | groups, policies, memberships, enrollment tokens, the gid shim, the server registry, the state query | `team:` on the group builder; `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` (the team name with non-alphanumerics as `_`) |
| A resource group the system's projects live under, and a gateway | the login projects, the relay | `OKTA_RESOURCE_GROUP`; `okta_gateway_selector` |
| For CI: a workload connection and a workload role, made by hand once | CI logs in as a workload, never with a key | `workload_connection`, `workload_role` on the group builder; [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md) is the checklist, step by step |
| For people: the `sft` client, enrolled in the team (`sft enroll`), with a live session (`sft login`) | `sft ssh <machine>` | your machine |

Enrollment tokens are the system's: one per project, created and rotated
through terraform, never typed. Users are looked up, not created: a person
makes them in the Okta admin console and declares them in `groups/`.

### 1.6 The age identities

Any value in the tree may be committed encrypted (`ENC[age:...]`), and the
live tree keeps its rosters and its e-mail domain that way. Each holder
keeps an age identity under `~/.config/cs-image-system/age/`, never
committed; every identity's public key is a recipient in
`cfg/_config.yml`'s `encryption.recipients`; CI's identity is a repository
secret. Whatever loads the configuration needs `CSIS_CONFIG_IDENTITY` in
its environment, and a load that meets a marker no identity can open
refuses with the field's path. A removed recipient is followed by `just
cli reencrypt`. Read [CONFIGURATION.md](docs/CONFIGURATION.md), section 13,
and [OPERATIONS.md](docs/OPERATIONS.md), "Encrypted values".

### 1.7 The shell

Each checkout has a gitignored `.envrc` you write by hand. This
repository's exports the Okta and `TF_VAR_<team>_*` names,
`CSIS_CONFIG_IDENTITY`, and the CI names; the recipe shell has no direnv,
so every session that drives the live tree starts:

```sh
cd cs-image-system-3
source .envrc
export AWS_PROFILE=noaa AWS_REGION=us-east-2
aws sso login --profile noaa        # when preflight says the session is absent or expired
```

`just preflight` reports every session the runtimes need without loading
anything, and `just cli validate` is the first thing to run after any
edit. The `sso-session` profile reports "refreshes itself (no fixed expiry
readable)": that is normal, and it means the portal session's end, not
the token's, is what ends a long run. The variable table is
[CONFIGURATION.md](docs/CONFIGURATION.md), section 14; the credentials
contract is [OPERATIONS.md](docs/OPERATIONS.md), "Credentials contract".

### 1.8 CI

The `verify` job needs nothing. The `live` and `perform` jobs need the
repository secrets listed in [OPERATIONS.md](docs/OPERATIONS.md),
"Repository secrets", and each gate says which are missing or empty; a
green job is not proof its steps ran, so read the summary. The `perform`
job performs on `main` alone, under the write role, logs into a standing
machine through the CI login policy as a workload, and commits its records
to the configuration repository with a fine-grained push token. Read
[OPERATIONS.md](docs/OPERATIONS.md), section 3.

### 1.9 The configuration repository, from scratch

Start from an example rather than from nothing:
[docs/examples/standard-aws/](docs/examples/standard-aws/README.md) is the
smallest tree that works on the AWS plugin set, one of everything, every
value you must replace obviously a placeholder and every line that is a
decision commented; [docs/examples/standard-gce/](docs/examples/standard-gce/README.md)
is the same for GCE; [docs/examples/complete/](docs/examples/complete/README.md)
has every plugin, every field and every variation, and is where to look
when the reference manual's table needs a living example. All three load
and validate in this repository's tests, so they cannot drift from the
code without the bar saying so. The tree and its load order are
[CONFIGURATION.md](docs/CONFIGURATION.md), section 1. Write `cfg/` first,
in any file order:

1. `_config.yml`: every `apply_*` flag `false` to begin with,
   `encryption.recipients`, `public_safe.allow` (what may appear in a public
   commit, by decision), `admin_public_keys` (public keys only; the schema
   refuses anything private), `module_source_base`,
   `preflight.expected_run_minutes`, `require_released_builds` and
   `require_image_tests`.
2. `executables.yml`: the tools and floors above.
3. `runtime-builders.yml`: one entry per cloud context, with its profile,
   region, VPC, subnets and security groups. Ids are configuration, never
   code.
4. `state-backends.yml`: the S3 bucket and prefix; every root resolves its
   backend own, then its runtime's, then the default, and `validate`
   refuses two roots that would share a location.
5. `os-builders.yml`, `image-builders.yml`, `mod-builders.yml`,
   `instance-builders.yml`, `storage-builders.yml`, `group-builders.yml`:
   one entry per builder, each marked `is_default` where a collection may
   omit `type`.

Then the collections: `groups/` (users, then groups), `storages/`,
`base_images/`, `images/`, `instances/`. `meta-state/` is the system's and
is written by runs; the one file a person touches there is `aliases.txt`,
and only by appending names to it. Install the public-safe hook (`just
hooks-live`) before the first commit.

## 2. The first run

```sh
just cli validate                 # every rule; exit 1 on any failure, nothing generated
just cli run --all                # a DRY run: generates, plans nothing against remote state
```

Read what it wrote. `generated/<lifecycle>/run-<lifecycle>.sh` is exactly
what a real run would execute, in order, reviewable line by line;
`generated/run-summary.json` says what was requested, what would apply,
and why each image would or would not bake (`bake_plan`);
`generated/state-report.json` is the state query that ran first. A dry run
never touches remote state and never burns anything: no alias is drawn,
no pin moves, no launch is recorded.

```sh
just cli run --all --commit       # still dry; commits the emission and the records into the configuration repository
```

The commit is by pathspec (`meta-state/` and the run's `generated/`), never
staging plans, state, tfvars or key material, and every staged file passes
the public-safe scanner. Push the configuration repository's `develop`
yourself: nothing in the tooling pushes.

A real run is `just cli --no-dry-run run <lifecycles> --commit`, and it
does exactly what the dry run's scripts showed, gated: each terraform root
plans to a file, the gate refuses any destroy no operation sanctioned,
`apply-check` re-reads the flag at execution, and only then applies. The
terraform commands run in a private mirror of the emission,
`_private/<lifecycle>/<root>/`, where the ciphertext is opened; the mirror
is never committed. Read [OPERATIONS.md](docs/OPERATIONS.md), "What a run
is" and "The apply gate".

## 3. Making things

Each thing is a declaration, a run of its lifecycle with the apply
allowed, and a record afterwards. The rhythm is always the same: declare,
validate, dry-run, read the script, run for real, commit, push, check the
state query.

### 3.1 A group and its access

Declare users and the group in `groups/` ([CONFIGURATION.md](docs/CONFIGURATION.md),
section 11): `members` may log in, `admins` may log in with sudo, and the
root group's admins are merged into every group's. Run the identity
lifecycle with `apply_identity: true` (a convergent flag, safe to leave
on: it applies only what the YAML says, and the gate refuses destroys):

```sh
just cli --no-dry-run run identity --commit
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
just cli --no-dry-run run storage --commit          # apply_storage: true in the live tree
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
just cli --no-dry-run run base-image --only-runtime aws-east2-runtime --commit
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
just test-mods --strict                                  # every modification twice in a container: apply, then idempotence
just cli --no-dry-run run base-image instance-image release retention --only-runtime aws-east2-runtime --commit
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
just cloud-launch aws-east2-runtime      # instance-image, no re-bake, the runtime's roots allowed to apply; preflight first
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
just cloud-verify aws-east2-runtime <name>     # startup scripts, booted image, mounts, the post-bake tests; recorded
just ci-login-proof <name>                     # sft ssh by name through the policy; recorded
```

A durable instance's FIRST launch of a brand-new image is the one case
where `require_released_builds: true` and `release` pull against each
other, since the proof can only run on the machine itself: the release
grace admits the series head while its own proof is under way, so the
sequence is launch, verify, then a release run, with the flag left on.
Read [OPERATIONS.md](docs/OPERATIONS.md), "A model image, end to end: the
second release".

## 4. Changing things

Every change is a change to the YAML, then a run. The procedures are in
[OPERATIONS.md](docs/OPERATIONS.md), "Procedures" and the sections named
below; this is the order a person meets them.

| Change | Do | Then |
| --- | --- | --- |
| A modification, a test or a package on an image | edit `images/`, `just test-mods --strict`, commit the configuration | the bake is due: a performing run bakes the new build. A durable instance then takes it in ONE command, `just cloud-upgrade <rt> <instance>`: pin, gated replace, proof on the new machine, release, names, with `require_released_builds` left true throughout. Four steps: "A model image, end to end: the second release" |
| The base an image is built from | `parent_policy: follow` re-bakes on its own when the base moves; `pinned` waits for `just cli upgrade image <image>` | then as above |
| The build an instance runs | `just cli upgrade instance <name> [--to <build>]`, or the `cloud-upgrade` recipe above | `just cloud-launch <rt>`: the plan carries one `-replace`, the gate whitelists it and the volume attachments; the new machine is the next generation with the next number, the old registration is retired, the names come back once it enrolls |
| A storage's size or type on EBS | declare what exists, or intend a replacement | `volume_type` and `size` force replacement |
| Detach a storage from a launched instance | remove it from the instance's `storages` | the run unmounts on the machine first and refuses the plan without the receipt; adding it back is a replacement |
| Archive, restore, destroy a storage | `state: archived` (EBS and pd only), `active` again, `destroyed`, or delete the entry | each goes through the gate; tombstones stay in `storage-state.yaml` |
| Who may log in | edit `members` or `admins` | a real identity run. A removal OPA still holds is a destroy the plan shows. A membership already gone from OPA (removed in the console, or a roster conformed to OPA by hand) is pruned from terraform state by the runner's `prune-attachments` step, after a backup to `_private/state-backups/`, so the provider's refresh error never blocks the plan |
| Stop managing a group | `unmanaged: true` | released from state, never destroyed; deleting the entry is a validation failure |
| Decommission an instance | delete the entry, or `--undeclare instance:<name>` for one run | the gate whitelists exactly its destroy; the launch record, pin and OPA registration are forgotten; the pool name it took stays spent |
| Rotate the admin key | add the new key, bake, upgrade every instance, remove the old key, repeat | "Rotate the admin key" |
| Move a root's state | change `state_configuration`, run with `--migrate-state <root>` | backs up, copies, accepts only a clean plan at the new location, records the move |
| Adopt something made by hand | `just cli state import`; for memberships, `tofu import` then a no-op apply | "Adopt out-of-band group membership" |

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
| `apply_*`, `--apply-runtime` | `cfg/_config.yml`, the CLI | `apply-check` at execution; the gate before it | `run-summary.json` `apply` |
| `members`, `admins` | `groups/` | the identity apply; the runner's prune step against OPA; the state query's membership diff; the login proof | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| `workload_connection`, `workload_role` | `cfg/group-builders.yml` | the CI policy reconcile after the identity apply; the state query's `workload` record; `verify login` | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| the canonical hostname, the aliases, the pool | the system's | `validate` (label rules, claimed names, the pool's free lines); the state query's notes; `sft resolve` | `launch-params.yaml`, `instance-state.yaml`, `aliases.txt` |
| the whole emission | `generated/` | the golden in `just test`; `just config-drift` against the committed emission | [tests/fixtures/v2_golden/](tests/fixtures/v2_golden/) |
| the records against reality | `meta-state/` | `state query --strict`, both clouds and the OPA API | `generated/state-report.json` |
| that nothing published is secret | everything committed | `just public-safe`, the pre-commit hook, the commit gate, the plaintext scan of the run's own decrypted values | a refusal naming the file and line |
| the example trees and the READMEs | `docs/examples/`, `packages/*/README.md` | `just test`: the examples load and validate; every README has the four sections; every link resolves | the bar |

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
[OPERATIONS.md](docs/OPERATIONS.md), "Run outputs and exit codes".

The failures below all happened, and each row names what was done. New
ones get a row here and, if they need work, an item in the open hygiene
bundle in [TODO.md](TODO.md).

| Symptom | Meaning | Do |
| --- | --- | --- |
| `preflight: a session has EXPIRED`; `Token has expired and refresh failed`; `Error reading config file : AWS Error ...` | the AWS portal session behind the profile ended (8h from a browser sign-in; less if the CLI token was minted mid-session); the `sso-session` profile has no fixed expiry the system can read, so a lapse mid-run is environmental, not a defect | `aws sso login --profile noaa`, then re-run; after a lapse during `full-test`, `just full-test-legs` re-runs only the live legs |
| `runtime gcloud-east1 could not answer` under `unavailable:` | no Application Default Credentials, or they expired, or Google was unreachable | `gcloud auth application-default login --impersonate-service-account=...`; an `unavailable` line is not drift, but the strict query refuses on it |
| `state query storages/gcp-pd unavailable: ... oauth2.googleapis.com ... Read timed out` (2026-09-23) | the network to Google, not the system; `cloud-preflight` then exits 1 and the recipe stops before its first step | check `gcloud auth application-default print-access-token`; run the recipe again |
| `Validation failed with N error(s)` | a rule failed before anything was generated; each line names the file and the rule | fix the declaration; `just cli validate` alone re-checks in seconds |
| `unavailable: groups/<g>: HTTP 401 ...` for every group at once | the OPA API could not be asked: a lapsed key pair, or `.envrc` not sourced (before 2026-09-23 this read as five `missing` groups) | `source .envrc`; a real absence is one `missing [HARD]` group, from an answered 404 |
| `no users found using search criteria: profile.login eq "x@ENC[age:..."` | a plan ran on the committed emission, where the e-mail domain is ciphertext | the system plans in the mirror since 2026-09-22; by hand, run terraform under `_private/`, never `generated/` |
| `user "x" is not present within group "g"` at plan | a membership the YAML dropped and OPA already lacks is still in terraform state; the provider errors on refresh instead of dropping it | since 2026-09-23 the identity runner's `prune-attachments` step removes it after a backup, and the group root's generation-time plan does not refresh; if it still appears, the runner did not reach that step: read the run's output above the plan |
| `state backup for workspace '...' REFUSED: ... is not an initialised terraform root` | the backup step was started somewhere other than the root the runner initialised; nothing left state | the runner stops; report it, since the step is the system's and ran where the system put it (2026-09-23 10:15, fixed the same day) |
| `DESTROY NOT WHITELISTED: <address>` (gate, exit 3) | the plan destroys something no operation sanctioned | read the plan; if a decommission, detach or replacement was intended, declare it so; never widen the whitelist by hand. A replacement whitelists the instance AND its volume attachments (2026-09-22) |
| `launch parameters are immutable after launch` | a launched instance's declaration changed in place | revert, or make it a replacement (`upgrade instance`), or a detach (remove the mount) |
| `instance 'x' is pinned to build ... which is not a released build (...; no grace: <reason>)` | `require_released_builds` and an unreleased pin the grace does not cover; the reason says which condition failed (not the series head, no in-bake record, a failed post-bake, or the instance neither stands on it nor is being replaced onto it) | act on the reason: move the pin, fix the build, or verify; never switch the flag off |
| `upgrade: instance 'x' is already pinned to <build>` (exit 1) | the pin is already at the target, usually because `cloud-upgrade` already ran to completion | nothing to do; the recipe stops here by design |
| `release: ... no passing post-bake record` | the build has never been verified on a launched machine | verify first (an ephemeral cycle, or the standing machine after the replace) |
| `changed instance x: booted image ... != pinned build ...` | the pin moved without a replacement, or a replacement is pending (then a `note`, not drift) | `upgrade instance` then `cloud-launch`; or move the pin back |
| `CI login policy '<g>_v1_security_policy_ci' is absent` | the identity apply has not run since the workload objects were named | `just cli --no-dry-run run identity --commit` with `apply_identity` on; never hard drift |
| `workload role '...' is not known to OPA` | the operator's object is missing | [WORKLOAD_CONNECTION.md](WORKLOAD_CONNECTION.md), section 2 |
| `sft resolve ...: exit 126` with nothing on stderr | the `sft` client's session lapsed and `--quiet` forbade the browser (2026-09-23, after a replace: the registration half of the proof had passed) | `sft login`, then the proof again; as the workload, the token was missing or refused |
| `'<name>' has 2 registrations: ...` in a login proof | two servers answer to one canonical hostname | retire the stale one (a replacement now does this itself); `sft ssh` would reach either |
| `Instance x: alias 'y' SKIPPED -- already claimed by <id>` | a stale record holds the name | retire that record; the alias comes back on the next applies-on run |
| `verify ...: SKIPPED -- the machine is STOPPED`; `login proof ...: SKIPPED` | the operator switched the machine off; a note, not drift; nothing is started for a proof | start it if you want the proof, then re-run |
| `Instance x: not enrolled within 300s of its launch; no alias this run` | the machine booted this run and sftd had not enrolled in time | the next applies-on run gives the names back |
| `with-tofu-lock: another tofu-using recipe holds ...` (exit 75) | one tofu process at a time; another recipe is running | wait; remove the lock directory only if the process is gone |
| `full-test: passed` above `SKIPPED the credential-gated legs` | the legs did not run: a session was absent | not a pass; source the shell, log in, `just full-test-legs` |
| `error: recipe 'pytest' failed` at the end of `just test`, after a summary that looked green | the bar failed; a pipe to `tail` or a pager hid the exit code | read the exit code itself (`just test; echo $?`), never a piped tail |
| `Meta-state commit: never staging generated/.../instances.auto.tfvars` | the instance root's variable file is where it belongs and is never committed by design; before 2026-09-23 the release and retention runs left stray copies too | nothing; a stray copy under `generated/release/` or `generated/retention/` from an older run is deleted by hand once |
| `mod tests: N failed` or `not idempotent` | a modification fails, or changes something on its second run | make it idempotent: `ensure`, `unless`, `changed_when: false`; read `meta-state/mod-tests.yaml` |
| `rpm -q vim` fails on AlmaLinux 10; `dnf install amazon-efs-utils` finds nothing | the package is `vim-enhanced`; efs-utils is not in AlmaLinux's repositories | name the real package; build efs-utils from source as the live image does |
| `OSError: No space left on device` under pytest | the temp volume filled during a run | `df -h` on `/private/var/folders`; re-run |
| `GlobalTypeContext must be constructed with its full configuration on first use` | a CLI command in a group the callback exempts from loading the configuration | a developer error: move the command to a loading group |
| `justfile does not contain recipe ...` in a dispatched workflow | the recipe is on the branch but the run was dispatched from a ref without it, or the tracked file is `Justfile` with a capital J | push the branch; add with the tracked name |

## 7. Every plugin, in one paragraph each

Each README ends, after its own content, with the same four sections:
**Prerequisites and integration**, **Configuration reference** (every field
and every variation), **What it tests and verifies**, **When it fails**. The
four links after each paragraph go straight to them.

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
- [hashicorp-utils](packages/hashicorp-utils/README.md): the terraform
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
  instances and storages on AWS: the instance root, EBS, EFS and S3,
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

1. Start the shell: `source .envrc`, the profile, `just preflight`.
2. `just cli validate` after every edit; a dry run before every real run;
   read the script it wrote.
3. `just cloud-preflight` before any cycle: reality must match the
   records. A provider that cannot answer stops the cycle before it
   starts; that is the point.
4. Real runs commit their records; you push the configuration repository.
5. `just test` before every commit here, and read its exit code, not its
   last lines; `just full-test` before a phase is done or a release is
   cut; `just full-test-legs` alone after a session lapse.
6. A change to the live configuration is committed and pushed on its
   `develop` as part of the work.
7. GCP costs are yours: a cycle there ends with `gce-empty`, and any
   billable resource left standing is named with its cost.
8. When something fails, the row in section 6 first, then the hygiene
   bundle in [TODO.md](TODO.md); a new failure gets a row.
9. Documentation changes with the code: a stage that changes behaviour
   owes the rolling documentation stage an item, and a documentation
   stage changes no code.
