# The daily driver

*Walked from nothing on 2026-10-05 to 2026-10-14 against releases
0.1.1.dev14 to 0.1.1.dev23 (stage 65): two configuration repositories
made, bootstrapped, baked, launched, logged into and torn down by an
operator typing from a page; what that found is in this page's words and
in [docs/history/WALK-2026-10.md](docs/history/WALK-2026-10.md).*

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

A development release (`0.1.2.devN`) is on TestPyPI and not on PyPI,
and the line above cannot find it. It needs TestPyPI named, the version
pinned, PyPI as the extra index for the dependencies that live there,
and `--index-strategy unsafe-first-match`: uv asks PyPI first and, by
default, stops at the first index that has a name at all -- and PyPI
has had `cs-image-system` since 0.1.1 -- so without it the pinned `.dev`
version is never looked for on TestPyPI (stage 99):

```sh
uv tool install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \
  --index-strategy unsafe-first-match "cs-image-system==0.1.2.dev2"
```

CI does the same by itself when `.csis-version` names a `.dev` version.
Which index a release is on, and which release is current, is the
system repository's business (section 9, and the releases on GitHub).

or, for a team that pins its dependencies in the repository, a
`pyproject.toml` in the configuration repository that depends on
`cs-image-system`, run through `uv run`:

```sh
uv init --bare && uv add cs-image-system
export CSIS="uv run cs-image-system"     # the Justfile reads CSIS; every recipe then goes through uv
```

CI installs the release the same way, pinned by the content of
`.csis-version` when that file exists (section 1.8). Upgrading the system
is upgrading the package; the configuration repository usually does not
change. The versions on the index, and what each carries, are the system
repository's releases ([OPERATIONS.md](docs/OPERATIONS.md), "Installing a
release").

Some releases do ask something of the tree, and then `validate` refuses
the tree until it is given, so the release and the change land in ONE
commit. The first was 0.1.1.dev13 (2026-10-04, the POSIX identity
plugin): every group builder of `type: okta-tf` must now carry a
`posix:` line -- the name of a `type: posix` group builder, which makes
the Okta groups exist on their machines, or `none`, which keeps them
off (section 3.1). The reference configuration took it as one commit:
`.csis-version` raised, `init-config --force` for the release-owned
files, a `posix-local` group builder declared, and `posix: posix-local`
on its Okta group builder.

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

Where they come from: `just`, `uv`, `yq`, `jq`, `age` and `git` from
your package manager (`dnf`, `apt`, Homebrew) or each project's releases
page; `tofu` and `packer` from their own installers or packages (the
starters' workflow pins each by version, and `cfg/executables.yml`
says the floor your tree expects); the AWS CLI v2, the Session Manager
plugin, the Google Cloud CLI and Okta's `sft` from their vendors'
installers or package repositories, each of which has an rpm and a deb
form (`just sft-install` does Okta's on an apt system; on an rpm system
add Okta's yum repository and `dnf install scaleft-client-tools`);
`ansible-core` with `uv tool install ansible-core` (what CI does);
`docker` as Docker Engine, Docker Desktop or any daemon the `docker`
command reaches. The walk of 2026-10 installed all of them on a Fedora
43 container from those sources and nothing else. That list is for your
local machine; CI does not install them: every job runs inside the
system's own runner image, AlmaLinux 10 with each of these tools at a
pinned version ([docs/CI_RUNNER.md](docs/CI_RUNNER.md), stage 92), and
the image's probe asks every tool its version before the image is
published.

A version below the floor fails validation by name; a tool that is absent
is a validation failure too. Version checks are real: a CI failure naming a
tool's version means the floor moved, not that the tool broke.

### 1.3 AWS, if you use the AWS runtime

| What | Why the system needs it | Where it is named |
| --- | --- | --- |
| An account and a way to log in: an SSO portal and a profile (an `sso-session` profile lets the CLI token renew itself while the portal session lives). A team working from temporary keys pasted into the shell or a credentials file can: the system reads no expiry for keys, so `preflight` calls them `NOT JUDGED`, a lapse shows as `RequestExpired` at the first cloud call, and the remedy is fresh keys, not `aws sso login` | every `aws` runtime, and every root whose state backend is `s3`. The system defers to what the tree declares: a GCE-only repository keeps its state in `gcs` (as the GCE starter does) and needs no AWS account at all; the reference deployment keeps its GCE roots' state in S3 beside its AWS roots by its own decision | `credentials.profile_name` on the runtime; `AWS_PROFILE` and `AWS_REGION` in your shell |
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
the declared storages; another configuration's things in the same
project are counted and left alone, since everything the system makes
carries `csis_config` (stage 93). Read [OPERATIONS.md](docs/OPERATIONS.md),
"GCE cost discipline".

A service account two configurations share (the reference tree and a
scratch tree in one project, say) is read by the bootstrap and granted
nothing by default: a grant held in one root's state leaves with that
root's destroy, and the other tree loses it too. Name roles at the
interview only when this tree is the one to hold them; the generated
bootstrap README lists what a destroy would take that the root did not
make ([CI_SETUP.md](docs/examples/standard-aws/CI_SETUP.md), 3.0).

### 1.5 Okta and Okta Privileged Access

| What | Why | Where it is named |
| --- | --- | --- |
| An Okta API services app with key-based auth and the read scopes, DPoP off, the `*.manage` scopes ungranted | user lookups by the `okta/okta` provider | `OKTA_API_CLIENT_ID`, `OKTA_API_PRIVATE_KEY`, `OKTA_API_PRIVATE_KEY_ID`, `OKTA_API_SCOPES` |
| An OPA team, and a service user's API key pair | groups, policies, memberships, enrollment tokens, the gid shim, the server registry, the state query | `team:` on the group builder; `TF_VAR_<team>_key` / `TF_VAR_<team>_secret` (the team name with non-alphanumerics as `_`); needed at load, not only at apply |
| A resource group the system's projects live under, and a gateway | the login projects, the relay | `OKTA_RESOURCE_GROUP`; `okta_gateway_selector` |
| For CI: a workload connection and a workload role, made by hand once | CI logs in as a workload, never with a key | `workload_connection`, `workload_role` on the group builder; [CI_SETUP.md, section 3.5](docs/examples/standard-aws/CI_SETUP.md#35-okta-and-okta-privileged-access), which every starter tree carries, is the checklist, step by step |
| For people: the `sft` client, enrolled in the team (`sft enroll`), with a live session (`sft login`) | `sft ssh <machine>` | your machine |

Enrollment tokens are the system's: one per project, created and rotated
through terraform, never typed. Users are looked up, not created: a person
makes them in the Okta admin console and declares them in `groups/`.

### 1.6 The age identities

Any value in the tree may be committed encrypted (`ENC[age:...]`), and the
reference deployment keeps its roster's personal names and its e-mail
domain that way (not the usernames, which every record carries in clear;
section 3.1). Each
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
if you run the release through `uv`. The recipes assume nothing about
how the variables got there, so there are two ways. Without direnv,
every session starts:

```sh
cd <your configuration repository>
source .envrc
export AWS_PROFILE=<profile> AWS_REGION=<region>
aws sso login --profile <profile>     # when preflight says the session is absent or expired
just preflight                        # every session the runtimes need, without loading anything
```

With direnv, the same `.envrc` of `export` lines is loaded whenever you
enter the directory and unloaded when you leave it (so a shell that has
not entered it has nothing: see section 6, the `MissingIdentityError`
row); direnv refuses a file that changed until you run `direnv allow`
in that directory, after every edit of `.envrc`. `source .envrc` still
works in a shell that has no direnv.

`just validate` is the first thing to run after any edit. An `sso-session`
profile reports "refreshes itself (no fixed expiry readable)": that is
normal, and it means the portal session's end, not the token's, is what
ends a long run. The variable table is
[CONFIGURATION.md](docs/CONFIGURATION.md), section 14; the credentials
contract is [OPERATIONS.md](docs/OPERATIONS.md), "Credentials contract".

### 1.8 CI

The configuration repository's own workflow, `.github/workflows/ci.yml`
from the starter tree, has three jobs. Each runs inside the system's
runner image on GitHub's machine (`container: image:
ghcr.io/infrastructurebuilder/csis-ci:alma10-<date>`, with the host's
docker socket mounted so the modification tests can run containers;
section 1.2 and [docs/CI_RUNNER.md](docs/CI_RUNNER.md)) and installs the
release the way section 1.1 does (pinned by `.csis-version` when
present):

- **`verify`** needs no secret: the tree must be public-safe and the
  `Justfile` must parse. Every push and pull request.
- **`live`** is read-only against the clouds and OPA: `just validate`, a
  dry run, the strict state query, then the private mirror removed.
  Pushes and the nightly schedule, never pull requests (forks carry no
  secrets).
- **`perform`** runs on `main` alone. First the record: a dry run of
  every lifecycle, committed and pushed (`just record`), so a record
  exists whatever happens next; then the guard (`just runtime-unchanged`
  on the runtime `GUARD_RUNTIME` names, a runtime CI must never bake on,
  such as one that is your own money; the vendor publishing a newer
  image under a base with no build yet there is not a change, and the
  guard names the move and passes); then, under the write identity
  alone, the performing run of the runtime the workflow names (`just
  cloud-perform`); the login proof as a workload (`just ci-login-proof`);
  the closing record, pushed even when the performing step failed, so
  nothing baked goes unrecorded; the strict state query last.

Each job is gated on the repository secrets it needs, named in the
workflow: none configured is SKIPPED and said so in the job summary, some
configured and some missing is a failure that names them. A green job is
not proof its steps ran, so read the summary. Every `REPLACE-ME` in the
workflow is a team value: the runtime it performs on, the region, the
`TF_VAR_<team>` names.

How to make those secrets exist, from nothing, is the guide every starter
tree carries: [CI_SETUP.md](docs/examples/standard-aws/CI_SETUP.md)
(the repository's settings, the AWS OIDC provider and its two roles with
their trust and permission documents, the GCP workload identity pool and
service accounts, the OPA workload connection and role, CI's age
identity, the secrets one by one, the proofs in order, and a table of the
failures a first setup meets). It is written for GitHub; the GitLab
sections are placeholders.

Most of its GitHub section can be generated rather than clicked: `just
bootstrap` (stage 70) interviews you -- or takes every default with
`--quiet`, refusing by name any it cannot derive -- writes the answers to
`bootstrap.yaml` at the root of the tree, and generates
`generated/bootstrap/`: terraform you apply once (`tofu init && tofu
apply` there; no run ever applies it), `bootstrap.auto.tfvars` with the
answers, `set-secrets.sh` that sets each secret from a file named after
it, and a README listing what remains by hand. Both the answers and the
tfvars are committed (names and ids, never a value); every run
regenerates the directory from the answers, so a stale root is drift and
a clone needs no interview. The GitHub section does the branches, the
ruleset that still lets `perform` push, Actions permissions and variables
and the secrets script; the AWS section does the OIDC provider, the two
roles with the guide's documents, and the state bucket and instance
profile when the account lacks them -- asking the account what already
exists when you have a session, adopting roles that stand, and refusing
under `--quiet` anything it cannot find out. Fill the starter's
`REPLACE-ME` values first: a placeholder is not a default. The GCP
section does the workload identity pool and provider, the read-only and
(when CI performs on GCE) write service accounts and their bindings; what
already exists there is read and never rewritten, since a provider's
condition may serve other repositories too. The Okta and OPA section
creates nothing: it checks the OPA workload connection and role and the
Okta API services app, and turns each check that fails into its step of
the guide, so a team sees exactly what its admins still have to do.

### 1.9 The configuration repository, from scratch

Start from a starter tree; do not write from nothing. There are four
starters, and three ways to get one, each giving the same tree:

1. **On GitHub, "Use this template"** on the starter's template
   repository. Each is generated from its starter with every final
   release (stage 66), takes no pull requests, and says so in its
   README's first lines; its `.csis-version` names the release:
   [cs-image-system-starter-standard-aws](https://github.com/infrastructurebuilder/cs-image-system-starter-standard-aws)
   (the default),
   [cs-image-system-starter-standard-gce](https://github.com/infrastructurebuilder/cs-image-system-starter-standard-gce),
   [cs-image-system-starter-complete](https://github.com/infrastructurebuilder/cs-image-system-starter-complete)
   and
   [cs-image-system-starter-standard-aws-posix](https://github.com/infrastructurebuilder/cs-image-system-starter-standard-aws-posix).
   Your copy is a repository of its own from the first minute; clone it
   and go on below.
2. **From the release, `init-config`** (the commands below), which needs
   no GitHub and is always the release you installed.
3. **A copy of `docs/examples/<name>`** from the system repository works
   too, but it carries no `.csis-version` and its links point into that
   repository: prefer the other two.

```sh
cs-image-system init-config my-config                          # standard-aws, the default
cs-image-system init-config my-config --from standard-gce
cs-image-system init-config my-config --from complete
cs-image-system init-config my-config --from standard-aws-posix   # AWS, people as POSIX accounts, no Okta
```

A destination that is empty, or a fresh clone holding only `.git` (the
usual order: create the repository on GitHub, clone it, write into the
clone), takes the whole starter; a directory that already holds a
configuration takes only the release-owned parts (below); any other
directory is refused by name and nothing is written, so the command
typed in the wrong place cannot replace that place's files.
[docs/examples/standard-aws/](docs/examples/standard-aws/README.md) is the
smallest repository that works on the AWS plugin set, one of everything,
every value you must replace an obvious `REPLACE-ME` and every line that
is a decision commented; [docs/examples/standard-gce/](docs/examples/standard-gce/README.md)
is the same for GCE; [docs/examples/standard-aws-posix/](docs/examples/standard-aws-posix/README.md)
is `standard-aws` with no Okta: its people are POSIX accounts on the machines
(the posix identity plugin, stage 75), and CI's login proof uses a key;
[docs/examples/complete/](docs/examples/complete/README.md)
has every plugin, every field and every variation, and is where to look
when the reference manual's table needs a living example. Those three
directories are the source the release is built from: all four load and
validate in the system's tests, the built wheel is held to them byte for
byte, and their `Justfile`, workflow, hook and modules are the release's,
so a tree written by `init-config` cannot drift from the system that wrote
it. `.csis-version` in the written tree names that release, and the
starter's Markdown links that lead out of it -- into the system
repository's documents, or to another starter -- point at that
release's tag on GitHub, since a relative one would point nowhere in a
repository of its own (hygiene XV; a template repository's do the
same).

Run `init-config` again, in the repository, after upgrading the release:
into a tree that already holds a configuration it writes only the parts
the release owns (the `Justfile`, the workflow, the hook, `.gitignore`,
`tfmodules/`, `.csis-version`) and never a line of the YAML; a
release-owned file you changed is refused by name until you pass
`--force`.

Then, in the written tree:

1. `git init -b develop` (git's own default branch is `master`, and
   this page and CI_SETUP expect `develop` and `main`; `main` does not
   exist until the first push of it, [CI_SETUP.md](docs/examples/complete/CI_SETUP.md),
   section 3.8), `just init` (the hook, the plugin cache, and a line naming
   the release it found, `init: cs-image-system <version> ready against
   <root>`; a release of 0.1.3 or before has no `--version`, and the line
   gives the bare name), and a first commit of the tree as it stands. From a
   template, the clone already holds `main` with that first commit:
   `git switch -c develop` instead of `git init`, then `just init`.
2. **The identity.** Make your own age key pair:

   ```sh
   age-keygen -o ~/.config/cs-image-system/age/<you>.age-identity   # prints the public key, age1...
   ```

   Put that public key in `cfg/_config.yml` `encryption.recipients` in
   place of the test recipient (one line per holder; CI's own identity is
   a second one, section 1.8), then re-encrypt every value to the new
   recipients with the TEST identity, which is the one that can still
   read them:

   ```sh
   CSIS_CONFIG_IDENTITY=.age-identity just cli reencrypt
   export CSIS_CONFIG_IDENTITY=~/.config/cs-image-system/age/<you>.age-identity   # and into .envrc
   just validate
   ```

   Then take the test identity out: `git rm .age-identity
   .age-recipient`, drop the `path:.age-identity` line from
   `public_safe.allow` in `cfg/_config.yml`, and reword the comments
   there and in `groups/` that call the recipient the TEST one. From here
   the tree opens only to your keys, and the starter's key can never open
   it again.
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

Names are yours to choose, with one rule the load enforces: `default`,
`self`, `none`, the empty string and null are reserved, in any case,
because each means "not set" wherever a value is read. Nothing may be
named after one, and no alias may be one; the refusal names the file,
the entry and the word. The same words written as a VALUE are a
different thing: `type: default` asks for the builder marked
`is_default`, while a reference written `none` names nothing and
`validate` says what to write instead. A few fields give `none` a
meaning of their own and say so where they are described
(`update: {policy: none}`, `--only none`).
[CONFIGURATION.md](docs/CONFIGURATION.md) 1.2 is the whole rule.

### 3.1 A group and its access

Declare users and the group in `groups/` ([CONFIGURATION.md](docs/CONFIGURATION.md),
section 11): `members` may log in, `admins` may log in with sudo, and the
root group's admins are merged into every group's. A declared person's
username is committed in clear: it is what OPA, the identity roots and
the records carry, and a marker on it in the roster hides nothing (the
e-mail domain and the personal names are what the markers hide). In a
public configuration repository, declare a person knowing that
(2026-10-08, F36; decided 2026-10-14). Run the identity
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

**The group on its machines.** OPA lets a member in; it does not make
the group exist on the machine. Every `okta-tf` group builder therefore
names, in `posix:`, a group builder of `type: posix` that does
([CONFIGURATION.md](docs/CONFIGURATION.md), 9.2). With one named, each
applying instance run (`just cloud-launch <runtime>`) creates every
group on its running machines with OPA's gid and writes its member list
under `/etc/csis/groups/`, and a PAM hook -- baked into the image and
installed again by that run -- adds each listed member to the group at
every login. The hook is needed because OPA's agent makes an account
only when someone logs in and drops its groups when it deletes it, so a
membership written once would not last. Afterwards `getent group <g>`
answers on the machine, the group's storage subtrees show its name
rather than a bare number, and a member's `id` carries it.
`posix: none` keeps all of that off, and `validate` notes what it
keeps off. A machine that is switched off waits for a run that finds
it running.

**A group without Okta.** A group whose builder is itself `type: posix`
lives on its machines alone ([CONFIGURATION.md](docs/CONFIGURATION.md),
11.5 and 11.6; the starter `standard-aws-posix` is a whole tree of
them). The group declares its `gid:`; each member is a user of a
`type: posix` user builder with a `uid:` and `public_keys:`. Both ids
are the configuration's, at least 1024 and the same on every machine,
because shared storage is owned by number. The group is baked into its
images with that gid, and after each applying instance run the users,
their private groups, their keys and the admins' sudo are made true on
every running machine. Two declarations of one name with different ids
are refused at `validate`; a machine where the name already stands with
a different id stops the run there and names both ids. Nothing is ever
deleted on a machine: an account removed from the YAML stays until it
is removed by hand, and a group the system once managed stays in the
YAML, marked `unmanaged: true`, when it is retired (section 4).

**The proof user.** `just ci-login-proof <instance>` proves a posix
group's access by logging in as its proof user: a member declared
`is_service_account: true`, with a `uid:` and one public key made for
it alone, whose private half reaches the proof as `CSIS_PROOF_SSH_KEY`
(the key itself, or a path to it; in CI a repository secret,
[CI_SETUP.md](docs/examples/standard-aws-posix/CI_SETUP.md), 3.7). The
login is real ssh through the runtime's session tunnel -- SSM's
`AWS-StartSSHSession` on AWS, an IAP tunnel on GCE -- so no machine
needs a public address, and the proof passes only when the group is
among the account's groups. It was first proved on 2026-10-04, on a
posix-only AlmaLinux 10 machine in a private subnet.

**A person's own login to a posix machine** is the same ssh, with their
own key, which no recipe makes for them:

```sh
id=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=<instance>" "Name=instance-state-name,Values=running" --query 'Reservations[].Instances[].InstanceId' --output text)
ssh -i ~/.ssh/<key> -o ProxyCommand="aws ssm start-session --target $id --document-name AWS-StartSSHSession --parameters portNumber=%p --region <region> --profile <profile>" <username>@$id
```

The instance id is also in `meta-state/instance-state.yaml`. The host
key is the machine's, new on every generation: accept it, or keep a
known-hosts file per machine. On GCE the tunnel is `gcloud compute ssh
<instance> --tunnel-through-iap` with the same key. An Okta group's
people log in with `sft ssh <name>` instead (section 3.5).

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

The in-bake tests fail the bake; a build is recorded only on success,
and when one bake of a run fails, the bakes that completed before it
are still recorded ([OPERATIONS.md](docs/OPERATIONS.md), "When a bake
fails"). The release lifecycle records the build as the model's
current release only once its post-bake tests have passed on a
launched machine, which for a brand-new image means launching an
instance of it first. Read [OPERATIONS.md](docs/OPERATIONS.md),
"Post-bake tests and releases".

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

Those are the system's logins. Yours: `sft ssh <name>` for an Okta
group's machine; for a posix group's, the ssh line in section 3.1 with
your own key.

**A VERIFICATION SWITCHES A STOPPED MACHINE ON.** If you have switched
a machine off, `just cloud-verify` (and a post-bake test) STARTS it,
does its work and stops it again, and says so in its log both times
(`... is STOPPED (switched off; not drift); STARTING it because
verifying instance ...`, then `... stopping it again, which is how it
was found`). You pay for that boot, and every startup script runs
again. Nothing else starts a machine: not the state query, which only
notes that it is off; not a launch run; and not `just ci-login-proof`,
which says `SKIPPED` and proves nothing while the machine is off. If
the system cannot stop the machine again it says `ERROR`, names it,
and the machine is then RUNNING: stop it by hand. A runtime that
cannot start machines skips the verification instead. This is
deliberate ([OPERATIONS.md](docs/OPERATIONS.md), "Starting a machine is
a bounded exception"). It was walked on 2026-10-09, when it surprised
its own operator; the decision that day was to keep it, and it is
reviewed every month until February 2027 ([TODO.md](TODO.md)). If you
do not want a machine booted, do not verify it while it is off.

A durable instance's FIRST launch of a brand-new image is the one case
where `require_released_builds: true` and `release` pull against each
other, since the proof can only run on the machine itself: the release
grace admits the series head while its own proof is under way, so the
sequence is launch, verify, then `just run release`, with the flag left
on. Read [OPERATIONS.md](docs/OPERATIONS.md), "A model image, end to end:
the second release".

### 3.6 A second cloud

A tree made from `standard-aws` or `standard-gce` has one cloud; adding
the other is ten declarations, and the walk of 2026-10 added GCE to an
AWS tree this way (stage 15). In load order: the cloud's tool in
`cfg/executables.yml` (`gcloud`, or `aws`); a runtime in
`cfg/runtime-builders.yml` (`type: gcloud` with project and zone, or
`type: aws` with profile and region; its session mechanism); a state
backend in `cfg/state-backends.yml` only if the new cloud's roots keep
their state somewhere else (they may keep it in the first cloud's
bucket, as the walk's did); an image builder (`packer-gce` or
`packer-ebs`), an instance builder (`tofu-gce` or `tofu-aws`) and a
storage builder (`gcp-pd` or `aws-ebs`) in their `cfg/` files, each
bound to the new runtime; on the base, a second source under
`os_builders[].runtimes[]` for the new runtime, and the new storage type
in `storage_types`; on each image that should exist there, a second
`runtimes[]` entry (a bake per runtime); a storage and an instance
declared on the new runtime (`runtime:` and the `type:` of its
builder). Then the credentials of section 1.3 or 1.4, CI's secrets for
the cloud ([CI_SETUP.md](docs/examples/complete/CI_SETUP.md), 3.3 or 3.4,
and the bootstrap's section for it), and, for GCE, the runner service
account's address allowed through `public_safe.allow`
(`".iam.gserviceaccount.com"`), which the hook otherwise reads as an
email. Two things to expect: a storage type added for the new cloud
re-bakes nothing on the old one (a bake takes only the types whose
builder lives on its runtime, hygiene XII item 21), while a field every
runtime shares (`admin_user`, the keys, `update`) still re-bakes the base
everywhere; and `validate` names each declaration the new runtime still
lacks, so declare, validate, and read what it says until it is quiet.
`complete` has every one of these declared, both clouds at once, as a
living example.

**Two trees in one project or account.** Everything the system makes
carries the configuration's id, `csis_config` (images since stage 82,
storages and machines since stage 93), so a second tree that shares
your project or account is not in your way: the state query and
`cloud-empty` count your things alone and say how many of the other
tree's they left alone, and a lookup by name takes yours, never theirs.
What stood before stage 93 carries no id yet and is listed as `(no
csis_config)` until `just cloud-relabel <runtime> no` gives it one, in
place, nothing replaced. Two trees that declare the same storage name
on one cloud still collide where the cloud's names are unique (a GCE
disk in one zone, a bucket); the query then says `a persistent disk of
that name belongs to configuration '<id>'`, and ours is absent.

## 4. Changing things

Every change is a change to the YAML, then a run. The procedures are in
[OPERATIONS.md](docs/OPERATIONS.md), "Procedures" and the sections named
below; this is the order a person meets them.

| Change | Do | Then |
| --- | --- | --- |
| A modification, a test or a package on an image | edit `images/`, `just test-mods --strict`, commit | the bake is due: `just cloud-perform <runtime>` bakes the new build. A durable instance then takes it in ONE command, `just cloud-upgrade <runtime> <instance>`: pin, gated replace, proof on the new machine, release, names, with `require_released_builds` left true throughout. "A model image, end to end: the second release" |
| The base an image is built from | `parent_policy: follow` re-bakes on its own when the base moves; `pinned` waits for `just cli upgrade image <image>` | then as above |
| The build an instance runs | `just cli upgrade instance <name> [--to <build>]`, or the `cloud-upgrade` recipe above | `just cloud-launch <runtime>`: the plan carries one `-replace`, the gate whitelists it and the volume attachments; the new machine is the next generation with the next number, the old registration is retired, the names come back once it enrolls |
| The size of a standing machine | edit `machine_type`; `just validate` passes (the one launch parameter that may change in place) | `just cloud-launch <runtime>`: `0 to add, 1 to change, 0 to destroy`, the provider stops, changes and starts the SAME machine; the ledger records a `resized` event on the open generation. "Resizing a durable instance in place" |
| The machine itself, from nothing, same image | `just cloud-decommission <runtime> <name>` (the gate whitelists exactly that instance), then nothing to edit | `just cloud-launch <runtime>`: the next generation, `<name>-NNN`, a new alias, the pin first-bound to the series head again; every declared storage comes back with its data. "Replacing a durable instance: decommission and redeclare" |
| Which storage an instance mounts | decommission first (a mount move on a launched instance is refused), then change the `name` under `storages`, declare the new storage if it is new, `just run storage` | `just cloud-launch <runtime>`: the new machine mounts exactly what its declaration names; the storage it left keeps its data until its entry is deleted. OPERATIONS "Storages", "Moving a mount is a replacement" |
| A storage's size or type on EBS | declare what exists, or intend a replacement | `volume_type` and `size` force replacement |
| Detach a storage from a launched instance | remove it from the instance's `storages` | the run unmounts on the machine first and refuses the plan without the receipt; adding it back is a replacement |
| Archive, restore, destroy a storage | `state: archived` (EBS and pd only), `active` again, `destroyed`, or delete the entry | each goes through the gate; tombstones stay in `storage-state.yaml` |
| Who may log in | edit `members` or `admins` | `just run identity`. A removal OPA still holds is a destroy the plan shows. A membership already gone from OPA (removed in the console, or a roster conformed to OPA by hand) is pruned from terraform state by the runner's `prune-attachments` step, after a backup to `_private/state-backups/`, so the provider's refresh error never blocks the plan |
| Who is in a group on its machines | edit `members` or `admins`; beside Okta, `just run identity` first, as above | the next applying instance run, `just cloud-launch <runtime>`, rewrites the member list on every running machine (beside Okta) or makes the accounts, keys and sudo true (a posix group). Beside Okta a member added joins at their next login after that run, and one removed is taken out of the group if their account stands then. Never a re-bake, and nothing is deleted: an account dropped from the YAML stays on the machine. Section 3.1; OPERATIONS "Identity" |
| Stop managing a group | `unmanaged: true` | released from state, never destroyed; deleting the entry is a validation failure. The identity run's pre-plan step decides it from what the state holds when it runs (stage 90), so a dry run or a `just record` made first changes nothing: look, then run. (Before 0.1.1.dev23 either one spent the release: the run that followed planned the group's destruction, and the gate refused it.) A retired posix group stays the same way, and needs no members (2026-10-04: the posix proof's group, its gid still claimed by the name) |
| Decommission an instance | delete the entry, or `just cli --undeclare instance:<name> run instance-image --only none --apply-runtime <runtime> --commit` for one run | the gate whitelists exactly its destroy; the launch record, pin and OPA registration are forgotten; the pool name it took stays spent |
| Rotate the admin key | add the new key, bake, upgrade every instance, remove the old key, repeat | "Rotate the admin key" |
| Move a root's state | change `state_configuration`, `just cli --no-dry-run run <lifecycle> --migrate-state <root>` | backs up, copies, accepts only a clean plan at the new location, records the move |
| Adopt something made by hand | `just cli state import`; for memberships, `tofu import` then a no-op apply | "Adopt out-of-band group membership". An adopted image counts as current when its tagged fingerprint matches today's inputs, so it is not baked again; it carries no in-bake record, so the release grace does not cover it |
| Upgrade the system | `uv tool upgrade cs-image-system` (or bump the pin and `uv lock`); `.csis-version` for CI | `just validate`, `just dry`, and read the diff of `generated/`: an emission change is what a system upgrade looks like. A release that asks something of the tree is refused by `validate` until it is given: make the change in the same commit (section 1.1) |

Three habits keep changes safe. Dry-run first and read the script: a dry
run regenerates and lists the commands the real run will execute -- it
does NOT plan against the cloud (no state is touched in a dry run), so
what you read is the command list (`--allow-destroy` on the gate line
means a destroy is intended) and the emission and records the dry run
commits; the plan itself appears in the real run's log, where the runner
prints tofu's `Plan:` line, the gate's verdict and the apply summary, and
the gate -- not the dry run -- is what refuses a destroy nothing
whitelisted. Never edit a launched instance's declaration expecting an
in-place change, with two exceptions the system makes for you: removing
a storage (a detach) and changing `machine_type` (a resize of the same
machine); everything else is immutable, and the system will tell you so
and name the way, a replacement or a detach. And after any applying
`cloud-*` run, `just record` before you push: the applying run committed
the script it executed, and a recording run restores the resting
emission with the journal's closing entry (CI's `config-drift` ignores
the apply-only lines since hygiene VIII item 4, so this is tidiness, not
a requirement). Between a decommission and its relaunch push `develop`
only -- a push to `main` would have the `perform` job launch the new
machine from CI.

### 4.1 Taking a configuration down

The walk of 2026-10 took two down (stage 17); this is the order it
found, each thing destroyed by what made it, through the gate, and a
look before every removal. Machines first: `just cloud-decommission
<runtime> <instance>` for each (its dry form `... yes` first), then
`instances: []` committed. Images: `just cloud-dispose-images <runtime>`
(dry form first; it refuses while a machine is pinned to a build).
Storages: `state: destroyed` on each, `just dry storage` to read the
gate line, `just run storage`. Groups: `unmanaged: true` on each, `just
run identity` (section 4's row; from 0.1.1.dev23 a dry run first is
safe). Then `just record`, `just state-query --strict` with nothing
declared, and push `develop` only: never `main` again from this tree,
whose `perform` would bake what you disposed of. Since 0.1.1.dev25 the instance root is still emitted, empty, once nothing
is declared on it, and that run lets the group it had made for its
machines go through the gate (before, the security group stood in the
cloud and in the root's state with no run to plan it, and went by hand).
By hand, in this order: CI disabled (`gh workflow disable ci.yml`), because its
roles are about to go; each bootstrap root destroyed from its own state
(`tofu -chdir=generated/bootstrap plan -destroy -out=<file>`, read it,
`apply <file>`; the GCP part needs your own token as the apply did);
the state bucket last and by hand, because no state manages it and
every root's state is in it, emptied version by version (`aws s3api
list-object-versions`, `delete-objects`, then `delete-bucket`); the
OPA objects in the console, which the system never destroys: the
workload role and connection, the three security policies, the
resource group with its project, token and server records, then the
two groups; the walk's repository taken out of the Google provider's
attribute condition; the repository's secrets deleted and the
repository archived or deleted; the GitHub token. The proof is the
picture before against the picture after: the same reads, empty, and
the reference configuration's own strict state query still clean.

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
| `storages[]` and `mount_point` | `instances/` | verify's "data disks mounted": on GCE each declared mount point's own line from the startup script on the serial console (`csis-mount: <mount point> mounted`; before hygiene XII a count of the kernel's clean XFS mounts, which the image's own filesystems satisfied, 2026-10-09, F50), on AWS the count under `/mnt` over SSM; an unmount receipt before a detach | `meta-state/verifications.yaml`; `unmount-receipts/` in the workspace |
| a storage's `state` and `lifecycle` | `storages/` | the storage lifecycle; the state query's `missing` and `stale` | `meta-state/storage-state.yaml`, `storage.yaml` |
| `apply_*` | `cfg/_config.yml` | `apply-check` at execution; the gate before it | `run-summary.json` `apply` |
| `members`, `admins` | `groups/` | the identity apply; the runner's prune step against OPA; the state query's membership diff; the login proof | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| `workload_connection`, `workload_role` | `cfg/group-builders.yml` | the CI policy reconcile after the identity apply; the state query's `workload` record; the `perform` job's login | `meta-state/identity.yaml`; `meta-state/login-proofs.yaml` |
| the canonical hostname, the aliases, the pool | the system's | `validate` (label rules, claimed names, the pool's free lines); the state query's notes; `sft resolve` | `launch-params.yaml`, `instance-state.yaml`, `aliases.txt` |
| the committed emission | `generated/` | `just config-drift`: a dry run against what is committed; minutes, nearly all of it a `tofu init` per root, each said as it happens | exit 1 with the diff |
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
| `preflight: a session has EXPIRED`; `Token has expired and refresh failed`; `the configuration cannot load: AWS refused the credentials (RequestExpired)` (before hygiene XII: `Error reading config file : AWS Error ... Request has expired` under a traceback) | the AWS portal session behind the profile ended (8h from a browser sign-in; less if the CLI token was minted mid-session); an `sso-session` profile has no fixed expiry the system can read, so a lapse mid-run is environmental, not a defect. `RequestExpired` is what temporary keys pasted into the shell or a credentials file say when they lapse, and `preflight` cannot see that coming: it reads no expiry for keys (2026-10-09, F30 and F40) | `aws sso login --profile <profile>` for an SSO profile; FRESH keys for pasted ones (`aws sso login` does nothing for them); then re-run |
| `preflight: N session(s) present; 1 NOT JUDGED (no expiry readable: ...)` in yellow, exit 0, where it used to say `every session present` | a session preflight can see but not time: static keys in a profile or in the environment. Present is all it can say without a cloud call, which it makes none of by design (stage 16); before hygiene XII the line was green over keys that had already lapsed | nothing, if you know the keys are fresh; if the next command says `RequestExpired`, fresh keys |
| `runtime <gce> could not answer` under `unavailable:` | no Application Default Credentials, or they expired, or Google was unreachable | `gcloud auth application-default login --impersonate-service-account=...`; an `unavailable` line is not drift, but the strict query refuses on it |
| `state query storages/<pd> unavailable: ... oauth2.googleapis.com ... Read timed out` (2026-09-23) | the network to Google, not the system; `cloud-preflight` then exits 1 and the recipe stops before its first step | check `gcloud auth application-default print-access-token`; run the recipe again |
| `Validation failed with N error(s)` | a rule failed before anything was generated; each line names the file and the rule | fix the declaration; `just validate` alone re-checks in seconds |
| `unavailable: groups/<g>: HTTP 401 ...` for every group at once | the OPA API could not be asked: a lapsed key pair, or `.envrc` not sourced (before 2026-09-23 this read as five `missing` groups) | `source .envrc`; a real absence is one `missing [HARD]` group, from an answered 404 |
| `the configuration cannot load: Okta builder <b> is missing a key value. Expected to find environment variable TF_VAR_<team>_key ...` from `validate` or a run (the gid shim's form is `OPA credentials for team '<t>' not found in the environment`); before hygiene XII, under a traceback (F10) | the `TF_VAR_<team>_key` / `_secret` pair is needed by `validate` and dry runs too, not only at apply | export them (`.envrc`); in CI, the secrets the workflow names |
| `no users found using search criteria: profile.login eq "x@ENC[age:..."` | a plan ran on the committed emission, where the e-mail domain is ciphertext | the system plans in the mirror since 2026-09-22; by hand, run terraform under `_private/`, never `generated/` |
| `user "x" is not present within group "g"` at plan | a membership the YAML dropped and OPA already lacks is still in terraform state; the provider errors on refresh instead of dropping it | since 2026-09-23 the identity runner's `prune-attachments` step removes it after a backup, and the group root's generation-time plan does not refresh; if it still appears, the runner did not reach that step: read the run's output above the plan |
| `state backup for workspace '...' REFUSED: ... is not an initialised terraform root` | the backup step was started somewhere other than the root the runner initialised; nothing left state | the runner stops; report it, since the step is the system's and ran where the system put it (2026-09-23 10:15, fixed the same day) |
| `DESTROY NOT WHITELISTED: <address>` (gate, exit 3) | the plan destroys something no operation sanctioned | read the plan; if a decommission, detach or replacement was intended, declare it so; never widen the whitelist by hand. Several such lines under `module.group_<name>` for a group you marked `unmanaged: true` are a release that was not carried out, in a tree on a release before 0.1.1.dev23 after a dry run or a record (2026-10-13): the gate was right, nothing was destroyed; take the release and run the identity lifecycle again. A replacement whitelists the instance AND its volume attachments (2026-09-22) |
| `launch parameters are immutable after launch` | a launched instance's declaration changed in place | revert, or make it a replacement (`upgrade instance`), or a detach (remove the mount) |
| `instance 'x' is pinned to build ... which is not a released build (...; no grace: <reason>)` | `require_released_builds` and an unreleased pin the grace does not cover; the reason says which condition failed (not the series head, no in-bake record, a failed post-bake, or the instance neither stands on it nor is being replaced onto it) | act on the reason: move the pin, fix the build, or verify; never switch the flag off |
| `upgrade: instance 'x' is already pinned to <build>` (exit 1) | the pin is already at the target, usually because `cloud-upgrade` already ran to completion | nothing to do; the recipe stops here by design |
| `release: ... no passing post-bake record` | the build has never been verified on a launched machine | verify first (an ephemeral cycle, or the standing machine after the replace) |
| `changed instance x: booted image ... != pinned build ...` | the pin moved without a replacement, or a replacement is pending (then a `note`, not drift) | `upgrade instance` then `cloud-launch`; or move the pin back |
| `CI login policy '<g>_v1_security_policy_ci' is absent` | the identity apply has not run since the workload objects were named | `just run identity` with `apply_identity` on; never hard drift |
| `resource group '<g>_rg' is not what the identity module makes` (or `user policy` / `admin policy`) | someone changed the object in OPA: a hand edit, or another configuration that holds the same objects in its own tofu state (2026-10-19, `basic`) | if another configuration manages them, it lets go first (`tofu state rm` there, never a destroy); then `just run identity` puts them back; never hard drift |
| `workload role '...' is not known to OPA` | the operator's object is missing | [CI_SETUP.md, section 3.5, step 2](docs/examples/standard-aws/CI_SETUP.md#35-okta-and-okta-privileged-access) |
| `sft resolve ...: exit 126` with nothing on stderr | the `sft` client's session lapsed and `--quiet` forbade the browser (2026-09-23, after a replace: the registration half of the proof had passed) | `sft login`, then the proof again; as the workload, the token was missing or refused |
| `'<name>' has 2 registrations: ...` in a login proof | two servers answer to one canonical hostname | retire the stale one (a replacement now does this itself); `sft ssh` would reach either |
| `Instance x: alias 'y' SKIPPED -- already claimed by <id>` | a stale record holds the name | retire that record; the alias comes back on the next applies-on run |
| `instance <x> verified` for a machine you had switched off, with `STARTING it because verifying instance <x>` above it; `login SKIPPED for <x> (nothing proved)`; `verify <x>: SKIPPED -- the machine is STOPPED` only on a runtime that cannot start machines | someone switched the machine off: a note, not drift. **Verification STARTS it, checks it and stops it again** (section 3.5); the login proof starts nothing and is skipped | nothing, when the log ends `stopping it again`; an `ERROR` there means the machine is now RUNNING and must be stopped by hand. For the login proof, start the machine yourself and run it again |
| `Instance x: not enrolled within 300s of its launch; no alias this run` | the machine booted this run and sftd had not enrolled in time | the next applies-on run gives the names back |
| `--locked: another tofu-using command holds ...` (exit 75) | one tofu process at a time; another recipe is running | wait; remove the lock directory only if the process is gone |
| `full-test: passed` above `SKIPPED the credential-gated legs` | the legs did not run: a session was absent | not a pass; source the shell, log in, run again |
| `Meta-state commit: never staging generated/.../instances.auto.tfvars` | the instance root's variable file is where it belongs and is never committed by design; before 2026-09-23 the release and retention runs left stray copies too | nothing; a stray copy under `generated/release/` or `generated/retention/` from an older run is deleted by hand once |
| `mod tests: N failed` or `not idempotent` | a modification fails, or changes something on its second run | make it idempotent: `ensure`, `unless`, `changed_when: false`; read `meta-state/mod-tests.yaml` |
| `rpm -q vim` fails on AlmaLinux 10; `dnf install amazon-efs-utils` finds nothing | the package is `vim-enhanced`; efs-utils is not in AlmaLinux's repositories | name the real package; build efs-utils from source as the reference image does |
| Annotations on every CI run naming the runner image or an action as deprecated or migrating; later, jobs never picked up, or a failure in "Set up job" before any step of yours | the workflow's names are old: an image or an action major GitHub is withdrawing | take the newest release (it carries the move); if none does yet, section 9.1, which also says how often to look |
| `verify` (or any job) fails in "Install the released system" with the index unreachable or `503`, on a tree whose `.csis-version` names a `.dev` release | TestPyPI is down; a development release is nowhere else | environmental: wait and rerun (`gh run rerun <run> --failed`); nothing in the tree is wrong (2026-10-05, F16) |
| you cannot find the job summary; `gh run watch` and `gh run view` show steps and annotations but no `SKIPPED` line | the summary is on the run's page, not in those commands; a skipped job has no summary at all | `gh run view <run> --web`, or Actions in the browser; the gate's own line (`live: SKIPPED -- ...`) is in the log of the step "Gate on the secrets" (2026-10-07, F20) |
| an applying identity run's log shows the group root's plan twice, the first saying `1 to destroy` and the second `No changes` | the first is a preview made as the run writes its files, never saved and never applied; the second, after the prune step, is the one the gate reads and the apply uses | read the second; a destroy in the first alone means the prune step took the attachment out of state because OPA no longer held it (2026-10-08, F39) |
| `the configuration cannot load: <tree>/cfg: ...: an encrypted value is present but CSIS_CONFIG_IDENTITY is not set`, exit 2, before anything is asked of a cloud (before hygiene XII a `MissingIdentityError` traceback) | the shell never loaded `.envrc` (a new terminal, a directory direnv has not entered or allowed) | `source .envrc`, or `direnv allow`; it is the first thing an unsourced shell meets in any tree that holds an encrypted value (2026-10-09, F41) |
| ` - <file>: instances[0].name: a name may not be 'none'` under `Validation failed with 1 error(s).`, exit 1, from `validate` or a run (before hygiene XII a `ReservedNameError` traceback) | a reserved word was used as a name, exactly as section 3 says it may not be | rename it (2026-10-09, F42) |
| `CANNOT START <image>/<mod>: cannot start a container from almalinux:10: docker pull (after 3 attempts) exited 1: ... context deadline exceeded` from `test-mods` (CI's `live` job), exit 1; the record says `unstarted` | the registry or the daemon did not answer: every `live` run pulls its test image from Docker Hub, without an account, at that moment, and the pull was retried three times over about half a minute. Nothing about the modification was tested, so it is not a failed modification (before hygiene XII: `CalledProcessError` under eighty lines of traceback, docker's words lost). `perform` waits behind `live`, so a registry outage stops every bake | a pull from your own machine tells the registry from the daemon (2026-10-09, F54: three runs in forty-five minutes while Docker Hub's sign-in service did not answer); wait and rerun (`gh run rerun <run> --failed`). The run's log says which modification it is on and which image it waits for |
| `Unable to find remote state ... No stored state was found` planning an instance root, after the bakes | the instance root reads its storage root's state, and that root has never applied (`apply_storage: false` from the first commit, the first `perform` before any storage run) | run the storage lifecycle with `apply_storage` first; the strict state query says it beforehand as a note (`mounts storage ... whose root has no state yet`; 2026-10-07, F26) |
| `cs-image-system run (FAILED) <id>` in the git log | an applying run failed after a root had applied; its record was committed so what applied is not lost (the after-apply hooks ran first) | read `meta-state/runs.yaml` for the error; a decommission that failed on another cloud's plan left the machine gone and the records right (since 0.1.1.dev25; 2026-10-13, F62) |
| `meta-state/runs.yaml` says `ok: false` with `error: interrupted (KeyboardInterrupt) during <lifecycle>` | you cancelled the run with Ctrl-C; nothing after that point ran, and what ran before stands as its own commands left it | read what it was in; a generation can simply be run again, an interrupted apply is read in the root's state first (until 0.1.1.dev25 a cancelled run was journalled `ok: true`; 2026-10-09, F45) |
| `config-drift: ... the vendor's newest image moved under a base this tree has not baked` (exit 0) | the vendor published a new image and the emission of a base with no build yet names the one of the day it was generated; nothing of yours changed | `just record`, and commit it; before 0.1.1.dev25 this was `BEHIND ... (1 files)` and a red scheduled run that could not be re-run green (2026-10-12, F55) |
| `runtime-unchanged: ... unchanged since <ref> (...), but the vendor's newest image moved under a base this tree has not baked` (exit 0), in `perform` | the same move on the guarded runtime: the job's record took it, and there is nothing to apply by hand | nothing; on 0.1.2 and before the guard read it as `CHANGED` and failed `perform` (hygiene XVII item 1), and the record the job had pushed already held the move, so the next push to `main` passed |
| the log of an apply shows the root's outputs and no `Apply complete!` line | the run keeps the last 40 lines of a command's output, and tofu prints its verdict BEFORE the outputs | since 0.1.1.dev25 every verdict line (`Plan:`, `Apply complete!`, the gate's, a bake's `Build ... finished`) is printed ahead of the tail with its line number; before, `just cli --verbose` or the DEBUG log (2026-10-07, F25) |
| `role <name>: not granted` from the workload probe dispatched on `main`; or `granted` from a branch that is not `main` | the first: the role is not bound to the connection, or its pin names another branch; the second: the pin does not hold. The probe's first line says `accepted` either way, since authenticating to the connection takes the role as a hint only (2026-10-08, F35) | [CI_SETUP.md, section 3.5](docs/examples/standard-aws/CI_SETUP.md#35-okta-and-okta-privileged-access), steps 2 and 6; `not judged` means no machine of a managed group stands yet |
| `data disks mounted` failed with `missing: /mnt/<x>` on GCE, the kernel's XFS count above it | the startup script did not report that mount point mounted: the device never attached, or `mount` failed and the script went on (`nofail`) | the script's own lines on the serial console (`csis-mount:`), then the storage's attachment in the instance root |
| a base shown DUE on a cloud you changed nothing for | a field every runtime shares moved (`admin_user`, the admin keys, `update`, the vendor source); a storage type added for one cloud re-bakes only there since hygiene XII (before, `pd` for a GCE disk re-baked the AWS base: 2026-10-09, F49) | read the run's reason for the bake; a shared field re-bakes everywhere by design |
| `unavailable: storages/<s3>: REFUSED (the identity lacks a permission, ...): An error occurred (AccessDenied) when calling the GetBucketTagging operation: User: ...assumed-role/csis-github-apply/... is not authorized` on a `perform` | the role the step ran as lacks a read the state query makes: the applied role's document lags the release's module (until 2026-10-14 the WRITE role carried no `StorageReality` statement at all, so every performing run read its S3 storage as unavailable and stayed green over it; hygiene XII item 33) | take the release, then apply the bootstrap root again (CI_SETUP.md 3.0, the Apply block; IAM writes are yours); a `REFUSED` line is never a retry |
| `note: storages/<s>: a persistent disk of that name belongs to configuration '<id>' (csis_config); ... ours is absent`; `empty: left alone on <rt>: N disks of configuration '<id>'` | another tree shares the project or account and made a thing of that name; it is theirs, counted and left alone (stage 93) | nothing for theirs; if ours is absent, declare a name the cloud does not hold yet |
| `empty: disks still present on <rt>: old-scratch (no csis_config)` | a thing with no configuration id, made before stage 93; it is counted as ours to answer for | if it is ours and declared, `just cloud-relabel <rt> no` gives it the id; if it is nothing of ours, remove it by hand |
| a job fails in "Initialize containers" before any step of yours: `denied`, `unauthorized` or `manifest unknown` pulling `ghcr.io/.../csis-ci:alma10-<date>` | the runner image (stage 92) could not be pulled: the tag does not exist yet (the Runner image workflow has not published the date the workflow pins); or the job's `permissions:` block lacks `packages: read`, so its token pulls as nobody (2026-10-16: `verify`, with no block, pulled; `live`, with one, was denied); or the package is PRIVATE and this repository was not granted access to it (the first publish came out private, and the organisation had disabled public packages) | a missing tag: the system's maintainers run the Runner image workflow and you rerun; a missing line: take the release that carries it; a private package: on the package's page, "Manage Actions access", add this repository with Read (same organisation), or have the organisation's administrators allow public packages ([docs/CI_RUNNER.md](docs/CI_RUNNER.md), section 4); never a credential in the workflow for it |
| `release: testpypi cannot take an upload now (above) -- nothing was changed; it is the index's condition, not the release's` (exit 75) | the index's upload endpoint or one of the twenty project pages did not answer, or answered 5xx; the release stopped before the bar, or after it and before the bump, so the tree is clean (stage 83; on 2026-10-05 the same outage was found only at the upload) | `just index-ready test wait`, then the release again; nothing to discard |
| `release: this checkout is on '<branch>'; a release is cut on develop alone` | the checkout is not on `develop` (the walk's F31: a version was once cut, committed and tagged on a walk branch) | `git checkout develop`, then the release again |
| `public-safe: ... <file>:<line>` from the hook | a committed line looks like a secret, a key, a plan or a state file | never bypass the hook; encrypt the value, or allow it BY DECISION in `cfg/_config.yml` `public_safe.allow` |
| `Build '<image>' errored after 20 minutes ...: Timeout waiting for SSH.` with `ssm error: ... StartSession, context canceled` | the bake machine booted and its SSM agent was Online, but packer's ssh session through SSM never opened: the bake host was a 1 GB t2.micro, too small for the image it boots (three `perform` runs, 2026-10-04 and -05; the same parent baked on an r5.4xlarge, and on a t3.medium once declared) | give the bake host 4 GB: `machine_type: t3.medium` on the image's runtime entry, or the runtime's `default_machine_type` (the starters ship t3.medium; the reference tree since stage 80). Since stage 79 the builds that completed before the failure are recorded anyway (a warning names them) |
| `foreign image <id>: ... tagged series=<s> run=<r> is not in lineage` | an image the system tagged and lineage does not record: a bake still running in another process (2026-10-04: `just full-test`'s strict query raced CI's `perform`), or one a failed run baked before stage 79, when a failed run recorded nothing | if a run is still baking, wait for it to finish and record. Otherwise `just cli state import --no-storages` adopts it (2026-10-04: five images), then `just record`; the adopted build counts as current, so it is not baked again |
| `identity: group '<g>' was managed by the system but is missing from the YAML; groups never leave the configuration` | a group the system once managed was deleted from the YAML (2026-10-04: removing the posix proof's declarations after the proof) | put the entry back with `unmanaged: true`; its members may go. The records stay, and its gid stays claimed by the name |
| the `live` or `perform` job green with `SKIPPED` in its summary | no secret was configured, so nothing ran | not a pass: set the secrets the workflow names |

## 7. Every plugin, in one paragraph each

Each README ends, after its own content, with the same four sections:
**Prerequisites and integration**, **Configuration reference** (every field
and every variation), **What it tests and verifies**, **When it fails**. The
four links after each paragraph go straight to them. The three core
packages come first; a plugin is selected by the `type:` a builder entry
declares.

- [contract](packages/contract/README.md): the plugin contract (stage
  30). The protocols a model and a builder satisfy, the constants and
  field helpers a model is declared with, the lifecycle phases, the data
  carriers a hook returns; it depends on nothing of the system, and
  `base` depends on it. A plugin is written against this package alone;
  its README says how.
  [prerequisites](packages/contract/README.md#prerequisites-and-integration) ·
  [configuration](packages/contract/README.md#configuration-reference) ·
  [tests](packages/contract/README.md#what-it-tests-and-verifies) ·
  [failures](packages/contract/README.md#when-it-fails)
- [base](packages/base/README.md): the core. Models and builder bases that
  implement the contract, the plugin registry and loader,
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
- [posix-identity-plugin](packages/posix-identity-plugin/README.md): groups
  and users as POSIX accounts on the machines, with the ids the
  configuration declares (`gid:`, `uid:`): the owning group baked into an
  instance image, the ids resolved at `validate`, the accounts script
  (users, memberships, keys, sudo) tested on EL10 and Debian.
  [prerequisites](packages/posix-identity-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/posix-identity-plugin/README.md#configuration-reference) ·
  [tests](packages/posix-identity-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/posix-identity-plugin/README.md#when-it-fails)
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
- [contract-example-plugin](packages/contract-example-plugin/README.md):
  the proof of the contract (stage 30): OpenTofu's `inmem` state backend
  as a plugin written against the contract alone, subclassing nothing of
  the core; never a backend for a real tree.
  [prerequisites](packages/contract-example-plugin/README.md#prerequisites-and-integration) ·
  [configuration](packages/contract-example-plugin/README.md#configuration-reference) ·
  [tests](packages/contract-example-plugin/README.md#what-it-tests-and-verifies) ·
  [failures](packages/contract-example-plugin/README.md#when-it-fails)
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
`just fixture-live` proves the frozen fixture against the real accounts
(what the system's CI does); `just release <part|version> [test|pypi]`
cuts a release to the index, from `develop` alone. Before anything
changes, and again after the bar, it asks the index whether it can take
an upload (`just index-ready [test|pypi]` asks the same on its own, and
`just index-ready test wait` waits for it, two hours at most): exit 75
means the index cannot take an upload now, nothing was changed, and it
is the index's condition, not the release's
([OPERATIONS.md](docs/OPERATIONS.md), "`just build`, `just release`,
`just publish`, `just publish-tree`"; stage 83). The recipes here drive that reference
configuration only through `just cli ...`, for the system's own live
proofs; its cycles, like any team's, run from its own `Justfile` (`cd
../cs-image-system-testconfig && just cloud-cycle gcloud-east1`), which
the release shipped and `init-config` wrote. The starter trees under
`docs/examples/` are the source the release is built from: change them
there, and the tests hold the built wheel to them. Read
[OPERATIONS.md](docs/OPERATIONS.md), sections 2 and 3,
[GOLDEN.md](GOLDEN.md), and [PARITY.md](PARITY.md).

### 9.1 The machine CI runs on, and its actions: a name ages

The workflows, this repository's and every starter's, say which GitHub
runner image they run on (`runs-on: ubuntu-24.04`), which version of
each action they use (`actions/checkout@v5`,
`aws-actions/configure-aws-credentials@v6`,
`google-github-actions/auth@v3`; stage 91) and, since stage 92, which
date of the system's own runner image every job runs inside
(`container: image: ghcr.io/infrastructurebuilder/csis-ci:alma10-<YYYYMMDD>`).
None of the three moves by itself, and that is the point: a tree's CI
does not change at no commit. Until stage 91 they said `ubuntu-latest`,
which GitHub moves when it chooses (to Ubuntu 26 from 2026-10-19), and
one action followed a branch. A test now refuses a floating image, a
second image, an action at a branch, and an action older than the
majors above.

The price of a name is a duty. GitHub publishes a runner image for each
Ubuntu LTS, about every two years, and withdraws the oldest; an
action's major version is withdrawn when the Node.js it was built for
is. A withdrawn name does not fail quietly: first every run's
annotations say so, for some months, then jobs wait and are never
picked up, or fail in "Set up job" before any step of yours. (What
this paragraph says of GitHub's schedule is from the notices seen on
2026-10-13; read GitHub's pages when you act on it.)

**When to look.** Twice a year, in the first working week of April and
of October, and at once whenever a run's annotations name an image or
an action as deprecated or migrating; `gh run view <run>` prints them
under ANNOTATIONS. (The interval is a proposal; set your own.)

**The runner image's date is the third name**, and it moves more
often. The Runner image workflow of this repository builds
`ci/runner-image/Dockerfile` monthly and on any change to it, probes
every tool, and publishes `csis-ci:alma10-<YYYYMMDD>`; a tool's new
version is a change to the Dockerfile's `ARG` line and to the table in
[docs/CI_RUNNER.md](docs/CI_RUNNER.md), which a test holds equal. A
release carries the newest date in every workflow it ships, and a tree
takes it with `init-config --force` as it takes the other names; a
tree may also pin a newer date by hand, since nothing but the date
differs. The from-scratch workflow of this repository, GitHub's image
with every tool installed by a step, is kept running weekly so the
list stays true on a machine that holds nothing.

**How to move it forward.** Whoever maintains the system does steps 1
to 4; a tree's holder does only step 5.

1. Read what GitHub offers now: the README of `actions/runner-images`
   lists the image labels and which are being withdrawn; each action's
   releases page, and the `using:` line of its `action.yml`, say which
   major targets which Node.js.
2. On a feature branch of this repository, change the names and
   nothing else, in every workflow: `grep -rn -E 'runs-on:|uses:'
   .github docs/examples` lists every line, and they all carry the same
   image. Move the test's floor of majors with them.
3. `just test`, then `just full-test`.
4. Prove it where it will run before anyone else takes it: cut a
   development release; in the reference configuration raise
   `.csis-version`, run `cs-image-system init-config . --force` (with
   `--from` naming the starter the tree was made from), read the diff
   (it should be the workflow lines you changed), commit, push
   `develop` and see `verify` and `live` green, the new image named in
   the log of "Set up job" (`Image: ubuntu-...`); then `main`, and
   `perform` green: a bake, the modification tests under docker and a
   login proof have then run on the new image. If a job fails for
   something the new image lacks, the fix is a step in the workflow
   that installs it, never a return to a floating name.
5. Every other tree takes it as it takes any release
   ([CI_SETUP.md](docs/examples/complete/CI_SETUP.md), section 3.1).

**What it looks like when it was not done:** annotations on every run
naming the image or an action; later, jobs that wait and are never
picked up, or "Set up job" failing before any step of yours. Nothing in
the tree is wrong; the names are old. Take the newest release, or do
steps 1 to 5.
